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

* **Parameters**: `value` – a `String` expression (or an expression evaluated to a string via string concatenation).
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

### The range function

The `range` function produces a sequence of integers over a half-open interval
`[start, stop)`.

#### Signature and definition

```sapphire
func range(stop: int): Range
func range(start: int, stop: int): Range
func range(start: int, stop: int, step: int = 1): Range
```

* **Parameters**:
  * `stop` – Exclusive upper bound integer.
  * `start` – Inclusive lower bound integer (defaults to `0` if omitted).
  * `step` – Increment/decrement step integer (defaults to `1` if omitted).
* **Return type**: `Range` – a first-class range sequence type.

#### Description and behavior

`range` creates a half-open numerical range. It is primarily used with `for-in`
loops for count-based or step-based iteration.
* **Positive step**: Iterates while `current < stop`.
* **Negative step**: Iterates while `current > stop`.
* **Transpilation**:
  * **Python target**: Transpiles to native Python `range(...)`.
  * **Lua 5.1 target**: Transpiles to `_sapphire_range(...)` utilizing a zero-allocation stateless iterator.

#### Usage examples

```sapphire
// Iterate 0 through 4 (5 iterations)
for i in range(5) {
  print(String.from(i));
}

// Iterate 2 through 9 with step of 2
for i in range(2, 10, 2) {
  print(String.from(i));  // 2, 4, 6, 8
}

// Store a range in a variable
let r: Range = range(0, 5);
for i in r {
  print(String.from(i));
}
```

## Built-in types and structures

### String

The `String` type represents textual data encoded in UTF-8.

#### Key properties and semantics

* **Reference type**: Unlike primitive numeric types (`int`, `float`) and `bool` which have value semantics, `String` is a reference-passed type subject to Sapphire's borrow-checking rules.
* **Immutability**: Strings in Sapphire are immutable once instantiated. String operations produce new string instances rather than mutating existing data.
* **Enum conversions**: Converting an `enum` variant to `String` requires an explicit cast (`variant as String`) or `String.from(variant)`. Converting `String` to an enum variant requires explicit fallible parsing via `EnumName.from(val)`.

#### Built-in methods

Sapphire provides standard methods on `String` instances. Methods that do not find a match return `none` via optional types (`T?`) rather than throwing exceptions or returning sentinel values like `-1`.

| Method signature | Description |
| :--- | :--- |
| `String.from(val: <primitive>): String` | Static constructor intrinsic that converts any primitive (`int`, `float`, `bool`) or `enum` to a `String`. |
| `size(): int` | Returns the number of characters in the string. |
| `empty(): bool` | Returns `true` if `size() == 0`, otherwise `false`. |
| `lower(): String` | Returns a new string with characters converted to lowercase. |
| `upper(): String` | Returns a new string with characters converted to uppercase. |
| `strip(chars: String? = none): String` | Returns a copy with leading & trailing whitespace (or characters in `chars`) removed. |
| `split(sep: String? = none): [String]`  | Splits the string by `sep` delimiter into an array of substrings. |
| `contains(sub: String): bool` | Returns `true` if `sub` is present within the string. |
| `find(sub: String, start: int = 0, reverse: bool = false): int?` | Searches for `sub` and returns its index, or `none` if not found. |
| `to_int(radix: int = 10): int?` | Parses the string as an integer with optional `radix`. Returns `none` if parsing fails. |
| `to_float(): float?` | Parses the string as a floating-point number. Returns `none` if parsing fails. |
| `to_bool(): bool?` | Parses `"true"` or `"false"` (case-insensitive) as a boolean. Returns `none` if parsing fails. |

### Enum associated methods

Every custom `enum` type implicitly provides a static associated function for fallible conversion from integer discriminators or string variant names into enum values:

| Method signature | Description |
| :--- | :--- |
| `EnumName.from(val: int \| String): EnumName?` | Converts an integer discriminator or string variant name into an `EnumName?`. Returns `none` if no variant matches. |

