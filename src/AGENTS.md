# Compiler & Toolchain Guidelines (`src/`)

These rules supplement the root `AGENTS.md` when working on the Sapphire compiler, semantic analyzer, transpilers, and LSP in `src/`.

## 1. Compiler Pipeline

```text
[.sp Source]
     │
     ▼ (ANTLR Lexer & Parser)
[Concrete Parse Tree]
     │
     ▼ (src/parser/ast_builder.py)
[Abstract Syntax Tree (AST)]
     │
     ▼ (src/semantics/type_checker.py, arena_checker.py, generics_checker.py)
[Typed AST & Symbol Table]
     │
     ▼ (src/code_gen/transpiler_registry.py)
     ├──> Python Transpiler (python_transpiler.py) ──> [.py file]
     ├──> Lua Transpiler (lua_transpiler.py)       ──> [.lua file + .lua.map]
     └──> LLVM Transpiler (llvm_transpiler.py)     ──> [.ll IR]
```

### Extending the Pipeline
* **Adding a target backend**: Decorate your transpiler class with `@TranspilerRegistry.register(aliases=[...], display_name=..., default_extension=...)` in `src/code_gen/`.
* **Keeping the toolchain in sync**: When modifying `grammar/Sapphire.g4`:
  1. Regenerate ANTLR files into `src/parser/gen/`:
     ```bash
     antlr -Dlanguage=Python3 -visitor -o src/parser/gen -Xexact-output-dir grammar/Sapphire.g4
     ```
     Ensure all four generated files (`SapphireLexer.py`, `SapphireParser.py`, `SapphireListener.py`, `SapphireVisitor.py`) are updated.
  2. Update `src/parser/ast.py` and `src/parser/ast_builder.py`.
  3. Update `src/semantics/type_checker.py` and `src/semantics/symbol_table.py`.
  4. Update both `src/code_gen/python_transpiler.py` and `src/code_gen/lua_transpiler.py`.
  5. Regenerate the VS Code TextMate grammar via `python3 tools/vscode-extension/scripts/generate_grammar.py`.
  6. Add or update unit tests in `src/` and end-to-end tests in `testing/e2e/`.

## 2. Semantic & Runtime Invariants
* Preserve existing semantic and codegen helpers when adding orthogonal checks rather than rewriting unrelated passes.
* Verify exact `ASTNode`/`Type` attribute names (`RefType.inner_type`, `OptionalType.base_type`) in `src/parser/ast.py` and `src/semantics/symbol_table.py`.
* Follow Sapphire syntax conventions: generic trait impls use `impl Trait for Struct<T>` (never `impl<T>`); never use `new` for constructors or runtime helpers (use `__init__` / `.init`); the built-in string type is capitalized `String`.
* In Python and Lua runtime preambles, `SapphireObject` clones delegate missing lookups to `__proto__`; per-instance lifecycle flags (e.g. `_sapphire_disposed_`) must inspect own storage (`__dict__` / `object.__setattr__` in Python; `rawget`/`rawset` in Lua), and implicit `clone` must inherit the source object's `__arena`.
* In Lua 5.1 codegen and `lib/std/*.lua`, never store raw `nil` for Sapphire `none` in tables, `[T?]` arrays, proto overrides, optional struct field overrides, or default-param checks — use the `_SP_NONE` sentinel (`_SP_RT.NONE`) and explicit unpack counts. Never use `a and b or c` as a ternary when `b` can be `false`/`nil`, do not rely on Lua 5.3+ `math.type` or `//`, and keep runtime helpers inside `local _SP_RT = {}` to stay well below Lua 5.1's 200-local limit.
* In `LuaTranspiler`, defer source-map registration in `visit()` via `_pending_source_mapping` and flush on the first non-whitespace `emit()` (after `newline()` has advanced `current_line`/`current_column`) to avoid off-by-one line mappings.
* For RAII values moved into non-constructor, non-intrinsic calls (`consume(move a)`), callers must schedule deterministic teardown via `_record_consumed_call_moves` / `_drain_pending_destroy_moved_vars` before nulling or returning (callees receive scoped borrows and never destroy parameters; CPython GC masks leaks that break Lua 5.1).
* Never mutate AST nodes in place during transpilation, always use lexical scope stacks for nested blocks across all backends (Python, Lua, LLVM), evaluate non-trivial receivers/indices once into temporaries, and capture shadowed host builtins (e.g. `abs`) before defining stdlib functions.
* In `TypeChecker`, `self.moved_symbols` stores `VariableSymbol` instances (not string names); check `sym not in self.moved_symbols and not sym.is_moved`.
* In `src/lsp/`, convert UTF-16 ↔ Unicode code-point columns at LSP boundaries, treat `end_column` as exclusive, keep semantic tokens strictly non-overlapping, resolve local declarations before globals, never overwrite open workspace buffers from disk, and preserve valid token caches across transient syntax errors.
* Keep `tools/vscode-extension/` compiled as CommonJS (`"module": "node16"` without `"type": "module"`) with `engines.vscode` compatible with `vscode-languageclient`.

