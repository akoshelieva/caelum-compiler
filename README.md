# Caelum Compiler — Stage 3 (Piping, AST Optimization, and Space Battle)

Caelum is a strictly typed, sky-themed language. The original Stage 1 syntax is retained: emoji primitive types, `fixed`/`calm`/`flow`, `when`/`otherwise`, `⟨ ... ⟩` blocks, period-terminated statements, Latin-only case-sensitive identifiers, and the original AST format. Stage 2 adds functions, nominal structures, member functions, integer arithmetic, checked errors, and LLVM IR generation. Stage 3 Task 1 adds typed, left-to-right piping (`|>`). Task 2 adds an optional checked-AST optimizer with dead-variable elimination, dead-function elimination, and limited function inlining. Task 3 adds the small interactive Space Battle game.

## Prerequisites

- Python 3.10+ and `llvmlite` (`python3 -m pip install llvmlite`).
- LLVM tools `llc` and `clang` for building the generated IR into executables.
- No parser generator: the lexer is hand-written and byte-oriented, and the parser is recursive descent.

## Build, run, and inspect

```bash
python3 compiler.py --ast examples/example.caelum
python3 compiler.py examples/example.caelum output.ll
python3 compiler.py --optimize examples/example.caelum output.ll
python3 compiler.py --ast --optimize examples/example.caelum
python3 compiler.py examples/example.caelum output.ll --optimize
clang output.ll -o caelum-program
./caelum-program
python3 run_tests.py
```

By default, `--ast` runs lexical and syntax checks only, preserving all Stage 1 golden files, including their error positions and AST nodes. When combined with `--optimize`, it first performs semantic checking and then prints **the optimized AST**. `--optimize` may appear anywhere in the argument list (before, between, or after file paths; also before or after `--ast`). Normal compilation runs the separate semantic analysis **before** LLVM generation. The compiler writes the builder-printed module to `output.ll`, not handwritten IR. No output file is left after a compilation error.

Errors in lexical, syntactic, and semantic checks use **one line on stderr** and a nonzero status:

```text
compilation error: line L:C: message
```

Runtime errors (division by zero, overflow, invalid input) print a `runtime error:` diagnostic to stderr and exit nonzero.

## Types and identifiers

| Caelum | Meaning |
| --- | --- |
| `☼` | Signed 32-bit integer, −2147483648 … 2147483647 |
| `☽` | Signed 64-bit integer, −9223372036854775808 … 9223372036854775807 |
| `☁︎` **or** `☁` | Boolean; both Unicode spellings resolve to **one** type |
| `light`, `dark` | Boolean values, printed as `true`, `false` |
| `fixed` | Constant primitive declaration |
| `calm` | Immutable declaration |
| `flow` | Mutable declaration |
| `⟨ ... ⟩` | Nonempty executable block; also encloses named constructor fields |
| `.` | Statement terminator |

The original `☁︎` is U+2601 followed by U+FE0E; plain `☁` is U+2601. Both are accepted, addressing the Stage 1 feedback about the invisible selector. U+FE0F is **not** supported. Identifiers contain only ASCII Latin letters (`A–Z`, `a–z`), without digits or underscores. All original Stage 1 keywords remain reserved; the new words `spark`, `astro`, `rise`, and `core` are contextual. The two builtin names are protected against declarations as global user functions but can be shadowed by ordinary variables.

### Variables, scopes, and comparisons

```text
fixed ☼ LIMIT = 100.
calm ☁ ready = light.
flow ☽ distance = 9000000000.
flow ☼ count = 2.
when ready == light ⟨
    flow ☼ count = 5.
    recordCoordinates(count).
⟩ otherwise ⟨
    recordCoordinates(distance).
⟩
```

Scopes are nested; shadowing is allowed, but duplicate definitions in one scope are not. A local name shadows fields, then globals, and ultimately built-ins. Methods of the current `astro` take precedence over global functions. Explicit `core ~ field` or `core ~ method()` bypasses local shadowing. A name resolving to a variable is not callable. Top-level statements execute top-to-bottom. Globals must be declared before use, including inside function bodies; function and `astro` types may be declared below their uses. Potentially unsafe global initialization dependencies are rejected.

