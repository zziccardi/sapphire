# AGENTS.md — Sapphire Project Agent Guide

This document serves as the primary technical reference and operating guide for AI coding agents working in the **Sapphire** repository. It summarizes the language specification, compiler and toolchain architecture, testing conventions, and engineering workflows.

## 1. Project Overview & Mission

**Sapphire** is a statically typed general-purpose programming language designed to combine:
1. The **safety and bare-metal performance** of systems languages (zero-cost abstractions, monomorphization, deterministic memory).
2. The **rapid prototyping ergonomics** of dynamic languages (opt-in prototypal state delegation, live hot-reloading).
3. The **clarity and expressiveness** of modern languages (Swift-style optionals and guard clauses, Python-style f-strings and initializers).

### Current Status
* **Transpiler Toolchain**: Compiles Sapphire source code (`.sp`) into executable **Python** (default) or **Lua 5.1** (e.g., for **Love2D** game development), with an experimental **LLVM IR** generator for native lowering.
* **Tooling**: Built-in test runner (`sapphire test`), Language Server Protocol (LSP) server (`src/lsp`), and VS Code extension (`tools/vscode-extension`).
* **Roadmap**: Once the language specification stabilizes, a native compiler (planned in Rust/LLVM) will replace the transpilation layer to enforce physical arena guarantees and machine-level performance.

## 2. Core Philosophy & Design Pillars

When generating or modifying Sapphire code, or extending the compiler, always uphold these core pillars:

* **Zero-vtable polymorphism**: Virtual method tables (vtables) are eliminated entirely.
  * Static code reuse uses **syntactic delegation** (composition + compiler-generated forwarding), resolving calls directly at compile time.
  * Behavioral polymorphism is offloaded to **traits** via compile-time monomorphization and compiler-synthesized tagged unions.
  * Prototypal inheritance (`proto` / `clone`) delegates **data only**; methods remain statically dispatched.
* **No struct up-casting**: Statically inherited structs cannot be up-cast to parent types (e.g. `Child as Parent` is prohibited). This prevents object slicing and dispatch ambiguities.
* **Scope-bound memory safety**: Non-primitive types are passed by **constant reference** by default. Call-site reference exclusivity (aliasing rules) eliminates data corruption without lifetime annotations.
* **Deterministic resource management**: Structs support deterministic RAII via `__del__()` destructors with Return-Value Optimization (RVO) copy elision. Dynamic prototypes and managed objects reside in explicit, lexically scoped `Arena`s with escape-checking.
* **No throwable exceptions**: Control flow does not use `try`/`catch`/`throw`. Errors are handled via optionals (`T?`), multiple return values (`T, bool`), or tagged result patterns with `guard` and `match`.

## 3. Sapphire Language Specification & Key Syntax

All Sapphire code files (`.sp`) must strictly adhere to the specification in [`docs/SPEC.md`](docs/SPEC.md).

### 3.1 Style & Formatting Rules
* **Line length**: Maximum 80 characters.
* **Indentation**: 2 spaces for block bodies; 4 spaces for continuation lines; parameter continuations align with opening parenthesis.
* **Statement termination**: Every statement must end with an explicit semicolon (`;`).
* **Naming conventions**:
  * Variables, functions, methods, built-ins: `snake_case`.
  * Types (`struct`, `proto`, `trait`, built-in non-primitives): `PascalCase`.
  * Primitive types: `lowercase` (`int`, `float`, `bool`, `none`, `void`).
  * Global/compile-time constants: `SCREAMING_SNAKE_CASE`.
  * Enum variants: `PascalCase` or `SCREAMING_SNAKE_CASE`.
  * Identifiers share a single namespace per scope (a struct and function cannot share a name).

### 3.2 Memory Semantics & Variables
* `let`: Immutable binding (constant).
* `var`: Mutable binding.
* **Types & Passing**:
  * Primitive scalar types (`int`, `float`, `bool`, `none`) are passed by **value**.
  * Reference types (`String`, `Array`, `Map`, `Arena`, `Range`, and all `struct` and `proto` types) are passed by **constant reference** by default.
  * Mutable parameters must be explicitly declared with `var` in signatures: `func update(var target: Entity)`. Callers cannot pass `let` constants to `var` parameters.
* **Call-site reference exclusivity**: A reference cannot be passed mutably (`var`) if it is also passed (mutably or immutably) elsewhere in the same function call.

### 3.3 Optionals & Unwrapping
* Optionals are denoted by `?` (e.g. `int?`, `Player?`). Null is represented as `none`.
* **Safe Unwrapping**: `if let target ?= optional_val { ... }`.
* **Init Statements**: Semicolon-delimited initialization in `if` and `while`: `if let x ?= get_val(); x > 10 { ... }`.
* **Nil-coalescing**: `let val = opt ?? default_val;`.
* **Optional chaining**: `let name = target?.get_name();`.
* **Guard statement**:
  ```sapphire
  guard let user ?= users[id]; user.is_active else {
    return -1;
  }
  // user is promoted to outer scope as non-optional User
  ```

