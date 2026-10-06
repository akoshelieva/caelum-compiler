# Caelum Compiler — Stage 1

Caelum is a small custom programming language with a sky-themed surface syntax.
Stage 1 implements a hand-written byte-oriented lexer, a recursive-descent
parser, an AST class hierarchy, a deterministic AST dump, source positions,
and golden-file tests.

## Language design

Caelum uses symbols for primitive type names and short English words for
language behavior.

| Caelum | Meaning |
| --- | --- |
| `☼` | signed 32-bit integer (`i32`) |
| `☽` | signed 64-bit integer (`i64`) |
| `☁︎` | boolean (`bool`) |
| `fixed` | constant declaration |
| `calm` | immutable variable declaration |
| `flow` | mutable variable declaration |
| `light` | boolean true |
| `dark` | boolean false |
| `when` | conditional (`if`) |
| `otherwise` | optional `else` branch |
| `=` | assignment / initializer |
| `==` | equality comparison |
| `!=` | inequality comparison |
| `.` | statement terminator |
| `⟨ ... ⟩` | non-empty statement block |

Identifiers contain Latin letters only (`A-Z`, `a-z`). Digits, underscores,
and non-Latin letters are not valid identifier characters.

## Syntax examples

### Constants

```text
fixed ☼ LIMIT = 100.
fixed ☽ DISTANCE = 9000000000.
```

### Immutable variables

```text
calm ☼ start = 10.
calm ☁︎ active = light.
```

### Mutable variables and assignment

```text
flow ☼ score = 15.
score = 20.
```

The parser records whether a declaration is `fixed`, `calm`, or `flow` in the
AST. Full semantic enforcement of mutability belongs to the later semantic
stage.

### Booleans

```text
calm ☁︎ visible = light.
calm ☁︎ hidden = dark.
```

### Comparisons

```text
score == 20
score != 0
visible == light
```

### Conditional without `otherwise`

A block must contain at least one statement.

```text
when score != 0 ⟨
    score = 20.
⟩
```

### Conditional with `otherwise`

```text
when active == light ⟨
    score = 20.
⟩ otherwise ⟨
    score = 0.
⟩
```

Nested `when` statements are allowed.

### Integer ranges and overflow

`☼` has the range `-2147483648..2147483647`.
`☽` has the range `-9223372036854775808..9223372036854775807`.

Typed integer literals in declarations are checked against these ranges. For
example, this is rejected:

```text
fixed ☼ BIG = 2147483648.
```

with an error such as:

```text
compilation error: line 1:15: integer literal overflows ☼ (i32)
```

## Grammar

The complete EBNF grammar is in [`grammar.ebnf`](grammar.ebnf). The parser is
implemented with recursive descent and mirrors the grammar using dedicated
methods such as `parse_program`, `parse_statement`, `parse_declaration`,
`parse_assignment`, `parse_if_statement`, `parse_block`, `parse_expression`,
`parse_comparison`, and `parse_primary`.

## Lexer implementation

The lexer in `lexer.py` is hand-written and operates directly on source bytes.
It does not use regular expressions, `split()`, or a lexer generator. ASCII
identifiers and integer literals are consumed byte-by-byte. Caelum's UTF-8
symbols (`☼`, `☽`, `☁︎`, `⟨`, `⟩`) are matched as exact byte sequences.

Every token stores:

- token kind;
- original token text;
- line;
- column.

## AST

AST nodes are classes rooted at `ASTNode`. The hierarchy includes program,
statement, expression, declaration, assignment, conditional, comparison,
identifier, integer literal, and boolean literal nodes. Every node stores its
source line and column.

The AST dump is deterministic and includes node types, source positions,
declaration kind, type, names, operators, values, and nesting.

## Running the compiler

Python 3.10 or newer is recommended. No third-party dependencies are required.

Run the included example:

```bash
python3 compiler.py --ast examples/example.caelum
```

Run another source file:

```bash
python3 compiler.py --ast path/to/program.caelum
```

On success, the AST is written to stdout and the exit code is `0`.

Lexical or syntax/required range errors are written as exactly one line to
stderr in this form:

```text
compilation error: line L:C: message
```

The exit code is non-zero and stdout is empty.

## Running tests

Run the complete suite with:

```bash
python3 run_tests.py
```

The repository contains 47 golden-file tests:

- 22 valid programs with expected AST dumps;
- 25 invalid programs with expected one-line errors.

The runner reports every passing/failing case and returns a non-zero exit code
if any test fails.

The tests cover declarations, all three primitive types, both boolean values,
assignment, `==`, `!=`, `when`, optional `otherwise`, nested conditionals,
non-empty block rules, identifier restrictions, lexical errors, malformed
syntax, and both valid boundaries and overflow for `☼` and `☽`.

## Project structure

```text
.
├── compiler.py
├── lexer.py
├── parser.py
├── tokens.py
├── errors.py
├── ast_nodes.py
├── ast_printer.py
├── grammar.ebnf
├── run_tests.py
├── README.md
├── examples/
│   └── example.caelum
└── tests/
    ├── valid/
    │   ├── *.caelum
    │   └── *.expected
    └── invalid/
        ├── *.caelum
        └── *.expected
```
