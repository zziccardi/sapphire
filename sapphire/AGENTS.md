# Compiler & Toolchain Guidelines (`sapphire/`)

These rules supplement the root `AGENTS.md` when working on the Sapphire compiler, semantic analyzer, transpilers, and LSP in `sapphire/`.

## 1. Compiler Pipeline

```text
[.sp Source]
     │
     ▼ (ANTLR Lexer & Parser)
[Concrete Parse Tree]
     │
     ▼ (sapphire/parser/ast_builder.py)
[Abstract Syntax Tree (AST)]
     │
     ▼ (sapphire/semantics/type_checker.py, arena_checker.py, generics_checker.py)
[Typed AST, SemanticContext & Symbol Table]
     │
     ▼ (sapphire/code_gen/transpiler_registry.py)
     ├──> Python Transpiler (python_transpiler.py) ──> [.py file]
     ├──> Lua Transpiler (lua_transpiler.py)       ──> [.lua file + .lua.map]
     └──> LLVM Transpiler (llvm_transpiler.py)     ──> [.ll IR]
```

### Extending the Pipeline
* **Adding a target backend**: Decorate your transpiler class with `@TranspilerRegistry.register(aliases=[...], display_name=..., default_extension=...)` in `sapphire/code_gen/`. `BaseTranspiler.__init_subclass__` enforces `@abstractmethod` completeness at class definition time (pass `allow_abstract=True` or inherit `ABC` for intermediate abstract bases).
* **Keeping the toolchain in sync**: When modifying `grammar/Sapphire.g4`:
  1. Regenerate ANTLR files into `sapphire/parser/gen/`:
     ```bash
     pipenv run antlr
     ```
     Ensure all four generated files (`SapphireLexer.py`, `SapphireParser.py`, `SapphireListener.py`, `SapphireVisitor.py`) are updated.
  2. Update `sapphire/parser/ast.py` and `sapphire/parser/ast_builder.py`.
  3. Update `sapphire/semantics/type_checker.py` and `sapphire/semantics/symbol_table.py`.
  4. Update both `sapphire/code_gen/python_transpiler.py` and `sapphire/code_gen/lua_transpiler.py`.
  5. Regenerate the VS Code TextMate grammar via `python3 tools/vscode-extension/scripts/generate_grammar.py`.
  6. Add or update unit tests in `sapphire/` and end-to-end tests in `testing/e2e/`.

## 2. Semantic & Runtime Invariants
* Preserve existing semantic and codegen helpers when adding orthogonal checks rather than rewriting unrelated passes.
* `ASTNode` and all subclasses in `sapphire/parser/ast.py` are `@dataclass(eq=False)` (preserving identity hashing for `dict[ASTNode, Type]` side-tables and exact `to_dict()` snapshots; keep `is_parenthesized` as `field(default=False, init=False, repr=False)`). Verify exact attribute names (`RefType.inner_type`, `OptionalType.base_type`, `SourceSpan`).
* Pass `SemanticContext` explicitly into transpilers and query types via `self.get_inferred_type(node)` instead of `getattr(node, "inferred_type", None)`. Use `BaseTranspiler`'s stackable `OutputBuffer` / `EmitterState` (`scoped_buffer`, `capture_expr`) instead of spawning sub-transpilers.
* Core diagnostics and stable `ErrorCode` constants live in `sapphire/common/diagnostics.py` and `sapphire/common/error_codes.py` — never import `sapphire.cli.*` from parser or semantics modules. In `TypeChecker._make_diagnostic()`, always run `_infer_diagnostic_metadata()` before falling back to `classify_error_code()` so fix-it hints are preserved.
* Follow Sapphire syntax conventions: generic trait impls use `impl Trait for Struct<T>` (never `impl<T>`); never use `new` for constructors or runtime helpers (use `__init__` / `.init`); the built-in string type is capitalized `String`.
* In Python and Lua runtime preambles, `SapphireObject` clones delegate missing lookups to `__proto__`; per-instance lifecycle flags (e.g. `_sapphire_disposed_`) must inspect own storage (`__dict__` / `object.__setattr__` in Python; `rawget`/`rawset` in Lua), and implicit `clone` must inherit the source object's `__arena`.
* In Lua 5.1 codegen and `sapphire/lib/std/*.lua`, never store raw `nil` for Sapphire `none` in tables, `[T?]` arrays, proto overrides, optional struct field overrides, or default-param checks — use the `_SP_NONE` sentinel (`_SP_RT.NONE`) and explicit unpack counts. Never use `a and b or c` as a ternary when `b` can be `false`/`nil`, do not rely on Lua 5.3+ `math.type` or `//`, and keep runtime helpers inside `local _SP_RT = {}` to stay well below Lua 5.1's 200-local limit.
* In `LuaTranspiler`, defer source-map registration in `visit()` via `_pending_source_mapping` and flush on the first non-whitespace `emit()` (after `newline()` has advanced `current_line`/`current_column`) to avoid off-by-one line mappings.
* For RAII values moved into non-constructor, non-intrinsic calls (`consume(move a)`), callers must schedule deterministic teardown via `_record_consumed_call_moves` / `_drain_pending_destroy_moved_vars` before nulling or returning (callees receive scoped borrows and never destroy parameters; CPython GC masks leaks that break Lua 5.1).
* Never mutate AST nodes in place during transpilation, always use lexical scope stacks for nested blocks across all backends (Python, Lua, LLVM), evaluate non-trivial receivers/indices once into temporaries, and capture shadowed host builtins (e.g. `abs`) before defining stdlib functions.
* In `TypeChecker`, `self.moved_symbols` stores `VariableSymbol` instances (not string names); check `sym not in self.moved_symbols and not sym.is_moved`.
* In `sapphire/lsp/`, use `create_server(workspace=...)` rather than a module-level server singleton, convert UTF-16 ↔ Unicode code-point columns at LSP boundaries, treat `end_column` as exclusive, keep semantic tokens strictly non-overlapping, resolve local declarations before globals, never overwrite open workspace buffers from disk, and preserve valid token caches across transient syntax errors.
* Keep `tools/vscode-extension/` compiled as CommonJS (`"module": "node16"` without `"type": "module"`) with `engines.vscode` compatible with `vscode-languageclient`, and keep `tools/vscode-extension/out/` untracked.

