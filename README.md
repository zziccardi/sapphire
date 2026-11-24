<p align="center">
  <img src="https://raw.githubusercontent.com/zziccardi/sapphire/main/web/public/favicon.svg" alt="Sapphire logo" width="72" />
</p>

<h1 align="center">Sapphire programming language</h1>

<p align="center">
  <a href="https://github.com/zziccardi/sapphire/actions/workflows/ci.yml">
    <img src="https://github.com/zziccardi/sapphire/actions/workflows/ci.yml/badge.svg" alt="CI" />
  </a>
  <a href="https://github.com/zziccardi/sapphire/actions/workflows/deploy-website.yml">
    <img src="https://github.com/zziccardi/sapphire/actions/workflows/deploy-website.yml/badge.svg" alt="Deploy Website" />
  </a>
  <a href="https://github.com/zziccardi/sapphire/blob/main/LICENSE">
    <img src="https://img.shields.io/badge/license-Apache--2.0-blue.svg" alt="License: Apache-2.0" />
  </a>
  <a href="https://github.com/zziccardi/sapphire/blob/main/pyproject.toml">
    <img src="https://img.shields.io/badge/python-3.12%2B-3776AB.svg" alt="Python 3.12+" />
  </a>
</p>

<p align="center">
  <a href="https://zziccardi.github.io/sapphire/">Website</a> ·
  <a href="https://zziccardi.github.io/sapphire/playground/">Playground</a> ·
  <a href="https://zziccardi.github.io/sapphire/docs/quickstart">Quickstart</a> ·
  <a href="https://zziccardi.github.io/sapphire/docs/spec">Language spec</a> ·
  <a href="https://github.com/zziccardi/sapphire/blob/main/samples/README.md">Examples</a> ·
  <a href="https://github.com/zziccardi/sapphire/blob/main/CONTRIBUTING.md">Contributing</a>
</p>

Sapphire is a statically typed general-purpose programming language that
combines the **safety and performance** of modern systems languages with the
**rapid-prototyping ergonomics** of dynamic languages. While general-purpose in
design, its deterministic memory model, lexical arenas, and live-reload
capabilities make it especially well-suited for simulations, interactive
applications, and game engines.

