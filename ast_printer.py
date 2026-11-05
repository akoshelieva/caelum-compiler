"""Deterministic text dump for Caelum AST nodes."""
from dataclasses import fields, is_dataclass
from ast_nodes import ASTNode

from ast_nodes import (
    ASTNode,
    AssignmentNode,
    BooleanLiteralNode,
    ComparisonNode,
    DeclarationNode,
    IdentifierNode,
    IfNode,
    IntegerLiteralNode,
    ProgramNode,
)


class ASTPrinter:
    def dump(self, node: ASTNode) -> str:
        lines: list[str] = []
        self._write_node(node, 0, lines)
        return "\n".join(lines) + "\n"

    def _write_node(self, node: ASTNode, level: int, lines: list[str]) -> None:
        if isinstance(node, ProgramNode):
            self._line(lines, level, self._header("Program", node))
            for statement in node.statements:
                self._write_node(statement, level + 1, lines)
            return

        if isinstance(node, DeclarationNode):
            self._line(lines, level, self._header("Declaration", node))
            self._line(lines, level + 1, f"kind: {node.declaration_kind}")
            self._line(lines, level + 1, f"type: {node.type_name}")
            self._line(lines, level + 1, f"name: {node.name}")
            self._line(lines, level + 1, "initializer:")
            self._write_node(node.initializer, level + 2, lines)
            return

        if isinstance(node, AssignmentNode):
            self._line(lines, level, self._header("Assignment", node))
            self._line(lines, level + 1, f"name: {node.name}")
            self._line(lines, level + 1, "value:")
            self._write_node(node.value, level + 2, lines)
            return

        if isinstance(node, IfNode):
            self._line(lines, level, self._header("If", node))
            self._line(lines, level + 1, "condition:")
            self._write_node(node.condition, level + 2, lines)
            self._line(lines, level + 1, "then:")
            for statement in node.then_body:
                self._write_node(statement, level + 2, lines)
            if node.else_body is None:
                self._line(lines, level + 1, "else: none")
            else:
                self._line(lines, level + 1, "else:")
                for statement in node.else_body:
                    self._write_node(statement, level + 2, lines)
            return

        if isinstance(node, ComparisonNode):
            self._line(lines, level, self._header("Comparison", node))
            self._line(lines, level + 1, f"operator: {node.operator}")
            self._line(lines, level + 1, "left:")
            self._write_node(node.left, level + 2, lines)
            self._line(lines, level + 1, "right:")
            self._write_node(node.right, level + 2, lines)
            return

        if isinstance(node, IntegerLiteralNode):
            self._line(lines, level, self._header("IntegerLiteral", node))
            self._line(lines, level + 1, f"value: {node.value}")
            return

        if isinstance(node, BooleanLiteralNode):
            self._line(lines, level, self._header("BooleanLiteral", node))
            value = "true" if node.value else "false"
            self._line(lines, level + 1, f"value: {value}")
            return

        if isinstance(node, IdentifierNode):
            self._line(lines, level, self._header("Identifier", node))
            self._line(lines, level + 1, f"name: {node.name}")
            return

        # Generic Stage 2 nodes retain every field, argument, and mutability flag.
        if is_dataclass(node):
            self._line(lines,level,self._header(type(node).__name__.removesuffix("Node"),node))
            for field in fields(node):
                if field.name in ("line","column"):continue
                value=getattr(node,field.name)
                self._line(lines,level+1,field.name+":")
                self._write_value(value,level+2,lines)
            return
        raise TypeError(f"unsupported AST node: {type(node).__name__}")

    def _write_value(self,value,level,lines):
        if isinstance(value,ASTNode):self._write_node(value,level,lines)
        elif isinstance(value,list):
            for item in value:self._write_value(item,level,lines)
        elif isinstance(value,tuple):
            for item in value:self._write_value(item,level,lines)
        else:self._line(lines,level,repr(value))

    @staticmethod
    def _header(name: str, node: ASTNode) -> str:
        return f"{name} @ {node.line}:{node.column}"

    @staticmethod
    def _line(lines: list[str], level: int, text: str) -> None:
        lines.append(f"{'  ' * level}{text}")
