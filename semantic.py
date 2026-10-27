"""Separate semantic pass: scoped names, nominal types, effects, and typed AST."""
from dataclasses import dataclass, field
from ast_nodes import *
from errors import CompilationError

I32='☼';I64='☽';BOOL='☁︎';STRING='string';INTEGERS={I32,I64}
BUILTINS={'lookThroughTelescope','recordCoordinates'}
LIMITS={I32:(-2**31,2**31-1),I64:(-2**63,2**63-1)}

@dataclass
class Symbol:
    name:str
    type:str
    mutable:bool
    kind:str
    node:object=None
    initialized:bool=True
    index:int|None=None  # LLVM struct field index, assigned when defining an astro

@dataclass(eq=False)
class FunctionInfo:
    node:FunctionNode
    owner:str|None=None
    params:list[Symbol]=field(default_factory=list)
    result:str=''
    direct_mutating:bool=False
    mutating:bool=False
    calls:set=field(default_factory=set)
    reads:set=field(default_factory=set)

@dataclass
class StructureInfo:
    node:StructNode
    fields:dict=field(default_factory=dict)
    methods:dict=field(default_factory=dict)

class Semantic:
    def __init__(self,program:ProgramNode):
        self.program=program;self.structs={};self.functions={};self.global_symbols={};self.scopes=[]
        self.owner=None;self.current=None;self.deferred=[];self.global_initializers=[]

    def error(self,node,message):raise CompilationError(node.line,node.column,message)
    def validate_type(self,type_name,node):
        if type_name not in INTEGERS|{BOOL} and type_name not in self.structs:self.error(node,f"unknown type '{type_name}'")
        return type_name
    def register_function(self,node,owner=None):
        if owner is None:
            if node.name in BUILTINS or node.name in self.functions or node.name in self.structs:
                self.error(node,f"duplicate function '{node.name}'")
        elif node.name in self.structs[owner].methods or node.name in self.structs[owner].fields:
            self.error(node,f"duplicate member '{node.name}'")
        names=set();params=[]
        for p in node.parameters:
            self.validate_type(p.type_name,p)
            if p.name in names or (owner and p.name=='core'):self.error(p,f"duplicate or reserved parameter '{p.name}'")
            names.add(p.name);params.append(Symbol(p.name,p.type_name,p.mutable,'parameter',p))
        info=FunctionInfo(node,owner,params,self.validate_type(node.result_type,node))
        if owner:self.structs[owner].methods[node.name]=info
        else:self.functions[node.name]=info
        node._info=info;return info

    def analyze(self):
        # Predeclare identified structs and function signatures before bodies.
        for n in self.program.statements:
            if isinstance(n,StructNode):
                if n.name in self.structs or n.name in BUILTINS:self.error(n,f"duplicate structure '{n.name}'")
                self.structs[n.name]=StructureInfo(n)
        for n in self.program.statements:
            if isinstance(n,StructNode):
                info=self.structs[n.name]
                for index,f in enumerate(n.fields):
                    self.validate_type(f.type_name,f)
                    if f.name in info.fields:self.error(f,f"duplicate field '{f.name}'")
                    if f.name=='core':self.error(f,"field name 'core' is reserved in methods")
                    info.fields[f.name]=Symbol(f.name,f.type_name,f.mutable,'field',f,index=index)
                    f._index=index
                for method in n.methods:self.register_function(method,n.name)
        for n in self.program.statements:
            if isinstance(n,FunctionNode):self.register_function(n)
        for n in self.program.statements:
            if isinstance(n,StructNode):
                # Methods are analyzed at the declaration site for globals visibility.
                for m in n.methods:self.analyze_function(m._info)
            elif isinstance(n,FunctionNode):self.analyze_function(n._info)
            else:self.statement(n,global_scope=True)
        # Mutating effect propagation across the complete call graph (handles cycles).
        infos=list(self.functions.values())+[m for s in self.structs.values() for m in s.methods.values()]
        for f in infos:f.mutating=f.direct_mutating
        changed=True
        while changed:
            changed=False
            for f in infos:
                if not f.mutating and any(c.mutating for c in f.calls):
                    f.mutating=True;changed=True
        for node,callee,mutable in self.deferred:
            if callee.mutating and not mutable:self.error(node,'mutating member call requires a mutable object chain')
        self.check_global_initializers(infos)
        return self

    def check_global_initializers(self,infos):
        # Calls in initializers may read globals before they are fully initialized.
        all_reads={f:set(f.reads) for f in infos}
        changed=True
        while changed:
            changed=False
            for f in infos:
                before=len(all_reads[f]);all_reads[f].update(*(all_reads[c] for c in f.calls))
                if len(all_reads[f])!=before:changed=True
        for init,declared,available,calls in self.global_initializers:
            visited=set()
            def scan(node):
                if isinstance(node,IdentifierNode):
                    sym=getattr(node,'_symbol',None)
                    if isinstance(sym,Symbol) and sym.kind=='global':visited.add(sym.name)
                if isinstance(node,CallNode):
                    callee=getattr(node,'_callee',None)
                    if isinstance(callee,FunctionInfo):visited.update(all_reads[callee])
                if isinstance(node,MemberNode) and node.args is not None:
                    callee=getattr(node,'_callee',None)
                    if isinstance(callee,FunctionInfo):visited.update(all_reads[callee])
                if hasattr(node,'__dict__'):
                    for v in node.__dict__.values():
                        if isinstance(v,ExpressionNode):scan(v)
                        if isinstance(v,list):
                            for e in v:
                                if isinstance(e,ExpressionNode):scan(e)
                                if isinstance(e,tuple) and len(e)==2 and isinstance(e[1],ExpressionNode):scan(e[1])
            scan(init)
            unsafe=visited-{*available}
            if unsafe:self.error(init,f"global initializer may read uninitialized '{sorted(unsafe)[0]}'")

    def push(self):self.scopes.append({})
    def pop(self):self.scopes.pop()
    def declare(self,sym,node):
        scope=self.scopes[-1] if self.scopes else self.global_symbols
        if sym.name in scope:self.error(node,f"duplicate declaration '{sym.name}'")
        if not self.scopes and (sym.name in self.functions or sym.name in self.structs):
            self.error(node,f"duplicate declaration '{sym.name}'")
        if self.owner and sym.name=='core':self.error(node,"name 'core' is reserved inside methods")
        scope[sym.name]=sym
    def resolve(self,name,node):
        if self.owner and name=='core':return Symbol('core',self.owner,True,'core')
        for scope in reversed(self.scopes):
            if name in scope:return scope[name]
        if self.owner and name in self.structs[self.owner].fields:return self.structs[self.owner].fields[name]
        if name in self.global_symbols:return self.global_symbols[name]
        return None

    def analyze_function(self,info):
        saved_owner,saved_current=self.owner,self.current
        self.owner=info.owner;self.current=info;self.push()
        for p in info.params:self.declare(p,p.node)
        guaranteed=self.statements(info.node.body,new_scope=False)
        if not guaranteed:self.error(info.node,f"function '{info.node.name}' does not return on every path")
        self.pop();self.owner,self.current=saved_owner,saved_current

    def statements(self,body,new_scope=True):
        if new_scope:self.push()
        guaranteed=False
        for statement in body:
            # Even unreachable statements must be type-checked.
            returned=self.statement(statement)
            if not guaranteed:guaranteed=returned
        if new_scope:self.pop()
        return guaranteed

    def statement(self,n,global_scope=False):
        if isinstance(n,DeclarationNode):
            typ=self.validate_type(n.type_name,n)
            if typ in self.structs and n.declaration_kind=='fixed':self.error(n,'fixed cannot declare an astro object')
            available=set(self.global_symbols)
            sym=Symbol(n.name,typ,n.declaration_kind=='flow','global' if global_scope else 'local',n,False)
            self.declare(sym,n);n._symbol=sym
            actual=self.expr(n.initializer,typ)
            self.require(typ,actual,n.initializer)
            sym.initialized=True
            if global_scope:self.global_initializers.append((n.initializer,n.name,available,set()))
            return False
        if isinstance(n,AssignmentNode):
            dest=IdentifierNode(n.line,n.column,n.name)
            self.assign(dest,n.value,n);n._target=dest;return False
        if isinstance(n,FieldAssignmentNode):
            self.assign(n.target,n.value,n);return False
        if isinstance(n,CallStatementNode):
            self.expr(n.call);return False
        if isinstance(n,ReturnNode):
            if not self.current:self.error(n,'rise is only allowed inside spark')
            self.require(self.current.result,self.expr(n.value,self.current.result),n.value);return True
        if isinstance(n,IfNode):
            self.require(BOOL,self.expr(n.condition,BOOL),n.condition)
            a=self.statements(n.then_body)
            b=self.statements(n.else_body) if n.else_body is not None else False
            return a and b
        self.error(n,'unsupported statement')

    def assign(self,target,value,n):
        # `core` is a stable receiver reference: its mutable *fields* may be
        # written, but rebinding the receiver itself is never permitted.
        if self.owner and isinstance(target, IdentifierNode) and target.name == 'core':
            self.error(target, "cannot reassign 'core'")
        typ,mutable=self.lvalue(target)
        if not mutable:self.error(target,'cannot assign through an immutable variable or field chain')
        self.require(typ,self.expr(value,typ),value)
        if self.current:
            if isinstance(target,MemberNode) or getattr(target,'_symbol',None) and target._symbol.kind=='field':
                self.current.direct_mutating=True

    def require(self,expected,actual,node):
        if expected!=actual:self.error(node,f"type mismatch: expected {expected}, got {actual}")

    def lvalue(self,node):
        if isinstance(node,IdentifierNode):
            sym=self.resolve(node.name,node)
            if sym is None:self.error(node,f"undeclared name '{node.name}'")
            node._symbol=sym;node._ty=sym.type
            if self.current and sym.kind=='global':self.current.reads.add(sym.name)
            return sym.type,sym.mutable
        if isinstance(node,MemberNode) and node.args is None:
            typ=self.expr(node.base)
            if typ not in self.structs:self.error(node,f"type '{typ}' has no fields")
            field_sym=self.structs[typ].fields.get(node.name)
            if field_sym is None:self.error(node,f"unknown field '{node.name}' on {typ}")
            node._field=field_sym;node._ty=field_sym.type
            # Only actual lvalues (not temporaries) are writable.
            if isinstance(node.base,(MemberNode,IdentifierNode)):
                if isinstance(node.base,MemberNode) and node.base.args is not None:base_mut=False
                else:_,base_mut=self.lvalue(node.base)
            else:base_mut=False
            return field_sym.type,base_mut and field_sym.mutable
        self.error(node,'assignment target is not a variable or field')

    def literal(self,node,expected=None):
        value=node.value
        if expected in INTEGERS:typ=expected
        else:typ=I32 if LIMITS[I32][0]<=value<=LIMITS[I32][1] else I64
        if not LIMITS[typ][0]<=value<=LIMITS[typ][1]:
            self.error(node,f'integer literal overflows {typ} ({"i32" if typ==I32 else "i64"})')
        node._ty=typ;node._constant=value;return typ

    def hint(self,node):
        if isinstance(node,IdentifierNode):
            s=self.resolve(node.name,node);return s.type if s else None
        if isinstance(node,(CallNode,MemberNode)):
            return getattr(node,'_ty',None)
        if isinstance(node,(BinaryNode,ComparisonNode)):
            return self.hint(node.left) or self.hint(node.right)
        return None

    def expr(self,n,expected=None):
        if isinstance(n,IntegerLiteralNode):return self.literal(n,expected)
        if isinstance(n,BooleanLiteralNode):n._ty=BOOL;return BOOL
        if isinstance(n,StringNode):
            n._ty=STRING
            if expected not in (None,STRING):self.error(n,'string literals are only allowed in recordCoordinates')
            return STRING
        if isinstance(n,IdentifierNode):
            sym=self.resolve(n.name,n)
            if not sym:self.error(n,f"undeclared name '{n.name}'")
            n._symbol=sym;n._ty=sym.type
            if self.current and sym.kind=='global':self.current.reads.add(sym.name)
            return n._ty
        if isinstance(n,UnaryNode):
            t=self.expr(n.value,expected)
            if t not in INTEGERS:self.error(n,'unary minus requires integer')
            n._ty=t
            if hasattr(n.value,'_constant'):
                c=-n.value._constant
                if not LIMITS[t][0]<=c<=LIMITS[t][1]:self.error(n,'constant arithmetic overflow')
                n._constant=c
            return t
        if isinstance(n,BinaryNode):
            typ=expected if expected in INTEGERS else self.hint(n.left) or self.hint(n.right)
            left=self.expr(n.left,typ)
            right=self.expr(n.right,typ or left)
            self.require(left,right,n)
            if left not in INTEGERS:self.error(n,'arithmetic requires integer operands')
            n._ty=left
            if hasattr(n.left,'_constant') and hasattr(n.right,'_constant'):
                a,b=n.left._constant,n.right._constant
                if n.operator=='/' and b==0:self.error(n,'division by zero')
                if n.operator=='+':c=a+b
                elif n.operator=='-':c=a-b
                elif n.operator=='*':c=a*b
                else:c=(abs(a)//abs(b))*(-1 if (a<0)!=(b<0) else 1)
                if not LIMITS[left][0]<=c<=LIMITS[left][1]:self.error(n,'constant arithmetic overflow')
                n._constant=c
            return left
        if isinstance(n,ComparisonNode):
            hint=self.hint(n.left) or self.hint(n.right)
            left=self.expr(n.left,hint);right=self.expr(n.right,left)
            self.require(left,right,n)
            if left==STRING:self.error(n,'string comparisons are unsupported')
            n._ty=BOOL;return BOOL
        if isinstance(n,ConstructorNode):
            if n.name not in self.structs:self.error(n,f"unknown astro '{n.name}'")
            struct=self.structs[n.name];found=set()
            for name,value in n.fields:
                if name in found:self.error(n,f"duplicate initializer for field '{name}'")
                found.add(name)
                if name not in struct.fields:self.error(n,f"unknown field '{name}' on {n.name}")
                sym=struct.fields[name];self.require(sym.type,self.expr(value,sym.type),value)
            missing=set(struct.fields)-found
            if missing:self.error(n,f"missing field '{sorted(missing)[0]}' in {n.name} constructor")
            n._ty=n.name;return n.name
        if isinstance(n,CallNode):
            s=self.resolve(n.name,n)
            # Local variables/parameters and fields shadow a callable, but methods
            # of the current astro take precedence over globals.
            if s is not None and s.kind!='global':self.error(n,f"'{n.name}' is not callable")
            if self.owner and n.name in self.structs[self.owner].methods:
                f=self.structs[self.owner].methods[n.name]
                n._implicit_receiver=True
                self.check_call(n,f,n.args,True)
                return n._ty
            if s is not None:self.error(n,f"'{n.name}' is not callable")
            if n.name in self.functions:
                f=self.functions[n.name];self.check_call(n,f,n.args,None);return n._ty
            if n.name in BUILTINS:return self.builtin(n)
            self.error(n,f"unknown function '{n.name}'")
        if isinstance(n,MemberNode):
            if n.args is None:
                typ,_=self.lvalue(n);n._ty=typ;return typ
            base_type=self.expr(n.base)
            if base_type not in self.structs:self.error(n,'member call requires an astro object')
            method=self.structs[base_type].methods.get(n.name)
            if method is None:self.error(n,f"unknown method '{n.name}' on {base_type}")
            mutable=False
            if isinstance(n.base,IdentifierNode) or isinstance(n.base,MemberNode) and n.base.args is None:
                _,mutable=self.lvalue(n.base)
            self.check_call(n,method,n.args,mutable)
            return n._ty
        self.error(n,'unsupported expression')

    def builtin(self,n):
        n._builtin=n.name
        if n.name=='lookThroughTelescope':
            if n.args:self.error(n,'lookThroughTelescope expects 0 arguments')
            n._ty=I32;return I32
        if not n.args:self.error(n,'recordCoordinates expects at least 1 argument')
        for a in n.args:
            if self.expr(a) not in INTEGERS|{BOOL,STRING}|set(self.structs):
                self.error(a,'unsupported recordCoordinates argument')
        n._ty='void';return 'void'

    def check_call(self,n,f,args,mutable):
        if len(args)!=len(f.params):self.error(n,f"'{f.node.name}' expects {len(f.params)} arguments, got {len(args)}")
        for a,p in zip(args,f.params):self.require(p.type,self.expr(a,p.type),a)
        n._callee=f;n._ty=f.result
        if self.current:self.current.calls.add(f)
        if f.owner:self.deferred.append((n,f,mutable))
