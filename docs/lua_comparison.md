# Sapphire vs. Lua

This document compares **Sapphire** and **Lua** as programming languages,
examining how their type systems, object models, memory semantics, and error
handling differ—and why Sapphire pairs static safety with Lua-inspired
ergonomics.

## 1. Overview & design philosophy

Lua is famous for its small footprint, simple semantics, and expressive
metatable-based object model. Tables act as arrays, maps, objects, modules, and
prototypes all at once, making Lua fast to embed and effortless to prototype
with.

As codebases grow, however, dynamic table-everything design introduces common
friction points:

* **Late error discovery**: Typos in field names, missing arguments, or
  unexpected `nil` values surface only when a branch executes at runtime.
* **Manual object plumbing**: Structuring data, inheritance, and method
  dispatch relies on hand-rolled metatables (`setmetatable`, `__index`) with
  project-specific conventions.
* **Implicit aliasing & global state**: Tables pass by mutable reference
  everywhere, making it hard to tell from a function signature whether a call
  mutates its arguments.
* **Garbage-collected lifetimes**: All allocations share a single GC heap,
  leaving resource cleanup timing non-deterministic.

Sapphire preserves Lua's lightweight feel—including first-class coroutines and
prototypal state delegation—while moving type checking, null safety, mutability
contracts, and memory scoping to **compile time** (and compiling cleanly to
readable Lua 5.1 today alongside Python, with a native compiler on the roadmap).

## 2. Detailed language comparison

### 2.1 Static types & null safety vs. dynamic `nil`

In Lua, accessing an undefined field or indexing past an array quietly returns
`nil`, often causing a crash far away from the real bug (`attempt to index a
nil value`).

Sapphire enforces static types and explicit optionals (`T?`). Values cannot be
empty unless declared optional, and optionals must be safely unwrapped via
`if let ?=`, `guard ... else`, `?.`, or `??`:

```lua
-- Lua: Missing field or typo silently yields nil until used later
local function heal(target, amount)
  if target ~= nil and target.hp > 0 then
    target.hp = target.hp + amount
    return true
  end
  return false
end
```

```sapphire
// Sapphire: Explicit optional type, guard promotion, compile-time field checks
struct Unit {
  var hp: int;
  let name: String;
}

func heal(var target_opt: Unit?, amount: int): bool {
  guard var target ?= target_opt; target.hp > 0 else {
    return false;
  }
  target.hp += amount;
  return true;
}
```

### 2.2 Structs, traits & delegation vs. metatables

Lua uses tables plus metatables to emulate classes, interfaces, and
inheritance. Every method lookup walks `__index` chains dynamically unless
cached manually, and refactoring a field name across files requires careful
manual search.

Sapphire separates **data composition**, **static polymorphism**, and
**opt-in dynamic prototypes** into three explicit tools:

