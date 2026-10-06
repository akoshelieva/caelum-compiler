#!/usr/bin/env python3
"""Command-line entry point for the Caelum Stage 1 compiler."""

import sys
from pathlib import Path

from ast_printer import ASTPrinter
from errors import CompilationError
from lexer import Lexer
from parser import Parser


def compile_to_ast(source: bytes) -> str:
    tokens = Lexer(source).tokenize()
    tree = Parser(tokens).parse_program()
    return ASTPrinter().dump(tree)


def main(argv: list[str]) -> int:
    if len(argv) != 3 or argv[1] != "--ast":
        print("usage: python3 compiler.py --ast <input-file>", file=sys.stderr)
        return 2

    path = Path(argv[2])
    try:
        source = path.read_bytes()
    except OSError as exc:
        print(f"compilation error: line 1:1: cannot read '{path}': {exc}", file=sys.stderr)
        return 1

    try:
        output = compile_to_ast(source)
    except CompilationError as exc:
        print(exc.format(), file=sys.stderr)
        return 1

    sys.stdout.write(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
