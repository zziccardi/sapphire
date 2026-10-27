# Sapphire vs. Swift

This document compares Sapphire's architecture and language design with
**Swift**, examining shared ergonomic features as well as differences in
memory management, polymorphism, and runtime predictability.

## 1. Overview & Motivation

Swift introduced expressive syntax, value-type ergonomics, and null safety
to mainstream software development—popularizing language features such as
`guard` statements with scope promotion, optional binding, and named
parameters.

However, Swift's design reflects its role in application development across
Apple platforms, incorporating specific architectural trade-offs:

1. **Automatic Reference Counting (ARC) overhead**: Reference types (`class`)
   incur atomic retain/release overhead on assignments and copies. Cyclical
   references require manual `weak` and `unowned` annotations to avoid memory
   leaks.
2. **Dual object models & virtual method tables (vtables)**: Swift retains
   class hierarchies with dynamic method overriding via vtables, inducing
   cache misses, pointer chasing, and inhibiting compiler inlining.
3. **Existential container overhead (`any Protocol`)**: Dynamic polymorphism
   using protocol types relies on existential containers (inline buffer + heap
   fallback) and protocol witness tables, introducing allocation overhead and
   indirect dispatch.
4. **Throwable exceptions**: Error propagation uses `throws`, `try`, and
   `catch`, introducing non-local branch points and stack unwinding.
5. **Runtime heaviness & embedding friction**: Swift's extensive runtime, ABI
   resilience metadata, and multithreaded task pool make embedding into
   lightweight scripting engines, game loops, or simulation contexts
   non-trivial.

Sapphire adopts Swift-style syntax for optionals, `guard` statements, and named
arguments, while replacing class hierarchies, universal ARC, vtables, and
exceptions with a **stack-first memory model, lexical arenas, zero-vtable
delegation, and explicit fallibility**.

## 2. Detailed Pain Point & Architectural Analysis

### 2.1 Automatic Reference Counting (ARC), Retain Cycles & Memory Determinism

* **The Swift Pain Point**:
  Swift uses Automatic Reference Counting (ARC) to manage the lifetime of reference types (`class`). Every assignment, copy, or closure capture of a class instance emits atomic retain/release calls (`swift_retain` / `swift_release`). In multi-threaded programs or performance-critical loops, these atomic operations cause CPU cache synchronization stalls.

  Furthermore, bidirectional relationships (e.g. parent-child nodes, observer patterns, or delegate callbacks) form **retain cycles**, leading to silent memory leaks unless developers meticulously decorate references with `weak` or `unowned`. Destructors (`deinit`) execute only when reference counts drop to zero, leading to non-deterministic deallocation timings when instances are captured in background tasks.

