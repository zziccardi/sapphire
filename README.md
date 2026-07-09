# Sapphire language-design specification

This document establishes the foundational design, syntax rules, and architectural specifications for **Sapphire**, a new general-purpose programming language. Sapphire prioritizes predictability, type safety, explicit function signatures, and highly ergonomic prototypal inheritance without traditional class-based OOP boilerplate or virtual method table (vtable) performance penalties.

## 1. Style & formatting standards

* **Indentation:** Exactly two spaces.
* **Naming conventions:** All variable names, function identifiers, and method identifiers must use `snake_case`.
* **Primitive types:** Lowercase naming (e.g., `int`, `float`, `bool`).
* **Non-primitive types:** `PascalCase` naming (e.g., `String`, `Player`, `Vector2`).

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

* **Primitive types:** Passed by value.
* **Non-primitive types:** Assumed to be passed by **constant reference** by default.
* **Mutable references:** Indicated by prefixing the parameter with `var`, causing it to be passed by mutable reference.
* **Named parameters:** Call-site arguments can be named explicitly using the `=` operator, mirroring assignment semantics and preserving the colon for types.

```
func calculate_damage(attacker: Player, var defender: Enemy): int {
  let base_damage = attacker.attack_power
  defender.health -= base_damage
  return base_damage
}

// Invocation using named parameters via assignment syntax
calculate_damage(defender = target_enemy, attacker = current_player)
```

## 5. First-class & anonymous functions

Functions are first-class citizens. To avoid double-colon confusion, function type declarations isolate the return block via an arrow token (`->`).

```
// Function type declaration
var math_op: (int, int) -> int
```

### Anonymous functions (lambdas)

Anonymous functions use an arrow-based block syntax. The arrow (`->`) is mandatory even when the return type is omitted. Type inference rules apply heavily inside function closures:

* **Single-parameter inference:** If an anonymous function takes a single parameter that can be contextually inferred, both the parentheses and the type annotation can be omitted.
* **Multi-parameter syntax:** Parentheses are required when declaring multiple parameters.

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

The primary data layout tool is the `struct` keyword. To separate clean data structures from behavior, methods can be defined inside a Rust-style implementation (`impl`) block.

* **Implicit self:** For all non-static member functions, the `self` token is implicitly available within the body of the function.
* **Static methods:** Declared using the explicit `static` keyword. Inside static functions, `self` is unavailable.
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

## 7. Prototypal inheritance

Sapphire implements clean, type-safe prototypal inheritance divided into a compile-time mechanism and a runtime mechanism. Manual self-referential prototype pointer definitions (like `var __proto__: Struct?`) are strictly forbidden by the compiler to prevent boilerplate antipatterns.

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

#### Performance guarantees (zero-overhead flattening)

To eliminate the historical runtime inefficiencies associated with traditional class-based inheritance—specifically virtual method table (vtable) pointer chasing—Sapphire treats static inheritance as **flat compile-time composition**. Statically inherited structures are optimized down to a single contiguous memory layout, calculating byte offsets entirely at compile time. This allows the execution engine to support direct, zero-overhead execution and efficient stack allocation for static layouts.

### B. Dynamic (run-time) prototypal inheritance via `clone`

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
