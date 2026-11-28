---
name: sapphire-lang
description: >-
  Reference guide for the custom Sapphire programming language (.sp files).
  Use when writing, editing, or refactoring Sapphire code, defining structs,
  protos, traits, coroutines, or enums, working with standard libraries
  (std.math, std.testing), or calling Love2D engine bindings (lib.love2d.*).
---

# Sapphire Language Reference

Sapphire is a statically typed systems and game-programming language that
compiles to Lua 5.1 / Love2D (as well as Python). It features zero-overhead
static structural delegation, trait-based polymorphism, prototypal delegation
with Copy-on-Write (`proto`/`clone` in `Arena`), scope-bound reference
exclusivity, compile-time null safety, exhaustive pattern matching, and
stackless coroutines (`Coroutine<T>`).

For full specifications and formatting rules, see
[docs/SPEC.md](../../../docs/SPEC.md) and
[docs/style_guide.md](../../../docs/style_guide.md).

## 1. Formatting & Style Rules (`style_guide.md`)

- **Line length**: Maximum **80 characters** per line.
- **Indentation**:
  - Block bodies: **2 spaces**.
  - Multi-line statement continuations: **4 spaces**.
  - Multi-line parameter lists or call arguments: align with the opening `(`.
  - Multi-line constructor chaining (`: Parent1(...), Parent2(...)`): indent
    each parent initializer **4 spaces**, with `{` on the final parent line.
- **Semicolons**: Every statement must end with `;`, except standalone control
  flow blocks ending in `}` (`if`, `while`, `for`, statement `match`).
- **Comments**: Two spaces before inline `//` comments. Supports `//` and
  `/* ... */`.
- **Parameter ordering**: Constant parameters precede mutable (`var`)
  parameters; parameters with default values come last.

## 2. Variables, Functions & Reference Exclusivity

### Variables & Mutability
- `let`: Immutable constant binding.
- `var`: Mutable variable binding or struct field.
- Module-level `let` bindings must be initialized with compile-time constant
  expressions (literals or plain struct literals, not function calls).

```sapphire
let TILE_SIZE = 32;
var current_hp = 100;
var x, y = 10.0, 20.0;
```

### Functions & Calling Conventions
- Primitive scalars (`int`, `float`, `bool`, `none`) are passed by **value**.
- Non-primitive types (`struct`, `proto`, `String`, `Array`, `Map`, `Arena`)
  are passed by **constant reference (borrow)** by default.
- Prefix a parameter with `var` for exclusive mutable borrow (`var target: Unit`).
  Callers cannot pass `let` bindings to `var` parameters.
- **Copy/CoW vs. Move-only ownership**:
  - Plain data `struct`s, primitives, `enum`s, `String`, `Range`, `proto`
    handles, and collections of Copy types copy (or CoW-share) on assignment.
    Copying a plain value `struct` or collection recursively copies nested
    plain value `struct`s and collections (isolating nested mutations) while
    preserving reference handle identity (`proto` handles, `WeakRef<T>`).
  - `Ref<T>`, `Arena`, `Coroutine<T>`, and any `struct` defining
    `func __del__()` (or holding move-only fields) are **move-only** and
    require explicit `move <ident>`.
  - `SharedRef<T>` lvalues are deeply immutable and require `.share()` or
    `move`.

```sapphire
func do_damage(attacker: Unit, var defender: Unit, bonus: int = 0): int, bool {
  let damage = attacker.stats.atk + bonus - defender.stats.def;
  defender.stats.hp = math.max(defender.stats.hp - damage, 0);
  return damage, damage > 0;
}

// Call site with named arguments:
let dmg, hit = do_damage(attacker = p1, defender = e1);
```

### Scope-Bound Reference Exclusivity & Aliasing Invariants
Within a single function or method call, a reference path (e.g. `player` or
`entity_store`) **cannot** be passed as a mutable `var` argument if it is
already referenced (mutably or immutably, including as `self`) in the same
call.
- **Subscript exclusivity**: Container projections cannot be passed to mutating
  methods on the same container (e.g. `arr.push(arr[0])` or inserting elements
  projected from the receiving collection is prohibited to prevent reallocation
  use-after-free).
- **Directional `proto` lineage exclusivity**: Mutably borrowing an ancestor
  prototype (`var base`) while borrowing a cloned descendant in the same call
  is an aliasing conflict; sibling clones and immutable dual borrows remain
  valid.