Arithmetic supports `+`, `-`, `*`, `/`, unary `-`, parentheses and `==`, `!=`; multiplication/division bind more tightly than addition/subtraction, which bind more tightly than equality. Expressions and arguments evaluate left-to-right. Division truncates toward zero. Literal ranges and literal-only constant arithmetic are checked at compile time; operations involving variables use runtime checks (including min-int / −1 and division by zero). There are no implicit casts between typed `☼` and `☽` values and no explicit numeric casts. Numeric **literals** can adopt an expected `☽` width in expression contexts. Equality for `astro` recursively compares fields of the same nominal type.

## Functions: `spark` and `rise`

```text
spark twice(☼ value) -> ☼ ⟨
    rise value + value.
⟩
recordCoordinates(twice(7)).
```

Function arguments are typed and passed **by value**. Parameters are `calm` by default; `flow ☼ value` permits reassignment to a local copy. All functions return their declared type, and all control-flow paths must execute `rise`. Recursive calls, forward calls, nested calls and calls used as standalone statements are allowed. Functions can read globals declared before them; `flow` globals can be assigned. Nested function declarations and top-level `rise` are forbidden. Every wrong argument count, type, or returned type produces a semantic diagnostic. A global `spark` named after a built-in is forbidden.

## Piping: `|>` (Stage 3 Task 1)

`value |> function1 |> function2` evaluates the input expression **once**, then passes the resulting value as the sole argument of `function1`, followed by `function2`. A pipe stage names an existing **global user-defined** `spark` function with **exactly one** parameter. Forward-declared global functions are permitted. A method, a built-in (`recordCoordinates`, `lookThroughTelescope`), a variable, a lambda, or a call with explicit arguments (`f(2)`) is not a valid stage. Piping is allowed in every expression context, including function arguments, arithmetic operands in parentheses, return values, named constructor fields and conditions.

The operator is **left associative**, and has lower precedence than `==` and `!=`. `a + b |> f |> g` means `g(f(a + b))`. Parentheses override precedence, e.g. `(a |> f) + b`. The first numeric literal can use the first function parameter's expected integer width, just as it would in an ordinary call. **No implicit conversions** are introduced: for each stage, its parameter type must exactly match the preceding value's type; the result type becomes the input type to the next stage. A bad stage reports its **1-based index, name, expected and actual types**, at the pipe operator's source position. A non-callable/missing stage or wrong parameter count also reports the precise stage. Evaluation order and function side effects are unchanged.

**Example 1 — arithmetic processing** (`tests/piping_valid/chain.caelum`, prints `20`):

```text
spark twice(☼ x) -> ☼ ⟨
    rise x * 2.
⟩
spark addTen(☼ x) -> ☼ ⟨
    rise x + 10.
⟩
recordCoordinates(5 |> twice |> addTen).
```

**Example 2 — wider integers and a boolean result** (`tests/piping_valid/types.caelum`, prints `true`):

```text
spark widen(☽ n) -> ☽ ⟨
    rise n + 1.
⟩
spark positive(☽ n) -> ☁ ⟨
    rise n != 0.
⟩
recordCoordinates(9000000000 |> widen |> positive).
```

**Builder-generated LLVM IR excerpt** (14 consecutive lines from `python3 compiler.py tests/piping_valid/chain.caelum output.ll`):

```llvm
define i32 @"main"()
{
entry:
  %".2" = call i32 @"caelum.fn.twice"(i32 5)
  %".3" = call i32 @"caelum.fn.addTen"(i32 %".2")
  %".4" = getelementptr inbounds [3 x i8], [3 x i8]* @"caelum.str.1", i32 0, i32 0
  %".5" = call i32 (i8*, ...) @"printf"(i8* %".4", i32 %".3")
  %".6" = getelementptr inbounds [2 x i8], [2 x i8]* @"caelum.str.2", i32 0, i32 0
  %".7" = call i32 (i8*, ...) @"printf"(i8* %".6")
  ret i32 0
}

@"caelum.str.1" = internal constant [3 x i8] c"%d\00"
@"caelum.str.2" = internal constant [2 x i8] c"\0a\00"
```