### 3.4 Resource Cleanup (`with` & `__del__`)
* `with` statement: Deterministic LIFO teardown for RAII resources defining `__del__` (or `Arena`):
  ```sapphire
  with let src ?= open_file("a.txt", "r");
       let dst ?= open_file("b.txt", "w") {
    dst.write(src.read());
  } else {
    print("Failed to open files");
  }
  ```
* Struct destructors: Defined as `func __del__()` inside `impl` blocks. Automatically executed LIFO on scope exit or early return, elided upon RVO value returns.

### 3.5 Functions, Closures & Coroutines
* Named parameters: `attack(bonus = 10, target = enemy)`.
* Default parameters: `func attack(target: Entity, bonus: int = 0)`.
* Multiple returns: `func pos(): float, float { return x, y; }` with destructuring `let x, y = pos();`.
* Lambdas: Single parameter shorthand `numbers.map(x -> x * 2)` or multi-param `(a: int, b: int) -> int { return a + b; }`.
* Coroutines: Declared with `Coroutine<T>` or `Coroutine<void>`. Use `yield;` or `yield <expr>;`. Stepped via `.step()`, `.is_done()`, `.reset()`.

### 3.6 Structs & Implementation Blocks
* Data definition (`struct`) and method implementation (`impl`) must be strictly separated:
  ```sapphire
  struct Weapon {
    var damage: int;
    let name: String;
  }

  impl Weapon {
    func __init__(dmg: int, name: String) {
      self.damage = dmg;
      self.name = name;
    }
    func get_damage(): int {
      return self.damage;
    }
  }
  ```
* `self` is implicit in non-static methods. Methods default to immutable `self`; mutating methods must be explicitly declared with `var func`.

### 3.7 Inheritance & Prototypal State Delegation
* **Static Structural Inheritance**: `struct Child: Parent1, Parent2 { ... }`. Under the hood, this compiles to composition and forwarding. **No up-casting** is permitted.
* **Traits**: `trait Actor { func update(); }` and `impl Actor for Cat { ... }`. Polymorphism is achieved via implicit trait subtyping and heterogeneous trait collections `[Actor]`.
* **Prototypal Inheritance (`proto`)**:
  ```sapphire
  let arena = Arena();
  proto Goblin {
    var health: int;
    var damage: int;
  }
  let base_goblin = Goblin { health = 100, damage = 10 } in arena;
  var elite_goblin = clone base_goblin {
    self.health = 200; // Local shadowing
  };
  ```
  * Requires allocation within an `Arena` via `in <arena>`.
  * Clones delegate state live to their prototype.
  * Mutating nested reference fields triggers **Copy-on-Write (CoW)** to protect the prototype.
  * Prototypal delegation is **data-only**. Methods remain statically dispatched.

### 3.8 Modules & Encapsulation
* All top-level declarations are **module-private by default**.
* Exactly one `export { ... }` manifest block per file defines public API:
  ```sapphire
  export {
    Player,
    create_player,
    create_player as spawn_player,
  }
  ```
* Importing: `import lib.std.math;` or `import lib.love2d.graphics as gfx;`.

### 3.9 Host Interoperability & Live Reloading
* `@extern var love: LoveEngine;`: Binds external runtime globals without variable redeclaration.
* `@export("love.update") func update(dt: float)`: Renames or routes functions to host callbacks.
* `@on_reload`: Lifecycle hook executed after fast live hot-reload (`sapphire run --dev`).

## 4. Repository Structure

```text
sapphire/
├── README.md               # High-level overview and feature showcase
├── Pipfile / Pipfile.lock  # Python virtual environment & dependencies
├── pyproject.toml          # Package metadata and CLI entrypoints
├── grammar/
│   └── Sapphire.g4         # ANTLR4 grammar specification
├── docs/                   # Documentation
│   ├── SPEC.md             # Definitive language specification
│   ├── compiler.md         # Compiler pipeline architecture
│   ├── development.md      # Setup, commands, and developer guide
│   ├── testing.md          # std.testing and test framework guide
│   └── builtins.md         # Standard library & built-in symbol docs
├── src/
│   ├── cli/
│   │   ├── sapphire.py     # Main CLI entry point ('sapphire')
│   │   └── test_runner.py  # Test discovery & execution harness
│   ├── common/
│   │   └── errors.py       # SapphireError exception hierarchy
│   ├── parser/
│   │   ├── ast.py          # AST node classes (ASTNode and descendants)
│   │   ├── ast_builder.py  # ANTLR visitor transforming Parse Tree to AST
│   │   ├── error_listener.py # Custom ANTLR syntax error listener
│   │   └── gen/            # Auto-generated ANTLR parser files (do not edit manually!)
│   ├── semantics/
│   │   ├── symbol_table.py # Scopes, symbols, and type representations
│   │   ├── type_checker.py # Core semantic analysis and type checking
│   │   ├── arena_checker.py # Memory arena validation and escape analysis
│   │   └── generics_checker.py # Monomorphization and type specialization
│   ├── code_gen/
│   │   ├── transpiler.py   # Compilation driver (transpile_file)
│   │   ├── transpiler_registry.py # Target backend registry
│   │   ├── python_transpiler.py # Sapphire -> Python transpiler
│   │   ├── lua_transpiler.py    # Sapphire -> Lua 5.1 transpiler
│   │   ├── llvm_transpiler.py   # Sapphire -> LLVM IR (experimental)
│   │   └── source_map.py   # Source Map v3 (VLQ) generator
│   └── lsp/
│       ├── server.py       # pygls-based Language Server Protocol server
│       └── semantic_tokens.py # Real-time semantic highlighting
├── lib/                    # Sapphire standard library (.sp)
│   ├── std/                # Built-in modules (testing, math, etc.)
│   └── love2d/             # Love2D engine bindings
├── samples/                # Sample Sapphire programs (.sp)
├── testing/                # Cross-backend integration tests and test utilities
│   ├── e2e/                # End-to-end .sp test suites and ground-truth expectations
│   └── test_utils.py       # Testing helpers
└── tools/
    └── vscode-extension/   # VS Code extension client
```

