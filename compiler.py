#!/usr/bin/env python3
"""Caelum compiler: --ast or semantic analysis + LLVM IR generation."""
import sys
from pathlib import Path
from ast_printer import ASTPrinter
from errors import CompilationError
from lexer import Lexer
from parser import Parser

def compile_to_ast(source:bytes,optimize:bool=False)->str:
    tree=Parser(Lexer(source).tokenize()).parse_program()
    if optimize:
        from semantic import Semantic
        from optimizer import Optimizer
        sem=Semantic(tree).analyze()
        Optimizer(tree,sem).run()
    return ASTPrinter().dump(tree)

def compile_to_llvm(source:bytes,optimize:bool=False)->str:
    from semantic import Semantic
    from codegen import LLVMGenerator
    tree=Parser(Lexer(source).tokenize()).parse_program()
    sem=Semantic(tree).analyze()
    if optimize:
        from optimizer import Optimizer
        sem=Optimizer(tree,sem).run()
    result=LLVMGenerator(sem).generate()
    from llvmlite import binding
    mod=binding.parse_assembly(result)
    mod.verify()
    return result

def main(argv:list[str])->int:
    arguments=argv[1:]
    optimize='--optimize' in arguments
    ast='--ast' in arguments
    paths=[arg for arg in arguments if arg not in ('--optimize','--ast')]
    valid_flags=(arguments.count('--optimize')<=1 and arguments.count('--ast')<=1
                 and not any(arg.startswith('--') for arg in paths))
    if not valid_flags or len(paths)!=(1 if ast else 2):
        print('usage: python3 compiler.py [--optimize] --ast <input-file> | [--optimize] <input-file> <output.ll>',file=sys.stderr)
        return 2
    path=Path(paths[0]);dest=Path(paths[1]) if not ast else None
    try:
        source=path.read_bytes()
    except OSError as exc:
        print(f"compilation error: line 1:1: cannot read '{path}': {exc}",file=sys.stderr);return 1
    try:
        output=compile_to_ast(source,optimize) if ast else compile_to_llvm(source,optimize)
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
