# Sapphire language-design specification

This document establishes the foundational design, syntax rules, and architectural specifications for **Sapphire**, a new general-purpose programming language. Sapphire prioritizes predictability, type safety, explicit function signatures, and highly ergonomic prototypal inheritance without traditional class-based OOP boilerplate or virtual method table (vtable) performance penalties.

## 1. Style & formatting standards

* **Indentation:** The bodies of blocks should be indented two spaces. When
continuing a function definition's parameter list or function call site on a
subsequent line, params should be indented to align with the opening parenthesis.
* **Naming conventions:** All variable names should use `snake_case`. Built-in
functions will use `snake_case` as well; user-defined functions/methods can use
either `snake_case` or `PascalCase` but should be consistent.
* **Primitive types:** Lowercase naming (e.g., `int`, `float`, `bool`).
* **Non-primitive types:** `PascalCase` naming (e.g., `String`, `Player`,
`Vector2`) for both built-in and user-defined types.

## 2. Variable declaration & memory semantics

Variables are immutable constants by default to encourage safety. Mutability must be explicitly declared.

* **`let`**: Declares a constant variable (immutable).
* **`var`**: Declares a mutable variable.
* **Type inference:** Within function bodies, variable types are inferred by default unless explicitly annotated.

```
let speed: int = 60
let name = "Hero"    // Type inferred as String

var health = 100
health = 90          // Valid mutation
```

## 3. Optionals (null safety)

The language completely forbids null pointers. Instead, it supports type-safe optionals utilizing a Swift-style syntax with an explicit `?` modifier and a `none` keyword representing the empty state.

```
var target: Enemy? = none
let damage: int? = 15

if let active_target = target {
  // active_target is guaranteed to be non-optional within this block
}
```

## 4. Functions & parameter modes

Named functions must fully declare the types of all parameters and the explicit return value using colon syntax.

* **Primitive types**: Passed by value.
* **Non-primitive types**: Assumed to be passed by **constant reference** by default.
* **Mutable references**: Indicated by prefixing the parameter with `var`, causing it to be passed by mutable reference. Callers may not pass variables declared with
`let` to these parameters.
* **Named parameters**: Call-site arguments can be named explicitly using the `=` operator, mirroring assignment semantics and preserving the colon for types.
* **Default parameters**: Parameters can define default values using the `=` operator in the function signature. If omitted at the call site, the default value is evaluated and used instead.

```
func calculate_damage(attacker: Player, var defender: Enemy,
                      is_critical: bool = false): int {
  var base_damage = attacker.attack_power
  if is_critical {
    base_damage *= 2
  }
  defender.health -= base_damage
  return base_damage
}

// Invocation using named parameters via assignment syntax (is_critical defaults
// to false)
calculate_damage(defender = target_enemy, attacker = current_player)

// Invocation overriding the default parameter value
calculate_damage(current_player, target_enemy, is_critical = true)
```

## 5. First-class & anonymous functions

Functions are first-class citizens. To avoid double-colon confusion, function type declarations isolate the return block via an arrow token (`->`).

```
// Function type declaration
var math_op: (int, int) -> int
```

### Anonymous functions (lambdas)

Anonymous functions use an arrow-based block syntax. The arrow (`->`) is mandatory even when the return type is omitted. Type inference rules apply heavily inside function closures:

* **Single-parameter inference**: If an anonymous function takes a single parameter that can be contextually inferred, both the parentheses and the type annotation can be omitted.
* **Multi-parameter syntax**: Parentheses are required when declaring multiple parameters.

```
let numbers = [1, 2, 3, 4]

// Explicitly typed parameter and return type
let doubled = numbers.map((x: int) -> int {
  return x * 2
})

// Single parameter with return type fully inferred
let squared = numbers.map(x -> {
  return x * x
})
```

## 6. Structs & the implementation block

The primary data layout tool is the `struct` keyword. To separate data structures from behavior, methods can be defined inside a Rust-style implementation (`impl`) block as opposed to within the `struct` block, but this is not required.

Sapphire provides a Python-style `__init__` initializer syntax. The compiler
enforces that all non-optional fields be initialized within this function.

* **Implicit self**: For all non-static member functions, the `self` token is implicitly available within the body of the function.
* **Static methods**: Declared using the explicit `static` keyword. Inside static functions, `self` is unavailable.
* **Constant methods**: Non-static methods may be marked `const`, which
indicates that `self` cannot be modified.

```
struct Weapon {
  var damage: int
  var durability: int
  let name: String
}

impl Weapon {
  func __init__(dmg: int) {
    self.damage = dmg
    self.durability = 100
  }

  func use() {
    self.durability -= 1
  }

  static func create_legendary(): Weapon {
    return Weapon(dmg = 250)
  }

  const func get_name(): String {
    return self.name
  }
}
```

The following code will not compile because `sword` is a constant:

```
let sword = Weapon(...)

// This method attempts to mutate `self`, which is not allowed since `sword` is
// declared as a constant.
sword.use()
```

## 7. Inheritance & polymorphism

Sapphire implements clean, type-safe inheritance divided into a compile-time mechanism and a runtime mechanism.

### A. Static (compile-time) inheritance

Structures can inherit the field layout, methods, and default values of another structure at compile time using a colon syntax similar to that in C++.

