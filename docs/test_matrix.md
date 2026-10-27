# Caelum Stage 2 — traceability & test matrix (draft)

**Status:** specification/test planning only. No tests, lexer/parser, README, or LLVM code were modified.

**Sources:** Stage 1 repository (`grammar.ebnf`, `README.md`, `lexer.py`, `parser.py`, 47 golden tests), Stage 2 assignment PDF, and all user-approved Caelum design choices through 64A. The Stage 1 grading feedback specifically requires allowing plain `☁` (U+2601) as well as existing `☁︎` (U+2601 U+FE0E).

## Test oracles and layout

- **AST:** `python3 compiler.py --ast NAME.caelum`; exit `0`, exact stdout `NAME.expected`, empty stderr; `--ast` does not run semantics (decision 62A).
- **LEX/SYN:** `--ast` or compilation; a malformed lexical/syntax construct produces exactly one line `compilation error: line L:C: message` on stderr, nonzero exit and no output `.ll`.
- **SEM:** `python3 compiler.py NAME.caelum output.ll`; semantic failure yields exactly the same one-line stderr format, nonzero exit, **no output.ll**, and never a Python traceback.
- **E2E:** compile to `.ll` using `llvmlite.ir`, assemble/link/run with `llc + clang` or `lli`, compare **exact bytes** of stdout to `NAME.expected` (including trailing newline); if `NAME.in` exists, provide it as stdin. An E2E test may also assert an AST snapshot.
- **RUNTIME:** run compiled program with `NAME.in`; check stderr and nonzero exit for input/overflow/division errors. Runtime error text is not yet frozen; it must be deterministic. It is **not** interchangeable with a compilation error.
- **REG:** Stage 1 golden regression: identical `.expected` AST and identical invalid error line.

**Naming below is a proposed test plan, not files already present.** `V(name)` means `tests/valid/name.caelum`, `I(name)` means `tests/invalid/name.caelum`, `E(name)` means `tests/runtime/name.caelum`. Each proposed valid/invalid program gets its `.expected` oracle as appropriate. The older 47 fixtures are preserved verbatim.

## A. Stage 1 compatibility, lexer, grammar, and AST

| ID | Rule / checked outcome | Positive program | Negative program | Oracle |
|---|---|---|---|---|
| A01 | All 22 old valid ASTs remain byte-identical | Existing `tests/valid/*.caelum` (22) | — | REG/AST |
| A02 | All 25 old invalid diagnostics remain byte-identical | — | Existing `tests/invalid/*.caelum` (25) | REG/LEX/SYN |
| A03 | Plain cloud U+2601 works as bool type | V(`cloud_plain_bool`): `calm ☁ ready = light.` | I(`cloud_emoji_selector`): `☁️` (U+FE0F) | AST/LEX |
| A04 | Existing cloud U+2601+U+FE0E remains valid | V(`cloud_vs15_bool`): `calm ☁︎ ready = light.`; same canonical AST type as A03 | I(`cloud_spurious_selector`): unexpected selector without ☁ | AST/LEX |
| A05 | Unicode symbols have correct error positions | V(`unicode_type_positions`) | I(`unknown_unicode_symbol`) | AST/LEX line:column |
| A06 | Only Latin alphabetic identifiers (case-sensitive) | V(`mixed_case_identifier`) | Existing invalid `identifier_with_digit`, `identifier_with_underscore`, `non_latin_identifier` | AST/REG |
| A07 | Contextual `spark`, `astro`, `rise`, `core` retain Stage 1 identifier use | V(`contextual_as_variables`): `flow ☼ spark = 1.` | I(`spark_missing_name`) | AST/SYN |
| A08 | Blocks stay non-empty and use ⟨ ⟩ | Existing `nested_when` | Existing `empty_when_block`, `empty_otherwise_block` | REG |
| A09 | '.' still terminates every statement; bare comparison not statement | Existing `multiple_statements` | Existing `missing_assignment_period`, `bad_assignment_operator` | REG |
| A10 | Old negative integer tokens keep old AST and boundary cases | Existing `i32_min_boundary`, `i64_min_boundary` | Existing `minus_without_integer`, `i32_negative_overflow`, `i64_negative_overflow` | REG |
| A11 | Standalone calls are statements; arbitrary expressions aren't | V(`standalone_function_call`) | I(`standalone_arithmetic_expression`) | AST/SYN |
| A12 | `~` requires at least one ASCII space on BOTH sides | V(`spaced_tilde_multiple_spaces`) | I(`tilde_missing_left_space`), I(`tilde_missing_right_space`) | LEX/AST |
| A13 | Tabs/newlines alone never substitute for required space beside `~` | V(`tilde_space_with_other_whitespace`) | I(`tilde_tab_only`), I(`tilde_newline_only`) | LEX |
| A14 | Constructor ⟨⟩ and `when` block ⟨⟩ parse in the right contexts | V(`constructor_inside_condition_expr`) (semantically invalid condition if astro; use `==` to yield bool) | I(`constructor_missing_right_angle`) | AST/SYN |
| A15 | New AST includes param/result types, field mutability, args and member-call-ending flag | V(`ast_full_stage2_shape`) | I(`missing_method_call_paren`) | AST/SYN |
| A16 | Valid source strings contain UTF-8 and approved escapes | V(`unicode_string_escapes`) | I(`invalid_string_escape`), I(`unterminated_string`), I(`physical_newline_in_string`) | AST/LEX |
| A17 | Malformed UTF-8 always reports lexical error, not traceback | V(`valid_utf8_source`) | I(`invalid_utf8_byte_stream`) (binary fixture) | LEX |
| A18 | No comment syntax silently added to Caelum source | V(`plain_program_no_comments`) | Existing `unknown_character` (`;`) | REG/LEX |