## 3. Python Code Quality Standards
* Target Python `>=3.12` with PEP 585/604 annotations (`list[...]`, `dict[...]`, `T | None`), 2-space indent, and ≤ 80-char lines on production code (enforced by `pipenv run lint` with Ruff `["E", "F", "B", "I", "W", "UP"]` and `pipenv run typecheck` with Pyright). Avoid wildcard imports (`import *`) and import-time `sys.path` mutations.
* **Typed mixins**: Use `if TYPE_CHECKING:` host base classes (`_TypeCheckerBase`, `_PythonTranspilerBase`, `_LuaTranspilerBase`) on visitor/emitter mixins. Inherit `_TypeCheckerBase` only on root mixins (`MemberAccessVisitorMixin`, `ControlFlowVisitorMixin`) so subclasses inherit it transitively without MRO conflicts.
* **Module size**: Aim for a soft maximum of ~1,000 lines per non-test implementation file in `sapphire/` (excluding `sapphire/parser/gen/`). Split larger analyzers or transpilers into cohesive mixins/helpers (e.g., `*_visitor.py`, `*_emitter.py`, `*_runtime.py`), re-export public symbols from the original module for backward compatibility, and use `type(self)()` rather than hardcoding the concrete transpiler class inside emitter mixins.
* **Function size & comments**: Aim for soft maximums of ~50–80 lines for standard functions/helpers and ~80–120 lines for AST visitors/dispatchers (splitting multi-responsibility blocks rather than adding `# 1. ...` section banners). Add inline comments for "why, not what": cross-pass AST attributes, ownership/freeze/escape invariants, target-backend asymmetries (e.g. Lua 1-based indexing), and ordering constraints.