* **Sapphire's Solution**:
  Sapphire eliminates universal ARC in favor of a predictable, stack-first hierarchy with lexical arenas and caller-driven ownership ([docs/SPEC.md §4](SPEC.md#4-variable-declaration--memory-semantics) & [§12.2](SPEC.md#stack-first-memory-model--arena-management)):
  1. **Stack Allocation by Default**: User-defined `struct` instances are stack-allocated by default with deterministic LIFO teardown. Destructors (`func __del__()`) execute predictably upon scope exit or loop jumps (`break`/`continue`), and local returns utilize compiler-enforced Return-Value Optimization (RVO) copy elision.
  2. **Lexical Arenas (`Arena`)**: Dynamic objects and prototypes live in explicit, lexically scoped arenas (`let arena = Arena(); let e = Entity { ... } in arena;`). When the arena exits its lexical block, all contained allocations are destroyed in bulk in zero-cost fashion. Compile-time **escape-checking** prevents inner-arena references from escaping into outer scopes or returning across function boundaries.
  3. **No Retain Cycles in Prototypes**: Cloned prototypes (`clone base`) delegate state live to their prototype without reference-counting cycles.
  4. **Explicit Move Semantics (`move`)**: Ownership transfers are explicitly declared at call sites using `move resource`, statically invalidating the source variable and preventing use-after-move bugs at compile time.
  5. **Explicit Smart Pointers for General Heap Life**: When unconstrained heap lifetimes or graph structures are required, developers opt into explicit smart references (`Ref<T>` for move-only unique ownership, `SharedRef<T>` with explicit `.share()`, and non-owning `WeakRef<T>`), avoiding invisible ARC overhead across the entire codebase.

```sapphire
// Sapphire: Deterministic LIFO teardown and scoped lexical arena
{
  let arena = Arena();

  // Allocated in arena; bulk-reclaimed when arena goes out of scope
  let goblin = Goblin { hp = 100 } in arena;
  let minion = clone goblin { self.hp = 50; };

  // FileHandle cleaned up deterministically via __del__() at block end
  let file = FileHandle("save.dat");
} // <- arena and file destroyed here; zero retain-cycle overhead
```

### 2.2 Classes, Object Slicing & Virtual Method Tables (vtables)

* **The Swift Pain Point**:
  Swift maintains a dual object model: value-type `struct`s and reference-type `class`es. Classes support single inheritance, polymorphism, and dynamic method overriding. However, class method calls dispatch through virtual method tables (vtables) or dynamic metadata lookups. This introduces pointer indirection (`instance -> metadata -> vtable -> func`), causes instruction-cache misses, and inhibits interprocedural optimizations like function inlining.

  Additionally, subtyping permits up-casting (`let animal: Animal = dog`), conflating structural reuse with dynamic polymorphism and introducing object-slicing risks or dispatch confusion.

* **Sapphire's Solution**:
  Sapphire completely eliminates classes and virtual method tables ([docs/SPEC.md §16.1](SPEC.md#avoiding-virtual-method-tables-vtables)):
  1. **No Classes**: All data types in Sapphire are `struct`s or `proto`s.
  2. **Syntactic Delegation (Auto-Forwarding)**: Structural inheritance (`struct Child: Parent1, Parent2`) is compile-time syntactic sugar for composition and generated forwarding methods ([docs/SPEC.md §11.1.3](SPEC.md#syntactic-delegation-transparent-forwarding)). The compiler inlines parent layouts and resolves forwarded calls directly to static functions, incurring zero runtime indirection and enabling full inlining.
  3. **Strict Prohibition of Struct Up-Casting**: Up-casting a child struct to a parent struct type (e.g. `cat as Animal`) is statically rejected at compile time ([docs/SPEC.md §5.2.1](SPEC.md#prohibited-conversions-with-the-as-operator)). Object slicing is physically impossible.
  4. **Data-Only Prototypal State Delegation**: Dynamic inheritance is restricted to data fields via `proto` and `clone`. Methods defined in `impl` blocks are always dispatched statically based on concrete types ([docs/SPEC.md §11.2.2](SPEC.md#structural-safety--method-dispatch-constraints)).

```swift
// Swift: Class inheritance with vtable dynamic dispatch
class Enemy {
  var health: Int = 100
  func takeDamage(amount: Int) { self.health -= amount } // Virtual dispatch
}
class Boss: Enemy {
  override func takeDamage(amount: Int) { super.takeDamage(amount: amount * 2) }
}
```

```sapphire
// Sapphire: Syntactic delegation; static resolution; zero vtables
struct Health {
  var hp: int = 100;
}
impl Health {
  func take_damage(amount: int) {
    self.hp -= amount;
  }
}

// Child composes Health; compiler generates forwarding methods statically
struct Boss: Health {
  var phase: int = 1;
}

let boss = Boss { hp = 500, phase = 1 };
boss.take_damage(amount = 20); // Statically resolved; zero vtable lookup

// Up-casting is rejected at compile time:
// let h: Health = boss; // Compile-time SemanticError
```

### 2.3 Protocol Existentials (`any Protocol`) & Witness Table Overhead

* **The Swift Pain Point**:
  Swift's protocol-oriented programming allows protocols to serve both as generic constraints (`<T: Renderable>`) and as dynamic types (`any Renderable`). When used as a dynamic type, Swift wraps the underlying value in an **existential container**:
  * An inline 3-word buffer (24 bytes on 64-bit platforms).
  * If the struct exceeds 24 bytes, Swift silently allocates heap memory to store the payload.
  * Method invocations dispatch indirectly through a Protocol Witness Table (PWT) and a Value Witness Table (VWT).

  Heterogeneous arrays (e.g. `[any Renderable]`) store arrays of existential containers, resulting in fragmented memory, pointer indirection, and unpredictable heap allocations.

* **Sapphire's Solution**:
  Sapphire achieves zero-vtable heterogeneous trait collections without fat pointers or existential containers ([docs/SPEC.md §11.1.4](SPEC.md#traits-compile-time-contracts--implicit-subtyping)):
  1. **Compiler-Synthesized Tagged Unions**: An array typed as `[Renderable]` does not use boxed containers or witness tables. Instead, the native compiler inspects all concrete struct types implementing `Renderable` and synthesizes an internal closed tagged union (sum type).
  2. **Contiguous Memory & Direct Jump Tables**: Heterogeneous trait collections are stored contiguously in memory. Iteration and method calls compile into inlinable branch/jump tables that dispatch directly to concrete static functions.
  3. **No Silent Heap Boxing**: Structs stored in trait collections never trigger silent heap promotions.

```swift
// Swift: Existential containers with witness table overhead
protocol Renderable {
  func render()
}
// Stores 40-byte existential containers; values larger than 24 bytes hit the heap
var items: [any Renderable] = [Circle(radius: 5.0), LargeMesh()]
for item in items {
  item.render() // Dynamic dispatch via Protocol Witness Table
}
```

```sapphire
// Sapphire: Zero-vtable heterogeneous collections via synthesized tagged unions
trait Renderable {
  func render();
}

// Stored contiguously as an internal closed tagged union
let items: [Renderable] = [Circle { radius = 5.0 }, Rectangle { w = 10.0, h = 4.0 }];
for item in items {
  item.render(); // Resolved via direct branch table; inlinable; zero heap boxing
}
```

### 2.4 Error Handling: Throwable Exceptions vs. Deterministic Fallibility

* **The Swift Pain Point**:
  Swift uses an exception-like error-handling model based on `throws`, `try`, `catch`, and `rethrows`. Although modern Swift has introduced typed throws (`throws(MyError)`), error propagation still introduces:
  * **Hidden control flow jumps**: Any function call marked with `try` can abort execution and jump to an enclosing `catch` block or unwind the stack.
  * **Stack unwinding runtime overhead**: Exception handling requires runtime table lookups and metadata to unwind function frames and invoke ARC releases.
  * **Interoperability complexity**: Scripting host engines (like Lua 5.1 in Love2D) cannot handle unwinding exceptions cleanly across FFI boundaries.

* **Sapphire's Solution**:
  Sapphire **completely omits throwable exceptions** (`try`/`catch`/`throw`) ([docs/SPEC.md §16.3](SPEC.md#avoiding-throwable-exceptions)):
  1. **Explicit, Type-Safe Fallibility**: Functions model fallibility exclusively through optionals (`T?`), multiple return values (`T, bool`), or tagged unions with exhaustive `match` expressions.
  2. **Predictable CPU Branching**: Without stack unwinding machinery, control flow remains entirely local and linear, making execution predictable and easily mapped to low-level target environments.
  3. **Deterministic RAII Resource Teardown**: Clean resource management does not depend on `finally` blocks or exception unwinding. Resources are cleaned up deterministically in LIFO order via struct `__del__()` destructors on lexical scope exit ([docs/SPEC.md §9.2](SPEC.md#deterministic-destructors-__del__)).

```swift
// Swift: Exception unwinding with try/catch
func loadConfig(path: String) throws -> Config {
  guard fileExists(path) else { throw ConfigError.missing }
  return try parse(path)
}

do {
  let cfg = try loadConfig(path: "settings.json")
} catch {
  print("Failed: \(error)")
}
```

```sapphire
// Sapphire: Explicit fallibility via optionals and guard; no exceptions
func load_config(path: String): Config? {
  guard file_exists(path) else { return none; }
  return parse_config(path);
}

guard let cfg ?= load_config("settings.json") else {
  print("Failed to load config");
  return;
}
// `cfg` is promoted to non-optional Config in the outer scope
```

### 2.5 Access Control: Fine-Grained Specifiers vs. Construction-Contract Encapsulation

* **The Swift Pain Point**:
  Swift provides six distinct access control levels: `open`, `public`, `package`, `internal` (default), `fileprivate`, and `private`. Developers must annotate individual struct fields, properties, initializers, and methods with these specifiers. This results in visual clutter, boilerplate member-wise initializers, and complex inheritance-visibility interactions (e.g. `open` vs `public` for subclassing).

* **Sapphire's Solution**:
  Sapphire intentionally omits member-level access control keywords in favor of a **module-manifest and construction-contract encapsulation model** ([docs/SPEC.md §9.1.1](SPEC.md#member-encapsulation-via-construction-contract) & [§13](SPEC.md#13-module-system--encapsulation)):
  1. **Module-Private by Default**: All top-level symbols (`struct`, `enum`, `trait`, `func`) are private to their source file unless explicitly listed in a single `export { ... }` block.
  2. **Encapsulation via Construction Contracts**:
     * **Plain-Old-Data Structs (no `__init__`)**: Structs without a custom constructor (e.g. `Vector2`, `Point`) have transparent, publicly readable and writable fields. No boilerplate getters and setters.
     * **Invariant-Enforcing Structs (with `__init__`)**: When a struct defines an `__init__` constructor, the compiler automatically protects its invariants. Its fields are **publicly readable, but module-write only**. External modules can read fields directly (`let dmg = weapon.damage;`), but cannot mutate them directly (`weapon.damage = 100;` triggers a compile-time error). Mutations must occur through methods declared in the struct's `impl` block.

```sapphire
// lib/game/weapon.sp
export { Weapon }

struct Weapon {
  var durability: int;
  let name: String;
}

impl Weapon {
  func __init__(name: String, durability: int = 100) {
    self.name = name;
    self.durability = durability;
  }
  func use() { self.durability -= 1; }
}

// In external module:
import lib.game.weapon;
let w = Weapon(name = "Excalibur");
print(w.durability); // Allowed: fields are publicly readable
// w.durability = 0; // Compile-time SemanticError: Invariant-enforcing struct fields are module-write only
w.use();             // Allowed: mutation through authorized methods
```

### 2.6 Concurrency & Execution: Multithreaded Actors vs. Frame-Steppable Coroutines

* **The Swift Pain Point**:
  Swift features a comprehensive structured concurrency system (`async`/`await`, `Task`, `TaskGroup`, and `actor` isolation). While powerful for I/O-bound networked applications and UI event loops, Swift's cooperative thread pool dynamically schedules tasks across OS worker threads. In simulations, physics engines, and game loops, this non-deterministic threading introduces scheduling jitter, lock contention, and frame-rate hitching.

* **Sapphire's Solution**:
  Sapphire focuses on deterministic, single-threaded cooperative execution via first-class **coroutines** (`Coroutine<T>`) ([docs/SPEC.md §8.4](SPEC.md#coroutines-coroutinet)):
  1. **Frame-Steppable Generators**: Declared with `Coroutine<T>` or `Coroutine<void>`. Use bare `yield;` to pause execution until the next tick, or `yield <expr>;` to stream values.
  2. **Explicit Step Control**: Stepped deterministically from game loops using `.step()`, `.is_done()`, and `.reset()`.
  3. **Zero Thread-Context Switching**: Eliminates multithreading race conditions, thread synchronization primitives, and non-deterministic frame scheduling.

```sapphire
// Sapphire: Deterministic frame sequencing for games and animations
func walk_and_wave(npc: NPC): Coroutine<void> {
  npc.walk_to(x = 100.0, y = 50.0);
  yield; // Pauses here; resumes on next frame tick
  npc.play_animation("wave");
  yield;
}

let anim = walk_and_wave(hero);
while !anim.is_done() {
  anim.step(); // Driven deterministically by the main game loop
}
```

### 2.7 Embeddability, Scripting Runtimes & Live Hot-Reloading

* **The Swift Pain Point**:
  Swift requires a substantial runtime layer, dynamic metadata tables, and the LLVM compiler toolchain. Embedding Swift as a guest scripting language inside a game engine or simulation runtime is difficult. Furthermore, Swift provides no native mechanism for live code hot-reloading without terminating process state.

* **Sapphire's Solution**:
  Sapphire is designed specifically for scripting host interoperability and instant developer feedback ([docs/SPEC.md §14](SPEC.md#14-host-runtime-interoperability--annotations)):
  1. **Native Host Annotations**: Host engine symbols are bound effortlessly using `@extern var love: LoveEngine;` and callbacks are exported with `@export("love.update") func update(dt: float)`.
  2. **Live Hot-Reloading (`sapphire run --dev`)**: In dev mode, Sapphire recompiles modified files on the fly, patches prototype metatables in place without losing active application/game state, and invokes `@on_reload` lifecycle hooks.
  3. **Multi-Backend Transpilation**: Compiles directly to clean Python and Lua 5.1 (e.g. for Love2D) with standard V3 source maps (`.lua.map`) and runtime call-stack demangling.

## 3. Explicit Trade-offs: What Sapphire Gives Up vs. Swift

Sapphire makes deliberate engineering concessions to prioritize systems performance, deterministic memory, and rapid simulation prototyping:

| Dimension | Swift | Sapphire | Rationale / Concession in Sapphire |
| :--- | :--- | :--- | :--- |
| **Class-Based OOP & Subclassing** | Full support for `class` inheritance, virtual method overrides, and `super` dispatch. | **No classes**. Structural inheritance is syntactic delegation; up-casting is forbidden. | **Trade-off:** Cannot build deeply nested, open class hierarchies. In exchange, vtable overhead, object slicing, and cache misses are eliminated. |
| **Open World Dynamic Polymorphism** | Open protocols (`any Protocol`) allow dynamic libraries to add conforming types at runtime. | Heterogeneous trait collections (`[Trait]`) synthesize closed tagged unions at compile time. | **Trade-off:** Storing heterogeneous traits requires module or whole-program visibility of implementors. In exchange, witness tables, heap boxing, and fat pointers are eliminated. |
| **Multithreaded Structured Concurrency** | Rich async/await runtime, actors, task groups, and OS thread pool scheduling. | Single-threaded, deterministic, frame-steppable coroutines (`Coroutine<T>`). | **Trade-off:** Does not provide automated background thread-pool dispatching for CPU-bound tasks. In exchange, delivers deterministic frame timing without thread jitter. |
| **Universal ABI Stability & SDK Interop** | Stable ABI on Apple OS platforms, runtime metadata reflection, and direct C/C++/Obj-C interop. | Lightweight host annotations (`@extern`, `@export`); targets Python and Lua backends. | **Trade-off:** Lacks native binary ABI compatibility with Apple operating system frameworks. In exchange, embeds cleanly into lightweight scripting hosts. |
| **Ecosystem & Toolchain Maturity** | Industrial compiler (Clang/LLVM), comprehensive package manager (SPM), and massive ecosystem. | Emerging toolchain (transpiler in Python/Lua, testing harness, LSP server, VS Code extension). | **Trade-off:** Sapphire is in active development with a native Rust/LLVM compiler on the roadmap. |

## 4. Feature-by-Feature Comparison Matrix

| Feature | Swift | Sapphire | Architectural Divergence / Sapphire Rationale |
| :--- | :--- | :--- | :--- |
| **Statement Termination** | Newline-separated; semicolons optional | **Mandatory semicolon (`;`)** | Eliminates parsing ambiguities across multi-line expressions and blocks |
| **Variable Declarations** | `let` (immutable), `var` (mutable) | `let` (immutable), `var` (mutable) | Identical constant-by-default philosophy |
| **Null Representation** | `nil` | `none` | Clean null-safety without raw pointers |
| **Optional Binding Syntax** | `if let x = opt` or `if let x` | `if let x ?= opt` | Explicit `?=` unwrapping assignment operator |
| **Precondition Enforcement** | `guard let x = opt else { ... }` | `guard let x ?= opt else { ... }` | Shared scope-promotion semantics; Sapphire uses semicolon binding delimiters and boolean operator condition combinations |
| **String Interpolation** | `"Hello \(name)"` | `f"Hello {name}"` | Python-style f-strings with support for nested quotes and brace escaping |
| **Parameter Semantics** | Value copy by default; `inout` for mutation | **Constant reference borrow** by default; `var` for mutable parameters | Avoids unnecessary struct copying without requiring reference punctuation |
| **Call-Site Aliasing Rules** | Exclusive access memory law (dynamic/static) | Compile-time scope-bound call-site reference exclusivity | Guarantees mutable borrow exclusivity at call sites without lifetime syntax |
| **Ownership Transfers** | Swift 5.9+ `consume` keyword on `~Copyable` | Caller-driven `move resource` keyword | Statically invalidates source variable; compile-time use-after-move prevention |
| **Inheritance Model** | Single class inheritance + Protocol conformance | Syntactic delegation (`struct Child: Parent`) + Traits | Composition with auto-generated forwarding; zero vtables |
| **Up-Casting** | Allowed on classes (`dog as Animal`) | **Strictly prohibited** (`Child as Parent` rejected) | Completely prevents object slicing and method-dispatch ambiguities |
| **Dynamic Polymorphism** | Existential containers + Protocol Witness Tables | Compiler-synthesized closed tagged unions for `[Trait]` | Contiguous memory storage; inlinable jump tables; zero heap allocation |
| **Prototypal Inheritance** | None | First-class opt-in `proto` and `clone` with Copy-on-Write | Rapid simulation and template-based object prototyping |
| **Memory Hierarchy** | ARC for classes; stack/value copy for structs | Stack-first default; lexical `Arena`s; explicit `Ref<T>` | Deterministic LIFO scope destruction; zero universal retain/release overhead |
| **Destructors & RAII** | `deinit` on classes (run on ARC deallocation) | `func __del__()` on structs (run on lexical scope exit) | Deterministic RAII with Return-Value Optimization (RVO) copy elision |
| **Error Handling** | `throws`, `try`, `catch`, `rethrows` | Optionals (`T?`), multi-returns (`T, bool`), `match` | Zero throwable exceptions or stack unwinding; explicit typed fallibility |
| **Scoped Resource Cleanup** | `defer { ... }` | Lexical blocks & `guard let` (`__del__` RAII) | Deterministic LIFO teardown with safe fallible unwrapping |
| **Access Control** | `open`, `public`, `package`, `internal`, `private` | File-private by default; single `export { ... }` manifest | Construction contracts govern field mutability; zero keyword clutter |
| **Concurrency / Yielding** | Async/await, Actors, Task Groups (multithreaded) | Frame-steppable coroutines (`Coroutine<T>`, `yield`) | Deterministic, cooperative tick-based stepping for game and simulation loops |
| **Host Interoperability** | Native C/C++/Obj-C bridging headers | `@extern`, `@export`, trait-based engine bindings | Zero-overhead bindings to game engines (e.g. Love2D) and host scripting runtimes |
| **Development Loops** | Native compilation via LLVM; no live hot-reload | Dev-mode live hot-reload (`sapphire run --dev`) | In-place metatable updates and `@on_reload` hooks without losing runtime state |