- **Deep immutability & `let Ref<T>` constness**: `SharedRef<T>` prohibits
  mutating methods and field mutations at any projection depth.
  `let r = Ref(...)` freezes inner fields and `var func` calls (use
  `var r = Ref(...)` when mutability is required).
- **Module-level `var` global reentrancy**: Non-primitive mutable module-level
  `var` bindings cannot be passed by reference if exported or if the callee
  reads or mutates them in its transitive call graph; top-level non-aliased
  method calls (`submit_btn.render()`) and `let` constants remain valid.
- Avoid cyclic back-pointers (such as `entity.entity_store = self`) where an
  entity method mutates its owning container.

## 3. Types, Optionals & Casts

### Primitive Types & Casts (`as`)
- Primitives: `int`, `float`, `bool`, `String`, `none`, `void`.
- `int` widens implicitly to `float`.
- Explicit infallible casts use `as`:
  - Numeric: `(damage as float)`, `(x as int)`.
  - Enum to underlying primitive: `(WeaponType.SWORD as String)`.
- **Built-in `assert` & `String.slice`**:
  - `assert(cond: bool, msg: String = "assertion failed"): void` checks runtime
    invariants.
  - `String.slice(start: int, end: int? = none): String` returns a 0-indexed
    half-open byte slice `[start, end)` (negative indices supported). For
    character-aware UTF-8 length and slicing (e.g., typewriter text), `import
    std.utf8;` and use `utf8.size(s)`, `utf8.offset(s, n, i)`, and `utf8.sub(s,
    start_char, end_char)`.
- **Prohibited with `as`**:
  - String parsing (`"123" as int` is forbidden; use `"123".to_int()`,
    `.to_float()`, `.to_bool()` returning optionals).
  - Struct up-casting (`enemy as Character` is strictly prohibited; use traits).

### Collections
- **Arrays (`[T]` or `Array<T>`)**: 0-indexed.
  - `arr[i]` panics on out-of-bounds; `arr.get(i)` returns `T?`.
  - Methods: `.size()`, `.empty()`, `.push(v)`, `.pop()`, `.insert(i, v)`,
    `.remove(i)`, `.clear()`, `.contains(v)`, `.map(fn)`, `.filter(fn)`,
    `.reduce(initial, fn)`, `.sort()`.
- **Maps (`[K: V]`)**: Keys must be `String`, `int`, or `enum`.
  - `map[k]` panics on missing key; `map.get(k)` returns `V?`.
  - Methods: `.size()`, `.empty()`, `.contains(k)`, `.keys()`, `.values()`,
    `.insert(k, v)`, `.remove(k)`, `.clear()`.

### Null Safety & Optionals
- Nullable type: `T?`. Empty literal is `none` (never `nil`).
- Optional chaining: `target?.get_name()` (evaluates to `String?`; nested
  optionals flatten to `T?`, never `T??`, on both property and method access).
  - **Multi-hop chains**: Because each `?.` expression evaluates to `T?`, every
    subsequent property or method access in a chain **must** also use `?.`
    (e.g. `outcome.defeated_character?.get_unit()?.name ?? ""`, never
    `outcome.defeated_character?.get_unit().name`).
- Nil-coalescing: `val ?? fallback`.
- Multi-binding `if let ?=` and `guard let ?=`:
  Use `let` for immutable bindings and `var` (never `let var`) when the
  unwrapped value needs to be mutated:
  ```sapphire
  guard let path ?= self.current_path; path.size() > 0 else {
    return;
  }

  if let node ?= path.get(idx); idx < path.size() {
    self.move_to_tile(node.x, node.y);
  }

  if var res ?= result {
    res.total_rounds += 1;
  }
  ```
