# Sapphire vs. Rust

This document compares Sapphire's architecture and language design with
**Rust**, focusing on memory management, polymorphism, ergonomics, and
compilation model.

## 1. Overview & Motivation

Rust demonstrates that compile-time ownership and affine types can provide
memory safety and deterministic performance without garbage collection.
However, mechanisms such as explicit lifetime annotations (`'a`), borrow
checker constraints on cyclic or self-referential structures, the lack of
structural code reuse, and long compilation times can add friction during
development and prototyping.

Sapphire targets a different balance:
* **Memory Safety Without Lifetimes**: Non-primitives are borrowed by constant
  reference by default, with call-site exclusivity checks replacing lifetime
  annotations.
* **Prototyping & Dynamic Ergonomics**: Opt-in prototypal state delegation
  (`proto` / `clone`) and lexical arenas simplify graph and entity modeling,
  while live hot-reloading allows fast iteration loops.
* **API Clarity**: Modern ergonomics such as Swift-style `guard` statements,
  named arguments, and explicit optionals reduce syntactic noise.

## 2. Detailed Pain Point Analysis

### 2.1 Lifetime Annotations (`'a`) and Borrow Checker Constraints

* **The Rust Pain Point**:
  Rust requires developers to explicitly annotate references with lifetimes
  (`&'a T`, `<'a, 'b: 'a>`) whenever references cross function boundaries or
  reside inside structs. Adding a borrowed reference can require propagating
  lifetime parameters onto enclosing structs and functions. Additionally, safe
  Rust strictly forbids returning references to data created inside an inner
  block or moving values while borrowed.
