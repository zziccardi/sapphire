# Built-in functions and types in Sapphire

This document provides a comprehensive reference for the standard built-in functions, primitive types, collections, and memory management constructs in the Sapphire language.

## Overview

Sapphire provides a set of built-in primitive types, strongly typed collections, memory-management primitives, and standard functions. Built-ins are globally available without requiring explicit module imports.

## Built-in functions

### The print function

The `print` function is Sapphire's primary output primitive for writing textual data to standard output (`stdout`).

#### Signature and definition

```sapphire
func print(value: String): void
```

* **Parameters**: `value` — a `String` expression (or an expression evaluated to a string via string concatenation).
* **Return type**: `void` (an alias for `none`).

#### Description and behavior

`print` emits the specified string followed by a newline character to standard output. When transpiling to backend target languages:
* **Python target**: Transpiles to native Python `print(value)`.
* **Lua 5.1 target**: Transpiles to native Lua `print(value)`.

#### Usage examples

```sapphire
// Simple string output
print("Hello, Sapphire!");

// Printing string expressions and variables
let user = "Alice";
let score = 100;
print("Player " + user + " achieved a score of " + score);
```

## Built-in types and structures

### String

The `String` type represents textual data encoded in UTF-8.

#### Key properties and semantics

* **Reference type**: Unlike primitive numeric types (`int`, `float`) and `bool` which have value semantics, `String` is a reference-passed type subject to Sapphire's borrow-checking rules.
* **Immutability**: Strings in Sapphire are immutable once instantiated. String operations produce new string instances rather than mutating existing data.
* **Enum interoperability**: Sapphire supports asymmetric string enum coercion. Any variant of a native `String` enum implicitly coerces to a `String` variable or parameter, whereas direct conversion from `String` to an enum variant is prohibited without explicit handling.

#### Operations and capabilities

| Operation | Syntax / example | Description |
| :--- | :--- | :--- |
| **Concatenation** | `"Hello " + name` | Concatenates two string expressions or string-convertible primitives into a new `String`. |
| **Equality** | `str1 == str2`, `str1 != str2` | Evaluates value equality across string contents. |
| **Nil-coalescing** | `opt_str ?? "default"` | Returns the fallback string when `opt_str` evaluates to `none`. |

#### Code example

```sapphire
enum LogLevel {
  Info = "INFO",
  Error = "ERROR",
}

// Implicit coercion from String enum variant
let prefix: String = LogLevel.Info;
let message = "System initialized";
let full_log = "[" + prefix + "] " + message;

print(full_log);
```

### Array

Arrays in Sapphire represent ordered, sequential, homogeneous collections of elements.

#### Type syntax

Sapphire supports both dynamic (unbounded) arrays and fixed-size (statically bounded) arrays:
* **Dynamic array**: `[T]` where `T` is the element type.
* **Fixed-size array**: `[T; N]` where `T` is the element type and `N` is a positive integer compile-time constant.

#### Operations and capabilities

| Operation | Syntax / example | Description |
| :--- | :--- | :--- |
| **Literal initialization** | `let numbers = [10, 20, 30];` | Instantiates an array literal. Element types must be strictly homogeneous. |
| **Index access** | `let first = numbers[0];` | Reads the element at index `i` (0-based indexing). |
| **Index mutation** | `numbers[1] = 25;` | Updates the element at index `i` on mutable array instances (declared with `var`). |
| **Iteration** | `for item in numbers { ... }` | Iterates sequentially over elements in the array. |

#### Compile-time bounds-checking

For fixed-size arrays (`[T; N]`) initialized with known lengths, constant integer indices are checked at compile time by the type checker. Out-of-bounds indices (`index < 0` or `index >= N`) trigger a compile-time type-checking error.

#### Type compatibility and assignability

A fixed-size array `[T; N]` is compatible with and assignable to an unbounded array target `[T]`. However, an unbounded array `[T]` cannot be assigned to a fixed-size target `[T; N]` without explicit size verification.

#### Code example

```sapphire
// Fixed-size array declaration
let scores: [int; 3] = [95, 88, 72];

// Index access (0-based)
let top_score = scores[0];

// Iterating over array elements
for score in scores {
  print("Score: " + score);
}
```

### Map

Maps in Sapphire are strongly typed, key–value associative arrays.

#### Type syntax

```sapphire
[K: V]
```

* `K` – the key type. Key types are strictly restricted to `String`, `int`, and `enum` types.
* `V` – the value type. Values can be any valid Sapphire type, including primitive types, user-defined structs, or nested collections.

#### Key constraints and rules