1. `main` evaluates the constant `5` and calls `caelum.fn.twice` with it; the returned `i32` value is bound to `%.2`.
2. The second call passes that result directly to `caelum.fn.addTen`, proving the left-to-right chain with no intermediate recomputation or casts.
3. `getelementptr` obtains the format-string addresses for `printf`, which prints the final `i32` and newline, then `main` returns zero. Every instruction above was emitted through `llvmlite.ir.IRBuilder` or its module/global APIs, not manually assembled.

## Structures: `astro` and named construction

```text
astro Point ⟨
    flow ☼ x.
    calm ☼ y.
    spark getX() -> ☼ ⟨ rise x. ⟩
⟩

flow Point point = Point⟨y = 4, x = 3⟩.
recordCoordinates(point, point ~ getX()).
```

Every `astro` declares at least one field. Fields use only `calm` or `flow`, without field defaults. Methods and fields can be declared in any order, with methods seeing other methods and fields declared later. Named constructors supply **every field exactly once**; missing, duplicate or unknown field names and wrong field types are errors. The initializer order is arbitrary and expressions run in their written order; the new object's fields do not implicitly become visible to each other during construction. Structures are nominally typed; self-referential by-value cycles are invalid. `fixed` objects are forbidden (use `calm` or `flow`).

Structure values are copied on assignment and when passed to ordinary functions. Copying `calm` to `flow` creates an independent mutable binding, but individual `calm` fields stay immutable. Assignment to a field through `~` requires **each link of the chain** to be mutable, including the root object and final field. An entire `flow` structure field may be replaced with a value of exactly its type. The `~` operator **requires at least one ordinary space on each side**; tabs and newlines alone do not count. A member call ends its `~` chain; a global function result may be read via `~` without assigning it first.

### Methods and mutating effects

```text
astro Star ⟨
    flow ☼ brightness.
    spark increase(☼ delta) -> ☼ ⟨
        core ~ brightness = brightness + delta.
        rise brightness.
    ⟩
⟩
flow Star sirius = Star⟨brightness = 100⟩.
recordCoordinates(sirius ~ increase(5)).
```

`core` refers to the current `astro` object and can be used as a value. It cannot be reassigned and cannot be shadowed by a method parameter/local variable. Fields can be read and written either by bare name or explicitly through `core`, with identical mutability rules. The compiler **automatically** determines whether a method is mutating: it writes a field of any `astro` object, or transitively calls a function/method that does. Writing a global primitive alone does not make a method mutating. Recursive and indirect calls are included in the effect analysis. A mutating method requires a mutable object chain. Calls on `calm` or temporary receivers are rejected; nonmutating methods can be used there.

## Input and output

```text
flow ☼ n = lookThroughTelescope().
recordCoordinates("Distance", n, light).
```

`lookThroughTelescope()` reads one **whole decimal integer token** from stdin and returns `☼`; malformed text, EOF and out-of-range values are runtime errors. Whitespace separates tokens. The runtime uses `scanf` for token acquisition and validates the entire token and range. The default C runtime is linked using `clang`.

`recordCoordinates()` accepts **one or more** arguments and prints each value immediately followed by a newline, before evaluating the next argument. Supported values: `☼` and `☽` in decimal (`%d`, `%lld`); booleans as `true` / `false`; literal strings without quotes; and `astro` objects recursively in declaration field order, for instance `Star⟨id=1, brightness=100⟩`. Strings have UTF-8 and `\n`, `\t`, `\"`, `\\` escapes. Strings cannot be variables, fields, function parameters or return types.

## AST optimizer: `--optimize` (Stage 3 Task 2)

The optimizer lives in `optimizer.py` and runs **after** `Semantic(tree).analyze()` and **before** `LLVMGenerator(sem).generate()`. The source language's lexer, parser, and grammar are unchanged. Optimized ASTs are **rechecked** after structural changes so that symbol identity, expression types, effects, callable targets and function tables are current. Without `--optimize` the compiler and Stage 1 AST output retain their original behavior. Optimizations operate only on syntax/AST nodes; LLVM is still emitted exclusively using the existing `llvmlite.ir.IRBuilder` and module APIs.

