#!/usr/bin/env python3
"""Caelum regression and end-to-end golden-file suite (all tests are run)."""
from pathlib import Path
from tempfile import TemporaryDirectory
import subprocess
import sys
import shutil
from itertools import product
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
from dataclasses import dataclass
import compiler

ROOT=Path(__file__).resolve().parent
TESTS=ROOT/'tests'
CLANG=shutil.which('clang')
LLC=shutil.which('llc')
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

def legacy(path,valid,optimize=False):
    expected=path.with_suffix('.expected').read_text(encoding='utf8')
    result=invoke('--optimize','--ast',path) if optimize else invoke('--ast',path)
    if valid:
        # A Stage 1 golden describes the original AST. The optimized AST is
        # intentionally different, but must remain compilable and well-formed.
        good = (result.returncode==0 and result.stderr==''
                and (result.stdout.startswith('Program @') if optimize else result.stdout==expected))
        return good,repr((result.returncode,result.stderr))
    return result.returncode!=0 and result.stdout=='' and result.stderr==expected and result.stderr.count('\n')==1,repr(result.stderr)

def semantic_invalid(path,optimize=False):
    expected=path.with_suffix('.expected').read_text(encoding='utf8')
    with TemporaryDirectory() as d:
        out=Path(d)/'unexpected.ll'
        result=invoke(path,out,'--optimize') if optimize else invoke(path,out)
        good=(result.returncode!=0 and result.stdout=='' and result.stderr==expected
              and result.stderr.count('\n')==1 and not out.exists())
    return good,repr(result.stderr)

def compile_run(path,runtime_error=False,optimize=False,input_file=None,expected_file=None):
    if CLANG is None:return False,'clang is not installed'
    with TemporaryDirectory() as d:
        d=Path(d);ir=d/'program.ll';exe=d/'program'
        result=invoke(path,'--optimize',ir) if optimize else invoke(path,ir)
        if result.returncode or result.stderr or not ir.exists():
            return False,'compile: '+repr(result.stderr)
        built=subprocess.run([CLANG,'-Wno-override-module',str(ir),'-o',str(exe)],capture_output=True,text=True,timeout=12)
        if built.returncode:return False,'clang: '+built.stderr
        session_input=input_file if input_file is not None else path.with_suffix('.in')
        stdin=session_input.read_text(encoding='utf8') if session_input.exists() else ''
        ran=subprocess.run([str(exe)],input=stdin,stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE,text=True,timeout=8)
        if runtime_error:
            expected=path.with_suffix('.stderr').read_text(encoding='utf8')
            good=(ran.returncode!=0 and ran.stdout=='' and ran.stderr==expected)
        else:
            golden=expected_file if expected_file is not None else path.with_suffix('.expected')
            expected=golden.read_text(encoding='utf8')
            good=(ran.returncode==0 and ran.stderr=='' and ran.stdout==expected)
        return good,repr((ran.returncode,ran.stdout,ran.stderr))

def stage1_codegen(path,optimize=False):
    with TemporaryDirectory() as d:
        result=invoke('--optimize',path,Path(d)/'stage1.ll') if optimize else invoke(path,Path(d)/'stage1.ll')
        return result.returncode==0 and result.stderr=='' ,repr(result.stderr)

# The tactical game is larger than the earlier examples. Compile each native
# variant once, then reuse the executable for every golden and strategy run.
_SPACE_GAME_DIRECTORY=None
_SPACE_GAME_BINARIES={}

