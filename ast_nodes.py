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
