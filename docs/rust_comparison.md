# Sapphire vs. Rust

This document compares Sapphire's architecture and language design with
**Rust**, focusing on memory management, polymorphism, ergonomics, and
compilation model.

## 1. Overview & motivation

Rust demonstrates that compile-time ownership and affine types can provide
memory safety and deterministic performance without garbage collection.
However, mechanisms such as explicit lifetime annotations (`'a`), borrow
checker constraints on cyclic or self-referential structures, the lack of
structural code reuse, and long compilation times can add friction during
development and prototyping.

Sapphire targets a different balance:
* **Memory safety without lifetimes**: Non-primitives are borrowed by constant
  reference at call sites by default, while local/field assignments store owned
  values (Copy/CoW or move-only RAII), replacing `'a` lifetime annotations with
  call-site exclusivity, iteration freezes, and lexical/LIFO escape checks.
* **Prototyping & dynamic ergonomics**: Opt-in prototypal state delegation
  (`proto` / `clone`) in mutable lexical `Arena`s simplifies mutable graph and
  entity modeling, while `Ref<T>` and deeply read-only `SharedRef<T>` handle
  heap topologies without `Rc<RefCell<T>>` panics.
* **API clarity**: Modern ergonomics such as Swift-style `guard` statements,
  named arguments, and explicit optionals reduce syntactic noise.

## 2. Detailed pain-point analysis

### 2.1 Lifetime annotations (`'a`) and borrow-checker constraints

* **The Rust pain point**:
  Rust requires developers to explicitly annotate references with lifetimes
  (`&'a T`, `<'a, 'b: 'a>`) whenever references cross function boundaries or
  reside inside structs. Adding a borrowed reference can require propagating
  lifetime parameters onto enclosing structs and functions. Additionally, safe
  Rust strictly forbids returning references to data created inside an inner
  block or moving values while borrowed.