#### Usage example

```sapphire
enum Direction {
  North = 1,
  South = 2,
}

if let d ?= Direction.from(1) {
  // d is Direction.North
}

if let d ?= Direction.from("South") {
  // d is Direction.South
}

let invalid = Direction.from(99);  // none
```

#### Conversions and casting for string-based enums

String-based enums in Sapphire (enums whose variants are assigned string values) support explicit static casting to strings and fallible runtime parsing back into enum variants.

##### 1. Explicit conversion to `String`

Converting a variant of a string-based enum to `String` requires explicit casting via `as String` or `String.from(variant)`:

```sapphire
enum LogLevel {
  Info = "INFO",
  Warn = "WARN",
  Error = "ERROR",
}

let level: LogLevel = LogLevel.Info;
let level_str: String = level as String;

// Implicit coercion to String
let msg: String = "Level: " + level;  // "Level: INFO"

// Explicit static cast via `as`
let raw_str: String = level as String;  // "INFO"

// Conversion via String.from
let str_val: String = String.from(level);  // "INFO"
```

##### 2. Fallible parsing from `String` (`EnumName.from`)

Directly casting a string to an enum variant using `as` is prohibited (e.g. `"INFO" as LogLevel` results in a compile error) because string parsing is inherently fallible. Parsing a string into a string-based enum value is accomplished via `EnumName.from(val: String)`, which performs a two-stage evaluation:

1. **Value lookup**: Evaluates whether `val` matches the assigned string value of any variant (e.g., `"INFO"` -> `LogLevel.Info`).
2. **Name lookup**: If no string value matches, evaluates whether `val` matches the identifier name of any variant (e.g., `"Info"` -> `LogLevel.Info`).
3. If neither lookup succeeds, `EnumName.from` returns `none`.

```sapphire
// Stage 1: Value lookup (matches variant value "INFO")
if let level ?= LogLevel.from("INFO") {
  // level is LogLevel.Info
}

// Stage 2: Name lookup (matches variant name "Info")
if let level ?= LogLevel.from("Info") {
  // level is LogLevel.Info
}

// Unmatched string returns none
let unknown = LogLevel.from("DEBUG");  // none
```

##### Detailed method behavior

* **`size(): int`**

  Returns the length of the string in characters (codepoints).
  ```sapphire
  let len = "Hello".size();  // 5
  ```

* **`empty(): bool`**

  Returns `true` if the string length is zero (`size() == 0`).
  ```sapphire
  let is_blank = "".empty();  // true
  ```

* **`lower(): String`**

  Returns a new string with all uppercase ASCII/Unicode characters converted to lowercase.
  ```sapphire
  let lower_str = "SAPPHIRE".lower();  // "sapphire"
  ```

* **`upper(): String`**

  Returns a new string with all lowercase ASCII/Unicode characters converted to uppercase.
  ```sapphire
  let upper_str = "sapphire".upper();  // "SAPPHIRE"
  ```

* **`strip(chars: String? = none): String`**

  Strips leading and trailing whitespace characters (`' '`, `'\t'`, `'\n'`, `'\r'`) when `chars` is `none`. If `chars` is specified, strips any characters listed in `chars` from both ends of the string.
  ```sapphire
  let clean = "  hello  ".strip();  // "hello"
  let trimmed = "///path///".strip("/");  // "path"
  ```

* **`split(sep: String? = none): [String]`**

  Splits the string into an array of substrings using `sep` as the delimiter.
  * If `sep` is `none` (default), splits on runs of whitespace.
  * If `sep` is `""`, splits the string into individual character substrings.
  ```sapphire
  // ["apple", "banana", "cherry"]
  let parts = "apple,banana,cherry".split(",");

  let words = "hello world".split();  // ["hello", "world"]
  ```

* **`contains(sub: String): bool`**

  Returns `true` if `sub` exists as a substring anywhere within the string. An empty `sub` (`""`) always returns `true`.
  ```sapphire
  let has_word = "hello world".contains("world");  // true
  ```

