# Sapphire documentation

A guided map of the documentation in this directory. You can also browse the
rendered docs and try code in the browser at
[zziccardi.github.io/sapphire](https://zziccardi.github.io/sapphire/).

## Learning Sapphire

1. [quickstart.md](quickstart.md) — Install the CLI and write your first
   Sapphire program.
2. [SPEC.md](SPEC.md) — Complete language specification (types, traits, arenas,
   ownership, coroutines, and memory model).
3. [style_guide.md](style_guide.md) — Formatting, naming, and idiomatic style.
4. [testing.md](testing.md) — Writing and running native `@test` suites with
   `std.testing`.
5. [ai_agents.md](ai_agents.md) — Human readability, compiler-verified agent
   workflows, and trade-offs when writing Sapphire with AI coding agents.

## Standard library & interop

* [builtins.md](builtins.md) — Built-in types (`Array`, `Map`, `String`,
  `Arena`, `Ref`, `SharedRef`, `WeakRef`, `Coroutine`) and global functions.
* [stdlib.md](stdlib.md) — Standard library modules (`std.math`, `std.fs`,
  `std.os`, `std.time`, `std.utf8`, `std.testing`).
* [host_interop.md](host_interop.md) — Host engine bindings (`@extern`,
  `@export`), Love2D integration, source maps, and live hot-reloading.

## Language comparisons

* [rust_comparison.md](rust_comparison.md) — Sapphire vs. Rust (borrowing,
  arenas, and traits without lifetime annotations).
* [swift_comparison.md](swift_comparison.md) — Sapphire vs. Swift (optionals,
  `guard`, value semantics, and protocols/traits).
* [cpp_comparison.md](cpp_comparison.md) — Sapphire vs. C++ (RAII, move
  semantics, and zero-vtable polymorphism).
* [lua_comparison.md](lua_comparison.md) — Sapphire vs. Lua (static types,
  Love2D workflows, and Lua 5.1 transpilation).

## Compiler internals & contributing

* [compiler.md](compiler.md) — Compiler pipeline architecture (ANTLR4, AST,
  semantic passes, transpilers, and LSP).
* [development.md](development.md) — Local development setup, test commands,
  and tooling workflow.
