# Sapphire programming language

Sapphire is a statically typed general-purpose programming language that
combines the **safety and performance** of modern systems languages with the
**rapid-prototyping ergonomics** of dynamic languages.

By resolving polymorphism at compile-time and restricting prototypal inheritance
to be data-only, it enables runtime object modification without virtual-method
tables, reference-cycle overhead, or lifetime annotations.

This repository contains the ANTLR4 grammar, abstract syntax tree (AST) builder,
semantic analyzer, type checker, transpilation backends that compile Sapphire
source code (`.sp`) into executable Python or Lua 5.1, as well as a Language
Server Protocol (LSP) server implementation and corresponding VS Code extension.

The project is a **work in progress**. The [language spec](docs/SPEC.md) may
change significantly over time. For now the transpiler toolchain targets Python
and Lua 5.1 to facilitate rapid iteration and scripting-engine integration; once
the language design is finalized, I'd like to introduce a proper native compiler
(likely built in Rust) to enable the memory-safety the performance features
described in the spec.

## Key features of Sapphire

### 1. Dual-paradigm code reuse
* **Traits**: Define interfaces/contracts (`trait Damageable`) that are
  statically checked and dispatched.
* **Static inheritance**: Structures can inherit layouts statically
  (`struct Character: Entity`) without runtime overhead or traditional OOP
  boilerplate.
* **Prototypal delegation**: Prototypal delegation is opt-in and uses
  the `proto` keyword (e.g. `proto Character`). Runtime objects can be created
  by cloning existing prototypes using the `clone` keyword.
  * Nested reference fields on cloned objects support **copy-on-write (CoW)** to
    isolate mutations from the shared prototype.
  * All `proto` instances and their clones are automatically managed in arenas
    (supporting both implicit default arenas and explicit RAII-style arenas).

### 2. Optional safety
* Null-pointer errors are prevented at compile time.
* Optionals are denoted by a `?` suffix (e.g., `Character?`).
* Optionals can be chained safely (`let speed = target?.speed`).
* Conditional unwrapping (`let x ?= optional`) and Go/C++17-style init statements within loop headers are supported.
* Nil-coalescing fallback values are supported via the `??` operator.

### 3. Advanced parameter modes
* Non-primitive types are passed by **constant reference** by default, avoiding
  reference-cycle overhead and a visual pointer syntax.
* Explicit mutable references are marked with `var` in parameters (e.g.,
  `func update(var target: Character)`).
* Native support for named and default parameters at the call site using `=`
  (e.g., `execute_strike(bonus = 10)`).

### 4. First-class functions & closures
* Support for block and single-expression lambda syntax (e.g., `x -> x * 2`).
* Bidirectional type inference resolves lambda parameters automatically based on
  expected types at assignment or call sites.

### 5. Scope-bound reference safety
* Enforces compile-time aliasing rules to prevent simultaneous mutable reference
  borrows without needing lifetime annotations.

### 6. Host engine & third-party interoperability
* Native interoperation with host runtimes (such as **Love2D** in Lua 5.1 / LuaJIT environments).
* `@extern var love: LoveEngine;` binds host runtime global variables with 100% type safety.
* `@export("love.update") func update(dt: float)` exposes functions directly as global engine callbacks (`function love.update(dt)`).
* Combines Sapphire `trait`s and `struct`s to model external host APIs without runtime performance penalties.
* **Source maps & Love2D error demangling**: Automatically generates standard [source map v3](https://tc39.es/ecma426/) files (`.lua.map`) and embeds runtime stack-trace demanglers. When a runtime error occurs in Love2D, both the terminal and Love2D error screen display original Sapphire `.sp` filenames, line numbers, and source line snippets.

## CLI overview
```bash
# Run a Sapphire script (transpiling to Python by default):
sapphire samples/overview.sp

# Transpile to Lua 5.1 (generating both main.lua and main.lua.map source maps by
# default):
sapphire build samples/love2d_demo.sp -t lua -o main.lua

# Build for release without source-map sidecars or runtime demanglers:
sapphire build samples/love2d_demo.sp -t lua -o main.lua --no_sourcemap

# Run transpiled game in Love2D (pass the directory containing `main.lua`):
love .
```

## Repository structure

* `docs/`
  * [SPEC.md](docs/SPEC.md): Deep dive language-design specification.
  * [compiler.md](docs/compiler.md): Comprehensive compiler pipeline and
    architectural documentation.
  * [development.md](docs/development.md): Instructions for parsing, testing,
    and developing Sapphire.
* `grammar/`: ANTLR4 grammar specification (`Sapphire.g4`).
* `samples/`: Code examples demonstrating all core language features in action.
* `src/`
  * `parser/`: AST definitions (`ast.py`) and the visitor that builds the AST
    (`ast_builder.py`).
  * `semantics/`: Scope management, symbol tables (`symbol_table.py`), and
    compiler type-checking rules (`type_checker.py`).
  * `code_gen/`: Transpiler logic for Python (`python_transpiler.py`) and Lua 5.1 (`lua_transpiler.py`), driver facade (`transpiler.py`), and runtime headers.
  * `lsp/`: Language Server Protocol (LSP) server implementation providing
    diagnostics, semantic tokens, hover info, and member autocompletion.
  * `cli/sapphire.py`: Unified CLI entry point (`build`, `run`).
  * `run_transpiler.py`: Script wrapper to compile `.sp` source files to Python or Lua.
* `tools/`
  * `vscode-extension/`: VS Code extension for Sapphire language support (syntax
    highlighting and LSP integration).
