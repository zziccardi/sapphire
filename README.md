# Sapphire programming language

Sapphire is a statically typed programming language that combines the
**safety and performance** of systems languages with the
**rapid-prototyping ergonomics** of dynamic languages and the
**expressive API clarity** of modern languages like Swift.

This repository contains the ANTLR4 grammar, abstract syntax tree (AST) builder,
semantic analyzer, type checker, and a transpiler that compiles Sapphire source
code (`.sp`) into clean, executable Python (`.py`).

## Key features of Sapphire

### 1. Dual-paradigm code reuse
* **Traits**: Define interfaces/contracts (`trait Damageable`) that are
  statically checked and dispatched.
* **Static inheritance**: Structures can inherit layouts statically
  (`struct Character: Entity`) without runtime overhead or traditional OOP
  boilerplate.
* **Prototypal delegation**: Create runtime objects by cloning existing
prototypes using the `clone` keyword (similar to JavaScript or Lua). Mutating a
base archetype propagates changes down to active clones unless they shadow those
fields locally.

### 2. Optional safety
* Null-pointer errors are prevented at compile time.
* Optionals are denoted by a `?` suffix (e.g., `Character?`).
* Swift-style conditional unwrapping:
  ```sapphire
  if let active_target = target_player {
    // active_target is unwrapped and guaranteed to be non-optional
  } else {
    // optional was none fallback branch
  }
  ```
* Safe optional chaining (`let speed = target?.speed`).

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

## Repository structure

* `grammar/`: ANTLR4 grammar specification (`Sapphire.g4`).
* `src/`
  * `parser/`: AST definitions (`ast.py`) and the visitor that builds the AST (`ast_builder.py`).
  * `semantics/`: Scope management, symbol tables (`symbol_table.py`), and compiler type-checking rules (`type_checker.py`).
  * `code_gen/`: Python transpiler logic (`transpiler.py`) and runtime wrappers.
  * `run_transpiler.py`: CLI tool to compile `.sp` source files to Python.
* `docs/`
  * [SPEC.md](docs/SPEC.md): Deep dive language-design specification.
  * [compiler.md](docs/compiler.md): Comprehensive compiler pipeline and architectural documentation.
  * [development.md](docs/development.md): Instructions for parsing, testing, and developing Sapphire.
* `sample.sp` & `simulation.sp`: Extensive code examples demonstrating all core language features in action.
