"""Recursive-descent parser for the Caelum language."""

from ast_nodes import (
    AssignmentNode,
    BooleanLiteralNode,
    ComparisonNode,
    DeclarationNode,
    ExpressionNode,
    IdentifierNode,
    IfNode,
    IntegerLiteralNode,
    ProgramNode,
    StatementNode,
)
from errors import CompilationError
from tokens import Token, TokenKind


_I32_MIN = -(2**31)
_I32_MAX = 2**31 - 1
_I64_MIN = -(2**63)
_I64_MAX = 2**63 - 1

_TYPE_KINDS = {TokenKind.TYPE_I32, TokenKind.TYPE_I64, TokenKind.TYPE_BOOL}
_DECLARATION_KINDS = {TokenKind.FIXED, TokenKind.CALM, TokenKind.FLOW}


class Parser:
    def __init__(self, tokens: list[Token]) -> None:
        self.tokens = tokens
        self.position = 0

    def peek(self, offset: int = 0) -> Token:
        index = self.position + offset
        if index >= len(self.tokens):
            return self.tokens[-1]
        return self.tokens[index]

    def eat(self, kind: TokenKind, expected: str | None = None) -> Token:
        token = self.peek()
        if token.kind is not kind:
            wanted = expected if expected is not None else kind.name
            raise CompilationError(
                token.line,
                token.column,
                f"expected {wanted}, got {self._describe(token)}",
            )
        self.position += 1
        return token

    def parse_program(self) -> ProgramNode:
        statements: list[StatementNode] = []
        start = self.peek()
        while self.peek().kind is not TokenKind.EOF:
            statements.append(self.parse_statement())
        self.eat(TokenKind.EOF, "end of file")
        return ProgramNode(start.line, start.column, statements)

    def parse_statement(self) -> StatementNode:
        token = self.peek()
        if token.kind in _DECLARATION_KINDS:
            return self.parse_declaration()
        if token.kind is TokenKind.IDENTIFIER:
            return self.parse_assignment()
        if token.kind is TokenKind.WHEN:
            return self.parse_if_statement()
        raise CompilationError(
            token.line,
            token.column,
            f"expected statement, got {self._describe(token)}",
        )

    def parse_declaration(self) -> DeclarationNode:
        kind_token = self.peek()
        self.position += 1

        type_token = self.peek()
        if type_token.kind not in _TYPE_KINDS:
            raise CompilationError(
                type_token.line,
                type_token.column,
                f"expected type name, got {self._describe(type_token)}",
            )
        self.position += 1

        name_token = self.eat(TokenKind.IDENTIFIER, "identifier")
        self.eat(TokenKind.ASSIGN, "'='")
        initializer = self.parse_expression()
        self._check_literal_overflow(type_token, initializer)
        self.eat(TokenKind.DOT, "'.'")

        return DeclarationNode(
            kind_token.line,
            kind_token.column,
            kind_token.text,
            type_token.text,
            name_token.text,
            initializer,
        )

    def parse_assignment(self) -> AssignmentNode:
        name_token = self.eat(TokenKind.IDENTIFIER, "identifier")
        self.eat(TokenKind.ASSIGN, "'='")
        value = self.parse_expression()
        self.eat(TokenKind.DOT, "'.'")
        return AssignmentNode(
            name_token.line,
            name_token.column,
            name_token.text,
            value,
        )

    def parse_if_statement(self) -> IfNode:
        when_token = self.eat(TokenKind.WHEN, "'when'")
        condition = self.parse_expression()
        then_body = self.parse_block()

        else_body = None
        if self.peek().kind is TokenKind.OTHERWISE:
            self.eat(TokenKind.OTHERWISE, "'otherwise'")
            else_body = self.parse_block()

        return IfNode(
            when_token.line,
            when_token.column,
            condition,
            then_body,
            else_body,
        )

    def parse_block(self) -> list[StatementNode]:
        self.eat(TokenKind.BLOCK_OPEN, "'⟨'")
        if self.peek().kind is TokenKind.BLOCK_CLOSE:
            token = self.peek()
            raise CompilationError(
                token.line,
                token.column,
                "block must contain at least one statement",
            )

        statements = [self.parse_statement()]
        while self.peek().kind is not TokenKind.BLOCK_CLOSE:
            if self.peek().kind is TokenKind.EOF:
                token = self.peek()
                raise CompilationError(
                    token.line,
                    token.column,
                    "expected '⟩' before end of file",
                )
            statements.append(self.parse_statement())

        self.eat(TokenKind.BLOCK_CLOSE, "'⟩'")
        return statements

    def parse_expression(self) -> ExpressionNode:
        return self.parse_comparison()

    def parse_comparison(self) -> ExpressionNode:
        left = self.parse_primary()
        token = self.peek()
        if token.kind in (TokenKind.EQUAL, TokenKind.NOT_EQUAL):
            self.position += 1
            right = self.parse_primary()
            return ComparisonNode(
                token.line,
                token.column,
                token.text,
                left,
                right,
            )
        return left

    def parse_primary(self) -> ExpressionNode:
        token = self.peek()

        if token.kind is TokenKind.MINUS:
            minus = self.eat(TokenKind.MINUS, "'-'")
            number = self.eat(TokenKind.INTEGER, "integer literal after '-'")
            return IntegerLiteralNode(minus.line, minus.column, -int(number.text))

        if token.kind is TokenKind.INTEGER:
            number = self.eat(TokenKind.INTEGER, "integer literal")
            return IntegerLiteralNode(number.line, number.column, int(number.text))

        if token.kind is TokenKind.LIGHT:
            value = self.eat(TokenKind.LIGHT, "'light'")
            return BooleanLiteralNode(value.line, value.column, True)

        if token.kind is TokenKind.DARK:
            value = self.eat(TokenKind.DARK, "'dark'")
            return BooleanLiteralNode(value.line, value.column, False)

        if token.kind is TokenKind.IDENTIFIER:
            identifier = self.eat(TokenKind.IDENTIFIER, "identifier")
            return IdentifierNode(
                identifier.line,
                identifier.column,
                identifier.text,
            )

        raise CompilationError(
            token.line,
            token.column,
            f"expected expression, got {self._describe(token)}",
        )

    @staticmethod
    def _check_literal_overflow(
        type_token: Token, initializer: ExpressionNode
    ) -> None:
        if not isinstance(initializer, IntegerLiteralNode):
            return

        if type_token.kind is TokenKind.TYPE_I32:
            if not _I32_MIN <= initializer.value <= _I32_MAX:
                raise CompilationError(
                    initializer.line,
                    initializer.column,
                    "integer literal overflows ☼ (i32)",
                )

        if type_token.kind is TokenKind.TYPE_I64:
            if not _I64_MIN <= initializer.value <= _I64_MAX:
                raise CompilationError(
                    initializer.line,
                    initializer.column,
                    "integer literal overflows ☽ (i64)",
                )

    @staticmethod
    def _describe(token: Token) -> str:
        if token.kind is TokenKind.EOF:
            return "end of file"
        return f"'{token.text}'"