* **Sapphire's Solution**:
  Sapphire achieves reference safety without lifetime annotations:
  1. **Const-Reference by Default**: Non-primitive types (`struct`, `Array`,
     `Map`, `String`, `proto`) are passed by **constant reference** by default.
     Callers do not need explicit reference or pointer syntax (`&`).
  2. **Call-Site Reference Exclusivity**: Instead of complex global lifetime
     tracking, Sapphire enforces a localized, compile-time scope-bound aliasing
     check: inside a single function or method invocation, a reference path
     cannot be passed mutably (`var`) if it is already referenced elsewhere
     (mutably or immutably) within that same call
     ([docs/SPEC.md (Scope-Bound Aliasing Rules)](SPEC.md#scope-bound-aliasing-rules-call-site-reference-exclusivity)).
  3. **By-Value Returns with RVO**: Returning references to local stack frames
     is statically prohibited, preventing use-after-free bugs entirely.
     Returning structs is done by value; the compiler guarantees
     **Return-Value Optimization (RVO)** and copy elision directly into the
     caller's stack frame ([docs/SPEC.md (Calling Conventions)](SPEC.md#calling-conventions-vs-storage-semantics)).
  4. **No Lifetime Syntax**: The language contains no lifetime parameters or
     lifetime subtyping rules.

### 2.2 Graphs, Cyclic Structures, and Self-Referential Data

* **The Rust Pain Point**:
  Creating graphs, trees with parent pointers, doubly linked lists, or cyclic
  entity structures in safe Rust is constrained by borrow checker rules.
  Managing cycles typically requires reference-counted wrappers
  (`Rc<RefCell<T>>` / `Arc<Mutex<T>>`), index-based arrays, or `unsafe` blocks.
* **Sapphire's Solution**:
  1. **Opt-in Prototypal State Delegation (`proto` & `clone`)**: Prototypal
     inheritance allows runtime objects to delegate state to an active
     prototype ([docs/SPEC.md (Prototypal State Delegation)](SPEC.md#prototypal-state-delegation-proto-clone)).
     Clones dynamically delegate field reads to their prototype, allowing
     state sharing without reference counting or runtime borrow checks.
  2. **Copy-on-Write (CoW) Mutation Safety**: When a clone mutates a nested
     reference field, Sapphire's runtime automatically intercepts the write,
     performs a shallow copy of that nested reference on the clone, and applies
     the mutation. This isolates the clone's state without altering the
     prototype or causing reference corruption.
  3. **Lexical Arenas (`Arena`)**: All `proto` instances are allocated in
     explicit arenas (`Entity { ... } in my_arena`). When the arena exits its
     lexical scope, all contained instances are automatically deallocated in
     bulk ([docs/SPEC.md (Memory Architecture)](SPEC.md#memory-architecture-arenas-smart-references)).
     Escape-checking prevents inner-arena objects from escaping to outer scopes
     or returning across function boundaries.

### 2.3 Structural Code Reuse and Forwarding Boilerplate

* **The Rust Pain Point**:
  Rust intentionally avoids struct inheritance. While this avoids traditional
  OOP fragility, sharing common fields or behavior requires manual composition
  (embedding `struct Base` inside `struct Derived`) followed by writing
  forwarding methods for every method on `Base`.
* **Sapphire's Solution**:
  1. **Syntactic Delegation (`struct Child: Parent1, Parent2`)**: Sapphire
     permits structural inheritance syntax, but treats it strictly as
     **compile-time syntactic delegation**
     ([docs/SPEC.md (Static Structural Inheritance)](SPEC.md#static-structural-inheritance)). The compiler
     inlines/nests parent layouts and automatically generates
     method-forwarding wrappers.
  2. **Zero Runtime Dispatch Penalty**: Because forwarding is resolved
     statically at compile time, the calls direct-dispatch with no pointer
     chasing, and are prime candidates for full inlining.
  3. **Strict Prohibition of Up-Casting (`Child as Parent`)**: Sapphire
     forbids casting child structs to parent structs. This eliminates object
     slicing, eliminates method-dispatch ambiguities, and prevents accidental
     runtime indirection.

### 2.4 Polymorphism Without Vtables or Object-Safety Constraints

* **The Rust Pain Point**:
  Dynamic polymorphism in Rust relies on trait objects (`dyn Trait`), which:
  - Incur vtable lookups and 2-word fat pointer overhead.
  - Suffer from strict "object safety" rules: traits cannot use generics or
    methods returning `Self`.
  - Prevent compiler inlining across dynamic call sites.
* **Sapphire's Solution**:
  1. **Monomorphization by Default**: Generic structs, functions, and
     implementations are fully monomorphized at compile time with zero runtime
     overhead ([docs/SPEC.md (Generics & Parametric Polymorphism)](SPEC.md#generics-parametric-polymorphism)).
  2. **Zero-Vtable Heterogeneous Trait Collections (`[Trait]`)**: An array
     typed as `[Renderable]` can store any struct implementing `Renderable`
     without vtables or fat pointers
     ([docs/SPEC.md (Traits)](SPEC.md#traits-compile-time-contracts-implicit-subtyping)).
     The native compiler synthesizes an internal closed tagged union (sum type)
     with contiguous memory layout and inlinable jump/branch tables to direct
     static function calls.
  3. **Data-Only Dynamic Delegation**: Methods on `proto` objects are
     dispatched statically based on concrete type; only state delegation is
     dynamic.
  4. **Explicit Open-Boundary Dynamic Trait Objects (`Dynamic<Trait>`)**:
     Unlike Rust where `dyn Trait` is often reached for inside crates, Sapphire
     isolates dynamic vtables to explicit `Dynamic<Trait>` wrappers used solely
     when crossing open dynamic library boundaries where whole-program closed
     tagged-union analysis cannot be performed ([docs/builtins.md](builtins.md#dynamic)).

### 2.5 Compilation Speed and Iteration Loops

* **The Rust Pain Point**:
  Rust's strict type system and compile times (monomorphization cascades and
  LLVM optimization passes) can slow down exploratory iteration. In domains
  like game development or simulations, tweaking logic, balance numbers, or
  component layouts often requires extensive recompilation.
* **Sapphire's Solution**:
  1. **Live Hot-Reloading (`sapphire run --dev`)**: Sapphire natively watches
     source files, performs fast incremental recompilation, patches living
     in-memory prototypes and structs in place, and triggers `@on_reload`
     lifecycle callbacks without resetting runtime application state
     ([docs/SPEC.md (Live Hot-Reloading)](SPEC.md#live-hot-reloading-on_reload-lifecycle-hook)).
  2. **High-Level Expressiveness**:
     - Python-style string interpolation: `f"Player {name} has {hp} HP"`.
     - Named parameters with default values:
       `attack(defender = enemy, bonus = 10)`.
     - Multiple return values with destructuring: `let x, y = get_pos();`.
     - Top-level scripting: Execution can start immediately without boilerplate
       `fn main()` harnesses.

### 2.6 Control Flow & Error/Optional Ergonomics

* **The Rust Pain Point**:
  Handling optional values and fallibility in Rust can lead to nested `match`
  or `if let` blocks. While Rust's `?` operator is powerful for early returns
  with `Result`, safe unwrapping of `Option` often requires `.as_ref()`
  conversions, and Rust lacks a construct like Swift's `guard` to promote
  unwrapped values into outer scope.
* **Sapphire's Solution**:
  1. **Swift-Style `guard` Statements**:
     ```sapphire
     func process(users: [String: User], id: String): int {
       guard let user ?= users[id]; user.is_active else {
         return -1;
       }
       // `user` is automatically promoted to non-optional User in outer scope
       return user.score;
     }
     ```
     `guard` keeps the "happy path" un-indented and cleanly exits early on precondition failures ([docs/SPEC.md (Guard Statements)](SPEC.md#guard-statements-guard-else-)).
  2. **Rich Optional Syntax**:
     - Optional modifier (`T?`) with `none`.
     - Semicolon-separated init headers: `if let target ?= enemy; target.hp > 0 { ... }`.
     - Nil-coalescing fallback: `let active = target ?? default_player;`.
     - Optional chaining: `let name = target?.get_profile()?.name;`.
  3. **Deterministic Cleanup Without `try`/`finally`**:
     Deterministic RAII via `__del__()` destructors and scoped `with` blocks ensuring LIFO teardown without runtime exception overhead ([docs/SPEC.md (Deterministic Destructors)](SPEC.md#deterministic-destructors-__del__)).

## 3. Explicit Trade-offs: What Sapphire Gives Up vs. Rust

Sapphire's design intentionally chooses ergonomics and simplicity in areas where Rust chooses absolute fine-grained control:

| Dimension | Rust | Sapphire | Rationale / Concession in Sapphire |
| :--- | :--- | :--- | :--- |
| **Heap Memory Granularity** | Individual heap allocations (`Box<T>`) freed immediately when dropped. | Stack-first allocation + Lexical Arenas (`Arena`). | **Trade-off:** Individual objects within an arena cannot be freed independently prior to whole-arena teardown. In exchange, manual reference tracking and lifetime annotations are eliminated. |
| **Interior Reference Returns** | Can return references to struct fields using matching lifetimes (`fn get<'a>(&'a self) -> &'a Field`). | Statically forbidden. Structs must be returned by value (via RVO) or copied. | **Trade-off:** Prevents returning zero-copy sub-field references from local stack allocations. In exchange, eliminates dangling references and lifetime parameters. |
| **Dynamic Proto Indirection** | Flat memory layouts; all layout known statically. | Standard `struct`s are flat; `proto` types use lookup and shadow tables. | **Trade-off:** Cloned `proto` property lookups carry minor pointer-chasing overhead. In exchange, grants dynamic live state delegation. |
| **Closed vs. Open Polymorphism** | Trait objects (`dyn Trait`) can be extended across crates without recompilation (open set). | Closed tagged unions for `[Trait]` within modules; explicit `Dynamic<Trait>` for open boundaries. | **Trade-off:** Internal collections require whole-program or module visibility of implementors for zero-vtable optimization. `Dynamic<Trait>` explicitly opts into vtables when crossing open library boundaries. |
| **Toolchain & Native Target** | Mature LLVM native compiler producing optimized machine code. | Transpiles to Python / Lua 5.1; experimental LLVM generator in progress. | **Trade-off:** Sapphire prioritizes fast prototyping, host engine integration (e.g. Love2D), and syntax stabilization before finalizing its native Rust/LLVM compiler. |

## 4. Feature-by-Feature Comparison Matrix

| Feature | Rust | Sapphire | Sapphire Advantage / Difference |
| :--- | :--- | :--- | :--- |
| **Reference Syntax** | Explicit `&T`, `&mut T` | Passed by constant reference by default; `var` for mutable parameters | Clean syntax without visual pointer markers |
| **Lifetime Annotations** | Mandatory for reference-holding structs and cross-scope borrows (`'a`) | None | Eliminates lifetime annotations via call-site exclusivity |
| **Aliasing Rules** | Dynamic/static borrow checker (`&T` XOR `&mut T` across entire lifetimes) | Scope-bound call-site reference exclusivity | Focused, predictable rules verified at the call site |
| **Cyclic / Graph Data** | Requires `Rc<RefCell<T>>`, unsafe, or index generational arenas | Opt-in `proto`, `clone`, Copy-on-Write, and lexical `Arena` | Direct state delegation within arenas without reference-counting overhead |
| **Structural Reuse** | Composition only; manual forwarding boilerplate | Syntactic delegation (`struct Child: Parent`) with auto-forwarding | Zero-vtable code reuse without forwarding boilerplate |
| **Up-casting** | Not allowed on structs; allowed via `dyn Trait` | Strictly forbidden (`Child as Parent` rejected) | Eliminates object slicing and method override ambiguity |
| **Dynamic Dispatch** | Vtables via `dyn Trait` fat pointers | Zero vtables by default; monomorphized traits and closed tagged unions; opt-in `Dynamic<Trait>` | Eliminates vtables in application code while preserving open-boundary ABI flexibility |
| **Iteration & Dev Loops** | Full native recompile; no hot reload | Live hot-reloading (`--dev`) with in-place metatable patching | Instant game/simulation tweaking without state loss |
| **Optional Unwrapping** | `if let Some(x) = opt`, `match`, `?` | `if let x ?= opt`, `guard let x ?= opt else`, `??`, `?.` | Swift-style readability; un-indented guard promotion |
| **Destructors & RAII** | `Drop::drop` | `__del__()` (with RVO elision) and scoped `with` blocks | Deterministic LIFO scope destruction without exception overhead |
| **Scriptability & Embeddability**| Complex FFI; heavy binary footprint | Native Lua 5.1 / Love2D and Python transpilation; `@extern`, `@export` | Effortless integration into host game and scripting runtimes |