1. **Structs & multi-parent syntactic delegation**: `struct Player: Position,
   Health` inlines parent fields and auto-forwards methods at compile time with
   zero vtables and no up-casting/slicing
   ([docs/SPEC.md (Static Structural Inheritance)](SPEC.md#static-structural-inheritance)).
2. **Traits**: `trait Damageable` defines compile-time behavioral contracts
   dispatched statically via monomorphization or closed tagged unions—no
   duck-typing surprises at runtime.
3. **Opt-in prototypes (`proto` & `clone`)**: When you actually want
   Lua-style prototype sharing, `proto` gives you typed dynamic field
   delegation with **Copy-on-Write (CoW)** isolation on nested mutations
   ([docs/SPEC.md (Prototypal State Delegation)](SPEC.md#prototypal-state-delegation-proto-clone)).

```lua
-- Lua: Manual metatable prototype setup
local Goblin = { hp = 50, speed = 4.0 }
Goblin.__index = Goblin

local elite = setmetatable({ hp = 120 }, Goblin)
-- Reading elite.speed delegates to Goblin.speed; nested tables risk aliasing
```

```sapphire
// Sapphire: Typed opt-in prototype with lexical Arena and CoW safety
proto Goblin {
  var hp: int = 50;
  var speed: float = 4.0;
}

func spawn_wave() {
  var arena = Arena();
  var base = Goblin {} in arena;
  var elite = clone base {
    self.hp = 120;
  };
  base.speed = 5.5;  // Live delegation: elite.speed is now 5.5
  print(f"Elite HP: {elite.hp}, speed: {elite.speed}");
}  // Arena cleans up base and elite deterministically
```

### 2.3 Explicit mutability & aliasing safety

In Lua, every table passed to a function is a mutable reference. Reading a call
like `resolve_combat(attacker, defender)` gives no guarantee about which
argument is modified—and passing the same table twice (`resolve_combat(u, u)`)
can silently corrupt state.

In Sapphire:

* Non-primitives pass by **constant reference** by default.
* Functions that mutate a parameter must mark it with `var`
  (`func attack(attacker: Unit, var defender: Unit)`), and mutating methods
  must be declared `var func`.
* Compile-time **call-site exclusivity** rejects aliasing conflicts such as
  passing the same mutable variable to two conflicting parameters in one call
  ([docs/SPEC.md (Scope-Bound Aliasing Rules)](SPEC.md#scope-bound-aliasing-rules-call-site-reference-exclusivity)).
* Collections are frozen during `for-in` iteration, preventing subtle table
  mutation bugs mid-loop.

### 2.4 Memory model & deterministic cleanup

Lua relies exclusively on tracing garbage collection. Cleanup hooks (`__gc`)
run on the collector's schedule rather than when a scope ends, and short-lived
table churn can trigger frame-time GC spikes.

Sapphire uses a stack-first model with deterministic lifetimes:

* **Stack structs & LIFO RAII**: Structs defining `func __del__()` run
  destructors deterministically in reverse declaration order on scope exit,
  `return`, `break`, or `continue`.
* **Explicit `Arena` scopes**: Dynamic `proto` objects allocate into a lexical
  `Arena` and are bulk-freed when the arena exits scope, with compile-time
  escape checking preventing dangling references.
* **Explicit ownership (`move`)**: Move-only resources (`Ref<T>`, `Arena`,
  `Coroutine<T>`, structs with `__del__()`) require explicit `move`, catching
  use-after-move at compile time.

### 2.5 Arrays, maps, indexing & pattern matching

Lua unifies arrays and dictionaries into a single 1-indexed `table` type, where
`#t` has subtle behavior when holes (`nil`) exist.

Sapphire separates typed homogeneous arrays (`[T]`, 0-indexed) from typed maps
(`[K: V]`), provides built-in functional methods (`.map()`, `.filter()`,
`.reduce()`, `.sort()`), and adds exhaustive `enum` types and `match`
expressions:

```sapphire
enum Weather {
  Clear,
  Rain,
  Storm,
}

func visibility(w: Weather): float {
  return match w {
    Weather.Clear -> 1.0,
    Weather.Rain  -> 0.65,
    Weather.Storm -> 0.25,
  };
}
```

### 2.6 Coroutines

Both Lua and Sapphire treat coroutines as first-class language primitives. Lua
provides stackful `coroutine.create` / `coroutine.resume` / `coroutine.yield`
with dynamically typed return tuples.

Sapphire provides statically typed stackless `Coroutine<T>` (and
`Coroutine<void>` for sequencing) with `.step(): T?`, `.is_done()`, and
`.reset()`, while statically preventing move-only RAII resources or escaping
stack borrows from dangling across a `yield` suspension point
([docs/SPEC.md (Coroutines)](SPEC.md#coroutines-coroutinet)).

### 2.7 Module encapsulation & function APIs

Lua modules return an ad-hoc table of public values, and optional/named
arguments are conventionally simulated by allocating an options table on every
call (`draw({ x = 10, y = 20 })`).

Sapphire provides:

* **Private-by-default modules** with a single explicit `export { ... }`
  manifest and prohibited mutable global exports.
* **First-class named arguments and default values** with zero table
  allocation (`move_by(dx = 5.0, dy = -3.0)`).
* **Multiple return values** with typed destructuring (`let dmg, hit = ...`),
  retaining one of Lua's nicest ergonomic features with compile-time checking.

## 3. Feature summary matrix

| Feature | Lua | Sapphire |
| :--- | :--- | :--- |
| **Type checking** | Dynamic (runtime) | Static (compile-time) with inference |
| **Null handling** | Pervasive `nil` | Explicit `T?`, `guard ?=`, `?.`, `??` |
| **Object model** | Tables + manual metatables | `struct` delegation, `trait`s, opt-in `proto` |
| **Mutability** | Tables mutable everywhere | Const-ref default, explicit `var` & `var func` |
| **Aliasing safety** | Unchecked at compile time | Call-site exclusivity & iteration freezes |
| **Memory & cleanup** | Tracing GC (`__gc`) | Stack-first RAII (`__del__`) & lexical `Arena`s |
| **Collections** | Unified 1-indexed `table` | Distinct 0-indexed `[T]` and typed `[K: V]` |
| **Named arguments** | Options table convention | Native zero-overhead named & default args |
| **Pattern matching** | `if`/`elseif` chains | Exhaustive `match` over `enum` & optionals |
| **Coroutines** | Dynamic stackful coroutines | Typed `Coroutine<T>` with borrow checks |
| **Tooling** | External linters / annotations | Built-in type checker, `@test`, LSP, source maps |

## 4. When to choose which

* **Choose Lua** when you need a tiny, zero-build runtime interpreter embedded
  directly inside a C/C++ host for end-user scripting or live REPL execution.
* **Choose Sapphire** when you want Lua's lightweight feel, coroutines, and
  prototypal flexibility—plus clean Lua compilation and host interop—backed by
  static typing, null safety, explicit mutability, deterministic cleanup, and
  strong IDE refactoring support.