* **`find(sub: String, start: int = 0, reverse: bool = false): int?`**

  Searches for `sub` starting at index `start`.
  * When `reverse` is `false` (default), searches forward from left to right.
  * When `reverse` is `true`, searches backward from right to left.
  * Returns the 0-based integer index if found; returns `none` if `sub` is not present.
  ```sapphire
  let text = "hello world";
  if let pos ?= text.find("o") {
    print("Found 'o' at index: " + pos);  // 4
  }

  let last_o = text.find("o", reverse = true);  // 7
  let missing = text.find("xyz");  // none
  ```

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

// Explicit conversion from String enum variant
let prefix: String = LogLevel.Info as String;
let message = "System initialized";
let full_log = "[" + prefix + "] " + message;

print(full_log);

// Using built-in string methods
let raw_input = "  USER_NAME  ";
let clean_name = raw_input.strip().lower();  // "user_name"

if let index ?= clean_name.find("name") {
  print("Found 'name' at index: " + index);
}
```

### Array

Arrays in Sapphire represent ordered, sequential, homogeneous collections of elements.

#### Type syntax

Sapphire supports both dynamic (unbounded) arrays and fixed-size (statically bounded) arrays:
* **Dynamic array**: `[T]` where `T` is the element type.
* **Fixed-size array**: `[T; N]` where `T` is the element type and `N` is a positive integer compile-time constant.

#### Built-in methods

Sapphire provides standard methods on `Array` instances (`[T]` and `[T; N]`).

| Method signature | Description |
| :--- | :--- |
| `size(): int` | Returns the total number of elements in the array. |
| `empty(): bool` | Returns `true` if `size() == 0`, otherwise `false`. |
| `contains(element: T): bool` | Returns `true` if `element` exists in the array, otherwise `false`. |
| `map<U>(fn: (T) -> U, in_place: bool = false): [U]` | Returns an array by applying `fn` to each element. Mutates `self` in place when `in_place = true` (requires `U == T`). |
| `filter(fn: (T) -> bool, in_place: bool = false): [T]` | Returns dynamic array containing elements for which `fn` returns `true`. Mutates `self` in place when `in_place = true`. |
| `reduce<U>(initial: U, fn: (acc: U, item: T) -> U, reverse: bool = false): U` | Accumulates elements using `fn` starting from `initial`. Iterates right-to-left when `reverse = true`. |
| `reverse(in_place: bool = false): [T]` | Returns array with elements in reversed order. Mutates `self` in place when `in_place = true`. |
| `sort(by: ((T, T) -> int)? = none, reverse: bool = false, in_place: bool = false): [T]` | Returns sorted array using optional comparator `by` and optional `reverse` flag. Mutates `self` in place when `in_place = true`. |
| `join(sep: String = ", "): String` | Concatenates array elements into a string joined by `sep`. |
| `push(element: T): T` | Appends `element` to a mutable dynamic array (`var [T]`) and returns `element`. |
| `pop(): T?` | Removes and returns the last element of a mutable dynamic array (`var [T]`), or `none` if empty. |
| `insert(index: int, element: T): T` | Inserts `element` at `index` in a mutable dynamic array (`var [T]`) and returns `element`. |
| `remove(index: int): T?` | Removes and returns element at `index` in a mutable dynamic array (`var [T]`), or `none` if out of bounds. |
| `clear(): void` | Clears all elements from a mutable dynamic array (`var [T]`). |

##### Detailed method behavior

* **`size(): int`**

  Returns the length of the array in elements.
  ```sapphire
  let nums = [10, 20, 30];
  let len = nums.size();  // 3
  ```

* **`empty(): bool`**

  Returns `true` if the array contains no elements (`size() == 0`).
  ```sapphire
  let is_empty = [].empty();  // true
  ```

* **`contains(element: T): bool`**

  Returns `true` if `element` is found in the array.
  ```sapphire
  let has_two = [1, 2, 3].contains(2);  // true
  ```

* **`map<U>(fn: (T) -> U, in_place: bool = false): [U]`**

  Transforms each element in the array using the function `fn` and returns a new array. When called on a fixed-size array `[T; N]`, produces a fixed-size array `[U; N]`.
  ```sapphire
  let numbers = [1, 2, 3];
  let doubled = numbers.map(x -> x * 2);  // [2, 4, 6]
  ```

* **`filter(fn: (T) -> bool, in_place: bool = false): [T]`**

  Evaluates predicate `fn` on each element and returns a new dynamic array containing only elements that satisfy the condition.
  ```sapphire
  let numbers = [1, 2, 3, 4, 5];
  let evens = numbers.filter(x -> x % 2 == 0);  // [2, 4]
  ```

* **`reduce<U>(initial: U, fn: (acc: U, item: T) -> U, reverse: bool = false): U`**

  Reduces the array elements to a single accumulated value starting with `initial`.
  * When `reverse` is `false` (default), iterates forward from left to right (index 0 to `size() - 1`).
  * When `reverse` is `true`, iterates backward from right to left (index `size() - 1` down to 0).
  ```sapphire
  let numbers = [1, 2, 3, 4];
  let sum = numbers.reduce(0, (acc, x) -> acc + x);  // 10

  let words = ["world", "hello"];
  let sentence = words.reduce("", (acc, w) -> acc + " " + w, reverse = true);  // " hello world"
  ```

* **`reverse(in_place: bool = false): [T]`**

  Returns a copy of the array with elements in reversed order.
  ```sapphire
  let rev = [1, 2, 3].reverse();  // [3, 2, 1]
  ```

* **`sort(by: ((T, T) -> int)? = none, reverse: bool = false, in_place: bool = false): [T]`**

  Returns a sorted copy of the array.
  ```sapphire
  let sorted = [3, 1, 2].sort();  // [1, 2, 3]
  let desc = [1, 2, 3].sort(reverse = true);  // [3, 2, 1]
  ```

* **`join(sep: String = ", "): String`**

  Joins array elements into a string with delimiter `sep` (defaults to `", "`).
  ```sapphire
  let text = ["a", "b", "c"].join("-");  // "a-b-c"
  ```

* **`push(element: T): T`**

  Appends `element` to the end of a mutable dynamic array (`var [T]`) and returns `element`.
  ```sapphire
  var items = [10, 20];
  let added = items.push(30);  // items is now [10, 20, 30], added is 30
  ```

* **`pop(): T?`**

  Removes and returns the last element of a mutable dynamic array (`var [T]`), or `none` if empty.
  ```sapphire
  var items = [10, 20];
  let last_val = items.pop();  // 20
  ```

* **`insert(index: int, element: T): T`**

  Inserts `element` at `index` in a mutable dynamic array (`var [T]`) and returns `element`.
  ```sapphire
  var items = [10, 30];
  let added = items.insert(1, 20);  // items is now [10, 20, 30], added is 20
  ```

* **`remove(index: int): T?`**

  Removes and returns the element at `index` in a mutable dynamic array (`var [T]`), or `none` if out of bounds.
  ```sapphire
  var items = [10, 20, 30];
  let removed = items.remove(1);  // 20
  ```

* **`clear(): void`**

  Clears all elements from a mutable dynamic array (`var [T]`).
  ```sapphire
  var items = [10, 20];
  items.clear();  // items is now []
  ```

#### Operations and capabilities

| Operation | Syntax / example | Description |
| :--- | :--- | :--- |
| **Literal initialization** | `let numbers = [10, 20, 30];` | Instantiates an array literal. Element types must be strictly homogeneous. |
| **Index access** | `let first = numbers[0];`<br>`let item: int? = numbers[i];` | Reads element at index `i` (0-based). Constant integer index returns `T`. Dynamic index returns `T?` (`none` if out of bounds). |
| **Index mutation** | `numbers[1] = 25;` | Updates the element at index `i` on mutable array instances (declared with `var`). |
| **Iteration** | `for item in numbers { ... }` | Iterates sequentially over elements in the array. |

#### Tiered bounds-checking
For fixed-size arrays (`[T; N]`) initialized with known lengths, constant integer indices are checked at compile time by the type checker; out-of-bounds constant indices trigger a compile-time error. Dynamic array indexing with variable integer expressions returns `T?` and evaluates to `none` at runtime if out of bounds (zero runtime exceptions).

#### Type compatibility and assignability

A fixed-size array `[T; N]` is compatible with and assignable to an unbounded array target `[T]`. However, an unbounded array `[T]` cannot be assigned to a fixed-size target `[T; N]` without explicit size verification.

#### Code example

```sapphire
// Fixed-size array declaration
let scores: [int; 3] = [95, 88, 72];

