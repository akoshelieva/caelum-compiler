"""Typed LLVM IR generation exclusively through llvmlite's builder API."""
from llvmlite import ir
from ast_nodes import *
from semantic import I32,I64,BOOL,STRING,INTEGERS,LIMITS,Symbol,FunctionInfo

class LLVMGenerator:
    def __init__(self,sem):
        self.sem=sem;self.context=ir.Context();self.module=ir.Module(name='caelum',context=self.context)
        self.i1=ir.IntType(1);self.i8=ir.IntType(8);self.i32=ir.IntType(32);self.i64=ir.IntType(64)
        self.ptr=self.i8.as_pointer();self.intptr=self.i32.as_pointer()
        self.types={I32:self.i32,I64:self.i64,BOOL:self.i1}
        self.structs={name:self.context.get_identified_type('caelum.struct.'+name) for name in sem.structs}
        self.types.update(self.structs)
        for name,info in sem.structs.items():
            self.structs[name].set_body(*(self.types[f.type] for f in info.fields.values()))
        self.fn_map={};self.globals={};self.strings={};self.scopes=[];self.builder=None;self.receiver=None;self.current_fn=None
        self.printf=ir.Function(self.module,ir.FunctionType(self.i32,[self.ptr],var_arg=True),name='printf')
        self.scanf=ir.Function(self.module,ir.FunctionType(self.i32,[self.ptr],var_arg=True),name='scanf')
        self.strtoll=ir.Function(self.module,ir.FunctionType(self.i64,[self.ptr,self.ptr.as_pointer(),self.i32]),name='strtoll')
        self.write=ir.Function(self.module,ir.FunctionType(self.i64,[self.i32,self.ptr,self.i64]),name='write')
        self.exit=ir.Function(self.module,ir.FunctionType(ir.VoidType(),[self.i32]),name='exit')
        self.overflow={}

    def type(self,name):return self.types[name]
    def integer(self,n,width=32):return ir.Constant(self.i32 if width==32 else self.i64,n)
    def string_ptr(self,text):
        if text not in self.strings:
            data=text.encode('utf-8')+b'\x00';t=ir.ArrayType(self.i8,len(data))
            g=ir.GlobalVariable(self.module,t,name='caelum.str.'+str(len(self.strings)))
            g.global_constant=True;g.linkage='internal';g.initializer=ir.Constant(t,bytearray(data))
            self.strings[text]=g
        g=self.strings[text]
        return self.builder.gep(g,[self.integer(0),self.integer(0)],inbounds=True)
    def call_printf(self,text,values=()):return self.builder.call(self.printf,[self.string_ptr(text),*values])
    def runtime_check(self,invalid,message):
        func=self.builder.function
        err=func.append_basic_block('runtime.error');ok=func.append_basic_block('runtime.ok')
        self.builder.cbranch(invalid,err,ok);self.builder.position_at_end(err)
        data=(f'runtime error: {message}\n').encode('utf8')
        self.builder.call(self.write,[self.integer(2),self.string_ptr(data.decode()),ir.Constant(self.i64,len(data))])
        self.builder.call(self.exit,[self.integer(1)]);self.builder.unreachable()
        self.builder.position_at_end(ok)

    def generate(self):
        # Register globals and all signatures before emitting a single function body.
        for n in self.sem.program.statements:
            if isinstance(n,DeclarationNode):
                g=ir.GlobalVariable(self.module,self.type(n.type_name),name='caelum.global.'+n.name)
                g.initializer=ir.Constant(self.type(n.type_name),None);self.globals[n.name]=g
        for fn in self.sem.functions.values():self.declare_function(fn)
        for struct in self.sem.structs.values():
            for fn in struct.methods.values():self.declare_function(fn)
        for fn in self.sem.functions.values():self.function_body(fn)
        for struct in self.sem.structs.values():
            for fn in struct.methods.values():self.function_body(fn)
        main=ir.Function(self.module,ir.FunctionType(self.i32,[]),name='main')
        self.builder=ir.IRBuilder(main.append_basic_block('entry'))
        self.scopes=[{}];self.receiver=None;self.current_fn=None
        for n in self.sem.program.statements:
            if not isinstance(n,(FunctionNode,StructNode)):self.statement(n)
        if not self.builder.block.is_terminated:self.builder.ret(self.integer(0))
        return str(self.module)

    def declare_function(self,info):
        sig=[self.types[p.type] for p in info.params]
        if info.owner:sig.insert(0,self.structs[info.owner].as_pointer())
        name=('caelum.method.'+info.owner+'.' if info.owner else 'caelum.fn.')+info.node.name
        self.fn_map[info]=ir.Function(self.module,ir.FunctionType(self.type(info.result),sig),name=name)

    def function_body(self,info):
        fn=self.fn_map[info];self.current_fn=info;self.builder=ir.IRBuilder(fn.append_basic_block('entry'))
        self.scopes=[{}];self.receiver=None
        start=0
        if info.owner:self.receiver=fn.args[0];self.receiver.name='core';start=1
        for parameter,value in zip(info.params,fn.args[start:]):
            value.name=parameter.name;ptr=self.builder.alloca(self.type(parameter.type),name=parameter.name+'.addr')
            self.builder.store(value,ptr);self.scopes[-1][parameter.name]=ptr
        self.statements(info.node.body,new_scope=False)
        if not self.builder.block.is_terminated:self.builder.unreachable() # semantic pass proved all returns

    def statements(self,body,new_scope=True):
        if new_scope:self.scopes.append({})
        for n in body:
            if self.builder.block.is_terminated:break
            self.statement(n)
        if new_scope:self.scopes.pop()

    def statement(self,n):
        if isinstance(n,DeclarationNode):
            value=self.value(n.initializer)
            if n._symbol.kind=='global':ptr=self.globals[n.name]
            else:
                ptr=self.builder.alloca(self.type(n.type_name),name=n.name+'.addr')
                self.scopes[-1][n.name]=ptr
            self.builder.store(value,ptr);return
        if isinstance(n,(AssignmentNode,FieldAssignmentNode)):
            self.builder.store(self.value(n.value),self.address(n._target if isinstance(n,AssignmentNode) else n.target));return
        if isinstance(n,CallStatementNode):self.value(n.call);return
        if isinstance(n,ReturnNode):self.builder.ret(self.value(n.value));return
        if isinstance(n,IfNode):
            cond=self.value(n.condition);func=self.builder.function
            then_b=func.append_basic_block('when.then');end_b=func.append_basic_block('when.end')
            else_b=func.append_basic_block('when.else') if n.else_body is not None else end_b
            self.builder.cbranch(cond,then_b,else_b)
            self.builder.position_at_end(then_b);self.statements(n.then_body)
            if not self.builder.block.is_terminated:self.builder.branch(end_b)
            self.builder.position_at_end(else_b)
            if n.else_body is not None:
                self.statements(n.else_body)
                if not self.builder.block.is_terminated:self.builder.branch(end_b)
            self.builder.position_at_end(end_b)
            # If both branches return, make the unused merge a valid unreachable block.
            if n.else_body is not None and all(b.is_terminated for b in (then_b,else_b)):
                # Branches may have created runtime check sub-blocks, so check actual
                # predecessors by completion flags handled by semantic guarantees.
                pass
            return
        raise RuntimeError('invalid semantic statement')

    def address(self,n):
        if isinstance(n,IdentifierNode):
            s=n._symbol
            if s.kind=='core':return self.receiver
            if s.kind=='field':return self.field_ptr(self.receiver,self.current_fn.owner,s.name)
            for scope in reversed(self.scopes):
                if s.name in scope:return scope[s.name]
            if s.name in self.globals:return self.globals[s.name]
            raise RuntimeError('missing variable address '+s.name)
        if isinstance(n,MemberNode) and n.args is None:
            ptr=self.address(n.base) if isinstance(n.base,(IdentifierNode,MemberNode)) and (not isinstance(n.base,MemberNode) or n.base.args is None) else self.temp(self.value(n.base))
            return self.field_ptr(ptr,n.base._ty,n.name)
        raise RuntimeError('not an lvalue')
    def field_ptr(self,obj,typ,name):
        # Resolve an accessor through the semantic field table, which stores
        # a stable LLVM index for every field in declaration order.
        index=self.sem.structs[typ].fields[name].index
        return self.builder.gep(obj,[self.integer(0),self.integer(index)],inbounds=True)
    def temp(self,value):
        p=self.builder.alloca(value.type);self.builder.store(value,p);return p

    def value(self,n):
        if isinstance(n,IntegerLiteralNode):return ir.Constant(self.type(n._ty),n.value)
        if isinstance(n,BooleanLiteralNode):return ir.Constant(self.i1,int(n.value))
        if isinstance(n,StringNode):return self.string_ptr(n.value)
        if isinstance(n,IdentifierNode):return self.builder.load(self.address(n))
        if isinstance(n,MemberNode) and n.args is None:return self.builder.load(self.address(n))
        if isinstance(n,UnaryNode):
            v=self.value(n.value)
            return self.checked_arithmetic('sub',ir.Constant(v.type,0),v)
        if isinstance(n,BinaryNode):
            a=self.value(n.left);b=self.value(n.right)
            if n.operator=='+':return self.checked_arithmetic('add',a,b)
            if n.operator=='-':return self.checked_arithmetic('sub',a,b)
            if n.operator=='*':return self.checked_arithmetic('mul',a,b)
            zero=ir.Constant(a.type,0);self.runtime_check(self.builder.icmp_signed('==',b,zero),'division by zero')
            minval=ir.Constant(a.type,LIMITS[n._ty][0]);minusone=ir.Constant(a.type,-1)
            overflow=self.builder.and_(self.builder.icmp_signed('==',a,minval),self.builder.icmp_signed('==',b,minusone))
            self.runtime_check(overflow,'integer overflow')
            return self.builder.sdiv(a,b)
        if isinstance(n,ComparisonNode):
            a=self.value(n.left);b=self.value(n.right);equal=self.equal(a,b,n.left._ty)
            return equal if n.operator=='==' else self.builder.not_(equal)
        if isinstance(n,ConstructorNode):
            ty=self.structs[n.name];obj=self.builder.alloca(ty)
            for field_name,expr in n.fields:
                slot=self.field_ptr(obj,n.name,field_name);self.builder.store(self.value(expr),slot)
            return self.builder.load(obj)
        if isinstance(n,CallNode):
            if getattr(n,'_builtin',None)=='lookThroughTelescope':return self.read_int()
            if getattr(n,'_builtin',None)=='recordCoordinates':
                for arg in n.args:self.print_value(self.value(arg),arg._ty);self.call_printf('\n')
                return ir.Constant(self.i32,0) # statement-only built-in
            callee=n._callee;args=[]
            if callee.owner:args.append(self.receiver)
            args.extend(self.value(arg) for arg in n.args)
            return self.builder.call(self.fn_map[callee],args)
        if isinstance(n,MemberNode) and n.args is not None:
            ptr=self.address(n.base) if isinstance(n.base,(IdentifierNode,MemberNode)) and (not isinstance(n.base,MemberNode) or n.base.args is None) else self.temp(self.value(n.base))
            args=[ptr]+[self.value(arg) for arg in n.args]
            return self.builder.call(self.fn_map[n._callee],args)
        raise RuntimeError('unsupported expression in codegen '+repr(n))

    def checked_arithmetic(self,op,a,b):
        kind={'add':'sadd','sub':'ssub','mul':'smul'}[op]
        name=f'llvm.{kind}.with.overflow.i{a.type.width}'
        if name not in self.overflow:
            typ=ir.LiteralStructType([a.type,self.i1]);ft=ir.FunctionType(typ,[a.type,a.type])
            self.overflow[name]=ir.Function(self.module,ft,name=name)
        pair=self.builder.call(self.overflow[name],[a,b])
        flag=self.builder.extract_value(pair,1);self.runtime_check(flag,'integer overflow')
        return self.builder.extract_value(pair,0)
    def equal(self,a,b,typ):
        if typ not in self.structs:return self.builder.icmp_signed('==',a,b)
        result=ir.Constant(self.i1,1)
        for i,field in enumerate(self.sem.structs[typ].fields.values()):
            left=self.builder.extract_value(a,i);right=self.builder.extract_value(b,i)
            result=self.builder.and_(result,self.equal(left,right,field.type))
        return result

    def print_value(self,value,typ):
        if typ==I32:self.call_printf('%d',[value]);return
        if typ==I64:self.call_printf('%lld',[value]);return
        if typ==BOOL:
            text=self.builder.select(value,self.string_ptr('true'),self.string_ptr('false'))
            self.builder.call(self.printf,[self.string_ptr('%s'),text]);return
        if typ==STRING:self.builder.call(self.printf,[self.string_ptr('%s'),value]);return
        # Print objects through their field table: a new astro requires no
        # object-specific code, only a GEP and load for each declared field.
        obj=self.temp(value)
        self.call_printf(typ+'⟨')
        for index,field in enumerate(self.sem.structs[typ].fields.values()):
            if index:self.call_printf(', ')
            self.call_printf(field.name+'=')
            field_value=self.builder.load(self.field_ptr(obj,typ,field.name))
            self.print_value(field_value,field.type)
        self.call_printf('⟩')

    def read_int(self):
        buff=self.builder.alloca(ir.ArrayType(self.i8,256),name='read.buffer')
        start=self.builder.gep(buff,[self.integer(0),self.integer(0)],inbounds=True)
        matched=self.builder.call(self.scanf,[self.string_ptr('%255s'),start])
        self.runtime_check(self.builder.icmp_signed('!=',matched,self.integer(1)),'invalid integer input')
        first=self.builder.load(start)
        plus=self.builder.icmp_unsigned('==',first,ir.Constant(self.i8,ord('+')))
        self.runtime_check(plus,'invalid integer input')
        endpoint=self.builder.alloca(self.ptr)
        value=self.builder.call(self.strtoll,[start,endpoint,self.integer(10)])
        end=self.builder.load(endpoint)
        no_digits=self.builder.icmp_unsigned('==',self.builder.ptrtoint(end,self.i64),self.builder.ptrtoint(start,self.i64))
        tail=self.builder.load(end)
        bad_end=self.builder.icmp_unsigned('!=',tail,ir.Constant(self.i8,0))
        self.runtime_check(self.builder.or_(no_digits,bad_end),'invalid integer input')
        too_big=self.builder.icmp_signed('>',value,ir.Constant(self.i64,2**31-1))
        too_small=self.builder.icmp_signed('<',value,ir.Constant(self.i64,-2**31))
        self.runtime_check(self.builder.or_(too_big,too_small),'integer input out of range')
        return self.builder.trunc(value,self.i32)