## B. Functions, returns, resolution, scopes

| ID | Rule / checked outcome | Positive program | Negative program | Oracle |
|---|---|---|---|---|
| F01 | Typed declaration, correct args/results | E(`function_basic`) | I(`function_wrong_result_type`) | E2E/SEM |
| F02 | Zero-argument call and result | E(`function_zero_args`) | I(`function_too_few_args`) | E2E/SEM |
| F03 | Exact argument count, not silently ignored by LLVM builder | E(`function_exact_arity`) | I(`function_too_many_args`) | E2E/SEM |
| F04 | Strict param argument types | E(`function_matching_types`) | I(`function_wrong_argument_type`) | E2E/SEM |
| F05 | Nested calls as expression arguments | E(`nested_function_calls`) | I(`nested_call_wrong_inner_type`) | E2E/SEM |
| F06 | Function can call declaration below | E(`forward_function_call`) | I(`call_unknown_function`) | E2E/SEM |
| F07 | Self recursion / mutual recursion terminates correctly | E(`recursive_factorial`), E(`mutual_recursion`) | I(`recursive_wrong_result_type`) | E2E/SEM |
| F08 | `rise` must appear on every path | E(`return_both_branches`) | I(`return_missing_branch`) | E2E/SEM |
| F09 | `rise` only inside spark body (including methods) | E(`return_in_method`) | I(`top_level_rise`) | E2E/SEM |
| F10 | Arguments pass by value, even `flow` ones | E(`flow_parameter_local_copy`) | I(`assign_default_calm_parameter`) | E2E/SEM |
| F11 | `calm` explicit parameter accepted; `flow` mutable | E(`parameter_kinds`) | I(`duplicate_parameter_name`) | E2E/SEM |
| F12 | Declaration before use for variables | E(`local_declare_then_use`) | I(`undeclared_variable_use`) | E2E/SEM |
| F13 | One declaration per scope, nested shadowing allowed | E(`nested_shadowing`) | I(`same_scope_duplicate`) | E2E/SEM |
| F14 | Method lookup: local/param > field/method > global | E(`lookup_priority`) | I(`call_shadowing_noncallable`) | E2E/SEM |
| F15 | `core ~ method()` disambiguates hidden method | E(`explicit_core_method_call`) | I(`core_local_parameter`) | E2E/SEM |
| F16 | No nested function or struct declarations | E(`top_level_function_and_astro`) | I(`nested_spark_declaration`), I(`nested_astro_declaration`) | AST/SYN |
| F17 | `rise` expression type must be exact (no typed i32→i64 conversion) | E(`return_correct_astro_type`) | I(`return_typed_i32_into_i64`) | E2E/SEM |
| F18 | Shared namespace within same scope; method/field name collision | E(`noncolliding_names`) | I(`function_variable_same_scope`), I(`field_method_same_name`) | E2E/SEM |
| F19 | Global declaration before use even inside functions | E(`global_precedes_function`) | I(`forward_global_in_function`) | E2E/SEM |
| F20 | Top-level statements preserve written order | E(`global_statements_in_order`) | I(`unsafe_global_init_cycle`) | E2E/SEM |
| F21 | Global state can change via ordinary spark function | E(`global_astro_updated_by_spark`) | I(`global_calm_astro_modified`) | E2E/SEM |