// Index access & size method
let count = scores.size();
let top_score = scores[0];

// Functional chaining
let total_high_scores = scores
    .filter(s -> s >= 80)
    .reduce(0, (acc, s) -> acc + s);
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

#### Built-in methods

Sapphire provides standard built-in instance methods on `Map` instances (`[K: V]`).

| Method signature | Description |
| :--- | :--- |
| `size(): int` | Returns the total number of entries in the map. |
| `empty(): bool` | Returns `true` if `size() == 0`, otherwise `false`. |
| `contains(key: K): bool` | Returns `true` if `key` exists in the map, otherwise `false`. |
| `keys(): [K]` | Returns a dynamic array `[K]` containing all keys in the map. |
| `values(): [V]` | Returns a dynamic array `[V]` containing all values in the map. |
| `insert(key: K, value: V): V` | Inserts or updates `key` with `value` in a mutable map (`var [K: V]`) and returns `value`. |
| `remove(key: K): V?` | Removes entry for `key` in a mutable map (`var [K: V]`) and returns `V?` (`none` if missing). |
| `clear(): void` | Clears all key-value entries from a mutable map (`var [K: V]`). |

##### Detailed method behavior

* **`size(): int`**

  Returns the total number of key-value entries in the map.
  ```sapphire
  let roles = { "admin": 100, "user": 10 };
  let count = roles.size();  // 2
  ```