Try Sapphire in your browser right now in the
[interactive playground](https://zziccardi.github.io/sapphire/playground/), or
browse the [documentation site](https://zziccardi.github.io/sapphire/docs/).

By resolving polymorphism at compile time and restricting prototypal inheritance
to be data-only, Sapphire enables runtime object modification without
virtual-method tables, reference-cycle overhead, or lifetime annotations.

This repository contains the ANTLR4 grammar, abstract syntax tree (AST) builder,
semantic analyzer, type checker, transpilation backends that compile Sapphire
source code (`.sp`) into executable Python or Lua, a built-in testing
runner, a Language Server Protocol (LSP) server, a VS Code extension, and the
documentation website.

The project is a **work in progress**. The [language spec](docs/SPEC.md) may
change significantly over time. For now the transpiler toolchain targets Python
and Lua to facilitate rapid iteration and scripting-engine integration; once the
language design is finalized, I'd like to introduce a proper native compiler
(likely built in Rust) to enable the memory-safety and performance features
described in the spec.

## Sapphire at a glance

```sapphire
struct Vector2 {
  var x: float = 0.0;
  var y: float = 0.0;
}

// Static structural inheritance: zero-overhead composition and auto-forwarding
struct Position: Vector2 {
  var z: float = 0.0;
}

// Opt-in prototypal inheritance: instances dynamically delegate state
proto Entity {
  var pos: Position;
  var health = 100;  // Inferred to be `int`
  let name: String;
}

trait Damageable {
  // Functions that mutate `self` must be marked `var`
  var func take_damage(amount: int);
}

impl Damageable for Entity {
  var func take_damage(amount: int) {
    self.health = self.health > amount ? self.health - amount : 0;
  }
}

// Const-ref by default; explicit `var` for mutation; named args with defaults
func attack(attacker: Entity, var target: Entity, bonus: int = 0) {
  target.take_damage(amount = 15 + bonus);
  print(f"{attacker.name} struck {target.name}! {target.health} HP remaining");
}

// Swift-style guard: early exit with validated value promoted to outer scope
func execute_turn(hero: Entity, var target_opt: Entity?) {
  guard var target ?= target_opt; target.health > 0 else {
    print("No valid target available!");
    return;
  }
  attack(attacker = hero, target = target, bonus = 10);
}

func main() {
  var arena = Arena();

  // Scoped prototype allocated within an explicit lexical arena
  let base_goblin = Entity {
    name = "Goblin",
    health = 50,
    pos = Position { x = 0.0, y = 0.0 }
  } in arena;

  // Dynamic cloning with live delegation and local property shadowing
  var elite_goblin = clone base_goblin {
    self.health = 120;
  };
  var target_ref: Entity? = elite_goblin;

  let hero = Entity {
    name = "Hero",
    health = 100,
    pos = Position { x = 10.0, y = 5.0 }
  } in arena;

  execute_turn(hero = hero, target_opt = target_ref);
}
```

## Key features of Sapphire

### Dual-paradigm code reuse
* **Zero-vtable traits**: Traits define statically checked contracts
  (`trait Damageable`) with **default method bodies**, **transitive
  inheritance** across `struct Child: Parent`, and **partial overrides** in
  `impl Trait for Child`. Heterogeneous collections (`[Damageable]`) eliminate
  vtables and fat pointers via compiler-synthesized closed tagged unions.
* **Structural delegation**: Structs compose and forward fields/methods
  statically (`struct Position: Vector2`) without runtime overhead or OOP
  boilerplate. Struct up-casting (`Child as Parent`) is prohibited to prevent
  object slicing.
* **Opt-in prototypal delegation**: Mark types with `proto` (e.g.
  `proto Entity`) to clone objects at runtime (`clone base { ... }`) with live
  property delegation, **copy-on-write (CoW)** isolation for nested references,
  and explicit lexical `Arena` lifetime bounds (`in <arena>`).

### Memory safety, RAII, & ownership
* **Const-ref by default without lifetime annotations**: Non-primitive values
  pass by constant reference by default; mutable parameters require explicit
  `var` (`func update(var target: Entity)`), and call-site aliasing checks
  prevent overlapping mutable borrows without lifetime syntax.
* **Deterministic RAII & `move` semantics**: Structs support LIFO destructors
  (`__del__`), explicit ownership transfer (`move x`) with compile-time
  use-after-move checks, and return-value optimization (RVO).
* **Smart references & arenas**: Exclusive heap ownership (`Ref<T>`),
  read-only reference-counted sharing (`SharedRef<T>`), cycle-safe weak handles
  (`WeakRef<T>`), and lexically scoped `Arena` teardown.

### Null safety, pattern matching, & expressive ergonomics
* **Zero throwable exceptions**: No `try`/`catch`/`throw` or hidden unwinding.
  Fallibility is explicit via optionals (`T?`), safe chaining (`?.`),
  nil-coalescing (`??`), conditional unwrapping (`if let x ?= opt`), Swift-style
  `guard` clauses, and multiple return destructuring.
* **Pattern matching & typed enums**: Value-producing `match` expressions with
  multi-pattern arms and `yield` blocks, alongside integer- and string-backed
  `enum` types.
* **Readable call sites**: Named arguments (`attack(bonus = 10)`), default
  parameter values, and f-string interpolation (`f"{name}: {hp}"`).

### Modules, encapsulation, generics, & coroutines
* **Explicit modules & construction-contract encapsulation**: Modules declare
  public APIs via `export { ... }` manifests. Structs with `__init__` enforce
  cross-module field encapsulation (mutated only via methods), while structs
  without `__init__` serve as lightweight plain-data records.
* **Zero-overhead generics**: Compile-time monomorphized generic structs,
  traits, `impl` blocks, and functions (`struct Stack<T>`, `func id<T>`) with
  call-site type inference.
* **First-class coroutines**: Stackless `Coroutine<T>` generators
  (`yield expr;`) and `Coroutine` sequencers (`yield;`).

### Host interop, live hot-reloading, & batteries-included tooling
* **Zero-cost host bindings**: Model external host environments (such as
  **Love2D**) with `@extern` globals and `@export("love.update")` callbacks.
* **Source maps & error demangling**: Emits
  [source map v3](https://tc39.es/ecma426/) files (`.lua.map`) and runtime
  stack-trace demanglers mapping Lua/Love2D errors back to `.sp` lines.
* **Live hot-reloading (`sapphire run --dev`)**: Incremental recompilation that
  patches live instances in-place and triggers `@on_reload` hooks.
* **Standard library, testing, & IDE support**: Cross-backend stdlib
  (`std.math`, `std.fs`, `std.os`, `std.time`, `std.utf8`), built-in `@test`
  runner (`std.testing`), LSP server (`sapphire lsp`), and VS Code extension.

## Installation

### Compiler and runtime CLI

Install the Sapphire CLI package using `pip` (Python 3.12+):

```bash
pip install sapphire-lang
```

Or install the wheel from a local build or
[GitHub releases](https://github.com/zziccardi/sapphire/releases):

```bash
pip install sapphire_lang-<version>-py3-none-any.whl
```

For an isolated system-wide command without managing environments, use `pipx`:

```bash
pipx install sapphire-lang
```

### VS Code extension

Download the `.vsix` asset from
[GitHub releases](https://github.com/zziccardi/sapphire/releases) and install it
via the command line:

```bash
code --install-extension sapphire-<version>.vsix
```

Alternatively, open VS Code, navigate to the Extensions pane, click `...` (More
Actions), and select **Install from VSIX...**.

## CLI overview

```bash
# Run a Sapphire script (transpiling to Python by default):
sapphire samples/overview.sp

# Run with live hot-reloading / dev mode (watches files and reloads in-place):
sapphire run samples/overview.sp --dev

# Transpile to Lua (generating both main.lua and main.lua.map source maps by
# default):
sapphire build samples/love2d_demo.sp -t lua -o main.lua

# Build for release without source map or runtime demangler:
sapphire build samples/love2d_demo.sp -t lua -o main.lua --no_sourcemap

# Run transpiled game in Love2D (passing the directory containing `main.lua`):
love .

# Run a Love2D game directly with live hot-reloading:
sapphire run samples/love2d_demo.sp -t love2d -o main.lua --dev

# Run native test suites (or emit machine-readable JSON for tooling/agents):
sapphire test
sapphire test --json

# Inspect parse tree, AST, type-check, or launch the LSP server:
sapphire parse samples/overview.sp
sapphire dump-ast samples/overview.sp
sapphire check samples/overview.sp
sapphire check samples/overview.sp -t lua --json
sapphire lsp
```

## Repository structure

* `docs/`: Core documentation (see [docs/README.md](docs/README.md)) including
  the [quickstart guide](docs/quickstart.md),
  [host interop & Love2D guide](docs/host_interop.md),
  [language spec](docs/SPEC.md), [style guide](docs/style_guide.md),
  [C++ comparison](docs/cpp_comparison.md),
  [Lua comparison](docs/lua_comparison.md),
  [Rust comparison](docs/rust_comparison.md),
  [Swift comparison](docs/swift_comparison.md),
  [compiler architecture](docs/compiler.md),
  [development guide](docs/development.md), [builtins](docs/builtins.md),
  [standard library](docs/stdlib.md), and [testing guide](docs/testing.md).
* `grammar/`: ANTLR4 grammar specification (`Sapphire.g4`).
* `samples/`: Example scripts demonstrating core language features (see
  [samples/README.md](samples/README.md)).
* `sapphire/`: Compiler pipeline, standard library, and tooling:
  * `cli/`: Unified `sapphire` CLI entry point (`sapphire.py`) and test runner
    (`test_runner.py`).
  * `common/`: Core diagnostic model (`diagnostics.py`), stable error codes
    (`error_codes.py`), and domain exception hierarchy (`errors.py`).
  * `lib/`: Sapphire standard library (`sapphire/lib/std/`) and host-engine
    bindings (`sapphire/lib/love2d/`).
  * `parser/`: AST definitions (`ast.py`), visitor builder (`ast_builder.py`),
    centralized error listener (`error_listener.py`), and ANTLR-generated
    parser.
  * `semantics/`: Symbol tables (`symbol_table.py`), type checker
    (`type_checker.py`), borrow/aliasing checker (`borrow_checker.py`), arena
    escape checks (`arena_checker.py`), layout & const evaluation
    (`struct_layout_pass.py`, `const_eval.py`), generics
    (`generics_checker.py`), and static lints (`lints.py`).
  * `code_gen/`: Transpiler driver (`transpiler.py`), target backend registry
    (`transpiler_registry.py`), Python generator (`python_transpiler.py`),
    Lua 5.1 generator (`lua_transpiler.py`), experimental LLVM IR generator
    (`llvm_transpiler.py`), and source-map generator (`source_map.py`).
  * `lsp/`: Language Server Protocol (LSP) server providing diagnostics,
    autocompletion, hover info, go-to-definition, and semantic tokens.
* `testing/`: Test suite runner, cross-backend integration and end-to-end tests
  (`testing/e2e/`), and test utilities (`test_utils.py`).
* `tools/`: Development tools including the
  [VS Code extension](tools/vscode-extension/).
* `web/`: Astro documentation website and browser playground deployed at
  [zziccardi.github.io/sapphire](https://zziccardi.github.io/sapphire/).