```
struct Animal {
  var name: String
  var age: int
}

struct Cat: Animal {
  var lives: int
}
```

#### Syntactic delegation (transparent forwarding)

To retain a simple and familiar structural inheritance syntax without introducing rigid physical memory layouts, Sapphire treats the colon syntax as compiler-driven **syntactic delegation**. Under the hood, the compiler converts this inheritance into composition (field nesting) and automatically generates forwarding methods. This provides the ergonomic benefits of traditional inheritance while giving the compiler full freedom to optimize, reorder, or pack fields under the hood.

#### Alternatives for static code reuse

To support data-oriented design and decouple behaviors from layout, Sapphire supports two primary alternatives:

##### 1. Traits (compile-time monomorphization)
Traits define behavioral contracts (methods) without prescribing any physical memory layout. They are resolved entirely at compile time through monomorphization, ensuring zero runtime overhead.

```
trait Actor {
  func update()
}

struct Cat {
  var lives: int
}

impl Actor for Cat {
  func update() {
    // Concrete implementation
  }
}
```

##### 2. Explicit composition (data-oriented design)
Instead of physical inheritance, structs can explicitly compose other structures. This allows clear separation of data components, which is ideal for Entity-Component-System (ECS) architectures where systems process arrays of single components to maximize cache locality.

```
struct PhysicsComponent {
  var velocity: Vector2
  var mass: float
}

struct Player {
  var physics: PhysicsComponent
  var health: int
}
```

### B. Dynamic (run-time) prototypal inheritance via `clone`

The compiler automatically generates a built-in `__proto__` property on every struct instance to access its prototype. Manual self-referential prototype pointer definitions (like `var __proto__: Struct?`) are strictly forbidden by the compiler to prevent boilerplate antipatterns.

To avoid implicit constructor resolution bugs, true runtime prototypal delegation is executed explicitly via the `clone` keyword. Using `clone` bypasses the `__init__` function and sets up a live reference delegation back to the cloned instance. An optional initialization block syntax allows immediate local property shadowing upon cloning.

```
let base_goblin = Enemy()
base_goblin.damage = 10

let elite_goblin = clone base_goblin {
  self.health = 200  // Shadowed locally
}

print(elite_goblin.damage)  // Outputs 10 (Delegated to base_goblin)

base_goblin.damage = 15
print(elite_goblin.damage)  // Outputs 15 (Reflected live from prototype)
```

#### Structural safety constraints

To prevent the chaotic unpredictability of JavaScript-style dynamic prototypes and to keep object memory shapes optimized, Sapphire enforces **value-shadowing only** during dynamic delegation. Users are strictly forbidden from dynamically appending entirely new fields that were not defined in the source struct blueprint. This maintains layout predictability and allows the engine to optimize dynamic property lookups using fixed byte offsets and uniform bitmasks rather than expensive string-keyed hash table lookups.

#### The `__proto__` property

Every struct instance automatically exposes a built-in, compiler-generated `__proto__` property to inspect its prototype chain:
* **Immutability**: The `__proto__` property is read-only. It cannot be reassigned at runtime, preventing prototype-pollution vulnerabilities and allowing the compiler to perform layout optimizations.
* **Type safety**: For any struct `T`, the type of the `__proto__` property is the optional `T?`. Accessing the prototype requires safe optional unwrapping.
* **Prototype assignment**:
  * For instances created via a standard constructor (e.g., `Enemy()`), `__proto__` evaluates to `none`.
  * For instances created via `clone` (e.g., `clone base_goblin`), `__proto__` points to the prototype instance (in this case, `base_goblin`).
  * Since static inheritance is resolved at compile time via delegation, it does not create a runtime parent object. Therefore, statically inherited instances that are not cloned will also have their `__proto__` set to `none`.

## 8. Design decisions

This section outlines the architectural decisions and design trade-offs made in Sapphire.

### Avoiding virtual method tables (vtables)

Traditional class-based object-oriented languages rely on virtual method tables (vtables) to resolve dynamic dispatch. This introduces vtable pointer-chasing overhead and prevents compiler optimizations like function inlining. Sapphire eliminates vtables entirely by:
* Resolving dynamic behavior explicitly via runtime prototypal delegation (`clone`).
* Resolving static polymorphism via compile-time monomorphized traits.

### Avoiding physical inheritance layouts

While single, flat physical inheritance avoids vtable overhead by organizing memory contiguously, it introduces severe bottlenecks for performance-critical systems like game engines:
* **Cache-line pollution**: Grouping parent and child fields together in a single contiguous block forces unrelated fields into CPU cache lines. In data-oriented design (like ECS), updates only needing a small subset of fields (e.g., `position` and `velocity`) are slowed down by reading unrelated fields.
* **Layout rigidity**: A rigid inheritance hierarchy prevents the compiler from reordering fields across the entire structure to minimize padding bytes and reduce memory footprint.
* **Tight coupling**: Flat physical layouts tightly couple structures to their base, meaning modifications to a base struct invalidate layout offsets across all descendants and trigger cascade recompilations.

Instead of binding developers to rigid memory layouts, Sapphire decouples the ergonomic syntax of inheritance from its physical representation using compile-time syntactic delegation and monomorphized traits.