* **`empty(): bool`**

  Returns `true` if the map contains no entries (`size() == 0`).
  ```sapphire
  let is_empty = {}.empty();  // true
  ```

* **`contains(key: K): bool`**

  Returns `true` if `key` is present in the map.
  ```sapphire
  let has_admin = roles.contains("admin");  // true
  ```

* **`keys(): [K]`**

  Returns a dynamic array containing all keys in the map.
  ```sapphire
  let k = roles.keys();  // ["admin", "user"]
  ```

* **`values(): [V]`**

  Returns a dynamic array containing all values in the map.
  ```sapphire
  let v = roles.values();  // [100, 10]
  ```

* **`insert(key: K, value: V): V`**

  Inserts or updates `key` with `value` on a mutable map instance (`var`) and returns `value`.
  ```sapphire
  var scores = { "alice": 90 };
  let new_score = scores.insert("bob", 95);  // scores is now {"alice": 90, "bob": 95}, new_score is 95
  ```

* **`remove(key: K): V?`**

  Removes `key` from a mutable map instance (`var`) and returns its associated value as `V?`, or `none` if the key was missing.
  ```sapphire
  var scores = { "alice": 90, "bob": 95 };
  let removed = scores.remove("bob");  // 95 (as int?)
  ```

* **`clear(): void`**

  Clears all key-value entries from a mutable map instance (`var`).
  ```sapphire
  var scores = { "alice": 90 };
  scores.clear();  // scores is now {}
  ```

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

// Built-in map methods
let all_roles = user_roles.keys();
let has_guest = user_roles.contains("guest");

