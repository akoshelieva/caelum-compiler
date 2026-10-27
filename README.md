# Caelum Compiler — Stage 2

Caelum is a strictly typed, sky-themed language. The original Stage 1 syntax is retained: emoji primitive types, `fixed`/`calm`/`flow`, `when`/`otherwise`, `⟨ ... ⟩` blocks, period-terminated statements, Latin-only case-sensitive identifiers, and the original AST format. Stage 2 adds functions, nominal structures, member functions, integer arithmetic, checked errors, and LLVM IR generation.

## Prerequisites

- Python 3.10+ and `llvmlite` (`python3 -m pip install llvmlite`).
- LLVM-compatible `clang` for building the generated IR into executables.
- No parser generator: the lexer is hand-written and byte-oriented, and the parser is recursive descent.

## Build, run, and inspect

```bash
python3 compiler.py --ast examples/example.caelum
python3 compiler.py examples/example.caelum output.ll
clang output.ll -o caelum-program
./caelum-program
python3 run_tests.py
```

`--ast` runs lexical and syntax checks only, preserving all Stage 1 golden files, including their error positions and AST nodes. Normal compilation runs the separate semantic analysis **before** LLVM generation. The compiler writes the builder-printed module to `output.ll`, not handwritten IR. No output file is left after a compilation error.

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

## LLVM implementation

The compiler declares all functions before generating function bodies. User functions use names such as `caelum.fn.twice`; members use `caelum.method.Star.increase` with a pointer to the receiver as the first argument. Named structs use LLVM identified struct types. Each field access uses the field's index from the semantic structure table to generate `getelementptr`; object construction has one value per field. Branching uses `if/else` basic blocks. Arithmetic overflow checks use `llvm.sadd/ssub/smul.with.overflow` intrinsic declarations and explicit branches on their flags. The `scanf` and `printf` functions are declared, with their format strings stored as global constants.

## Tests and submission

`python3 run_tests.py` runs the 47 original Stage 1 AST golden tests unchanged, checks that all Stage 1 valid cases still compile to LLVM, checks Stage 2 semantic-invalid programs and one-line diagnostics, builds and executes end-to-end programs with `clang`, verifies exact stdout, supplies `.in` files for stdin tests, and checks runtime error stderr and exit status. It reports every failure and exits nonzero when any test fails.

The local `stage2` branch contains Git commits and is not pushed. Generated `.ll` files, executables and scratch files are excluded from the repository. Existing AI usage files were deliberately left untouched per the provided instructions; the assignment separately requires an `ai_usage_2.txt` disclosure at final submission.