- **Iteration & unwrap freeze**:
  - Collections are frozen against mutation during `for-in` loops and
    `.map()`/`.filter()`/`.reduce()`/`.sort()` callbacks.
  - In-place unwrapping (`if var target ?= ...` and
    `guard var target ?= ... else { return; }`) requires a **mutable source
    lvalue** (e.g. `self.active_item`, `var opt`) **or** `.get(k)` on a mutable
    `Map` or `Array` lvalue (`if var row ?= grid.get(y)`,
    `guard var sources ?= map.get(k) else { ... }`).
    - Prefer `if var v ?= container.get(k)` / `guard var v ?= container.get(k)`
      over `contains(k)` + `container[k]` to perform a single lookup.
    - Non-lvalue temporaries (e.g. `foo().get(k)`, `make_opt()`) and `.get(k)`
      on immutable containers are rejected at compile time.
  - Both `if var` and `guard var` freeze the source optional path or container
    lvalue while `target` is live, and both share:
    - **Field-disjoint** mutations on `self` (mutating other fields or calling
      `var func` methods that do not touch `active_item`).
    - **Post-last-use (non-lexical lifetime) unfreezing**: once the last
      statement referencing `target` finishes, the source path/container is
      unfrozen for subsequent statements (e.g., `self.finish()`). When mutating
      an outer container based on the unwrapped element (e.g., pruning an empty
      row), capture a boolean before closing the unwrap or finishing the last
      use (`var empty = false; if var row ?= m.get(k) { row.remove(x); empty =
      row.empty(); } if empty { m.remove(k); }`).
    - **Terminating early-return branch unfreezing**: inside an `if var` or
      `guard var` scope, a nested terminating branch (e.g., `if cond {
      self.finish(); return; }`) that does not reference `target` temporarily
      unfreezes the source path for that branch while keeping the freeze active
      after it.
  - **Optional chaining before indexing**: Do not chain `?.` directly into
    `?[idx]` (`a?.b?[0]` is not supported—check non-empty / unwrap with
    `if let` first).
- **Static array bounds**: Fixed-size array bounds are checked statically, and
  non-fixed-size arrays (`var arr: [T] = [];`) automatically invalidate their
  static size when passed to a `var` parameter or mutated via `.push()`,
  `.pop()`, `.insert()`, `.remove()`, or `.clear()`.

## 4. Control Flow, Pattern Matching & Coroutines

### Pattern Matching (`match`)
- Arms use `->` and **must** be separated by commas `,`.
- Multiple comma-separated patterns can share a single arm body
  (`Pattern1, Pattern2 -> body,`).
- Wildcard fallback is `... ->`.
- In value-producing `match` expressions, multi-statement block arms `{ ... }`
  **must** output their value via `yield <expr>;`.
- In statement-only `match` blocks (no assignment), `yield` suspends the
  enclosing `Coroutine<T>`.

```sapphire
func get_multiplier(weapon: WeaponType): float {
  return match weapon {
    WeaponType.SWORD -> 1.2,
    WeaponType.AXE   -> {
      print("Axe equipped");
      yield 1.0;
    },
    ...              -> 1.0,
  };
}
```

### Closures & Escape Restrictions
- Non-escaping closures (such as callbacks passed to `.map()`, `.filter()`, or
  invoked synchronously within their lexical scope) may borrow surrounding
  stack bindings freely.
- Closures that **escape**—returned from a function, stored in an outer scope,
  stored in an earlier LIFO variable, or boxed in `Ref`/`SharedRef`—**cannot**
  capture local stack non-primitives or local `var` bindings. Immutable
  primitive scalars (`let x: int`) are copied by value and allowed.
- **Trait adapters over escaping closures**: Passing a closure that captures a
  local struct (`() -> { store.draw_sorted_entities(); }`) into another struct
  returned from the same function triggers a borrow-checker error (`Cannot
  return coroutine borrowing local variable`). Define a behavioral `trait` (e.g.
  `EntityDrawer`) implemented by the struct and pass the struct as that trait
  instead.

### Coroutines (`Coroutine<T>`)
Stackless coroutines represent generators (`Coroutine<T>`) or steppable tasks
(`Coroutine<void>`):
- Suspend with `yield <expr>;` or `yield;`.
- Advance with `.step()` (returns `T?` or `none`), query completion with
  `.is_done()`, and reset with `.reset()`.
- **Yield data over borrowing `var` state across frames**: Prefer generators
  yielding target data (`Coroutine<PathNode>`) rather than holding a `var`
  borrow of an entity across multi-frame `yield`s.
- **Declaration order for stored coroutines**: When storing a `Coroutine<T>`
  in a local struct (`ctrl.turn_coroutine = run_turn(path)`), declare borrowed
  inputs (`let path = ...`) **before** the receiver struct (`var ctrl = ...`)
  to satisfy LIFO borrow-escape checks.
- **Stack-borrow escape restriction**: A coroutine invocation borrowing
  non-primitive reference arguments (or `self` on methods) cannot be returned
  or assigned to a variable that outlives any borrowed argument.
- **Suspension (`yield`) RAII safety**: Move-only RAII types (`__del__()`,
  `Arena`, `Ref<T>`, `Coroutine<T>`) cannot remain live across a `yield`
  suspension point. Execute RAII resources inside an inner `{ ... }` block that
  exits before `yield`, or move ownership before `yield`.