## 4. Testing & Verification Standards
* **No test masking via `self.skipTest()`**: Only skip tests if optional prerequisite binaries (e.g. `lua`) are genuinely absent from `PATH`. Never catch runtime errors or non-zero exit codes to call `self.skipTest()`; failures must fail with `self.fail()`.
* **Strict semantic checks**: Never wrap `TypeChecker().check(ast)` in blanket `try...except Exception: pass` in transpiler tests unless testing compile-time rejection.
* **Process & DI isolation**: `run_tests_python()` runs in an isolated subprocess (matching `run_tests_lua()`) — do not mutate `sys.path` or `sys.modules` in-process. Use `TranspilerRegistry.create_isolated()` / `TranspilerRegistry.scoped()` for backend registry tests, and pass `workspace=FakeWorkspace(...)` to `SapphireLanguageServer` / `create_server()` (never mock `ls.protocol._workspace`).
* **Shared test helpers**: Prefer `parse_source()`, `parse_and_check()`, `check_source()`, `TypeCheckerTestBase`, and `FakeWorkspace` from `testing/test_utils.py` over duplicating lexer/parser boilerplate.
* **True backend verification**: Do not rely purely on substring matching. For LLVM IR, verify structural integrity via `llvmlite.binding.parse_assembly(ir).verify()` and assert execution output with MCJIT where feasible.
* **Cross-backend parity**: For every new language feature or stdlib API, run both `pipenv run sapphire test` and `pipenv run sapphire test -t lua`, and add parity tests in `sapphire/code_gen/transpiler_parity_test.py` covering edge values (`none`, `false`, `0`, `NaN`, negative indices, Unicode) plus negative compile-time tests for new semantic rules. In Lua 5.1 differential harnesses comparing `tostring()` output, normalize IEEE-754 `-0.0` (`if _r == 0 then _r = 0 end`).
* **Runnable sample execution**: Non-host-bound scripts in `samples/` must execute cleanly with exit code 0 in `samples_compilation_test.py`.
* **Standard library & negative runtime coverage**: Additions to `sapphire/lib/std/` require unit tests for happy paths and boundary values. Verify runtime safety guards (`.get()` bounds checks, nil coalescing, coroutine exhaustion) in `testing/e2e/negative_runtime_test.sp`.
* **Modular test files & zero-dependency CI tooling**: Add new unit/regression tests to pass- or domain-specific modules (e.g., `type_checker_*_test.py`, `*_visitor_test.py`, `*_emitter_test.py`, `soundness_matrix_test.py`, `diagnostics_golden_test.py`) rather than growing monolithic files. Use `.sp.fixture` (not `.sp`) for intentionally failing CLI fixtures so `sapphire test` workspace discovery skips them. Prefer stdlib-only harnesses (`random.Random`, `ProcessPoolExecutor`, Lua `LUA_INIT` + `debug.sethook`) so CI on Python 3.14/3.15 and bare `lua5.1` stays dependency-free.
* **Targeted coverage runs**: `pipenv run coverage` runs the full `Pipfile` script; for single-file coverage checks, invoke `pipenv run python -m coverage run ...`.
* **Cross-backend integration & verification commands**:
  ```bash
  pipenv run lint && pipenv run typecheck
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

### Transpiler invariants for Python & LuaJIT

* **No statement-level IIFE closures**: Never emit `(function(...) ... end)()`
  in Lua or `(lambda ...)(...)` in Python statement-level expression paths. Both
  `FNEW` (closure creation) and `UCLO` (upvalue close) are NYI in LuaJIT 2.1,
  aborting trace compilation and creating per-iteration GC pressure. Lift `??`,
  `?:`, optional `?.` member/call/intrinsics, optional primitive `as T?` casts,
  and `CloneNode` blocks into straight-line `local` + `if` blocks in Lua and
  walrus/straight-line forms in Python.
* **Shared Lua metatables & direct Python `__dict__`**: Prototype, CoW proxy,
  and smart-ref metatables in `lua_runtime.py` must be shared module-level
  constants keyed by cross-module `_G._SP_K_*` tokens (never allocated per
  instance). In Python, `SapphireObject` stores own fields directly in
  `__dict__` without a custom `__setattr__` hook, and eligible non-proto
  single-inheritance structs emit `__slots__`.
* **Deterministic Python RAII (`_sapphire_destroy`)**: Emit
  `def _sapphire_destroy(self):` (not `def __del__(self):`) on user structs so
  they stay off CPython's GC finalizer queue; reserve `__del__` for runtime
  wrappers (`Arena`, `_SapphireRef`, `_SapphireSharedRef`). Emit diamond
  destruction guards (`_sapphire_destroyed_classes_`) only for structs in
  `_diamond_destructible_structs`.
* **Fixed-arity constructors, optional defaults & unboxed multi-return**: Emit
  fixed-arity `Struct._new(...)` and non-`@export` optional-default functions in
  Lua (padding omitted optional non-`none` defaults with `_SP_RT._SP_UNSET`),
  unbox multi-return `ReturnNode` and multi-yield `MatchExprNode` into multiple
  locals, spill Lua modules exceeding 120 top-level declarations into
  `local _MOD = {}`, and hoist Python coroutine generators (`_sp_gen_*`) to
  module/class scope.
* **Loop-free runtime fast-paths**: Keep hot runtime helpers (`_unwrap_read`,
  `_unwrap_write`) loop-free on the common fast-path
  (`type(obj) ~= "table" or getmetatable(obj) == nil`) and isolate `while` loops
  in `*_slow` helpers so plain tables/arrays/maps never trigger
  `inner loop in root trace` aborts.
* **Native numeric `for` loops (`FORL`) & stateless iterators**: Lower direct
  `for v in range(...)` and `for v in arr` loops to native Lua numeric `for`
  statements rather than allocating closure/table iterators (reserving
  `_SP_RT._sapphire_range` for first-class `Range` values), and keep
  `_SP_RT._sapphire_iter_array` / `_SP_RT._sapphire_iter_map` stateless.
* **Benchmarking**: Run `pipenv run python testing/perf/bench_transpilers.py`
  (`--compare` / `--save-baseline`) to measure Python and LuaJIT runtime and
  `luajit -jv` trace-abort regressions.

