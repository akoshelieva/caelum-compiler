#!/usr/bin/env python3
"""Caelum regression and end-to-end golden-file suite (all tests are run)."""
from pathlib import Path
from tempfile import TemporaryDirectory
import subprocess
import sys
import shutil
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
from dataclasses import dataclass
import compiler

ROOT=Path(__file__).resolve().parent
TESTS=ROOT/'tests'
CLANG=shutil.which('clang')
PYTHON=sys.executable

@dataclass
class Result:
    returncode: int
    stdout: str
    stderr: str

def invoke(*args,input=None):
    out,err=StringIO(),StringIO()
    with redirect_stdout(out),redirect_stderr(err):
        code=compiler.main(['compiler.py',*map(str,args)])
    return Result(code,out.getvalue(),err.getvalue())

def legacy(path,valid):
    expected=path.with_suffix('.expected').read_text(encoding='utf8')
    result=invoke('--ast',path)
    if valid:return result.returncode==0 and result.stderr=='' and result.stdout==expected,repr((result.returncode,result.stderr))
    return result.returncode!=0 and result.stdout=='' and result.stderr==expected and result.stderr.count('\n')==1,repr(result.stderr)

def semantic_invalid(path):
    expected=path.with_suffix('.expected').read_text(encoding='utf8')
    with TemporaryDirectory() as d:
        out=Path(d)/'unexpected.ll'
        result=invoke(path,out)
        good=(result.returncode!=0 and result.stdout=='' and result.stderr==expected
              and result.stderr.count('\n')==1 and not out.exists())
    return good,repr(result.stderr)

def compile_run(path,runtime_error=False):
    if CLANG is None:return False,'clang is not installed'
    with TemporaryDirectory() as d:
        d=Path(d);ir=d/'program.ll';exe=d/'program'
        result=invoke(path,ir)
        if result.returncode or result.stderr or not ir.exists():
            return False,'compile: '+repr(result.stderr)
        built=subprocess.run([CLANG,'-Wno-override-module',str(ir),'-o',str(exe)],capture_output=True,text=True,timeout=12)
        if built.returncode:return False,'clang: '+built.stderr
        input_file=path.with_suffix('.in')
        stdin=input_file.read_text(encoding='utf8') if input_file.exists() else ''
        ran=subprocess.run([str(exe)],input=stdin,stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE,text=True,timeout=8)
        if runtime_error:
            expected=path.with_suffix('.stderr').read_text(encoding='utf8')
            good=(ran.returncode!=0 and ran.stdout=='' and ran.stderr==expected)
        else:
            expected=path.with_suffix('.expected').read_text(encoding='utf8')
            good=(ran.returncode==0 and ran.stderr=='' and ran.stdout==expected)
        return good,repr((ran.returncode,ran.stdout,ran.stderr))

def stage1_codegen(path):
    with TemporaryDirectory() as d:
        result=invoke(path,Path(d)/'stage1.ll')
        return result.returncode==0 and result.stderr=='' ,repr(result.stderr)

def main():
    suites=[('stage1-valid',TESTS/'valid',lambda x:legacy(x,True)),
            ('stage1-invalid',TESTS/'invalid',lambda x:legacy(x,False)),
            ('semantic-invalid',TESTS/'semantic_invalid',semantic_invalid),
            ('runtime',TESTS/'runtime',compile_run),
            ('runtime-error',TESTS/'runtime_errors',lambda x:compile_run(x,True)),
            ('stage1-llvm',TESTS/'valid',stage1_codegen)]
    total=failed=0
    for name,folder,fn in suites:
        for path in sorted(folder.glob('*.caelum')):
            total+=1
            try:passed,detail=fn(path)
            except Exception as exc:passed=False;detail=f'{type(exc).__name__}: {exc}'
            print(('PASS' if passed else 'FAIL')+f' {name}/{path.stem}'+('' if passed else ': '+detail))
            failed+=not passed
    print(f'\n{total-failed}/{total} tests passed')
    return int(bool(failed))

if __name__=='__main__':raise SystemExit(main())
