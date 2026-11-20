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
  5. Add or update unit tests in `src/` and end-to-end tests in `testing/e2e/`.

## 2. Semantic & Runtime Invariants
* Preserve existing semantic and codegen helpers when adding orthogonal checks rather than rewriting unrelated passes.
* Verify exact `ASTNode`/`Type` attribute names (`RefType.inner_type`, `OptionalType.base_type`) in `src/parser/ast.py` and `src/semantics/symbol_table.py`.
* In Python and Lua runtime preambles, `SapphireObject` clones delegate missing lookups to `__proto__`; per-instance lifecycle flags (e.g. `_sapphire_disposed_`) must inspect own storage (`__dict__` / `object.__setattr__` in Python; `rawget`/`rawset` in Lua), and implicit `clone` must inherit the source object's `__arena`.
* In `TypeChecker`, `self.moved_symbols` stores `VariableSymbol` instances (not string names); check `sym not in self.moved_symbols and not sym.is_moved`.

## 3. Python Code Quality Standards
* Follow the Google Python Style Guide rather than PEP 8, maintain 2-space or 4-space consistency with surrounding files, and include explicit type annotations where appropriate.
* **Module size**: Aim for a soft maximum of ~1,000 lines per non-test implementation file in `src/` (excluding `src/parser/gen/`). Split larger analyzers or transpilers into cohesive mixins/helpers (e.g., `*_visitor.py`, `*_emitter.py`, `*_runtime.py`), re-export public symbols from the original module for backward compatibility, and use `type(self)()` rather than hardcoding the concrete transpiler class inside emitter mixins.
* **Function size & comments**: Aim for soft maximums of ~50–80 lines for standard functions/helpers and ~80–120 lines for AST visitors/dispatchers (splitting multi-responsibility blocks rather than adding `# 1. ...` section banners). Add inline comments for "why, not what": cross-pass AST attributes, ownership/freeze/escape invariants, target-backend asymmetries (e.g. Lua 1-based indexing), and ordering constraints.

## 4. Testing & Verification Standards
* **No test masking via `self.skipTest()`**: Only skip tests if optional prerequisite binaries (e.g. `lua`) are genuinely absent from `PATH`. Never catch runtime errors or non-zero exit codes to call `self.skipTest()`; failures must fail with `self.fail()`.
* **Strict semantic checks**: Never wrap `TypeChecker().check(ast)` in blanket `try...except Exception: pass` in transpiler tests unless testing compile-time rejection.
* **True backend verification**: Do not rely purely on substring matching. For LLVM IR, verify structural integrity via `llvmlite.binding.parse_assembly(ir).verify()` and assert execution output with MCJIT where feasible.
* **Runnable sample execution**: Non-host-bound scripts in `samples/` must execute cleanly with exit code 0 in `samples_compilation_test.py`.
* **Standard library & negative runtime coverage**: Additions to `lib/std/` require unit tests for happy paths and boundary values. Verify runtime safety guards (`.get()` bounds checks, nil coalescing, coroutine exhaustion) in `testing/e2e/negative_runtime_test.sp`.
* **Cross-backend integration commands**:
  ```bash
  pipenv run python -m unittest src/code_gen/python_transpiler_test.py
  pipenv run python -m unittest src/code_gen/lua_transpiler_test.py
  ```