## C. Astro fields, constructors, member functions and mutability

| ID | Rule / checked outcome | Positive program | Negative program | Oracle |
|---|---|---|---|---|
| S01 | At least one field; field order/method order flexible | E(`astro_mixed_member_order`) | I(`astro_only_methods`) | E2E/SYN |
| S02 | Primitive and astro typed fields; known types | E(`astro_nested_type`) | I(`field_unknown_type`) | E2E/SEM |
| S03 | Forward astro type reference allowed | E(`forward_astro_type`) | I(`recursive_astro_value_cycle`) | E2E/SEM |
| S04 | Constructor has all fields named, any order | E(`constructor_reordered_fields`) | I(`constructor_missing_field`) | E2E/SEM |
| S05 | Constructor forbids duplicate and unknown fields | E(`constructor_unique_fields`) | I(`constructor_duplicate_field`), I(`constructor_unknown_field`) | E2E/SEM |
| S06 | Constructor evaluates fields in written order | E(`constructor_two_reads`) with `.in` | I(`constructor_wrong_value_type`) | E2E/SEM |
| S07 | Constructor field expressions are independent | E(`constructor_uses_outer_variable`) | I(`constructor_reads_other_initializer_field`) | E2E/SEM |
| S08 | Constructor is an expression in args and rise | E(`constructor_in_call_and_return`) | I(`constructor_invalid_in_call`) | E2E/SEM |
| S09 | `fixed` forbidden for astro, while calm/flow permitted | E(`calm_and_flow_astro`) | I(`fixed_astro_declaration`) | E2E/SYN |
| S10 | Nested field access and immutable reading work | E(`nested_field_read`) | I(`unknown_nested_field`) | E2E/SEM |
| S11 | Mutable assignment requires entire chain to be flow | E(`nested_field_mutable_assignment`) | I(`assignment_via_calm_intermediate`) | E2E/SEM |
| S12 | Mutable field can be replaced by whole astro value | E(`replace_nested_astro_field`) | I(`replace_nested_astro_in_calm_chain`) | E2E/SEM |
| S13 | Whole mutable astro assignment copies the value | E(`whole_object_copy_assign`) | I(`whole_object_assign_wrong_nominal_type`) | E2E/SEM |
| S14 | Copy of calm astro into flow can be mutated (flow fields only) | E(`calm_to_flow_copy_mutable`) | I(`mutate_calm_field_in_copy`) | E2E/SEM |
| S15 | Method sees own fields and members, including later ones | E(`implicit_fields_and_forward_method`) | I(`implicit_unknown_member`) | E2E/SEM |
| S16 | Implicit field assignment and `core ~ field` agree | E(`core_and_implicit_assignment`) | I(`core_field_assignment_to_calm`) | E2E/SEM |
| S17 | `core` printable/returnable/copyable; not assignable | E(`core_as_value`) | I(`assign_to_core`) | E2E/SEM |
| S18 | Non-mutating call on calm; mutating call forbidden | E(`nonmutating_on_calm`) | I(`mutating_on_calm`) | E2E/SEM |
| S19 | Mutating call forbidden on temporary; nonmutating permitted | E(`temporary_nonmutating_call`) | I(`temporary_mutating_call`) | E2E/SEM |
| S20 | Transitive mutating detection through methods and ordinary spark | E(`method_global_primitive_nonmutating`) | I(`indirect_mutating_method_on_calm`) | E2E/SEM |
| S21 | Global astro field mutation counts; global primitive mutation does not | E(`global_primitive_effect_calm_receiver`) | I(`global_astro_field_effect_calm_receiver`) | E2E/SEM |
| S22 | Member call terminates accessor chain | E(`method_result_saved_first`) | I(`member_chain_after_method`), I(`parenthesized_method_chain_bypass`) | AST/SEM |
| S23 | Global spark result can be accessed directly via ~ | E(`global_call_result_field_read`) | I(`assign_to_temporary_field`) | E2E/SEM |
| S24 | Astro comparison structural but requires same named type | E(`same_astro_structural_equality`) | I(`compare_distinct_astro_types`) | E2E/SEM |
| S25 | `~` method call arguments and direct calls work | E(`member_call_nested_args`) | I(`member_call_too_many_args`), I(`member_call_wrong_arg_type`) | E2E/SEM |

