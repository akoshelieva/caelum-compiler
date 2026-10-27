#!/usr/bin/env python3
"""Run all Caelum Stage 1 golden-file tests."""

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

import compiler


ROOT = Path(__file__).resolve().parent
TESTS = ROOT / "tests"


def invoke(path: Path) -> tuple[int, str, str]:
    stdout = StringIO()
    stderr = StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = compiler.main(["compiler.py", "--ast", str(path)])
    return code, stdout.getvalue(), stderr.getvalue()


def run_valid(path: Path) -> tuple[bool, str]:
    expected = path.with_suffix(".expected").read_text(encoding="utf-8")
    code, stdout, stderr = invoke(path)

    if code != 0:
        return False, f"expected exit 0, got {code}: {stderr.strip()}"
    if stderr != "":
        return False, f"expected empty stderr, got: {stderr.strip()}"
    if stdout != expected:
        return False, "AST output differs from expected file"
    return True, ""


def run_invalid(path: Path) -> tuple[bool, str]:
    expected = path.with_suffix(".expected").read_text(encoding="utf-8")
    code, stdout, stderr = invoke(path)

    if code == 0:
        return False, "expected non-zero exit code, got 0"
    if stdout != "":
        return False, f"expected empty stdout, got: {stdout.strip()}"
    if stderr != expected:
        return False, "error output differs from expected file"
    if stderr.count("\n") != 1:
        return False, "error must be exactly one line"
    return True, ""


def main() -> int:
    cases = []
    for path in sorted((TESTS / "valid").glob("*.caelum")):
        cases.append(("valid", path, run_valid))
    for path in sorted((TESTS / "invalid").glob("*.caelum")):
        cases.append(("invalid", path, run_invalid))

    failures = 0
    for category, path, runner in cases:
        ok, detail = runner(path)
        label = f"{category}/{path.stem}"
        if ok:
            print(f"PASS {label}")
        else:
            failures += 1
            print(f"FAIL {label}: {detail}")

    passed = len(cases) - failures
    print(f"\n{passed}/{len(cases)} tests passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