def space_battle_executable(optimize=False):
    global _SPACE_GAME_DIRECTORY
    if optimize in _SPACE_GAME_BINARIES:
        return _SPACE_GAME_BINARIES[optimize]
    if CLANG is None:
        raise RuntimeError('clang is not installed')
    if _SPACE_GAME_DIRECTORY is None:
        _SPACE_GAME_DIRECTORY=TemporaryDirectory()
    d=Path(_SPACE_GAME_DIRECTORY.name)
    label='optimized' if optimize else 'plain'
    source=ROOT/'programs'/'space_battle.txt'
    ir=d/(label+'.ll')
    obj=d/(label+'.o')
    executable=d/(label+'.bin')
    result=invoke(source,ir,'--optimize') if optimize else invoke(source,ir)
    if result.returncode or result.stderr or not ir.exists():
        raise RuntimeError(f'game compilation failed: {result.stderr}')
    # Prefer the exact WSL build with llc; the clang IR backend can emit the
    # same native object on systems where llc is not installed.
    build=([LLC,'-mtriple=x86_64-pc-linux-gnu','-filetype=obj',str(ir),'-o',str(obj)]
           if LLC else [CLANG,'-Wno-override-module','-target','x86_64-pc-linux-gnu',
                        '-c',str(ir),'-o',str(obj)])
    made=subprocess.run(build,capture_output=True,text=True,timeout=15)
    if made.returncode:
        raise RuntimeError(f'game object compilation failed: {made.stderr}')
    linked=subprocess.run([CLANG,'-no-pie',str(obj),'-o',str(executable)],
                          capture_output=True,text=True,timeout=15)
    if linked.returncode:
        raise RuntimeError(f'game linking failed: {linked.stderr}')
    _SPACE_GAME_BINARIES[optimize]=executable
    return executable

def play_space_battle(actions,optimize=False):
    executable=space_battle_executable(optimize)
    return subprocess.run([str(executable)],input=actions,stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE,text=True,timeout=8)

def space_battle_case(input_file,optimize=False):
    """Compare a recorded tactical game with its exact native transcript."""
    stdin=input_file.read_text(encoding='utf-8')
    expected=input_file.with_suffix('.expected').read_text(encoding='utf-8')
    ran=play_space_battle(stdin,optimize)
    passed=ran.returncode==0 and ran.stderr=='' and ran.stdout==expected
    return passed,repr((ran.returncode,ran.stdout,ran.stderr)) if not passed else ''

def space_battle_strategy_sweep():
    """Exhaust all 3**5 action sequences in both native modes."""
    endings=set()
    winners=set()
    observed=set()
    for actions in product((1,2,3),repeat=5):
        stdin='\n'.join(map(str,actions))+'\n'
        plain=play_space_battle(stdin)
        optimized=play_space_battle(stdin,True)
        if any(x.returncode or x.stderr for x in (plain,optimized)):
            return False,f'native program failed for {actions}'
        if plain.stdout!=optimized.stdout:
            return False,f'--optimize changes output for {actions}'
        output=plain.stdout
        turns=output.count('ROUND ')
        if output.count('GAME OVER\n')!=1 or not 1<=turns<=5:
            return False,f'game termination incorrect for {actions}'
        frame=[line for line in output.splitlines() if line.startswith(('|','+'))]
        if len(frame)!=5*(turns+1) or any(len(line)!=29 for line in frame):
            return False,f'battlefield alignment incorrect for {actions}'
        final=[line for line in output.splitlines() if line.startswith(('VICTORY:', 'DEFEAT:', 'INVALID ACTION:'))]
        if len(final)!=1:
            return False,f'expected one ending for {actions}, got {final}'
        endings.add(final[0])
        if final[0].startswith('VICTORY:'):
            winners.add('with EMP' if 3 in actions[:turns] else 'without EMP')
        for cue in ('Shield activated.', 'Charging heavy laser.', 'Heavy laser fired!',
                    'Aggressive response.', 'Final strike!'):
            if cue in output:observed.add(cue)
    required={'VICTORY: Enemy destroyed!', 'VICTORY: Barely survived!',
              'DEFEAT: Ship destroyed.', 'DEFEAT: Reactor meltdown.',
              'DEFEAT: Enemy survived five rounds.',
              'INVALID ACTION: Not enough energy for Fire.',
              'INVALID ACTION: Not enough energy for EMP.'}
    if not required.issubset(endings):
        return False,f'uncovered ending categories: {required-endings}'
    if winners!={'with EMP','without EMP'} or len(observed)!=5:
        return False,f'missing winning strategy or enemy response: {winners}, {observed}'
    return True,'243 action sequences, both native modes, diverse wins and losses'