## 3. Python Code Quality Standards
* Follow the Google Python Style Guide rather than PEP 8, maintain 2-space or 4-space consistency with surrounding files, and include explicit type annotations where appropriate.
* **Module size**: Aim for a soft maximum of ~1,000 lines per non-test implementation file in `src/` (excluding `src/parser/gen/`). Split larger analyzers or transpilers into cohesive mixins/helpers (e.g., `*_visitor.py`, `*_emitter.py`, `*_runtime.py`), re-export public symbols from the original module for backward compatibility, and use `type(self)()` rather than hardcoding the concrete transpiler class inside emitter mixins.
* **Function size & comments**: Aim for soft maximums of ~50–80 lines for standard functions/helpers and ~80–120 lines for AST visitors/dispatchers (splitting multi-responsibility blocks rather than adding `# 1. ...` section banners). Add inline comments for "why, not what": cross-pass AST attributes, ownership/freeze/escape invariants, target-backend asymmetries (e.g. Lua 1-based indexing), and ordering constraints.

## 4. Testing & Verification Standards
* **No test masking via `self.skipTest()`**: Only skip tests if optional prerequisite binaries (e.g. `lua`) are genuinely absent from `PATH`. Never catch runtime errors or non-zero exit codes to call `self.skipTest()`; failures must fail with `self.fail()`.
* **Strict semantic checks**: Never wrap `TypeChecker().check(ast)` in blanket `try...except Exception: pass` in transpiler tests unless testing compile-time rejection.
* **True backend verification**: Do not rely purely on substring matching. For LLVM IR, verify structural integrity via `llvmlite.binding.parse_assembly(ir).verify()` and assert execution output with MCJIT where feasible.
* **Cross-backend parity**: For every new language feature or stdlib API, run both `pipenv run sapphire test` and `pipenv run sapphire test -t lua`, and add parity tests in `src/code_gen/transpiler_parity_test.py` covering edge values (`none`, `false`, `0`, `NaN`, negative indices, Unicode) plus negative compile-time tests for new semantic rules. In Lua 5.1 differential harnesses comparing `tostring()` output, normalize IEEE-754 `-0.0` (`if _r == 0 then _r = 0 end`).
* **Runnable sample execution**: Non-host-bound scripts in `samples/` must execute cleanly with exit code 0 in `samples_compilation_test.py`.
* **Standard library & negative runtime coverage**: Additions to `lib/std/` require unit tests for happy paths and boundary values. Verify runtime safety guards (`.get()` bounds checks, nil coalescing, coroutine exhaustion) in `testing/e2e/negative_runtime_test.sp`.
* **Modular test files & zero-dependency CI tooling**: Add new unit/regression tests to pass-specific modules (e.g., `*_visitor_test.py`, `*_emitter_test.py`, `soundness_matrix_test.py`, `diagnostics_golden_test.py`) rather than growing monolithic files (`type_checker_test.py`, `python_transpiler_test.py`, `lua_transpiler_test.py`). Use `.sp.fixture` (not `.sp`) for intentionally failing CLI fixtures so `sapphire test` workspace discovery skips them. Prefer stdlib-only harnesses (`random.Random`, `ProcessPoolExecutor`, Lua `LUA_INIT` + `debug.sethook`) so CI on Python 3.14/3.15 and bare `lua5.1` stays dependency-free.
* **Targeted coverage runs**: `pipenv run coverage` runs the full `Pipfile` script; for single-file coverage checks, invoke `pipenv run python -m coverage run ...`.
* **Cross-backend integration & verification commands**:
  ```bash
  pipenv run test-fast
  pipenv run coverage && pipenv run coverage-lua
  pipenv run sapphire test && pipenv run sapphire test -t lua
  ```

## 5. LuaJIT codegen & profiling guidelines

### Profiling LuaJIT & Love2D
* Use `luajit -jp=vlF` (`jit.p`) to inspect VM states (`Compiled`, `Interpreted`, `C code`, `GC`) alongside per-line hotspot percentages.
* Use `luajit -jv` (`jit.v`) to identify trace compilation aborts (such as `NYI: bytecode FNEW`, `NYI: bytecode UCLO`, or `inner loop in root trace`) and `luajit -jdump` when inspecting IR/mcode for a specific hot trace.
* Time hot paths with `love.timer.getTime()` in Love2D or LuaJIT FFI `clock_gettime(CLOCK_MONOTONIC)` in headless `luajit` benchmarks.
* Never use `debug.sethook` when profiling JIT-compiled code: Lua debug hooks disable or abort LuaJIT trace compilation, skewing measurements toward interpreter overhead.

### Transpiler invariants for LuaJIT
* **No statement-level IIFE closures**: Never emit `(function(...) ... end)()` in statement-level expression paths. Both `FNEW` (closure creation) and `UCLO` (upvalue close) are NYI in LuaJIT 2.1, aborting trace compilation and creating per-iteration GC pressure. Lift `??`, `?:`, optional `?.` member/call/intrinsics, and optional primitive `as T?` casts into straight-line `local` + `if` blocks via `_lift_match_expressions` (keeping IIFE emitters only as fallbacks for non-statement contexts).
* **Loop-free runtime fast-paths**: Keep hot runtime helpers (`_unwrap_read`, `_unwrap_write`) loop-free on the common fast-path (`type(obj) ~= "table" or getmetatable(obj) == nil`) and isolate `while` loops in `*_slow` helpers so plain tables/arrays/maps never trigger `inner loop in root trace` aborts.
* **Native numeric `for` loops (`FORL`)**: Lower direct `for v in range(...)` loops to native Lua numeric `for` statements rather than allocating closure/table iterators (reserving `_SP_RT._sapphire_range` for first-class `Range` values).