## D. Types, arithmetic, limits and control flow

| ID | Rule / checked outcome | Positive program | Negative program | Oracle |
|---|---|---|---|---|
| T01 | Exact primitive/boolean assignment types | E(`typed_assignments`) | I(`assign_bool_to_i32`) | E2E/SEM |
| T02 | `when` requires ☁/☁︎ expression | E(`when_bool_condition`) | I(`when_integer_condition`) | E2E/SEM |
| T03 | Literals fit both i32 and i64 in expected contexts | E(`small_literal_expected_i64`) | I(`typed_i32_variable_to_i64`) | E2E/SEM |
| T04 | Context drives width of literal-only arithmetic | E(`i64_expected_literal_expression`) (`2147483647 + 1`) | I(`i32_expected_literal_overflow`) | E2E/SEM |
| T05 | No explicit casts ☼(x) / ☽(x) | E(`compatible_literal_width`) | I(`forbidden_cast`) | E2E/SYN or SEM |
| T06 | Numeric operator precedence (+ − × ÷) | E(`arithmetic_precedence`) | I(`arithmetic_wrong_operand_type`) | E2E/SEM |
| T07 | Unary minus works; old negative integers stay folded AST | E(`unary_minus_expression`) | I(`unary_minus_bool`) | E2E/SEM |
| T08 | Parentheses override precedence | E(`parenthesized_arithmetic`) | I(`unclosed_parenthesized_expr`) | E2E/SYN |
| T09 | Signed division truncates toward zero | E(`negative_division_truncation`) | I(`constant_divide_by_zero`) | E2E/SEM |
| T10 | Runtime zero division and signed MIN/-1 checked | E(`safe_runtime_division`) | I(`constant_min_over_negone`), E(`runtime_divide_by_zero`) (negative runtime fixture) | E2E/SEM/RUNTIME |
| T11 | Constant expression overflow rejected at compile time | E(`safe_constant_arithmetic`) | I(`constant_add_overflow`) | E2E/SEM |
| T12 | Variable-based arithmetic overflow checked at runtime | E(`safe_variable_arithmetic`) | E(`runtime_add_overflow`) (negative runtime fixture) | E2E/RUNTIME |
| T13 | Old declaration overflow errors preserved exactly | Existing `i32_max_boundary`, `i64_min_boundary` | Existing 4 overflow golden invalid tests | REG |
| T14 | `==`/`!=` are binary and no unapproved operator chaining | E(`comparison_operators`) | I(`comparison_chain_without_parentheses`) | E2E/SYN |
| T15 | Expression operands evaluated left-to-right | E(`read_operands_in_order`) with `.in` | I(`compare_incompatible_types`) | E2E/SEM |
| T16 | Boolean printing true/false; never numeric i1 | E(`bool_output_both_values`) | I(`boolean_in_integer_arithmetic`) | E2E/SEM |

## E. Built-ins, strings, printing and I/O

