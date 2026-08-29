# Sapphire programming language

Sapphire is a statically typed general-purpose programming language that
combines the **safety and performance** of modern systems languages with the
**rapid-prototyping ergonomics** of dynamic languages.

By resolving polymorphism at compile time and restricting prototypal inheritance
to be data-only, Sapphire enables runtime object modification without
virtual-method tables, reference-cycle overhead, or lifetime annotations.

This repository contains the ANTLR4 grammar, abstract syntax tree (AST) builder,
semantic analyzer, type checker, transpilation backends that compile Sapphire
source code (`.sp`) into executable Python or Lua 5.1, a built-in testing
runner, a Language Server Protocol (LSP) server, and a VS Code extension.

The project is a **work in progress**. The [language spec](docs/SPEC.md) may
change significantly over time. For now the transpiler toolchain targets Python
and Lua 5.1 to facilitate rapid iteration and scripting-engine integration; once
the language design is finalized, I'd like to introduce a proper native compiler
(likely built in Rust) to enable the memory-safety and performance features
described in the spec.

## Key features of Sapphire

### Dual-paradigm code reuse
* **Traits**: Traits define interfaces/contracts (`trait Damageable`) that are
  statically checked and dispatched.
* **Structural delegation**: Structs can "inherit" layouts statically
  (`struct Character: Entity`) without runtime overhead or traditional OOP
  boilerplate. The compiler treats this as syntactic sugar for composition and
  automatically generates forwarding methods.
* **Prototypal delegation**: Prototypal delegation is opt-in and uses
  the `proto` keyword (e.g. `proto Character`). Runtime objects can be created
  by cloning existing prototypes using the `clone` keyword.
  * Nested reference fields on cloned objects support **copy-on-write (CoW)** to
    isolate mutations from the shared prototype.
  * All `proto` instances and their clones are automatically managed in arenas
    (supporting both implicit default arenas and explicit RAII-style arenas).

### Optional & reference safety
* Null-pointer errors are prevented at compile time.
* Optionals are denoted by a `?` suffix (e.g., `Character?`).
* Optionals can be chained safely (`let speed = target?.speed`).
* Optionals can be conditionally unwrapped (`let x ?= optional`) within
  Go/C++17-style init statements in `if` and `while` headers.
* Nil-coalescing fallback values are supported via the `??` operator.
* Compile-time aliasing rules enforce reference safety without requiring
  lifetime annotations.

### Reference semantics & parameter modes
* Non-primitive types are passed by **constant reference** by default, avoiding
  reference-cycle overhead and a visual pointer syntax.
* Mutable parameters must be explicitly marked with `var` in function signatures
  (e.g., `func update(var target: Character)`).
* Named parameters are supported at the call site using `=`
  (e.g., `execute_strike(bonus = 10)`); functions can also specify default
  parameter values in their signatures.

### Zero-overhead generics
* Type-parameterized structs, implementation blocks, traits, and functions
  (`struct Stack<T>`, `func identity<T>`).
* Resolved at compile-time via **monomorphization** with automatic call-site
  type inference and explicit type arguments (`Stack<int>`).

### First-class coroutines & generators
* Steppable coroutines via `Coroutine<T>` and `Coroutine<void>`.
* Bare `yield;` for sequencing; `yield <expr>;` for value streams.
* Step, inspect, or reset coroutines with `.step(): T?`, `.is_done(): bool`, and `.reset(): void`.
* Transpiles to zero-allocation native Lua asymmetric coroutines on Lua/Love2D targets and generator objects on Python.

### Host engine, Love2D & live hot-reloading
* Native interoperation with host runtimes (such as **Love2D** in Lua 5.1 /
  LuaJIT environments).
* Direct Love2D target support via `-t love2d` (or `-t love`).
* **Live hot-reloading & dev mode (`sapphire run --dev`)**: Automatically watches `.sp` project files, performs fast incremental re-compilation, patches existing living prototype/struct instances in-place without losing state, and executes `@on_reload` lifecycle hooks.
* `@extern var love: LoveEngine;` binds host runtime global variables with 100%
  type safety.
* `@export("love.update") func update(dt: float)` exposes functions directly as
  global engine callbacks (`function love.update(dt)`).
* Combines traits and structs to model external host APIs without runtime
  performance penalties.
* **Source maps & Love2D error demangling**: Automatically generates standard
  [source map v3](https://tc39.es/ecma426/) files (`.lua.map`) and embeds
  runtime stack-trace demanglers. When a runtime error occurs in Love2D, both
  the terminal and Love2D error screen display original Sapphire `.sp`
  filenames, line numbers, and source line snippets.

## CLI overview

```bash
# Run a Sapphire script (transpiling to Python by default):
sapphire samples/overview.sp

# Run with live hot-reloading / dev mode (watches files and reloads in-place):
sapphire run samples/overview.sp --dev

# Transpile to Lua 5.1 (generating both main.lua and main.lua.map source maps by
# default):
sapphire build samples/love2d_demo.sp -t lua -o main.lua

# Build for release without source map or runtime demangler:
sapphire build samples/love2d_demo.sp -t lua -o main.lua --no_sourcemap

# Run transpiled game in Love2D (passing the directory containing `main.lua`):
love .

# Run a Love2D game directly with live hot-reloading:
sapphire run samples/love2d_demo.sp -t love2d -o main.lua --dev

# Run native test suites:
sapphire test
```

## Repository structure

* `docs/`: Core documentation including the [language spec](docs/SPEC.md),
  [compiler architecture](docs/compiler.md),
  [development guide](docs/development.md), [builtins](docs/builtins.md), and
  [testing guide](docs/testing.md).
* `grammar/`: ANTLR4 grammar specification (`Sapphire.g4`).
* `lib/`: Sapphire standard library (`lib/std/`) and host-engine bindings
  (`lib/love2d/`).
* `samples/`: Example scripts demonstrating core language features.
* `src/`: Compiler pipeline and tooling:
  * `cli/`: Unified `sapphire` CLI entry point (`sapphire.py`) and test runner
    (`test_runner.py`).
  * `common/`: Domain exception hierarchy (`errors.py`).
  * `parser/`: AST definitions (`ast.py`), visitor builder (`ast_builder.py`),
     centralized error listener (`error_listener.py`), and ANTLR-generated
     parser.
  * `semantics/`: Symbol tables (`symbol_table.py`), type checker
    (`type_checker.py`), arena memory checks (`arena_checker.py`), and generic
    substitution helpers (`generics_checker.py`).
  * `code_gen/`: Transpiler driver (`transpiler.py`), target backend registry
    (`transpiler_registry.py`), Python generator (`python_transpiler.py`),
    Lua 5.1 generator (`lua_transpiler.py`), experimental LLVM IR generator
    (`llvm_transpiler.py`), and source-map generator (`source_map.py`).
  * `lsp/`: Language Server Protocol (LSP) server providing diagnostics,
    autocompletion, hover info, and semantic tokens.
* `testing/`: Test suite runner, integration-test fixtures
  (`testing/fixtures/`), and test utilities (`test_utils.py`).
* `tools/`: Development tools including the
  [VS Code extension](tools/vscode-extension/).
