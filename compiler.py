#!/usr/bin/env python3
"""Caelum compiler: --ast or semantic analysis + LLVM IR generation."""
import sys
from pathlib import Path
from ast_printer import ASTPrinter
from errors import CompilationError
from lexer import Lexer
from parser import Parser

def compile_to_ast(source:bytes)->str:
    return ASTPrinter().dump(Parser(Lexer(source).tokenize()).parse_program())

def compile_to_llvm(source:bytes)->str:
    from semantic import Semantic
    from codegen import LLVMGenerator
    tree=Parser(Lexer(source).tokenize()).parse_program()
    sem=Semantic(tree).analyze()
    result=LLVMGenerator(sem).generate()
    from llvmlite import binding
    mod=binding.parse_assembly(result)
    mod.verify()
    return result

def main(argv:list[str])->int:
    is_ast=len(argv)==3 and argv[1]=='--ast'
    is_compile=len(argv)==3 and argv[1]!='--ast'
    if not (is_ast or is_compile):
        print('usage: python3 compiler.py --ast <input-file> | <input-file> <output.ll>',file=sys.stderr);return 2
    path=Path(argv[2] if is_ast else argv[1]);dest=Path(argv[2]) if is_compile else None
    try:
        source=path.read_bytes()
    except OSError as exc:
        print(f"compilation error: line 1:1: cannot read '{path}': {exc}",file=sys.stderr);return 1
    try:
        output=compile_to_ast(source) if is_ast else compile_to_llvm(source)
        if dest is not None:dest.write_text(output,encoding='utf-8')
        else:sys.stdout.write(output)
        return 0
    except CompilationError as exc:
        if dest is not None:dest.unlink(missing_ok=True)
        print(exc.format(),file=sys.stderr);return 1
    except Exception as exc:
        if dest is not None:dest.unlink(missing_ok=True)
        print(f'compilation error: line 1:1: internal compiler failure: {exc}',file=sys.stderr);return 1

if __name__=='__main__':raise SystemExit(main(sys.argv))