var mut_scores = { "alice": 100 };
mut_scores.insert("bob", 90);
mut_scores.remove("alice");

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

## Standard library

### Standard math module (`std.math`)

The `std.math` standard-library module provides a set of generic mathematical functions operating on numeric types (`int` and `float`). To use the math module, import it using `import std.math;`.

#### Available functions

| Function signature | Description |
| :--- | :--- |
| `abs<T>(x: T): T` | Returns the absolute value of `x`. |
| `sqrt<T>(x: T): float?` | Returns the square root of `x`. Returns `none` if `x < 0`. |
| `min<T>(a: T, b: T): T` | Returns the minimum of `a` and `b`. |
| `max<T>(a: T, b: T): T` | Returns the maximum of `a` and `b`. |
| `safe_div<T>(a: T, b: T): T?` | Returns `a / b`. Returns `none` if `b == 0`. |
| `log<T>(x: T, base: float? = none): float?` | Returns the logarithm of `x` (defaults to natural log `e` if `base` is omitted). Returns `none` if `x <= 0` or `base <= 0` or `base == 1`. |
| `pow<T>(base: T, exp: T): float` | Raises `base` to the power of `exp`. |
| `ceil<T>(x: T): int` | Returns the smallest integer greater than or equal to `x`. |
| `floor<T>(x: T): int` | Returns the largest integer less than or equal to `x`. |

#### Usage example

```sapphire
import std.math;

func demo_math() {
  // Absolute value & min/max
  let abs_val  = math.abs(-42);         // 42
  let smallest = math.min(10, 20);      // 10
  let largest  = math.max(3.14, 2.71);  // 3.14

  // Square root
  if let root ?= math.sqrt(16.0) {
    print(f"Square root: {root}");  // 4.0
  }

  // Exponentiation
  let p = math.pow(2.0, 3.0);  // 8.0

  // Safe division (returns `T?`)
  if let res ?= math.safe_div(10, 2) {
    print(f"10 / 2 = {res}");  // 5
  }

  let div_by_zero = math.safe_div(10, 0);  // none

  // Logarithm
  if let l10 ?= math.log(100, base = 10.0) {
    print(f"log10(100) = {l10}");  // 2.0
  }

  // Ceiling and floor
  let c = math.ceil(3.14);   // 4
  let f = math.floor(3.89);  // 3
}
```

### Disposable

The `Disposable` trait is a standard contract for any type whose instances require deterministic resource disposal (e.g. closing file descriptors, flushing buffers, releasing GPU resources, or tearing down memory arenas).

#### Definition

```sapphire
trait Disposable {
  func dispose(var self);
}
```

#### Implementing `Disposable`

```sapphire
struct FileHandle {
  var path: String;
}

impl Disposable for FileHandle {
  func dispose(var self) {
    print("Closing file: " + self.path);
  }
}

func main() {
  with let f = FileHandle { path = "data.csv" } {
    print("Processing file: " + f.path);
  }
  // `f.dispose()` is automatically called upon leaving the `with` block
}
```

## Summary of built-in features

| Built-in | Category | Key syntax / signature | Primary use case |
| :--- | :--- | :--- | :--- |
| **`print`** | Function | `print(value: String): void` | Standard output logging |
| **`range`** | Function | `range(...)` | Numeric iteration |
| **`String`** | Reference type | `String` | Immutable UTF-8 text representation |
| **`Array`** | Collection type | `[T]`, `[T; N]` | Sequential element collections with 0-based indexing |
| **`Map`** | Collection type | `[K: V]` | Key–value associative lookup (`K`: String, int, or enum) |
| **`Arena`** | Memory manager | `Arena()`, `expr in arena` | Scope-bound RAII memory allocation & safety control |
| **`Disposable`** | Trait | `func dispose(var self);` | Deterministic RAII cleanup for `with` blocks |
| **`Range`** | Iteration type | `Range()` | Type returned by `range()` for numeric iteration |