1. **Unused variables (1 point).** Identify read references using semantic `Symbol` identity rather than spelling, so nested block scopes and shadowing are handled. Remove dead `flow`/`calm`/`fixed` declarations and writes to them, repeating passes until no more can be removed (e.g., removing `second = first` exposes `first` as unused). An initializer/RHS containing a function call, Piping, `lookThroughTelescope()`, a member call, or potentially trapping arithmetic is **retained as an expression statement**, in its original position and evaluation order. Thus read, print, mutation, division-by-zero and overflow behavior cannot disappear merely because the assigned value is unused. Dead assignment targets are simple variables, not structure fields; structure-field assignments are retained.
2. **Unused functions (1 point).** Compute reachability from top-level executable expressions, following the complete, type-checked call graph. Remove all unreachable global `spark` functions and unreachable `astro` methods; transitive orphan chains disappear together. Re-run semantic analysis after deletion. No dynamic function pointers exist in Caelum, so all callable targets are statically known.
3. **Inlining (2 points).** For a global, nonrecursive `spark` called at **exactly one syntactic call site**, copy its straight-line body into an optimizer-only `InlineExpr` AST node. Every parameter becomes a scoped local declaration initialized from its corresponding argument in left-to-right order; the final `rise` expression becomes the value of the inlined expression. All parameter and local binding names are alpha-renamed to fresh Caelum-legal ASCII identifiers, avoiding collisions with caller variables and with each other. Nested calls in the caller, including Piping stages, are supported; a targeted pipe is lowered to equivalent left-to-right nested AST calls. Inlining and dead-function elimination run repeatedly, with semantic rechecking between expansions. The inlined function's no-longer-used definition is removed.

**Inlining boundaries:** only global functions whose body has zero or more straight-line local variable declarations/simple local or parameter assignments, followed by exactly one final `rise`, are expanded. The candidate body must not read or assign global variables or implicit `astro` fields, or itself contain calls or pipelines. Recursive and mutually recursive functions, methods, conditionals/early `rise` inside `when`, function bodies with global effects, and bodies with nested calls are **deliberately left as calls**. Such functions remain perfectly valid and execute normally. These restrictions protect global-name resolution, member receiver context, branch/return semantics and side-effect ordering; they are not general language limitations. An optimized call can still contain side-effectful argument expressions, evaluated once in their original order.

**Example — builder-generated IR before/after inlining** (`tests/optimizer/inlining/identity.caelum`; main-body excerpts):

Before (`python3 compiler.py tests/optimizer/inlining/identity.caelum output.ll`):

```llvm
define i32 @"main"()
{
entry:
  %".2" = call i32 @"caelum.fn.identity"(i32 7)
  %".3" = getelementptr inbounds [3 x i8], [3 x i8]* @"caelum.str.0", i32 0, i32 0
  %".4" = call i32 (i8*, ...) @"printf"(i8* %".3", i32 %".2")
  %".5" = getelementptr inbounds [2 x i8], [2 x i8]* @"caelum.str.1", i32 0, i32 0
  %".6" = call i32 (i8*, ...) @"printf"(i8* %".5")
  ret i32 0
}
```

After (`python3 compiler.py tests/optimizer/inlining/identity.caelum output.ll --optimize`):

```llvm
define i32 @"main"()
{
entry:
  %"inlineA.addr" = alloca i32
  store i32 7, i32* %"inlineA.addr"
  %".3" = load i32, i32* %"inlineA.addr"
  %".4" = getelementptr inbounds [3 x i8], [3 x i8]* @"caelum.str.0", i32 0, i32 0
  %".5" = call i32 (i8*, ...) @"printf"(i8* %".4", i32 %".3")
  %".6" = getelementptr inbounds [2 x i8], [2 x i8]* @"caelum.str.1", i32 0, i32 0
  %".7" = call i32 (i8*, ...) @"printf"(i8* %".6")
  ret i32 0
}
```

