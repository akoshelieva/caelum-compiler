"""AST class hierarchy for Caelum."""

from dataclasses import dataclass


@dataclass
class ASTNode:
    line: int
    column: int


@dataclass
class StatementNode(ASTNode):
    pass


@dataclass
class ExpressionNode(ASTNode):
    pass


@dataclass
class ProgramNode(ASTNode):
    statements: list[StatementNode]


@dataclass
class DeclarationNode(StatementNode):
    declaration_kind: str
    type_name: str
    name: str
    initializer: ExpressionNode


@dataclass
class AssignmentNode(StatementNode):
    name: str
    value: ExpressionNode


@dataclass
class IfNode(StatementNode):
    condition: ExpressionNode
    then_body: list[StatementNode]
    else_body: list[StatementNode] | None


@dataclass
class IntegerLiteralNode(ExpressionNode):
    value: int


@dataclass
class BooleanLiteralNode(ExpressionNode):
    value: bool


@dataclass
class IdentifierNode(ExpressionNode):
    name: str


@dataclass
class ComparisonNode(ExpressionNode):
    operator: str
    left: ExpressionNode
    right: ExpressionNode

@dataclass
class FunctionNode(StatementNode):
    name: str
    parameters: list['ParameterNode']
    result_type: str
    body: list[StatementNode]

@dataclass
class ParameterNode(ASTNode):
    name: str
    type_name: str
    mutable: bool

@dataclass
class StructNode(StatementNode):
    name: str
    fields: list['FieldNode']
    methods: list[FunctionNode]

@dataclass
class FieldNode(ASTNode):
    name: str
    type_name: str
    mutable: bool

@dataclass
class ReturnNode(StatementNode):
    value: ExpressionNode

@dataclass
class CallStatementNode(StatementNode):
    call: ExpressionNode

@dataclass
class FieldAssignmentNode(StatementNode):
    target: ExpressionNode
    value: ExpressionNode

@dataclass
class BinaryNode(ExpressionNode):
    operator: str
    left: ExpressionNode
    right: ExpressionNode

@dataclass
class UnaryNode(ExpressionNode):
    operator: str
    value: ExpressionNode

@dataclass
class StringNode(ExpressionNode):
    value: str

@dataclass
class CallNode(ExpressionNode):
    name: str
    args: list[ExpressionNode]

@dataclass
class MemberNode(ExpressionNode):
    base: ExpressionNode
    name: str
    args: list[ExpressionNode] | None = None

@dataclass
class ConstructorNode(ExpressionNode):
    name: str
    fields: list[tuple[str,ExpressionNode]]
