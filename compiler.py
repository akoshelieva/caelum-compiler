#!/usr/bin/env python3
"""Caelum compiler: --ast or semantic analysis + LLVM IR generation."""
import os
import sys
from pathlib import Path
from tempfile import NamedTemporaryFile
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

def report_error(message:str)->int:
    # Keep all user-visible compiler errors on one stderr line.
    clean=' '.join(str(message).splitlines())
    print(f'compilation error: line 1:1: {clean}',file=sys.stderr)
    return 1

def remove_output(dest:Path)->None:
    # Never remove a directory in place of an output file.
    if not dest.is_dir():
        dest.unlink(missing_ok=True)

def write_output(dest:Path,output:str)->None:
    # Write in the destination directory and replace atomically on success.
    temporary=None
    try:
        with NamedTemporaryFile(mode='w',encoding='utf-8',dir=dest.parent,
                                prefix=f'.{dest.name}.',suffix='.tmp',delete=False) as file:
            temporary=Path(file.name)
            file.write(output)
        os.replace(temporary,dest)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)

def main(argv:list[str])->int:
    arguments=argv[1:]
    optimize='--optimize' in arguments
    ast='--ast' in arguments
    paths=[arg for arg in arguments if arg not in ('--optimize','--ast')]
    valid_flags=(arguments.count('--optimize')<=1 and arguments.count('--ast')<=1
                 and not any(arg.startswith('--') for arg in paths))
    if not valid_flags or len(paths)!=(1 if ast else 2):
        return report_error('usage: python3 compiler.py [--optimize] --ast <input-file> | [--optimize] <input-file> <output.ll>')
    path=Path(paths[0]);dest=Path(paths[1]) if not ast else None
    if dest is not None:
        try:
            if path.resolve()==dest.resolve():
                return report_error('input and output paths must be different')
            # Even when compilation fails, do not leave a stale output.ll.
            remove_output(dest)
        except OSError as exc:
            return report_error(f"cannot prepare output '{dest}': {exc}")
    try:
        source=path.read_bytes()
    except OSError as exc:
        return report_error(f"cannot read '{path}': {exc}")
    try:
        output=compile_to_ast(source,optimize) if ast else compile_to_llvm(source,optimize)
        if dest is not None:write_output(dest,output)
        else:sys.stdout.write(output)
        return 0
    except CompilationError as exc:
        return_code=1
        error=exc.format()
    except Exception as exc:
        return_code=1
        error=f'compilation error: line 1:1: internal compiler failure: {exc}'
    if dest is not None:
        try:remove_output(dest)
        except OSError:pass
    print(' '.join(error.splitlines()),file=sys.stderr)
    return return_code

if __name__=='__main__':raise SystemExit(main(sys.argv))
