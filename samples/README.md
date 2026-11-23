# Sapphire sample programs

Runnable `.sp` examples demonstrating core Sapphire language features, memory
management, host interoperability, and idioms.

Run any sample with the Python backend (default) or Lua 5.1 backend:

```bash
sapphire samples/overview.sp
sapphire samples/overview.sp -t lua
```

## Start here

| Sample | What it demonstrates |
| :--- | :--- |
| [overview.sp](overview.sp) | Core tour: structs, traits, optionals, `guard`, lambdas, and collections |
| [script_demo.sp](script_demo.sp) | Module entry (`func main()`) and compile-time module constants |
| [sample_test.sp](sample_test.sp) | Native unit testing with `std.testing` (`sapphire test samples/sample_test.sp`) |

## Types, collections & control flow

| Sample | What it demonstrates |
| :--- | :--- |
| [array_demo.sp](array_demo.sp) | Array methods (`map`, `filter`, `reduce`, `sort`, `push`, `pop`, etc.) |
| [map_demo.sp](map_demo.sp) | Map creation, lookup, iteration, and mutation |
| [string_demo.sp](string_demo.sp) | Built-in `String` methods and interpolation |
| [enum_demo.sp](enum_demo.sp) | Integer- and string-backed enums |
| [match_demo.sp](match_demo.sp) | `match` expressions, multi-patterns, and `yield` blocks |
| [loop_control_demo.sp](loop_control_demo.sp) | `while`, `for-in`, `range()`, `break`, and `continue` |
| [casting_demo.sp](casting_demo.sp) | Infallible static casting (`as`) and string conversions |

## Traits, delegation & generics

| Sample | What it demonstrates |
| :--- | :--- |
| [trait_subtyping_demo.sp](trait_subtyping_demo.sp) | Nominal traits, implicit subtyping, and heterogeneous `[Trait]` arrays |
| [multi_parent_delegation_demo.sp](multi_parent_delegation_demo.sp) | Static multi-parent struct composition and method forwarding |
| [generics_demo.sp](generics_demo.sp) | Compile-time monomorphized generic structs and functions |

## Memory, arenas, RAII & coroutines

| Sample | What it demonstrates |
| :--- | :--- |
| [arena_demo.sp](arena_demo.sp) | Lexical `Arena` allocation, `proto`, `clone`, and copy-on-write |
| [destructors.sp](destructors.sp) | Deterministic LIFO destructors (`__del__`) |
| [raii_resource_demo.sp](raii_resource_demo.sp) | Scope-bound RAII resource cleanup and explicit `move` |
| [coroutine_demo.sp](coroutine_demo.sp) | Stackless `Coroutine<T>` generators and `yield` |

## Game dev, apps & host interop

| Sample | What it demonstrates |
| :--- | :--- |
| [love2d_demo.sp](love2d_demo.sp) | Love2D host bindings (`@extern` / `@export`) targeting Lua 5.1 |
| [game_loop.sp](game_loop.sp) | Love2D-style `load` / `update` / `draw` game loop architecture |
| [simulation.sp](simulation.sp) | Multi-entity simulation combining traits, arenas, and state updates |
| [python_interop.sp](python_interop.sp) | Calling into Python host runtime APIs via `@extern` |
| [gui.sp](gui.sp) | Typed UI component tree using enums and traits |
| [web_api_client.sp](web_api_client.sp) | Typed HTTP client SDK modeling status enums and optionals |

## Language comparisons

| Sample | What it demonstrates |
| :--- | :--- |
| [rust_comparison_ergonomics.sp](rust_comparison_ergonomics.sp) | Companion code for [docs/rust_comparison.md](../docs/rust_comparison.md) |
| [rust_comparison_graphs.sp](rust_comparison_graphs.sp) | Arena-backed graph structures compared against Rust |