1. **Key restriction**: Map keys must be `String`, `int`, or an `enum`. Floating-point numbers (`float`), optionals, structs, and collections are disallowed as map keys.
2. **Homogeneity**: All keys within a map instance must share the exact same key type `K`, and all values must share the exact same value type `V`. Mixed key or value types are prohibited.

#### Operations and capabilities

| Operation | Syntax / example | Description |
| :--- | :--- | :--- |
| **Map literal** | `let map = { "a": 1, "b": 2 };` | Instantiates a map with key-value pairs separated by colons. Supports trailing commas. |
| **Key access** | `let val = map["a"];` | Accesses the value associated with the specified key using square-bracket indexing. |
| **Key insertion / update**| `map["c"] = 3;` | Inserts or updates the key-value pair on mutable map instances (`var`). |
| **Iteration** | `for key, val in map { ... }` | Iterates over key-value entries in the map using dual loop variables. |

#### Code example

```sapphire
enum Status {
  Active,
  Inactive,
}

// String-keyed map
let user_roles = {
  "admin": "Superuser",
  "editor": "Content Editor",
  "guest": "Visitor",  // Trailing commas supported & encouraged
};

// Enum-keyed map
let status_codes = {
  Status.Active: 200,
  Status.Inactive: 404,
};

let admin_role: String = user_roles["admin"];
let active_code: int = status_codes[Status.Active];

// Iterating over key-value pairs
for role, title in user_roles {
  print(role + ": " + title);
}
```

### Arena

`Arena` is Sapphire's built-in memory-management structure. It provides scope-bound allocation and deterministic RAII (Resource Acquisition Is Initialization) deallocation for prototype objects (`proto`) and standard structures (`struct`).

#### Type syntax and constructor

```sapphire
let my_arena = Arena();
```

* **Constructor**: `Arena()` instantiates an explicit arena object bound to the current lexical scope.

#### Operations and capabilities

| Mechanism / syntax | Description |
| :--- | :--- |
| **Targeted allocation (`in`)** | `let p = Point { x = 1.0, y = 2.0 } in my_arena;`<br>`let e = Enemy { hp = 100 } in my_arena;`<br>`let c = clone base_goblin in my_arena;`<br>Directs object memory allocation into an explicit `Arena` instance. |
| **Scope-bound RAII teardown** | Explicit arenas have lexical lifecycles. When an `Arena` variable exits its enclosing block, the runtime automatically tears down the arena and deallocates all registered objects. |
| **Implicit default arena** | If no explicit arena is targeted using `in`, prototype (`proto`) allocations and their clones land in an implicit default arena. |
| **Clone arena propagation** | When cloning a prototype object (`clone base`), the cloned instance automatically inherits the arena of the original prototype unless explicitly overridden with `in`. |

#### Static-escape rules

To prevent dangling pointers and reference corruption following arena teardown, the Sapphire compiler statically enforces scope-bound escape rules:

1. **Outer-scope variable escape**: A reference to an object allocated in an inner arena cannot be assigned to a variable (`let` or `var`) declared in an outer scope.
2. **Function-return escape**: A function cannot return a reference to an object allocated in a local arena created within that function's scope.
3. **Prohibited stack allocations**: `proto` instances cannot be allocated directly on the call stack without an arena.

#### Code example

```sapphire
struct Point {
  var x: float;
  var y: float;
}

proto Enemy {
  var hp: int;
  var pos: Point;
}

func demo_arena() {
  // Create an explicit arena
  let level_arena = Arena();

  // Allocate a struct inside level_arena
  let spawn_pos = Point { x = 10.0, y = 20.0 } in level_arena;

  // Allocate a proto object inside level_arena
  let boss = Enemy {
    hp = 500,
    pos = spawn_pos,
  } in level_arena;

  // Clone inherits level_arena automatically
  let minion = clone boss {
    self.hp = 100;
  };

  {
    // Local temporary arena
    let temp_arena = Arena();
    let temp_point = Point { x = 0.0, y = 0.0 } in temp_arena;

    // Leaving this block automatically tears down temp_arena and frees
    // temp_point
  }

  // Leaving demo_arena tears down level_arena, deallocating spawn_pos, boss,
  // and minion
}
```

## Summary of built-in features

| Built-in | Category | Key syntax / signature | Primary use case |
| :--- | :--- | :--- | :--- |
| **`print`** | Function | `print(value: String): void` | Standard output logging |
| **`String`** | Primitive Type | `String` | Immutable UTF-8 text manipulation & reference passing |
| **`Array`** | Collection Type | `[T]`, `[T; N]` | Sequential element collections with 0-based indexing |
| **`Map`** | Collection Type | `[K: V]` | Key-value associative lookup (`K`: String, int, or enum) |
| **`Arena`** | Memory Manager | `Arena()`, `expr in arena` | Scope-bound RAII memory allocation & safety control |