```sapphire
func run_enemy_turn(path: [PathNode],
                    var active_enemy: Enemy): Coroutine<void> {
  for i in range(1, path.size()) {
    let node = path[i];
    active_enemy.move_to_tile(node.x, node.y);
    while active_enemy.is_moving {
      yield;
    }
  }
  active_enemy.end_turn();
}
```

## 5. Structs, Traits, Protos & Arenas

### Structs & Mutating Methods (`var func`)
- All methods are declared inside `impl StructName { ... }`.
- `self` is **immutable by default**. Any method that modifies `self` **must**
  be declared as `var func`.
- Static methods use `static func` (`self` is unavailable).
- **Static constants (`static let`)**: Structs may declare immutable
  type-scoped compile-time constants (`static let SPEED_THRESHOLD = 5;`),
  accessed via `Struct.CONST` (and inherited by `Child.CONST`). They occupy
  zero instance layout bytes (cannot be passed to `Struct { ... }` or read on
  instances), require compile-time constant initializers, and disallow
  `static var`.
- **Finite inline struct layout**: Non-`proto` `struct`s cannot directly or
  mutually contain themselves unboxed (`var next: Node?` is a compile error).
  Break cycles with `proto` in an `Arena`, `Ref<T>`, `SharedRef<T>`, or dynamic
  `[T]`.
- **RAII destructors (`func __del__()`)**: Executed in LIFO order on scope exit
  or live `var` reassignment; `self` cannot escape `__del__()`.

### Construction-Contract Encapsulation (`__init__` vs. Plain Structs)
1. **Plain Data Structs (no `__init__`)**:
   - Instantiated with curly braces: `Stats { hp = 20, atk = 8 }`.
   - Fields can be freely read and mutated on `var` instances across modules.
   - Ideal for data components or host-interop structs using factory functions
     (`func create_enemy(...): Enemy`).
2. **Constructed Structs (`func __init__`)**:
   - Instantiated with parentheses: `Weapon(dmg = 10)`. Curly braces are
     disallowed.
   - **Field mutation lockout**: Fields cannot be mutated directly outside the
     defining module; external callers must use `var func` mutators.

### Static Structural Inheritance vs. Polymorphic Traits
- `struct Child: Parent` inlines parent fields and forwards parent methods.
- If `Parent` defines `__init__`, `Child.__init__` must chain it via colon
  syntax: `func __init__(...): Parent(...) { ... }`.
- **No duplicate `impl` methods & qualified ancestor dispatch**: Implementing
  a trait method via `impl Trait for Struct` already exposes that method on
  `Struct`; do not redefine it in `impl Struct`. When child structs override
  methods like `update(dt)` or `draw()`, invoke the ancestor implementation
  statically using `Parent.method(self, ...)` or
  `mod.Parent.method(self, ...)` (e.g. `character.Character.update(self, dt)`).
  **Never call `self.method()`** inside a trait `impl` on a child struct when
  the method shares a name with an ancestor method (e.g. `impl CameraTarget
  for Player { func get_height_offset() ... }`): the trait `impl` overrides the
  ancestor method, so `self.get_height_offset()` tail-recursively calls itself
  forever at runtime. Always use `character.Character.get_height_offset(self)`.
- **Up-casting is prohibited**: A `Child` struct cannot be cast or assigned to
  `Parent` (`enemy as Character` or `[Entity]` storing `Enemy` is a compile
  error).
- **Use Traits for Polymorphism**: Define behavioral contracts with `trait` and
  `impl Trait for Struct`. Trait methods may declare optional default bodies
  (`{ ... }`), and child structs may partially override inherited trait methods
  while inheriting the remaining methods from their parent:
  ```sapphire
  trait Combatant {
    func get_unit(): Unit;
    var func set_hp(hp: int);
    func is_alive(): bool { return self.get_unit().hp > 0; }
  }
  ```

### Prototypal Delegation (`proto` & `clone` in `Arena`)
For runtime state delegation and archetypes (both `struct` and `proto` types
can implement behavioral `trait`s via `impl Trait for ProtoName`):
- **Mutable `var` required for allocation**: Allocating via `in <arena>` mutates
  the arena; local arenas, arena parameters (`var a: Arena`), and struct-owned
  arenas (`var arena: Arena;` on a mutable receiver) **must** be declared `var`.