| ID | Rule / checked outcome | Positive program | Negative program | Oracle |
|---|---|---|---|---|
| I01 | `lookThroughTelescope()` has exactly zero arguments, returns ☼ | E(`read_single_i32`) with `.in` | I(`read_with_argument`) | E2E/SEM |
| I02 | Read full valid signed decimal token, separated by whitespace | E(`read_two_tokens`) with `.in` (`3 4`) | E(`read_malformed_suffix`) (`12abc`) as negative runtime fixture | E2E/RUNTIME |
| I03 | Read out-of-range integer gives runtime failure | E(`read_i32_min_max`) | E(`read_i32_out_of_range`) as negative runtime fixture | E2E/RUNTIME |
| I04 | EOF and noninteger input give runtime failure | E(`read_valid_then_print`) | E(`read_eof`), E(`read_letters`) as negative runtime fixtures | E2E/RUNTIME |
| I05 | `recordCoordinates` supports >=1 args, heterogeneous types | E(`print_mixed_arguments`) | I(`print_zero_args`) | E2E/SEM |
| I06 | Printing string literals only; no stored string type | E(`print_literal_utf8`) | I(`declare_string_variable`), I(`pass_string_to_user_function`) | E2E/SYN/SEM |
| I07 | Escapes decode and print as characters; invalid escapes rejected | E(`print_escapes`) | I(`invalid_escape_in_print`) | E2E/LEX |
| I08 | Print object type and fields in DECLARATION order; nested recursion | E(`print_nested_objects`) | I(`print_illegal_type_expression`) | E2E/SEM |
| I09 | Output newline after EVERY print argument, exact stdout | E(`print_separate_lines`) | I(`print_missing_expression`) | E2E/SYN |
| I10 | `recordCoordinates` eval+prints each argument immediately | E(`print_argument_side_effects`) prints `1\ninner\n2\n3\n` | I(`print_wrong_nested_call_type`) | E2E/SEM |
| I11 | i64 print uses correct signed 64-bit format, i32 signed 32-bit | E(`print_large_i64_and_i32`) | I(`print_wrong_argument_count_custom_call`) | E2E/SEM |
| I12 | Variable with builtin name shadows callable builtin | E(`contextual_builtin_name_as_variable`) | I(`builtin_shadowed_by_variable_then_called`) | E2E/SEM |
| I13 | User-defined global spark cannot override builtins | E(`other_user_function_name`) | I(`redefine_builtin_as_spark`) | E2E/SEM |
| I14 | Unicode text is allowed only in strings, not identifiers | E(`print_ukrainian_text`) | Existing `non_latin_identifier` | E2E/REG |

## F. End-to-end baseline (minimum 10; plan 18)

Recommended first 18 E2E sources (all must have exact `.expected` output; append `.in` when indicated):

1. `function_basic` — typed declaration, return, simple print.
2. `nested_function_calls` — nested expression-call arguments.
3. `forward_function_call` — function declared later.
4. `recursive_factorial` — recursion and base branch.
5. `astro_mixed_member_order` — methods and fields interleaved.
6. `constructor_reordered_fields` — named fields order and print order.
7. `nested_field_read` — chained field access.
8. `nested_field_mutable_assignment` — mutable multi-hop assignment.
9. `nonmutating_on_calm` — method call on immutable object.
10. `calm_to_flow_copy_mutable` — value semantics.
11. `same_astro_structural_equality` — recursive equality.
12. `read_two_tokens` **(+ `.in`)** — two reads and print, no echo.
13. `print_mixed_arguments` — i32, i64, bool, UTF-8 literal, object.
14. `print_nested_objects` — exact recursive object representation.
15. `print_argument_side_effects` — output order 1 / inner / 2 / 3.
16. `i64_expected_literal_expression` — expected width semantics.
17. `negative_division_truncation` — signed `sdiv` behavior.
18. `global_statements_in_order` — top-level execution and globals.

## G. Test construction and grading cautions