def optimizer_case(path):
    """Golden AST and identical native behavior with / without optimization."""
    expected_ast=path.with_suffix('.ast.expected').read_text(encoding='utf8')
    ast_first=invoke('--optimize','--ast',path)
    ast_last=invoke('--ast',path,'--optimize')
    if (ast_first.returncode or ast_first.stderr or ast_first.stdout!=expected_ast
            or ast_last!=ast_first):
        return False,'optimized AST differs from golden or flag position: '+repr(ast_first.stderr)
    plain_ok,plain_result=compile_run(path)
    opt_ok,opt_result=compile_run(path,optimize=True)
    return plain_ok and opt_ok,repr((plain_result,opt_result))

def optimizer_runtime_error(path):
    before=compile_run(path,runtime_error=True)
    after=compile_run(path,runtime_error=True,optimize=True)
    return before[0] and after[0],repr((before[1],after[1]))

def main():
    suites=[('stage1-valid',TESTS/'valid',lambda x:legacy(x,True)),
            ('stage1-invalid',TESTS/'invalid',lambda x:legacy(x,False)),
            ('semantic-invalid',TESTS/'semantic_invalid',semantic_invalid),
            ('runtime',TESTS/'runtime',compile_run),
            ('runtime-error',TESTS/'runtime_errors',lambda x:compile_run(x,True)),
            ('stage1-llvm',TESTS/'valid',stage1_codegen),
            ('piping-valid',TESTS/'piping_valid',compile_run),
            ('piping-invalid',TESTS/'piping_invalid',semantic_invalid),
            ('optimizer',TESTS/'optimizer',optimizer_case),
            ('optimizer-runtime-error',TESTS/'optimizer_errors',lambda x:optimizer_runtime_error(x)),
            ('space-battle',ROOT/'programs',space_battle_case),
            ('optimized-space-battle',ROOT/'programs',lambda x:space_battle_case(x,True))]
    # Run all earlier stages with the new flag too, including negative cases.
    suites += [('optimized-stage1-valid',TESTS/'valid',lambda x:legacy(x,True,True)),
               ('optimized-stage1-invalid',TESTS/'invalid',lambda x:legacy(x,False,True)),
               ('optimized-semantic-invalid',TESTS/'semantic_invalid',lambda x:semantic_invalid(x,True)),
               ('optimized-runtime',TESTS/'runtime',lambda x:compile_run(x,optimize=True)),
               ('optimized-runtime-error',TESTS/'runtime_errors',lambda x:compile_run(x,True,True)),
               ('optimized-stage1-llvm',TESTS/'valid',lambda x:stage1_codegen(x,True)),
               ('optimized-piping-valid',TESTS/'piping_valid',lambda x:compile_run(x,optimize=True)),
               ('optimized-piping-invalid',TESTS/'piping_invalid',lambda x:semantic_invalid(x,True))]
    total=failed=0
    for name,folder,fn in suites:
        files=(folder.rglob('*.caelum') if name=='optimizer' else
               folder.glob('space_battle_*.in') if 'space-battle' in name else
               folder.glob('*.caelum'))
        for path in sorted(files):
            total+=1
            try:passed,detail=fn(path)
            except Exception as exc:passed=False;detail=f'{type(exc).__name__}: {exc}'
            print(('PASS' if passed else 'FAIL')+f' {name}/{path.stem}'+('' if passed else ': '+detail))
            failed+=not passed
    total+=1
    try:passed,detail=space_battle_strategy_sweep()
    except Exception as exc:passed=False;detail=f'{type(exc).__name__}: {exc}'
    print(('PASS' if passed else 'FAIL')+' space-battle/strategy-sweep'+(': '+detail if not passed else ' ('+detail+')'))
    failed+=not passed
    print(f'\n{total-failed}/{total} tests passed')
    return int(bool(failed))

if __name__=='__main__':raise SystemExit(main())