- **Reassignment, field order, & escape rules**:
  - Reassigning (`a = Arena();`) or moving (`move a`) a local `Arena` destroys
    or transfers the prior arena and invalidates local variables backed by it.
  - Struct `Arena` fields cannot be reassigned after `__init__` and **must** be
    declared *before* dependent `proto` fields so LIFO teardown drops `proto`
    fields first.
  - Arena-backed values obey lexical + same-scope LIFO declaration order and
    cannot escape via returns, outer `var` sinks, or `Ref()`/`SharedRef()`.
  - **Move-only propagation**: Because `Arena` is move-only, place `var arena:
    Arena;` on a single-owner struct (not a struct shared across multiple
    subsystems) and construct child structs directly (`context = move ctx`)
    rather than partial-moving fields off an intermediate base struct.
  - **Closed-world trait heap-boxing (`Ref<T>` / `SharedRef<T>`)**: Structs
    containing closed-world `trait` fields (including host resource handle
    traits like `graphics.Image`/`graphics.Quad` and struct-only traits) may be
    boxed in `Ref<T>`/`SharedRef<T>` as long as no known implementor of those
    traits is a `proto` or transitively holds an arena reference. Traits with
    `proto` implementors and unbounded generic type parameters remain rejected.

```sapphire
var arena = Arena();
proto UnitArchetype {
  var name: String;
  var stats: Stats;
}
var base_goblin = UnitArchetype {
  name = "Goblin", stats = Stats { hp = 15 }
} in arena;
var elite_goblin = clone base_goblin {
  self.stats = Stats { hp = 30 };  // Copy-on-Write isolation
};
```

## 6. Modules, Host Interop & Love2D Bindings

### Exports, Imports & `@extern`
- Single `export { ... }` block per file (everything else is module-private).
- Mutable module-level `var` bindings cannot be exported (`Cannot export
  mutable module-level variable`). Keep mutable globals module-private and
  export typed getter/setter functions (`is_combat_log_enabled()`,
  `set_combat_log_enabled(...)`) instead.
- Declare runtime globals with `@extern`:
  ```sapphire
  @extern
  var love: love2d.LoveEngine;
  ```

### Love2D Bindings (`sapphire/lib/love2d/`) & Trait Rules
- **Host API Traits (`static func`)**: `graphics.Graphics`, `timer.Timer`,
  `keyboard.Keyboard`, and `mouse.Mouse` declare module functions with
  `static func` (transpiling to Lua dot syntax `love.graphics.rectangle(...)`).
- **Resource Handle Traits (implicit `self`)**: `graphics.Image`, `graphics.Quad`,
  `graphics.Canvas`, `graphics.Font`, `mouse.Cursor`, and `joystick.Joystick`
  use `func` / `var func` without `self` (transpiling to Lua colon syntax
  `quad:getViewport()`), while module traits use `static func` (transpiling to
  Lua dot syntax). Explicit `self` in parameter lists is a compiler error.
- **String Enums (`lib.love2d.enums`)**: Includes `DrawMode`, `FilterMode`,
  `WrapMode`, `AlignMode`, `ArcMode`, `KeyCode` (full Love2D `KeyConstant` set:
  `A`–`Z`, `Num0`–`Num9`, `F1`–`F12`, navigation/editing, modifiers/locks,
  punctuation, numpad, and misc keys), `GamepadButton`, and `GamepadAxis`.
- **Quad-less `love.graphics.draw` (`drawImageAt` / `drawCanvasAt`)**: Never
  pass `none` (`nil`) as `quad` to `drawImage` / `drawCanvas` — Love2D rejects
  `nil` in argument #2 (`Quad expected, got nil`). Branch on `if let quad ?=
  opts.quad` and call `drawImageAt` / `drawCanvasAt` when `quad` is `none`.
- When implementing mock traits (e.g. for headless unit tests), match
  `static func`, `var func`, parameter types, defaults, and `@export("...")`
  aliases exactly. Note that multiple `static func`s sharing an
  `@export("draw")` alias on the same mock struct collide on the single Lua
  table key `draw` (the last definition wins), so assertions should check call
  counts/coordinates rather than overloaded variant names.

## 7. Testing with `std.testing`

Test suites must be declared as `struct FooTestSuite {}` + `impl
testing.TestCase for FooTestSuite` (never `test FooTestSuite { ... }`). Because
`set_up()` and `tear_down()` mutate fields on `self`, declare them with
`var func`:

```sapphire
import std.testing;

struct MathTestSuite {
  var base: int;
}

impl testing.TestCase for MathTestSuite {
  var func set_up() {
    self.base = 10;
  }

