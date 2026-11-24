# AGENTS.md — Sapphire Project Agent Guide

This document is the primary operating guide for AI coding agents working in the **Sapphire** repository.

## 1. Project Overview & Status

**Sapphire** is a statically typed general-purpose programming language combining:
1. Systems-language safety and performance (zero-cost abstractions, monomorphization, deterministic memory).
2. Rapid prototyping ergonomics (opt-in prototypal state delegation, live hot-reloading).
3. Modern expressiveness (Swift-style optionals and `guard` clauses, Python-style f-strings and initializers).

* **Transpiler Toolchain**: Compiles `.sp` files to **Python** (default) or **Lua 5.1** (e.g. Love2D), with an experimental **LLVM IR** generator.
* **Tooling**: Built-in test runner (`sapphire test`), LSP server (`sapphire/lsp`), and VS Code extension (`tools/vscode-extension`).
* **Roadmap**: A native Rust/LLVM compiler is planned once the language specification stabilizes.

## 2. Core Philosophy & Language Non-Negotiables

When authoring Sapphire code or extending the compiler, always uphold these invariants:

* **Zero-vtable polymorphism by default**: Standard structs use syntactic delegation (composition + forwarding) and traits use compile-time monomorphization / closed tagged unions. Vtables are strictly isolated to `Dynamic<Trait>`.
* **No struct up-casting**: `Child as Parent` is prohibited to prevent object slicing.
* **Scope-bound memory safety**: Non-primitives pass by constant reference by default; mutable parameters require `var`. Call-site aliasing checks prevent data corruption without lifetime annotations.
* **Deterministic resource management**: Structs support LIFO RAII via `__del__()` (making them move-only, with RVO). Dynamic prototypes (`proto` / `clone`) reside in lexically scoped `Arena`s with escape checking and copy-on-write on nested reference mutations.
* **No throwable exceptions**: No `try`/`catch`/`throw`; use optionals (`T?`), multiple return values, `guard`, and `match`.
* **Formatting & module rules**: Max 80 chars per line, 2-space indent, explicit semicolons (`;`) on all statements (except `export { ... }` manifest blocks), no executable procedural statements at module scope.

For full syntax, types, and Love2D bindings, consult the `sapphire-lang` skill (`.agents/skills/sapphire-lang/SKILL.md`) and [`docs/SPEC.md`](docs/SPEC.md).

## 3. Repository & Documentation Map

* `grammar/Sapphire.g4` — ANTLR4 grammar specification.
* `sapphire/` — Compiler, AST, semantic analyzer, transpilers, CLI, and LSP (see `sapphire/AGENTS.md` and [`docs/compiler.md`](docs/compiler.md)).
* `sapphire/lib/` — Sapphire standard library (`sapphire/lib/std/`) and Love2D bindings (`sapphire/lib/love2d/`).
* `samples/` & `testing/` — Sample programs and cross-backend E2E tests.
* `docs/` — Language docs ([`SPEC.md`](docs/SPEC.md), [`style_guide.md`](docs/style_guide.md), [`development.md`](docs/development.md), [`builtins.md`](docs/builtins.md), [`testing.md`](docs/testing.md), [`docs/AGENTS.md`](docs/AGENTS.md)).
* `web/` — Astro documentation & playground site ([`web/AGENTS.md`](web/AGENTS.md)).

## 4. Essential Commands

```bash
# Run Python compiler/LSP unit tests (serial or parallel)
pipenv run test
pipenv run test-fast

# Lint & coverage (Python statement+branch gate and Lua stdlib report)
pipenv run lint
pipenv run coverage
pipenv run coverage-lua

# Run native Sapphire tests (Python & Lua 5.1)
pipenv run sapphire test
pipenv run sapphire test -t lua

# Type-check a Sapphire file and transitive imports
pipenv run sapphire check samples/overview.sp -t lua --json

# Transpile & execute a Sapphire program
pipenv run sapphire samples/overview.sp
pipenv run sapphire samples/overview.sp -t lua
```

## 5. General Agent Guardrails

* **Preserve documentation & comments**: Do not delete or mangle docstrings, inline architectural comments, or existing specs. Update `docs/SPEC.md`, `docs/compiler.md`, or `docs/builtins.md` when modifying language semantics or built-ins.
* **Markdown conventions**: Keep lines ≤ 80 characters (except links), use sentence case for headings, avoid horizontal rules (`---`), and ensure any edited complete Sapphire sample in Markdown compiles cleanly.
* **Phased planning**: For cross-cutting compiler or specification initiatives spanning multiple subsystems, structure plans into small, independently testable phases and pause after each phase for review unless asked to run continuously.
* **Pre-Completion Checklist**:
  * [ ] `pipenv run test` passes with zero failures, zero errors, and no unexpected skipped tests.
  * [ ] Affected e2e/integration tests pass across all relevant backends.
  * [ ] Any edited complete Sapphire sample code in Markdown files compiles correctly.
  * [ ] Newly created files adhere to repository naming and layout conventions.

## 6. Planning (`/plan`)

Whenever `/plan` is used, always generate the plan as an artifact rather than outputting it only inline in chat.