The original `call` invokes the separate `identity` function. After optimization, `identity` no longer has a definition or a call; the `inlineA` alloca/store/load represents its by-value parameter and the following `printf` receives the result directly. Both outputs print `7` and a newline. The optimizer did not assemble any LLVM text; the excerpts come directly from the same LLVM builder used for unoptimized compilation.

**Mechanical verification:** `tests/optimizer/` contains 13 programs: four unused-variable cases, two unused-function cases, and seven inlining/guard cases (including recursion and global-read non-inline checks, dead locals and input evaluation order). Each has an exact `.ast.expected` for `--ast --optimize` and a native `.expected` output. The test script checks the same output both with and without the optimization flag, and tests both placements of `--optimize` with `--ast`. Two extra `tests/optimizer_errors/` programs prove that removed assignments cannot suppress input validation or division-by-zero failures. The entire preexisting Stage 1, Stage 2 and Task 1 suite is run a second time with `--optimize` (including errors, native execution and LLVM compilation).

## LLVM implementation

The compiler declares all functions before generating function bodies. User functions use names such as `caelum.fn.twice`; members use `caelum.method.Star.increase` with a pointer to the receiver as the first argument. Named structs use LLVM identified struct types. Each field access uses the field's index from the semantic structure table to generate `getelementptr`; object construction has one value per field. Branching uses `if/else` basic blocks. Arithmetic overflow checks use `llvm.sadd/ssub/smul.with.overflow` intrinsic declarations and explicit branches on their flags. The `scanf` and `printf` functions are declared, with their format strings stored as global constants.

## Space Battle (Stage 3 Task 3)

Space Battle is a small console game written in Caelum. You control a spaceship and try to defeat an enemy within three rounds. The game shows a simple battlefield and the health of both ships. Enter `1` to attack or `2` to defend. An invalid choice ends the game.

The game uses an `astro Ship` structure with a `takeHit()` method, `spark` functions, `when` / `otherwise`, `lookThroughTelescope()` for input, and `recordCoordinates()` for output. Piping is used in the main battle logic: `2 |> chargeLaser` calculates attack damage, and `2 |> raiseShield` reduces damage when defending.

### Build and run

Generate LLVM IR, build a native program with `llc` and `clang`, then run it:

```bash
python3 compiler.py programs/space_battle.txt space_battle.ll
llc -filetype=obj space_battle.ll -o space_battle.o
clang space_battle.o -o space_battle
./space_battle
```

To compile with AST optimization enabled, use:

```bash
python3 compiler.py --optimize programs/space_battle.txt space_battle_opt.ll
llc -filetype=obj space_battle_opt.ll -o space_battle_opt.o
clang space_battle_opt.o -o space_battle_opt
```

### Recorded game sessions

The game has three recorded sessions:

- **Win:** attack twice to destroy the enemy (`space_battle_win`).
- **Lose:** attack once, then defend twice (`space_battle_lose`).
- **Invalid action:** enter `9` instead of `1` or `2` (`space_battle_invalid`).

Each `.in` file contains the player's choices. Its matching `.expected` file contains the exact output, including prompts. Run the sessions with:

```bash
./space_battle < programs/space_battle_win.in
./space_battle < programs/space_battle_lose.in
./space_battle < programs/space_battle_invalid.in
```

Run all automated tests with `python3 run_tests.py`. The test script checks each game's output against its `.expected` file, both with and without `--optimize`.

## Tests and submission

`python3 run_tests.py` runs all original Stage 1 AST golden tests unchanged, the Stage 2 semantic and runtime tests, four native Piping tests and six invalid Piping tests. It also tests the optimizer's expected AST and native output for all thirteen programs, plus two preservation-of-runtime-error cases. All previous suites are repeated with `--optimize`, checking error diagnostics and side-effect preservation. It also checks three recorded Space Battle sessions with and without optimization. It reports every failure and exits nonzero on a mismatch.

The local `stage3` branch is created from `stage2` and contains only local commits; it has not been pushed. Generated `.ll` files, executables and scratch files are excluded from the repository. Existing AI usage files were deliberately left untouched per the provided instructions. The Stage 3 assignment separately requires `ai_usage_3.txt` at submission; it is not included yet.
