"""Shared compiler error type."""


class CompilationError(Exception):
    def __init__(self, line: int, column: int, message: str) -> None:
        super().__init__(message)
        self.line = line
        self.column = column
        self.message = message

    def format(self) -> str:
        return f"compilation error: line {self.line}:{self.column}: {self.message}"