## 5. Compiler Pipeline & Architecture

The compilation pipeline operates in distinct stages:

```
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
* **Updating Grammar**: Modify `grammar/Sapphire.g4`, regenerate ANTLR files into `src/parser/gen/`, update `src/parser/ast.py` if new nodes are introduced, update `src/parser/ast_builder.py`, and adapt `src/semantics/` and `src/code_gen/`.

## 6. Developer & Agent Workflows

### 6.1 Environment Setup
Dependencies are managed via `pipenv`:
```bash
# Install dependencies into virtualenv
pipenv install --dev

# Run commands within virtualenv
pipenv run <command>
```

### 6.2 Regenerating ANTLR Parser Files
When modifying `grammar/Sapphire.g4`, you **must** regenerate the parser files:
```bash
antlr -Dlanguage=Python3 -visitor -o src/parser/gen -Xexact-output-dir grammar/Sapphire.g4
```
Ensure all four generated files (`SapphireLexer.py`, `SapphireParser.py`, `SapphireListener.py`, `SapphireVisitor.py`) are placed in `src/parser/gen/`.

### 6.3 Running Tests
Agents must run tests to verify changes before completing any task.

```bash
# 1. Run all Python unit tests (compiler, parser, semantic analyzer, LSP)
pipenv run test

# 2. Run test coverage suite
pipenv run coverage

# 3. Run cross-backend integration tests
pipenv run python -m unittest src/code_gen/python_transpiler_test.py
pipenv run python -m unittest src/code_gen/lua_transpiler_test.py

# 4. Run native Sapphire language test runner
pipenv run sapphire test
```

### 6.4 Building & Executing Sapphire Programs
```bash
# Transpile and execute a script using Python backend (default)
pipenv run sapphire samples/overview.sp

# Transpile and execute using Lua backend (requires lua or luajit)
pipenv run sapphire samples/overview.sp -t lua

# Transpile to file without executing
pipenv run sapphire build samples/overview.sp -o output.py
pipenv run sapphire build samples/overview.sp -t lua -o output.lua

# Live hot-reloading dev mode
pipenv run sapphire run samples/overview.sp --dev
```

## 7. Guidelines & Guardrails for AI Agents

1. **Keep the Toolchain in Sync**: If you change the grammar in `grammar/Sapphire.g4`:
   * Regenerate ANTLR files (`antlr -Dlanguage=Python3 ...`).
   * Update `src/parser/ast.py` (AST node representations).
   * Update `src/parser/ast_builder.py` (AST visitor).
   * Update `src/semantics/type_checker.py` and `symbol_table.py`.
   * Update both `python_transpiler.py` and `lua_transpiler.py`.
   * Add or update unit tests in `src/` and end-to-end tests in `testing/e2e/`.
2. **Never Violate Language Constraints**:
   * Do **not** generate code or semantics relying on vtables or dynamic method overriding.
   * Do **not** allow struct up-casting.
   * Do **not** introduce exceptions or stack-unwinding constructs into Sapphire syntax.
   * Always enforce semicolon statement termination in `.sp` code.
3. **Preserve Documentation & Comments**:
   * Do not delete or mangle docstrings, inline architectural comments, or existing specs.
   * When modifying language semantics or adding built-ins, update `docs/SPEC.md`, `docs/compiler.md`, or `docs/builtins.md` accordingly.
4. **Code Quality Standards**:
   * Python codebase: Follow PEP 8, maintain 2-space or 4-space consistency with surrounding files, include explicit type annotations where appropriate.
   * Sapphire code: Follow `docs/SPEC.md §2` (80 chars max line length, 2-space indentation, semicolon terminated).
5. **Pre-Completion Checklist**:
   * [ ] `pipenv run test` passes with zero failures or errors.
   * [ ] Affected e2e/integration tests pass across all relevant backends.
   * [ ] Newly created files adhere to repository naming and layout conventions.