* **Sapphire's solution**:
  Sapphire achieves reference safety without lifetime annotations:
  1. **Const-reference parameters & owned storage**: Non-primitive types
     (`struct`, `Array`, `Map`, `String`, `proto`) are passed to functions by
     **constant reference** by default without `&` syntax, while struct fields
     and local bindings hold owned Copy/CoW or move-only values rather than raw
     stack borrows.
  2. **Call-site exclusivity & collection freeze**: Instead of global `'a`
     lifetime subtyping, Sapphire enforces compile-time call-site reference
     exclusivity across member and subscript paths (`items.push(items[0])` is
     rejected), freezes collections during `for-in` and `.map`/`.filter`
     iteration, and blocks reentrant module-level `var` global aliasing
     ([docs/SPEC.md (Scope-Bound Aliasing Rules)](SPEC.md#scope-bound-aliasing-rules-call-site-reference-exclusivity)).
  3. **By-value returns with RVO**: Returning references to local stack frames
     (or escaping stack-capturing closures/coroutines) is statically
     prohibited. Returning structs is done by value with guaranteed
     **return-value optimization (RVO)** copy elision directly into the
     caller's stack frame
     ([docs/SPEC.md (Calling Conventions)](SPEC.md#calling-conventions-vs-storage-semantics)).
  4. **No lifetime syntax**: The language contains no lifetime parameters or
     lifetime subtyping rules.
  5. **Collection mutation ergonomics**: In Rust, mutating two elements of the
     same slice or vector simultaneously requires `slice::split_at_mut` or
     `slice::swap`, and removing elements during iteration requires
     `Vec::retain` or index loops. Sapphire provides native `arr.swap(i, j)`
     to swap elements in place (including move-only RAII types, with negative
     index support) without unsafe or split borrowings, and provides in-place
     functional filters (`arr.filter(fn, in_place = true)`) for clean in-place
     removal.

### 2.2 Graphs, cyclic structures, and self-referential data

* **The Rust pain point**:
  Creating graphs, trees with parent pointers, doubly linked lists, or cyclic
  entity structures in safe Rust is constrained by borrow checker rules.
  Managing cycles typically requires reference-counted wrappers
  (`Rc<RefCell<T>>` / `Arc<Mutex<T>>`), index-based arrays, or `unsafe` blocks.
* **Sapphire's solution**:
  1. **Opt-in prototypal state delegation (`proto` & `clone`)**: Prototypal
     inheritance allows runtime objects to delegate state to an active
     prototype
     ([docs/SPEC.md (Prototypal State Delegation)](SPEC.md#prototypal-state-delegation-proto-clone)).
     Clones dynamically delegate field reads to their prototype, allowing
     state sharing without reference counting or runtime `RefCell` panics.
  2. **Copy-on-Write (CoW) mutation safety**: When a clone mutates a nested
     reference field, Sapphire's runtime automatically intercepts the write,
     performs a shallow copy of that nested reference on the clone, and applies
     the mutation. Directional lineage exclusivity prevents mutating a base
     prototype while borrowing one of its clones in the same call.
  3. **Mutable lexical arenas (`var a = Arena()`) & smart heap references**:
     Mutable cyclic graphs and `proto` instances reside in explicit mutable
     arenas (`Entity { ... } in my_arena`), running LIFO `__del__()` destructors
     and bulk-freeing upon scope exit while scope/LIFO escape checks prevent
     dangling references
     ([docs/SPEC.md (Memory Architecture)](SPEC.md#memory-architecture-arenas-smart-references)).
     For heap lifetimes outliving lexical scopes, `Ref<T>` provides unique
     ownership and `SharedRef<T>` / `WeakRef<T>` provide deeply immutable
     shared DAG topologies.

### 2.3 Structural code reuse and forwarding boilerplate

* **The Rust pain point**:
  Rust intentionally avoids struct inheritance. While this avoids traditional
  OOP fragility, sharing common fields or behavior requires manual composition
  (embedding `struct Base` inside `struct Derived`) followed by writing
  forwarding methods for every method on `Base`.
* **Sapphire's solution**:
  1. **Syntactic delegation (`struct Child: Parent1, Parent2`)**: Sapphire
     permits structural inheritance syntax, but treats it strictly as
     **compile-time syntactic delegation**
     ([docs/SPEC.md (Static Structural Inheritance)](SPEC.md#static-structural-inheritance)).
     The compiler inlines/nests parent layouts and automatically generates
     method-forwarding wrappers.
  2. **Zero runtime dispatch penalty**: Because forwarding is resolved
     statically at compile time, the calls direct-dispatch with no pointer
     chasing, and are prime candidates for full inlining.
  3. **Strict prohibition of up-casting (`Child as Parent`)**: Sapphire
     forbids casting child structs to parent structs. This eliminates object
     slicing, eliminates method-dispatch ambiguities, and prevents accidental
     runtime indirection.

### 2.4 Polymorphism without vtables or object-safety constraints

* **The Rust pain point**:
  Dynamic polymorphism in Rust relies on trait objects (`dyn Trait`), which:
  - Incur vtable lookups and 2-word fat pointer overhead.
  - Suffer from strict "object safety" rules: traits cannot use generics or
    methods returning `Self`.
  - Prevent compiler inlining across dynamic call sites.
* **Sapphire's solution**:
  1. **Monomorphization by default**: Generic structs, functions, and
     implementations are fully monomorphized at compile time with zero runtime
     overhead
     ([docs/SPEC.md (Generics & Parametric Polymorphism)](SPEC.md#generics-parametric-polymorphism)).
  2. **Zero-vtable heterogeneous trait collections (`[Trait]`)**: An array
     typed as `[Renderable]` can store any struct implementing `Renderable`
     without vtables or fat pointers
     ([docs/SPEC.md (Traits)](SPEC.md#traits-compile-time-contracts-implicit-subtyping)).
     The native compiler synthesizes an internal closed tagged union (sum type)
     with contiguous memory layout and inlinable jump/branch tables to direct
     static function calls.
  3. **Data-only dynamic delegation**: Methods on `proto` objects are
     dispatched statically based on concrete type; only state delegation is
     dynamic.
  4. **Explicit open-boundary dynamic trait objects (`Dynamic<Trait>`)**:
     Unlike Rust where `dyn Trait` is often reached for inside crates, Sapphire
     isolates dynamic vtables to explicit `Dynamic<Trait>` wrappers used solely
     when crossing open dynamic library boundaries where whole-program closed
     tagged-union analysis cannot be performed
     ([docs/builtins.md](builtins.md#dynamic)).

### 2.5 Compilation speed and iteration loops

* **The Rust pain point**:
  Rust's strict type system and compile times (monomorphization cascades and
  LLVM optimization passes) can slow down exploratory iteration. In domains
  like game development or simulations, tweaking logic, balance numbers, or
  component layouts often requires extensive recompilation.
* **Sapphire's solution**:
  1. **Live hot-reloading (`sapphire run --dev`)**: Sapphire natively watches
     source files, performs fast incremental recompilation, patches living
     in-memory prototypes and structs in place, and triggers `@on_reload`
     lifecycle callbacks without resetting runtime application state
     ([docs/SPEC.md (Live Hot-Reloading)](SPEC.md#live-hot-reloading-on_reload-lifecycle-hook)).
  2. **High-level expressiveness**:
     - Python-style string interpolation: `f"Player {name} has {hp} HP"`.
     - Named parameters with default values:
       `attack(defender = enemy, bonus = 10)`.
     - Multiple return values with destructuring: `let x, y = get_pos();`.
     - Top-level scripting: Execution can start immediately without boilerplate
       `fn main()` harnesses.

### 2.6 Control flow & error/optional ergonomics

* **The Rust pain point**:
  Handling optional values and fallibility in Rust can lead to nested `match`
  or `if let` blocks. While Rust's `?` operator is powerful for early returns
  with `Result`, safe unwrapping of `Option` often requires `.as_ref()`
  conversions, and Rust lacks a construct like Swift's `guard` to promote
  unwrapped values into outer scope.
* **Sapphire's solution**:
  1. **Swift-style `guard` statements**:
     ```sapphire
     func process(users: [String: User], id: String): int {
       guard let user ?= users[id]; user.is_active else {
         return -1;
       }
       // `user` is automatically promoted to non-optional User in outer scope
       return user.score;
     }
     ```
     `guard` keeps the "happy path" un-indented and cleanly exits early on
     precondition failures
     ([docs/SPEC.md (Guard Statements)](SPEC.md#guard-statements-guard-else-)).
  2. **Rich optional syntax**:
     - Optional modifier (`T?`) with `none`.
     - Semicolon-separated init headers:
       `if let target ?= enemy; target.hp > 0 { ... }`.
     - Nil-coalescing fallback: `let active = target ?? default_player;`.
     - Optional chaining: `let name = target?.get_profile()?.name;`.
  3. **Deterministic cleanup without `try`/`finally`**:
     Deterministic RAII via `__del__()` destructors and lexical `{ ... }`
     blocks ensuring LIFO teardown without runtime exception overhead
     ([docs/SPEC.md (Deterministic Destructors)](SPEC.md#deterministic-destructors-__del__)).

## 3. Explicit trade-offs: what Sapphire gives up vs. Rust

Sapphire's design intentionally chooses ergonomics and simplicity in areas
where Rust chooses absolute fine-grained control:

| Dimension | Rust | Sapphire | Rationale / concession in Sapphire |
| :--- | :--- | :--- | :--- |
| **Heap memory granularity** | Individual heap allocations (`Box<T>`) freed immediately when dropped. | Stack-first + mutable lexical `Arena`s + `Ref<T>` / deeply read-only `SharedRef<T>`. | **Trade-off:** Individual objects within an `Arena` cannot be freed independently prior to whole-arena teardown, and `SharedRef<T>` forbids interior mutation. In exchange, lifetime annotations and `RefCell` panics are eliminated. |
| **Shared-memory concurrency** | Multi-threaded shared state via `Send`/`Sync` and `Arc<Mutex<T>>`. | Share-nothing thread-local isolates with message passing. | **Trade-off:** Arenas, `SharedRef<T>`, and globals cannot be shared directly across OS threads. In exchange, data races are impossible and standard refcounts avoid atomic overhead. |
| **Interior reference returns** | Can return references to struct fields using matching lifetimes (`fn get<'a>(&'a self) -> &'a Field`). | Statically forbidden. Structs must be returned by value (via RVO) or copied. | **Trade-off:** Prevents returning zero-copy sub-field references from local stack allocations. In exchange, eliminates dangling references and lifetime parameters. |
| **Dynamic proto indirection** | Flat memory layouts; all layout known statically. | Standard `struct`s are flat; `proto` types use lookup and shadow tables. | **Trade-off:** Cloned `proto` property lookups carry minor pointer-chasing overhead. In exchange, grants dynamic live state delegation. |
| **Closed vs. open polymorphism** | Trait objects (`dyn Trait`) can be extended across crates without recompilation (open set). | Closed tagged unions for `[Trait]` within modules; explicit `Dynamic<Trait>` for open boundaries. | **Trade-off:** Internal collections require whole-program or module visibility of implementors for zero-vtable optimization. `Dynamic<Trait>` explicitly opts into vtables when crossing open library boundaries. |
| **Toolchain & native target** | Mature LLVM native compiler producing optimized machine code. | Transpiles to Python / Lua 5.1; experimental LLVM generator in progress. | **Trade-off:** Sapphire prioritizes fast prototyping, host engine integration (e.g. Love2D), and syntax stabilization before finalizing its native Rust/LLVM compiler. |

## 4. Feature-by-feature comparison matrix

| Feature | Rust | Sapphire | Sapphire advantage / difference |
| :--- | :--- | :--- | :--- |
| **Reference syntax** | Explicit `&T`, `&mut T` | Passed by constant reference by default; `var` for mutable parameters | Clean syntax without visual pointer markers |
| **Lifetime annotations** | Mandatory for reference-holding structs and cross-scope borrows (`'a`) | None | Eliminates lifetime annotations via call-site exclusivity and owned storage |
| **Aliasing rules** | Static borrow checker (`&T` XOR `&mut T` across entire lifetimes) | Scope-bound call-site exclusivity + collection iteration freeze | Focused, predictable rules without cross-struct `'a` cascades |
| **Cyclic / graph data** | Requires `Rc<RefCell<T>>`, unsafe, or index generational arenas | Mutable `proto` / `struct` in `var` `Arena`; read-only `SharedRef<T>` / `WeakRef<T>` | Direct state delegation in arenas without `RefCell` runtime panics |
| **Structural reuse** | Composition only; manual forwarding boilerplate | Syntactic delegation (`struct Child: Parent`) with auto-forwarding | Zero-vtable code reuse without forwarding boilerplate |
| **Up-casting** | Not allowed on structs; allowed via `dyn Trait` | Strictly forbidden (`Child as Parent` rejected) | Eliminates object slicing and method override ambiguity |
| **Dynamic dispatch** | Vtables via `dyn Trait` fat pointers | Zero vtables by default; monomorphized traits and closed tagged unions; opt-in `Dynamic<Trait>` | Eliminates vtables in application code while preserving open-boundary ABI flexibility |
| **Iteration & dev loops** | Full native recompile; no hot reload | Live hot-reloading (`--dev`) with in-place metatable patching | Instant game/simulation tweaking without state loss |
| **Optional unwrapping** | `if let Some(x) = opt`, `match`, `?` | `if let x ?= opt`, `guard let x ?= opt else`, `??`, `?.` | Swift-style readability; un-indented guard promotion |
| **Destructors & RAII** | `Drop::drop` | Move-only `__del__()` (with RVO & drop flags) and lexical `{ ... }` blocks | Deterministic LIFO scope destruction without exception overhead |
| **Pairwise collection mutation** | `slice::swap`, `split_at_mut`, `Vec::retain` | Native `arr.swap(i, j)` and `arr.filter(..., in_place = true)` | Built-in safe in-place swaps (supporting negative indices) and functional in-place mutations |
| **Scriptability & embeddability** | Complex FFI; heavy binary footprint | Native Lua 5.1 / Love2D and Python transpilation; `@extern`, `@export` | Effortless integration into host game and scripting runtimes |