1. **Do not replace** old fixtures: 22 original valid AST golden tests and 25 original invalid golden tests must pass without changed outputs or positions. New tests are additive.
2. **Treat feedback as a hard regression:** both `☁` and `☁︎` must parse as the same boolean type; comparison of AST output should normalize the spelling to existing `☁︎`.
3. Only **syntactically** erroneous programs should fail `--ast`; semantically invalid examples must be run through full compilation because decision 62A keeps `--ast` syntax-only.
4. Negative compile-time tests have a `NAME.expected` with the **exact one-line error** once implementation defines the stable message; do not fabricate line:column before lexer/parser positions are implemented. Failed compilation leaves no `.ll`.
5. Runtime-invalid tests are **not** counted as compile-time invalid programs: distinguish their `.in`, `.stderr.expected`, and exit status; a runtime `stderr` format is separate from `compilation error: line L:C: message`.
6. Check LLVM IR structural behavior in representative E2E tests: 32/64-bit widths, `if/else` basic blocks and conditional branch, prefixed user function names, forward function declarations, identified struct types and GEP via field indexes, hidden object-pointer argument to method calls, `scanf`/`printf` declarations and global format strings.
7. Every new semantic rule in README should cite at least one valid and one invalid case from this matrix (where a pure behavior/output requirement cannot meaningfully be made a compile-time error, pair an execution oracle with an invalid input/type case).
8. The assignment minimum is **20 valid, 20 invalid total** (including Stage 1), and **at least 10 valid E2E** with one stdin test. The 18 E2E programs above are a recommended target, not yet-created files.
9. Include `ai_usage_2.txt` with exact used tools, prompts/full transcripts, taken/changed code explanation, and own understanding; missing/incomplete disclosure means zero for Stage 2.

## H. Implementation-independent acceptance gates

- **Gate 1 — Stage 1 compatibility:** 47/47 existing tests unchanged, plus both cloud spellings recognized.
- **Gate 2 — grammar/AST:** all Stage 2 constructions parse; AST includes return/parameter types, field mutability, argument lists, and whether a member chain ends in a call.
- **Gate 3 — semantics:** every invalid case reports a controlled one-line compilation error (never a traceback); no output `.ll` is left behind.
- **Gate 4 — LLVM + runtime:** all Stage 1/2 constructs generate IR through the builder; all 18 recommended E2E programs execute and match expected stdout exactly.
- **Gate 5 — submission:** README examples, complete EBNF, test runner, AI usage disclosure, clean repository/PR.

## I. Two unresolved formalization subtleties to track (do not silently change design)

- **Method-call chain via parentheses:** approved 35B forbids further `~` after a member call. Grammar permits parenthesized expressions as atoms, so a checker must reject `(obj ~ method()) ~ field` as well, or the grammar must be refined to disallow that shape. Matrix `parenthesized_method_chain_bypass` tests the agreed intent.
- **Special names and whitespace:** a contextual keyword can be an identifier when not in keyword position, but `core` cannot be declared locally/parametrically in a method. For `~`, ensure lexer whitespace skipping does not erase the byte-level mandatory ASCII spaces; error line:column points to offending `~`.

## J. Practical priority for implementation (matrix rows may share fixtures)

The **94 matrix rows are requirements/coverage checks, NOT a demand for 188 distinct programs**. One carefully designed valid or invalid program may cover several rows, provided each semantic rule remains individually traceable and can be broken by a targeted negative fixture.

**P0 — mandatory before submission:** all 47 Stage 1 golden cases; the two `☁`/`☁︎` positive cases and U+FE0F negative; wrong call arities (too many, too few), wrong argument type, wrong `rise` type, unknown field, immutable chain, mutating-on-calm, wrong constructor fields, direct and indirect mutating effects, correct i32/i64 printf, object format, at least 10 compile-run-compare E2E tests, and at least one `.in` test. Include zero arguments for `recordCoordinates` and invalid `lookThroughTelescope` input.

**P1 — important for the approved extended design:** nested method effects, unsafe global initialization, structural equality, copy semantics, the exact whitespace rule for `~`, constructor evaluation order, full Unicode strings, runtime overflow and full integer-token input validation.

**P2 — implementation hardening:** comprehensive diagnostic position testing for all Unicode variants, rejection of syntax-bypass attempts with nested parentheses, deeper mutual recursion and uncommon lexical errors.

**Audit checklist:** after adding tests, derive a `README` rules-to-test index from this matrix and verify no rule in README lacks a cited passing and failing test. Every `.expected` is produced intentionally as a specification, not copied from an implementation that might be wrong.
