"""One recursive-descent parser method per Caelum grammar construct."""
from ast_nodes import *
from errors import CompilationError
from tokens import Token,TokenKind as K

_I32_MIN=-(2**31);_I32_MAX=2**31-1
_I64_MIN=-(2**63);_I64_MAX=2**63-1
_TYPES={K.TYPE_I32,K.TYPE_I64,K.TYPE_BOOL};_KINDS={K.CALM,K.FLOW,K.FIXED}

class Parser:
    def __init__(self,tokens:list[Token]):self.tokens=tokens;self.position=0
    def peek(self,offset=0):return self.tokens[min(self.position+offset,len(self.tokens)-1)]
    def eat(self,kind,expected=None):
        tok=self.peek()
        if tok.kind!=kind:raise CompilationError(tok.line,tok.column,f"expected {expected or kind.name}, got {self._describe(tok)}")
        self.position+=1;return tok
    def is_word(self,name,offset=0):
        t=self.peek(offset);return t.kind==K.IDENTIFIER and t.text==name
    def word(self,name):
        if not self.is_word(name):
            t=self.peek();raise CompilationError(t.line,t.column,f"expected '{name}', got {self._describe(t)}")
        self.position+=1;return self.tokens[self.position-1]
    def type_name(self):
        t=self.peek()
        if t.kind not in _TYPES|{K.IDENTIFIER}:
            raise CompilationError(t.line,t.column,f"expected type name, got {self._describe(t)}")
        self.position+=1;return t.text if t.kind!=K.TYPE_BOOL else '☁︎'
    def parse_program(self):
        top=[];start=self.peek()
        while self.peek().kind!=K.EOF:
            if self.is_word('spark') and self.peek(1).kind==K.IDENTIFIER:top.append(self.parse_function())
            elif self.is_word('astro') and self.peek(1).kind==K.IDENTIFIER:top.append(self.parse_struct())
            else:top.append(self.parse_statement())
        self.eat(K.EOF,'end of file');return ProgramNode(start.line,start.column,top)
    def parse_statement(self):
        t=self.peek()
        if t.kind in _KINDS:return self.parse_declaration()
        if t.kind==K.WHEN:return self.parse_if_statement()
        if self.is_word('rise') and self.peek(1).kind not in (K.ASSIGN,K.DOT):
            return self.parse_return()
        if t.kind in (K.IDENTIFIER,K.TYPE_I32,K.TYPE_I64,K.TYPE_BOOL):
            return self.parse_assignment_or_call()
        raise CompilationError(t.line,t.column,f"expected statement, got {self._describe(t)}")
    def parse_declaration(self):
        kind=self.peek();self.position+=1
        t=self.peek()
        if t.kind==K.IDENTIFIER and self.peek(1).kind!=K.IDENTIFIER:
            raise CompilationError(t.line,t.column,f"expected type name, got {self._describe(t)}")
        name_type=self.type_name()
        name=self.eat(K.IDENTIFIER,'identifier')
        self.eat(K.ASSIGN,"'='");value=self.parse_expression()
        self._check_literal_overflow(t,value)
        self.eat(K.DOT,"'.'")
        return DeclarationNode(kind.line,kind.column,kind.text,name_type,name.text,value)
    def parse_assignment_or_call(self):
        start=self.peek();node=self.parse_postfix()
        if self.peek().kind==K.ASSIGN:
            self.position+=1;value=self.parse_expression();self.eat(K.DOT,"'.'")
            if isinstance(node,IdentifierNode):return AssignmentNode(start.line,start.column,node.name,value)
            if isinstance(node,MemberNode) and node.args is None:return FieldAssignmentNode(start.line,start.column,node,value)
            raise CompilationError(start.line,start.column,'assignment requires a variable or field')
        if isinstance(node,(CallNode,MemberNode)) and (not isinstance(node,MemberNode) or node.args is not None):
            self.eat(K.DOT,"'.'");return CallStatementNode(start.line,start.column,node)
        self.eat(K.ASSIGN,"'='")  # preserves Stage 1 assignment diagnostics
        raise AssertionError('unreachable')
    def parse_assignment(self):return self.parse_assignment_or_call()
    def parse_return(self):
        t=self.word('rise');value=self.parse_expression();self.eat(K.DOT,"'.'")
        return ReturnNode(t.line,t.column,value)
    def parse_if_statement(self):
        t=self.eat(K.WHEN,"'when'");c=self.parse_expression();then=self.parse_block();otherwise=None
        if self.peek().kind==K.OTHERWISE:self.position+=1;otherwise=self.parse_block()
        return IfNode(t.line,t.column,c,then,otherwise)
    def parse_block(self):
        self.eat(K.BLOCK_OPEN,"'⟨'")
        if self.peek().kind==K.BLOCK_CLOSE:
            t=self.peek();raise CompilationError(t.line,t.column,'block must contain at least one statement')
        body=[self.parse_statement()]
        while self.peek().kind!=K.BLOCK_CLOSE:
            if self.peek().kind==K.EOF:
                t=self.peek();raise CompilationError(t.line,t.column,"expected '⟩' before end of file")
            body.append(self.parse_statement())
        self.eat(K.BLOCK_CLOSE,"'⟩'");return body
    def parse_function(self):
        t=self.word('spark');name=self.eat(K.IDENTIFIER,'function name')
        self.eat(K.LPAREN,"'('");params=[]
        if self.peek().kind!=K.RPAREN:
            params.append(self.parse_parameter())
            while self.peek().kind==K.COMMA:self.position+=1;params.append(self.parse_parameter())
        self.eat(K.RPAREN,"')'");self.eat(K.ARROW,"'->'");result=self.type_name()
        body=self.parse_block()
        return FunctionNode(t.line,t.column,name.text,params,result,body)
    def parse_parameter(self):
        t=self.peek();mutable=False
        if t.kind in (K.CALM,K.FLOW):mutable=t.kind==K.FLOW;self.position+=1
        typ=self.type_name();name=self.eat(K.IDENTIFIER,'parameter name')
        return ParameterNode(t.line,t.column,name.text,typ,mutable)
    def parse_struct(self):
        t=self.word('astro');name=self.eat(K.IDENTIFIER,'structure name')
        self.eat(K.BLOCK_OPEN,"'⟨'");fields=[];methods=[]
        while self.peek().kind not in (K.BLOCK_CLOSE,K.EOF):
            if self.is_word('spark') and self.peek(1).kind==K.IDENTIFIER:methods.append(self.parse_function())
            else:
                kind=self.peek()
                if kind.kind not in (K.FLOW,K.CALM):
                    raise CompilationError(kind.line,kind.column,'expected calm/flow field or spark method')
                self.position+=1;typ=self.type_name();field=self.eat(K.IDENTIFIER,'field name')
                self.eat(K.DOT,"'.'");fields.append(FieldNode(kind.line,kind.column,field.text,typ,kind.kind==K.FLOW))
        self.eat(K.BLOCK_CLOSE,"'⟩'")
        if not fields:raise CompilationError(t.line,t.column,'astro must declare at least one field')
        return StructNode(t.line,t.column,name.text,fields,methods)
    def parse_expression(self):return self.parse_comparison()
    def parse_comparison(self):
        left=self.parse_additive()
        if self.peek().kind in (K.EQUAL,K.NOT_EQUAL):
            t=self.peek();self.position+=1;right=self.parse_additive()
            return ComparisonNode(t.line,t.column,t.text,left,right)
        return left
    def parse_additive(self):
        left=self.parse_multiplicative()
        while self.peek().kind in (K.PLUS,K.MINUS):
            t=self.peek();self.position+=1;right=self.parse_multiplicative();left=BinaryNode(t.line,t.column,t.text,left,right)
        return left
    def parse_multiplicative(self):
        left=self.parse_unary()
        while self.peek().kind in (K.STAR,K.SLASH):
            t=self.peek();self.position+=1;right=self.parse_unary();left=BinaryNode(t.line,t.column,t.text,left,right)
        return left
    def parse_unary(self):
        if self.peek().kind==K.MINUS:
            t=self.eat(K.MINUS,"'-'")
            # Preserve all Stage 1 negative integer AST and error positions.
            if self.peek().kind==K.INTEGER:
                n=self.eat(K.INTEGER,'integer literal after \'-\'')
                return IntegerLiteralNode(t.line,t.column,-int(n.text))
            if self.peek().kind not in (K.LPAREN,K.IDENTIFIER,K.MINUS,K.TYPE_I32,K.TYPE_I64):
                self.eat(K.INTEGER,"integer literal after '-'")
            return UnaryNode(t.line,t.column,'-',self.parse_unary())
        return self.parse_postfix()
    def parse_postfix(self):
        value=self.parse_primary()
        while True:
            if self.peek().kind==K.LPAREN and isinstance(value,IdentifierNode):
                args=self.parse_arguments();value=CallNode(value.line,value.column,value.name,args);continue
            if self.peek().kind==K.MEMBER:
                if isinstance(value,MemberNode) and value.args is not None:
                    self.eat(K.DOT,"'.'")  # A member call terminates its access chain.
                tok=self.eat(K.MEMBER);member=self.eat(K.IDENTIFIER,'member name')
                args=self.parse_arguments() if self.peek().kind==K.LPAREN else None
                value=MemberNode(tok.line,tok.column,value,member.text,args)
                if args is not None:break  # Member call terminates the chain.
                continue
            break
        return value
    def parse_arguments(self):
        self.eat(K.LPAREN,"'('");args=[]
        if self.peek().kind!=K.RPAREN:
            args.append(self.parse_expression())
            while self.peek().kind==K.COMMA:
                self.position+=1;args.append(self.parse_expression())
        self.eat(K.RPAREN,"')'");return args
    def parse_primary(self):
        t=self.peek()
        if t.kind==K.INTEGER:self.position+=1;return IntegerLiteralNode(t.line,t.column,int(t.text))
        if t.kind in (K.LIGHT,K.DARK):self.position+=1;return BooleanLiteralNode(t.line,t.column,t.kind==K.LIGHT)
        if t.kind==K.STRING:self.position+=1;return StringNode(t.line,t.column,t.text)
        if t.kind in (K.IDENTIFIER,K.TYPE_I32,K.TYPE_I64,K.TYPE_BOOL):
            self.position+=1
            if (self.peek().kind==K.BLOCK_OPEN and t.kind==K.IDENTIFIER
                and self.peek(1).kind==K.IDENTIFIER and self.peek(2).kind==K.ASSIGN):
                self.position+=1;fields=[]
                if self.peek().kind!=K.BLOCK_CLOSE:
                    fields.append(self.parse_field_initializer())
                    while self.peek().kind==K.COMMA:
                        self.position+=1;fields.append(self.parse_field_initializer())
                self.eat(K.BLOCK_CLOSE,"'⟩'");return ConstructorNode(t.line,t.column,t.text,fields)
            return IdentifierNode(t.line,t.column,t.text)
        if t.kind==K.LPAREN:
            self.position+=1;value=self.parse_expression();self.eat(K.RPAREN,"')'");return value
        raise CompilationError(t.line,t.column,f"expected expression, got {self._describe(t)}")
    def parse_field_initializer(self):
        name=self.eat(K.IDENTIFIER,'field name');self.eat(K.ASSIGN,"'='");return (name.text,self.parse_expression())
    @staticmethod
    def _check_literal_overflow(t,v):
        if not isinstance(v,IntegerLiteralNode):return
        lim={K.TYPE_I32:(_I32_MIN,_I32_MAX,'☼ (i32)'),K.TYPE_I64:(_I64_MIN,_I64_MAX,'☽ (i64)')}.get(t.kind)
        if lim and not lim[0]<=v.value<=lim[1]:raise CompilationError(v.line,v.column,f'integer literal overflows {lim[2]}')
    @staticmethod
    def _describe(t):return 'end of file' if t.kind==K.EOF else f"'{t.text}'"