  var func tear_down() {
    self.base = 0;
  }

  @test
  func test_add() {
    self.expect_eq(self.base + 5, 15);
  }
}
```

### Unit Testing Best Practices
- **Non-fatal `expect_*` vs. fatal `assert_*`**: Use `testing.expect_eq`,
  `testing.expect_true`, `testing.expect_false`, and `testing.expect_none` for
  normal test assertions. Reserve `testing.assert_*` for preconditions needed
  to safely continue the test (e.g. checking collection `.size()` before
  accessing an element or verifying a value is not `none`).
- **Self-documenting fixtures**: Pass plain structs with defaulted fields
  (e.g. `Stats { hp = 20, atk = 10 }`) and named arguments to test factory
  helpers instead of long positional number lists.
- **True `proto`/`clone` CoW tests**: When testing `proto` delegation in an
  `Arena`, leave inherited fields untouched inside the `clone` block so the
  system under test triggers Copy-on-Write mutation on the clone while the base
  prototype's state remains unchanged.

## 8. Performance & Writing Efficient Sapphire Code

- **In-place nested container mutation (`if var`)**: Assigning a local map,
  array, or struct back into a container (`grid[y] = row`) triggers a value
  copy to preserve value semantics. Inside a loop over columns,
  copy-out/write-back (`var row = grid.get(y) ?? {}; row[x] = true;
  grid[y] = row;`) turns row population into O(W^2) table copying. Mutate
  existing inner containers in place via `if var`:
  ```sapphire
  func set_coord_flag(x: int, y: int, var grid: [int: [int: bool]]) {
    if var row ?= grid.get(y) {
      row[x] = true;
    } else {
      grid[y] = { x: true };
    }
  }
  ```
- **Prefer non-optional containers in hot loops**: Use `[T]` and `[K: V]`
  rather than `[T?]` or `[K: V?]` whenever elements are always present.
  Non-optional collections hit unwrapped Lua fast paths (no `none` sentinel
  wrapping/unwrapping on indexing or iteration) and use shallow copy fast paths
  when element types are immutable.
- **Keep hot data records as plain non-`proto` structs**: Non-`proto`,
  single-inheritance value structs with flat fields compile to Python
  `__slots__` classes, presized Lua table constructors, and direct field-copy
  helpers. Reserve `proto`/`clone` in an `Arena` for genuine archetype
  delegation and CoW sharing.
- **Hoist outer container lookups & accumulators out of inner loops**: Unwrap
  outer rows once before iterating columns (`if let row ?= data.get(y)` before
  `for x in range(width)`), and accumulate per-pass counts in a local `var`
  (writing back to a map key once after the loop) instead of reading and
  writing a map entry on every iteration.
- **Measuring performance in Love2D & LuaJIT**: Time hot paths with
  `love.timer.getTime()` (or FFI `clock_gettime` in headless `luajit`), inspect
  JIT compilation ratios and line hotspots with `luajit -jp=vlF` (`jit.p`), and
  check for trace compilation aborts with `luajit -jv` (`jit.v`). Avoid
  `debug.sethook` during performance profiling because it disables JIT traces.

## 9. Common Cross-Language Pitfalls

Quick checklist of frequent mistakes when switching from Rust, Swift, Python,
or Lua:

- **Null literal**: Always use `none` (never `nil`, `None`, or `null`).
- **Optional unwrapping**: Use `?=` (`if let x ?= opt`, `guard var x ?= opt`),
  never `=`, and use `var` (never `let var`) for mutable bindings.
- **Semicolons & `match` commas**: Every statement ends with `;` (except
  standalone `if`/`while`/`for`/statement-`match` blocks and `export { ... }`
  manifests). Every `match` arm uses `->` and ends with `,`; wildcard is
  `... ->`; value-producing block arms return via `yield <expr>;`.
- **Parameter order**: Immutable (`const`) parameters first, mutable (`var`)
  parameters next, defaulted parameters last.
- **No struct up-casting**: `Child as Parent` is prohibited; use `trait`s.
- **Optional chaining**: Repeat `?.` on every hop after the first (`a?.b()?.c`);
  do not chain `?.` into `?[idx]` (unwrap with `if let` first).
- **Container unwrap freeze**: `if var v ?= m.get(k)` freezes `m` until the
  last use of `v`; capture a flag or finish using `v` before mutating `m`.
- **Module scope**: No executable procedural statements at module scope;
  module-level `let` initializers must be compile-time constant expressions.

