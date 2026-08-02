# Sapphire language-design specification

This document establishes the foundational design, syntax rules, and architectural specifications for **Sapphire**, a new general-purpose programming language. Sapphire prioritizes predictability, type safety, explicit function signatures, and highly ergonomic prototypal inheritance without traditional class-based OOP boilerplate or virtual method table (vtable) performance penalties.

## 1. Design philosophy & value proposition

Sapphire occupies a unique niche in the language ecosystem: it combines the **safety and bare-metal performance of a systems language** (like Rust or C++) with the **rapid prototyping ergonomics** of dynamic languages (like JavaScript or Lua) and the **expressive API clarity** of modern languages (like Swift).

Unlike other performance-oriented languages, Sapphire distinguishes itself
through four key pillars:
* **Zero-overhead static & dynamic reuse**: Inheritance is treated as
  compile-time syntactic delegation (composition and generated forwarding),
  completely eliminating virtual-method tables (vtables), pointer chasing, and
  object-slicing risks. Dynamic prototypal delegation is opt-in and data-only,
  and uses copy-on-write (CoW) to protect prototypes.
* **Scope-bound memory safety**: Non-primitive types are passed by constant
  reference by default. Compile-time scope-bound aliasing rules guarantee
  memory safety and reference validity without the visual noise of Rust-style
  lifetime annotations or C++ pointer syntax.
* **Deterministic lifecycle control**: Opt-in dynamic prototypal references
  are allocated in managed, lexically scoped arenas. The compiler enforces
  strict escape-checking to automatically tear down allocations at scope
  boundaries.
* **Modern API & host-environment ergonomics**: Native support for named
  parameters and default values makes interfaces self-documenting. First-class
  host annotations (`@extern`, `@export`) compile to zero-overhead bindings for
  interoperability with scripting environments.

## 2. Style, formatting, & comments

* **Line length**: Lines should be kept to a maximum of 80 characters.
* **Indentation**:
  * The bodies of blocks should generally be indented two spaces.
  * When continuing a statement on a subsequent line, indent with four spaces.
  * When continuing a function definition's parameter list or function call site
  on a subsequent line, params should be indented to align with the opening
  parenthesis.
* **Statement termination**: All statements must be explicitly terminated with a semicolon (`;`). This prevents syntax parsing ambiguities with multi-line statements and expressions.
* **Naming conventions**: All variable names should use `snake_case`. Built-in
functions will use `snake_case` as well; user-defined functions/methods can use
either `snake_case` or `PascalCase` but should be consistent.
  * Note that variables, functions, and structs all share the same identifier
  namespace; i.e. you cannot have a function and a struct with the same name.
* **Compile-time constants**: Global or compile-time constant expressions should use `SCREAMING_SNAKE_CASE` (e.g., `MAX_SPEED`).
* **Primitive types**: Lowercase naming (e.g., `int`, `float`, `bool`).
* **Non-primitive types**: `PascalCase` naming (e.g., `String`, `Player`, `Vector2`) for both built-in and user-defined types.
* Comments on the same line as code should have two spaces before the `//`.
* Constant params should precede mutable params in function definitions.

### Comments

Sapphire supports both single-line and multi-line block comments:

```
// This is a single-line comment

/*
 * This is a multi-line
 * block comment.
 */
```

## 3. Program entry & top-level script execution

Sapphire supports top-level script-style execution. Programs do not require a mandatory `func main()` entry point. Top-level statements (variable initializations, function calls, conditional branches, and loops) are executed sequentially upon program execution. If a `func main()` function is defined, it will be automatically invoked after any top-level statements execute. Return statements (`return`) at top-level module scope are prohibited and produce a compile-time error.

## 4. Variable declaration & memory semantics

Variables are immutable constants by default to encourage safety. Mutability must be explicitly declared.

* **`let`**: Declares a constant variable (immutable).
* **`var`**: Declares a mutable variable.
* **Type inference:** Within function bodies, variable types are inferred by default unless explicitly annotated.
* **Implicit type-widening**: The type system automatically coerces and widens `int` values to `float` where appropriate. An `int` expression can be assigned to a `float` variable or passed as a `float` parameter.
* **Multi-variable declarations & assignments**: Multiple variables can be declared or assigned simultaneously using comma separation (e.g. `let x, y = getPosition();` or `x, y = 10.0, 20.0;`).

```
let speed: int = 60;
let name = "Hero";  // Type inferred as String

// Python-style string interpolation
let msg = f"Hello {name}, speed: {speed}!";

var health = 100;
health = 90;  // Valid mutation

let x, y = 10.0, 20.0;  // Multi-variable declaration
```

### String interpolation

Sapphire supports Python-style string interpolation using the `f"..."` prefix:

* **Syntax**: `f"literal {expression} literal"`
* **Nested quotes**: Expressions inside interpolation braces support nested quotes (e.g. `f"Hello {user.get("name")}"`).
* **Brace escaping**: Double curly braces `{{` and `}}` within an f-string evaluate to literal `{` and `}` characters.
* **Automatic type coercion**: Primitive types (`int`, `float`, `bool`), `none`, and `enum` variants are automatically coerced to strings inside `{expression}`.
* **Structs**: User-defined `struct` types cannot be interpolated directly and cause a compile-time error; explicit conversion methods (e.g. `{player.to_string()}`) must be called.

## 5. Core operators & expressions

This section outlines the basic syntax of Sapphire's core operators, expressions, and collection access.

### Core operators

Sapphire supports standard operator families with well-defined precedence (e.g., multiplicative operators bind tighter than additive operators):

* **Arithmetic**: `+` (addition), `-` (subtraction), `*` (multiplication), `/` (division), `%` (modulo).
* **Unary**: `-` (negation/additive inverse), `+` (prefix positive), `!` (logical NOT).
* **Comparison**: `==` (equality), `!=` (inequality), `<` (less than), `<=` (less than or equal), `>` (greater than), `>=` (greater than or equal).
* **Logical**: `&&` (logical AND), `||` (logical OR).
* **Ternary**: `condition ? true_expr : false_expr`.
* **Compound assignment**: `+=`, `-=`, `*=`, `/=`, `%=`.
* **Type casting**: `as` (infallible static type conversion, e.g. `x as float`).

### Ternary expressions (the `? :` operator)

Sapphire supports C-style inline conditional expressions using the `? :` ternary operator:

* **Syntax**: `condition ? true_expr : false_expr`
* **Expression context only**: The ternary operator is scoped strictly to expression contexts, avoiding any syntactic or parsing ambiguity with optional type annotations (`int?`).
* **Condition type safety**: The condition must evaluate to a boolean expression (`bool`).
* **Branch compatibility & type inference**: The true and false branches must have compatible types. Widening (e.g., `int` and `float` coercing to `float`) and optional wrapping (e.g., `int` and `none` producing `int?`) are handled automatically by the compiler.
* **Mandatory parentheses for nested ternaries**: Unparenthesized nested ternary expressions (e.g., `a ? b : c ? d : e`) are strictly forbidden and produce a compile-time error. Nested ternary expressions must be explicitly enclosed in parentheses: `a ? b : (c ? d : e)`.

```sapphire
let age = 20;
let status = age >= 18 ? "Adult" : "Minor";

// Numeric widening (int 10 and float 2.5 produce float)
let val: float = is_high ? 10 : 2.5;

// Optional wrapping (int 42 and none produce int?)
let num: int? = active ? 42 : none;

// Nested ternary with mandatory parentheses
let grade = score >= 90 ? "A" : (score >= 80 ? "B" : "C");
```

### Type casting (the `as` operator)

The `as` operator is used for infallible, compile-time guaranteed static type conversions:

* **Numeric conversions**: Widening and narrowing between numeric types (`int as float`, `float as int` which truncates decimals, `bool as int` where `true` -> 1 and `false` -> 0).
* **Enum conversions**: Static conversion from an enum variant to its underlying primitive representation (`enum_variant as int` or `enum_variant as String`).

```sapphire
let f: float = 10 as float;  // 10.0
let i: int = 3.14 as int;    // 3 (truncated)
let b: int = true as int;    // 1

let dir_code: int = Direction.North as int;       // 1
let dir_str: String = Direction.North as String;  // "North"
```

#### Prohibited conversions with the `as` operator

1. **Fallible string parsing**: Parsing strings into primitive types (e.g. `"123" as int`) or enum variants (e.g. `"North" as Direction`) using `as` is prohibited at compile-time. Fallible parsing must use instance methods (`"123".to_int()`, `"3.14".to_float()`, `"true".to_bool()`) or static associated functions (`Direction.from("North")`).
2. **Struct up-casting**: Up-casting child struct instances to parent struct types (e.g. `cat as Animal`) is strictly prohibited to eliminate object slicing and method-dispatch ambiguities.

### Expressions & collection access

* **Array literals & type syntax**: Arrays are defined as comma-separated values inside square brackets. Array types are annotated using `[T]` (or `Array<T>`). Trailing commas in literals are optional and recommended for multi-line literals. Arrays are strongly typed and homogeneous; all elements must have compatible types:
  ```sapphire
  let numbers = [10, 20, 30];  // Inferred as `[int]`
  ```
* **Array indexing**: Elements of an array are accessed via zero-based integer index brackets:
  ```sapphire
  let first = numbers[0];
  ```
  * **Compile-time bounds-checking**: For arrays with compile-time known lengths (such as array literals or statically-initialized array variables), constant integer indices are checked at compile time. Negative indices (`index < 0`) or out-of-bounds indices (`index >= size`) produce a compile-time type-checking error.
* **Map literals & type syntax**: Maps are defined as key–value pairs separated by colons inside curly braces (`{key: value}`). Map types are annotated using `[K: V]` (or `Map<K, V>`). Entries are separated by commas. Trailing commas are supported and encouraged. Maps are strongly typed and strictly homogeneous: all keys must have compatible key types (`String`, `int`, or an `enum`), and all values must have compatible value types. Mixing different key types or value types in the same map is prohibited:
  ```sapphire
  let scores = {"alice": 100, "bob": 95};  // [String: int]
  let config = {1: "low", 2: "high"};      // [int: String]

  // [Direction: int]
  let dir_speeds = {
      Direction.North: 10,
      Direction.South: 5,
  };
  ```
* **Map indexing**: Values in a map are accessed by key using square brackets:
  ```sapphire
  let alice_score = scores["alice"];
  ```
  * **Compile-time key validation**: Indexing map literals directly with a constant literal key validates key existence at compile time; accessing a non-existent literal key emits a compile-time error.
* **Optional chaining**: To safely traverse properties or methods of an optional instance without unwrapping it first, Sapphire supports the optional chaining operator `?.`. If the receiver is `none`, the entire expression evaluates to `none`:
  ```
  let name = target?.get_name();
  ```

## 6. Control flow & pattern matching

Sapphire supports conditional execution, pattern matching, and iteration loops.

### Conditionals (if/else)

Sapphire supports standard conditional execution via `if`, `else if`, and `else` blocks. Parentheses around the condition are optional:

```
let score = 85;
if score >= 90 {
  print("Grade: A");
} else if score >= 80 {
  print("Grade: B");
} else {
  print("Grade: C");
}
```

### Match expressions

Sapphire provides a first-class `match` construct for pattern matching, supporting both safe value transformation (expressions) and side-effect control flow (statements).

* **Syntax**: `match subject { pattern -> body, ... }`
* **Single-expression cases**: Cases with a single expression implicitly evaluate to that expression's value.
* **Multi-statement blocks**: Cases using a block `{ ... }` **must** explicitly use `yield <expr>;` to output a value. Using `return` inside a match block returns from the *enclosing function*.
* **Implicit `none` fallback**: Multi-statement blocks without a `yield` statement automatically evaluate to `none` (type `none`), enabling clean side-effect-only branching without boilerplate.
* **Optional wrapping for mixed return types**: If a `match` expression contains a mix of value-yielding arms (producing type `T`) and arms that evaluate to `none` (or multi-statement blocks without a `yield`), the compiler automatically wraps the overall result type of the `match` expression into an optional `T?`.
* **Mandatory comma separators**: Every case branch (including multi-statement blocks ending in `}`) must be followed by a comma `,`.
* **Default case**: The default/wildcard pattern uses the ellipsis token `... ->`.
* **Exhaustiveness**: The compiler statically verifies that all cases of `enum`, `bool`, and `optional` subjects are handled or an ellipsis `...` default branch is present.

```sapphire
// Expression mapping
let label = match status {
  HttpStatus.Ok -> "Success",
  HttpStatus.NotFound -> {
    log("Not found");
    yield "Resource Missing";
  },
  ... -> "Unknown Error",
};

// Mixed arms produce an optional (type inferred as String?)
let result: String? = match status {
  HttpStatus.Ok -> "Success",
  HttpStatus.InternalError -> {
    log("Internal server error encountered");
    // No yield: evaluates to none, wrapping `result` as String?
  },
  ... -> none,
};

// Side-effect-only usage
match direction {
  Direction.North -> {
    move_player(dx = 0, dy = -1);
  },
  Direction.South -> {
    move_player(dx = 0, dy = 1);
  },
  ... -> {
    log("Horizontal movement");
  },
};
```

### Control-flow loops

Sapphire supports conditional iteration and collection traversal:

#### `while` loop

Executes a block of code as long as the condition evaluates to `true`. No parentheses are required around the condition:

```
var count = 5;
while count > 0 {
  print(count);
  count -= 1;
}
```

#### `for-in` loop

Iterates over elements in a collection (arrays or maps).

* **Scoping & mutability**: By default, loop variables (e.g., `name`, or `key, val`) are implicitly declared as immutable constants (`let`) scoped strictly to the loop body block.
* **Array iteration**: Uses a single loop variable to iterate over array elements (`for item in array`).
* **Map Iteration**: Uses dual key-value loop variables (`for key, val in map`) to iterate over entries in a map.
* **Mutable loop variables**: To allow mutation of loop variables within the block, they can be explicitly declared using the `var` keyword (`for var key, val in map`):

```
let names = ["Alice", "Bob", "Charlie"];

// Array iteration: single loop variable
for name in names {
  print(name);
}

let inventory = { "potions": 5, "elixirs": 2 };

// Map iteration: dual key-value loop variables
for key, val in inventory {
  print(key + ": " + val);
}

// Mutable loop variables: `var` binding
for var key, val in inventory {
  val = val + 1;
  print(key + ": " + val);
}
```

## 7. Optionals (null safety) & conditional bindings

The language completely forbids null pointers. Instead, it supports type-safe
optionals utilizing a `?` modifier and a `none` keyword representing the empty
state.

To unwrap optionals, Sapphire provides a conditional unwrapping operator `?=`
used within conditional headers:

```
var target: Enemy? = none;
let damage: int? = 15;

if let active_target ?= target {
  // active_target is guaranteed to be non-optional within this block
} else {
  // Optionals also support standard fallback blocks via `else` or `else if`
}
```

### Semicolon-separated init statements
Both `if` and `while` statement headers support declaring an init statement
before the condition, separated by a semicolon. This is useful for limiting the
scope of helper variables or combining unwrapping with other checks. The init
statement evaluates **once** before entering the block or loop, while the loop
condition to the right of the semicolon is re-evaluated on each iteration:

```
if let active_target ?= target; active_target.health > 50 {
  // `active_target` is unwrapped once and its health is checked
}

while let score = get_score(); score < 100 {
  // `score` is initialized once; `score < 100` is re-evaluated ever iteration
}
```

### Nil-coalescing operator (`??`)
Sapphire provides the binary coalescing operator `??` to supply a fallback value
when unwrapping an optional:

```
let active_enemy = target ?? default_enemy;

// `active_enemy` is guaranteed to be non-optional
```

## 8. Functions & closures

Named functions must fully declare the types of all parameters and the explicit
return value(s) using colon syntax.

* **Primitive types**: Assumed to be passed by **value** by default.
* **Non-primitive types**: Assumed to be passed by **constant reference** by
default.
* **Mutable references**: Indicated by prefixing the parameter with `var`,
causing it to be passed by mutable reference. Callers may not pass variables
declared with `let` to these parameters. This applies to both primitive and
non-primitive types.
* **Named parameters**: Call-site arguments can be named explicitly using the
`=` operator, mirroring assignment semantics and preserving the colon for types.
* **Default parameters**: Parameters can define default values using the `=`
operator in the function signature. If omitted at the call site, the default
value is evaluated and used instead.
* **Multiple Return Values**: Functions can declare multiple return types as a comma-separated list following the colon (e.g.,
`func getPosition(): float, float`). Return statements accept comma-separated
expressions (`return x, y;`).

```
func calculate_damage(attacker: Player, var defender: Enemy,
                      is_critical: bool = false): int {
  var base_damage = attacker.attack_power;
  if is_critical {
    base_damage *= 2;
  }
  defender.health -= base_damage;
  return base_damage;
}

// Function with multiple return values
func get_position(entity: Player): float, float {
  return entity.x, entity.y;
}

// Invocation using multi-variable destructuring
let pos_x, pos_y = get_position(current_player);

// Invocation using named parameters via assignment syntax (is_critical defaults
// to false)
calculate_damage(defender = target_enemy, attacker = current_player);

// Invocation overriding the default parameter value
calculate_damage(current_player, target_enemy, is_critical = true);
```

### Scope-bound aliasing rules (borrow-checking)

To guarantee reference safety and eliminate runtime aliasing logic bugs without introducing the visual overhead of Rust-style lifetime annotations, Sapphire's compiler enforces compile-time **scope-bound aliasing rules** at call sites:
* **Reference types only**: Primitive types (`int`, `float`, `bool`) and `none` are value-copied and ignored by this check. User-defined `struct` types and `String` are reference-passed and validated.
* **Overlapping mutability restrictions**: Inside any single function or method call, a reference path (a root variable name and its nested member accesses, e.g., `player` or `player.pos`) cannot be mutably borrowed (`var` parameter) if it is already borrowed (either mutably or immutably) within the same call.
* **Implicit-receiver checking**: In a non-static method call (`p.heal(...)`), the receiver is implicitly treated as an argument (borrowed mutably for mutable methods, or immutably for `const` methods).

```
// Rejected: 'player' is borrowed mutably as 'target' and immutably as
// 'observer'.
execute_interaction(target = player, observer = player);

// Rejected: 'player' (receiver) is mutably borrowed, conflicting with its use
// as 'other'.
player.mutate(other = player);
```

### First-class functions

Functions are first-class citizens. To avoid double-colon confusion, function type declarations isolate the return block via an arrow token (`->`).

```
// Function type declaration
var math_op: (int, int) -> int;
var callback: (String) -> void;  // `void` is an alias for `none`
```

### Anonymous functions (lambdas)

Anonymous functions use an arrow-based block syntax. The arrow (`->`) is mandatory even when the return type is omitted. Type inference rules apply heavily inside function closures:

* **Single-parameter inference**: If an anonymous function takes a single parameter that can be contextually inferred, both the parentheses and the type annotation can be omitted.
* **Multi-parameter syntax**: Parentheses are required when declaring multiple parameters.
* **Single-expression shorthand**: If a lambda body consists of a single expression, the curly braces and the `return` keyword can be omitted. The result of the expression is implicitly returned.

```
let numbers = [1, 2, 3, 4];

// Explicitly typed parameter and return type
let doubled = numbers.map((x: int) -> int {
  return x * 2;
});

// Fully inferred single parameter and return type
let squared = numbers.map(x -> {
  return x * x;
});

// Single-expression shorthand
let tripled = numbers.map(x -> x * 3);

// Chaining map, filter, and reduce using single-expression lambdas
let sum_of_even_squares = numbers
    .map(x -> x * x)
    .filter(x -> x % 2 == 0)
    .reduce(initial = 0, (acc, x) -> acc + x);
```

## 9. Structs & the implementation block

The primary data layout tool is the `struct` keyword. To strictly separate data structures from behavior, all methods (including constructors) **must** be defined inside a Rust-style implementation (`impl`) block; defining method signatures or bodies inside the `struct` block itself is strictly forbidden.

Sapphire provides a Python-style `__init__` initializer syntax defined inside the `impl` block. The compiler enforces that all non-optional fields declared in the `struct` be initialized within this function.

* **Implicit self**: For all non-static member functions, the `self` token is implicitly available within the body of the function.
* **Static methods**: Declared using the explicit `static` keyword. Inside static functions, `self` is unavailable.
* **Constant methods**: Non-static methods may be marked `const`, which
indicates that `self` cannot be modified.

```
struct Weapon {
  var damage: int;
  var durability: int = 100;
  let name: String;
}

impl Weapon {
  func __init__(dmg: int, name: String = "Cool Sword") {
    self.damage = dmg;
    self.durability = 100;
    self.name = name;
  }

  func use() {
    self.durability -= 1;
  }

  static func create_legendary(): Weapon {
    return Weapon(dmg = 250);
  }

  const func get_name(): String {
    return self.name;
  }
}
```

### Struct initializers (curly-brace syntax)

For direct instantiation of structs, Sapphire supports a curly-brace initializer syntax. This is the preferred way to instantiate structs (unless complex constructor setup is needed). The syntax matches named parameters, using the `=` operator, and allows trailing commas:

```
let sword = Weapon {
  damage = 45,
  durability = 100,
  name = "Broadsword",
};
```

Fields declared with default initialization expressions (e.g.
`var durability: int = 100;`) or optional types (`T?`) may be omitted during
struct initialization. The compiler statically verifies that all remaining
required (non-optional) fields are initialized and that their assigned types are
compatible.

The following code will not compile because `sword` is a constant:

```
let sword = Weapon(...);

// This method attempts to mutate `self`, which is not allowed since `sword` is
// declared as a constant.
sword.use();
```

## 10. Enums

Sapphire provides native support for integer-backed and string-backed enumerations via the `enum` keyword. Enums define a named set of constants with static type safety and optional explicit assignments.

### Definition & auto-incrementing values

Enum members are declared as comma-separated identifiers inside curly braces. Trailing commas are optional and recommended.

* **Default values**: By default, integer enum members are automatically
  assigned sequential integers starting at `0`.
* **Explicit integer values**: Members can be assigned explicit integer values.
  Unassigned subsequent members automatically resume auto-incrementing from the
  previous member's value.
* **Native String Enums**: Members can be assigned explicit string literal
  values (e.g., `Fill = "fill"`). Any subsequent unassigned member in a string
  enum automatically defaults to its identifier string (`Line` -> `"Line"`).

```sapphire
// Default auto-incrementing integer values:
// North = 0, East = 1, South = 2, West = 3
enum Direction {
  North,
  East,
  South,
  West,
}

enum DrawMode {
  Fill = "fill",
  Line = "line",
  Default,  // Auto-assigned "Default" (note that capitalization is maintained)
}

// Explicit integer values
enum HttpStatusCode {
  Ok = 200,
  Created = 201,
  BadRequest = 400,
  NotFound = 404,
  InternalError = 500,
}
```

### Type semantics & interoperability

* **Nominal typing**: Declaring an enum introduces a named type into the scope
  (e.g., `Direction` or `DrawMode`).
* **Type inference**: Variable bindings assigned an enum variant automatically
  infer the enum type without requiring explicit type annotations.
* **Asymmetric primitive interoperability**: Enum values can be implicitly
  coerced to their underlying primitive types (e.g., assigning an enum variant
  to an `int` or `String` variable). However, the reverse is not allowed: raw
  primitive values cannot be implicitly assigned or passed where an enum type is
  expected.

```sapphire
// Type inferred as `Direction`
let current_dir = Direction.North;

let mode: DrawMode = DrawMode.Fill;

// String enum interoperability (asymmetric)
//
// Allowed: Enum implicitly coerces to String
let mode_str: String = DrawMode.Line;

// Compile error: Cannot assign String to DrawMode
// let invalid: DrawMode = "fill";

// Fallible conversion from String or int via EnumName.from
if let mode ?= DrawMode.from("line") {
  // mode is DrawMode.Line
}

if let code ?= HttpStatusCode.from(200) {
  // code is HttpStatusCode.Ok
}

// Comparison
if status == HttpStatusCode.Ok {
  let is_ok = true;
}

// Infallible static integer conversion
let dir_code: int = current_dir as int;
```

## 11. Inheritance & polymorphism

Sapphire implements clean, type-safe inheritance divided into a compile-time mechanism and a runtime mechanism.

### Static inheritance

Structures can inherit the field layout, methods, and default values of another structure at compile time using a colon syntax similar to that in C++.

```
struct Animal {
  var name: String;
  var age: int;
}

struct Cat: Animal {
  var lives: int;
}
```

#### Disallowed up-casting

To prevent historical OOP design flaws, Sapphire **strictly disallows up-casting** for statically inherited structures (e.g., a `Cat` reference cannot be cast or passed as an `Animal`).

This design choice provides several key benefits:
* **Eliminates object slicing**: Because a child struct cannot be assigned to a parent struct type, the compiler prevents object slicing (where child fields are silently discarded during assignment).
* **Eliminates method-override ambiguity**: In traditional languages without vtables, calling an overridden method through an up-cast reference statically dispatches to the parent's method. Disallowing up-casting makes this class of logical bugs impossible.
* **Separates concerns**: Static inheritance behaves strictly as a *code and layout reuse utility*. Behavioral polymorphism is offloaded entirely to **traits** (using monomorphization), ensuring that memory layout composition and dynamic typing are never conflated.

#### Syntactic delegation (transparent forwarding)

To retain a simple and familiar structural inheritance syntax without introducing rigid physical memory layouts, Sapphire treats the colon syntax as compiler-driven **syntactic delegation**. Under the hood, the compiler converts this inheritance into composition (field nesting) and automatically generates forwarding methods.

This approach incurs **zero runtime performance penalty** and avoids the overhead typical of traditional dynamic/virtual method dispatch because resolution is done entirely at compile-time:
* **Direct static calls (no indirection)**: Unlike virtual method tables (vtables) that require pointer chasing and dynamic lookups, the compiler resolves target functions statically and outputs direct branch/jump instructions.
* **Inlining opportunities**: Since the forwarded calls are resolved statically, they are prime candidates for compiler inlining. When inlined, the forwarding layer is completely optimized away, resulting in absolute zero runtime instruction overhead.
* **Compile-time offset calculation**: Any adjustment to the `self` reference pointer (from the wrapper struct to the nested composition struct) is calculated at compile-time and folded directly into CPU instructions.

This provides the ergonomic benefits of traditional inheritance while giving the compiler full freedom to optimize, reorder, or pack fields under the hood.

#### Alternatives for static code reuse

To support data-oriented design and decouple behaviors from layout, Sapphire supports two primary alternatives:

##### Traits (compile-time monomorphization)
Traits define behavioral contracts without prescribing physical memory layout.
They are resolved entirely at compile time through monomorphization, ensuring
zero runtime overhead.

* **Implicit and explicit `self` for instance methods**: Non-static trait methods implicitly operate on `self` when implemented. In standard Sapphire code, the explicit `self` parameter can be omitted in trait declarations. Specifying an explicit first `self` parameter (which may be `var self` for mutable access) is primarily used when creating bindings for external host libraries (like Love2D) to explicitly designate instance methods that transpile to colon syntax in Lua (e.g. `:draw(x, y)`).
* **Module/static functions**: For external host bindings, omitting `self` from a trait method signature designates it as a module or static function (e.g. transpiling to Lua dot syntax `.rectangle(...)`).

```
// Resource-handle trait (instance methods)
trait Image {
  func draw(self, x: float, y: float);
  func getWidth(self): float;
}

// Module trait (static functions)
trait Graphics {
  func rectangle(mode: String, x: float, y: float, w: float, h: float);
}

struct Cat {
  var lives: int;
}

impl Actor for Cat {
  func update() {
    // Concrete implementation
  }
}
```

##### Explicit composition (data-oriented design)
Instead of physical inheritance, structs can explicitly compose other structures. This allows clear separation of data components, which is ideal for Entity-Component-System (ECS) architectures where systems process arrays of single components to maximize cache locality.

```
struct PhysicsComponent {
  var velocity: Vector2;
  var mass: float;
}

struct Player {
  var physics: PhysicsComponent;
  var health: int;
}
```

### Dynamic prototypal inheritance

Prototypal inheritance allows objects to delegate state to other objects at runtime. Instead of defining a rigid class hierarchy or instantiating duplicate structures, one object can serve as an active prototype for another. The clone dynamically delegates field lookups to its prototype: changes made to the prototype propagate live to the cloned instance, while the clone can selectively shadow (override) specific values. This is highly valuable for rapid prototyping, template-based object creation (such as defining variations of a base enemy archetype in a game), and zero-boilerplate data sharing.

In Sapphire, prototypal inheritance is opt-in and is declared using the `proto` syntax (e.g., `proto Enemy`). Standard structures (`struct`) do not support `clone` and are compiled to flat, fast layout structures with no runtime prototype lookup overhead.

For prototype structures (`proto`), the compiler automatically generates a built-in `__proto__` property on every instance to access its prototype. Manual self-referential prototype pointer definitions (like `var __proto__: Struct?`) are strictly forbidden by the compiler to prevent boilerplate antipatterns.

Prototypal delegation is executed explicitly via the `clone` keyword. Using `clone` bypasses the `__init__` function and sets up a live reference delegation back to the cloned instance. An optional initialization block syntax allows immediate local property shadowing upon cloning.

```
var base_goblin = Enemy { damage = 10 };

let elite_goblin = clone base_goblin {
  self.health = 200;  // Shadowed locally
};

print(elite_goblin.damage);  // Outputs 10 (Delegated to base_goblin)

base_goblin.damage = 15;
print(elite_goblin.damage);  // Outputs 15 (Reflected live from prototype)
```

#### Immutability and live updates

When an instance is bound using `let` (e.g., `let elite_goblin = clone base_goblin`), the variable binding and its local shadow table are immutable (meaning you cannot reassign the variable or mutate its properties directly). However, live modifications to its prototype (`base_goblin`) will still propagate through the delegation chain.

#### Structural safety & method dispatch constraints

To prevent the unpredictability of JavaScript-style dynamic prototypes and keep performance consistent, Sapphire enforces the following constraints:
* **Value-shadowing only**: Users are strictly forbidden from dynamically appending entirely new fields that were not defined in the source struct blueprint.
  * Additionally, shadowing of nested reference types implements **copy-on-write (CoW)**. Mutating properties inside a nested reference type (e.g., modifying a field of a composed struct) will automatically intercept the write, deep-copy the nested reference locally on the clone (shadowing it), and then apply the mutation. This guarantees that mutations on the clone do not propagate back to the prototype.
* **Data-only delegation**: Prototypal inheritance only delegates and shadows data fields. Methods (defined inside `impl` blocks) are resolved statically at compile-time based on the concrete type of the struct. Sapphire does not support runtime overriding of methods on individual instances, which keeps method dispatch zero-cost.
* **Opt-in proto declarations**: To prevent pointer-chasing overhead for standard structs, prototypal delegation is restricted to structures declared with the `proto` keyword. Standard structs are compiled as flat, contiguous blocks with zero pointer-chasing overhead.

#### The `__proto__` property

Every struct instance automatically exposes a built-in, compiler-generated `__proto__` property to inspect its prototype chain:
* **Immutability**: The `__proto__` property is read-only. It cannot be reassigned at runtime, preventing prototype-pollution vulnerabilities and allowing the compiler to perform layout optimizations.
* **Type safety**: For any struct `T`, the type of the `__proto__` property is the optional `T?`. Accessing the prototype requires safe optional unwrapping.
* **Prototype assignment**:
  * For instances created via a standard constructor (e.g., `Enemy()`), `__proto__` evaluates to `none`.
  * For instances created via `clone` (e.g., `clone base_goblin`), `__proto__` points to the prototype instance (in this case, `base_goblin`).
  * Since static inheritance is resolved at compile time via delegation, it does not create a runtime parent object. Therefore, statically inherited instances that are not cloned will also have their `__proto__` set to `none`.

## 12. Compiler & runtime implementation

This section outlines how the Sapphire compiler and runtime optimize code execution and manage memory without sacrificing performance or safety.

### Proto compilation

To preserve the zero-overhead promise of standard structures, the compiler does not generate any prototype lookup wrappers or metadata for standard `struct` declarations.
1. **Standard Structs**: Standard structs compile directly to flat layouts. Field lookups (e.g. `t.field`) compile to direct offset/index accesses.
2. **Proto structures**: Structures declared with the `proto` keyword compile to instances wrapping their properties in a lookup system containing `__proto__` and `__shadow__` tables.
3. **Copy-on-Write (CoW) Wrapper**: Field writes targeting a nested reference field inside a cloned object trigger a copy-on-write intercept. The runtime duplicates the nested reference locally to isolate the cloned instance's mutations.

### Arena-based memory management

All `proto` instances and their clones are automatically allocated on a managed arena. Additionally, standard `struct` instances can opt into arena allocation using the `in` suffix. Sapphire prohibits allocating `proto` instances or their clones on the call stack, eliminating LIFO stack escape issues.

1. **Implicit default arena**: If no arena is explicitly specified, `proto` instances are allocated in an implicit, thread-local or global reference-counted arena.
2. **Implicit clone arena propagation**: When a prototype is cloned, it is automatically allocated in the same arena as its prototype by default, unless overridden by an explicit `in` suffix (e.g. `clone base in other_arena`).
3. **Explicit Arenas and RAII**: Developers can instantiate explicit arenas (e.g. `let my_arena = Arena();`). Allocations are targeted to the arena using the `in` suffix (e.g., `Point { x = 10 } in my_arena`).
4. **Lexical scope destruction (RAII) & escape-checking**: Explicit `Arena`
instances have lexical lifecycles. When the `Arena` variable goes out of scope,
the runtime automatically tears down the arena and deallocates all objects (both
`struct` and `proto` references) allocated within it. To prevent dangling
references, the compiler statically enforces scope-bound escape rules:
   * **Outer-scope variable escape**: A variable (`let` or `var`) declared in an
     outer scope cannot be assigned a reference to an object allocated in a
     nested/inner arena.
   * **Function-return escape**: A function cannot return a reference to an
     object allocated in an arena local to the function scope.

### Source map generation & runtime stack trace demangling

When transpiling Sapphire (`.sp`) code to target environments (such as Lua 5.1 / Love2D), the compiler tracks AST node position metadata (`start_line`, `start_column`) to generate source-map sidecars and runtime demanglers:

1. **Standard V3 source maps (`.lua.map`)**: Generated automatically during compilation using Base64 [VLQ](https://en.wikipedia.org/wiki/Variable-length_quantity) encoding. Sidecar files include embedded `sourcesContent` strings to support offline IDE debugging (such as setting breakpoints in VS Code).
2. **Runtime stack-trace demangling**: Embedded `_SP_LINE_MAP` lookup tables pair generated line numbers with original Sapphire source lines and snippets.
3. **Love2D error-handler hook**: Intercepts uncaught runtime errors (asset-loading failures, out-of-bounds dynamic indices, or failed optional unwrapping) and translates Lua call stack frames into original `.sp` filenames and line numbers on both terminal logs and Love2D's graphical crash screen.
4. **CLI control**: Source maps are enabled by default and can be disabled using the `--no_sourcemap` flag.

## 13. Module system & encapsulation

Sapphire provides a type-safe module system with explicit encapsulation.

### Private by default
All top-level declarations (`struct`, `enum`, `trait`, `func`, `let`, `var`) in a Sapphire source file are **module-private by default** and cannot be accessed outside their defining file unless explicitly listed in an `export` block.

### Explicit export manifest (`export { ... }`)
A module defines its public API using an `export` manifest block:
* **Single-block Enforcement**: Exactly one `export { ... }` block is permitted per file.
* **Top-level placement**: The `export` block can be placed anywhere at top-level scope (e.g., at the top of the file above symbol definitions for readability, or at the bottom). Forward references to symbols defined later in the file are fully supported.
* **Aliasing & re-exporting**: Members can be exported under aliases using `as` (e.g. `new_image as create_image`), and imported module symbols can be re-exported via dot notation (e.g. `enums.DrawMode`).
* **Trailing Commas**: Trailing commas inside `export { ... , }` are allowed and
  recommended.

```sapphire
// lib/love2d/graphics.sp

import lib.love2d.enums;

export {
  Image,
  new_image,
  new_image as create_image,
  enums.DrawMode,
}

struct Image {
  var handle: int;
}

func new_image(path: String): Image {
  return Image { handle = 1 };
}
```

### Module imports (`import`)
Modules are imported using dot-separated identifier paths:

```sapphire
// Imports module namespace 'graphics'
import lib.love2d.graphics;

// Imports module namespace with custom alias 'gfx'
import lib.love2d.graphics as gfx;

// Member access via qualified dot notation
let img = graphics.new_image("hero.png");
```

### Transpilation semantics
* **Lua 5.1 target**: Module imports transpile to `local graphics = require("lib.love2d.graphics")`. Export manifests emit a module table `local _M = {}` populated with exported references and append `return _M`.
* **Python target**: Module imports transpile to `import lib.love2d.graphics`. Export manifests emit `__all__ = ["Image", "new_image", "create_image", "DrawMode"]`.

## 14. Host runtime interoperability & annotations

Sapphire supports native interoperability with third-party scripting host engines (such as **Love2D** in Lua 5.1 / LuaJIT environments) through single-purpose annotation decorators:

### `@extern` (host variable binding)

The `@extern` annotation binds Sapphire variables to external host symbols
provided at runtime.
* **Syntax**: `@extern("external_name") var identifier: Type;` or `@extern var identifier: Type;` (where the external symbol is also named `identifier`).
* **Runtime behavior**: Tells the transpiler to omit runtime variable initializations (`local name = ...`), permitting 100% type-safe access to host-provided engine modules.

### `@export` (transpiled symbol renaming)

The `@export` annotation configures symbol renaming during transpilation.
* **Global callback export**: `@export("love.update") func handler(...) { ... }`. In Lua 5.1 target code, transpiles directly into global callback paths (e.g. `function love.update(dt) ... end`).
* **Trait method aliasing**: `@export("native_name")` placed on a trait method signature configures the transpiler to emit `native_name` instead of the Sapphire method identifier (e.g. `@export("setColor") func setColorRGBA(r: float, g: float, b: float);`).

### Trait-based host interfaces & resource handles

External host–module contracts are defined cleanly using standard Sapphire `trait`s composed inside container `struct` types:

* **Resource-handle traits**: Specifying an explicit first `self` parameter (e.g. `func draw(self, x: float, y: float)`) designates an instance method on a handle object, transpiling to Lua colon syntax (`handle:draw(x, y)`).
* **Module traits**: Omitting `self` designates a module or static function, transpiling to Lua dot syntax (`love.graphics.rectangle(...)`).
* **Method aliases**: Overloaded host functions can be exposed as distinct, type-safe Sapphire methods annotated with `@export("native_name")`.

```sapphire
// 1. Opaque resource-handle trait (instance methods take `self`)
trait Image {
  func draw(self, x: float, y: float);
  func getWidth(self): float;
}

// 2. Host API trait (module functions without `self`, method aliases for
// overloaded host APIs)
trait Graphics {
  @export("setColor")
  func setColorRGBA(r: float, g: float, b: float, a: float = 1.0);

  @export("setColor")
  func setColorObj(color: Color);

  func rectangle(mode: String, x: float, y: float, w: float, h: float);
  func clear(r: float, g: float, b: float);
  func newImage(path: String): Image;
}

trait Keyboard {
  func isDown(key: String): bool;
}

// 3. Engine container struct
struct LoveEngine {
  var graphics: Graphics;
  var keyboard: Keyboard;
}

// 4. External host variable binding
@extern("love")
var love: LoveEngine;

// 5. Exported engine callbacks
@export("love.update")
func update(dt: float) {
  // Host call correctly transpiles to dot notation in Lua, i.e.:
  // `love.keyboard.isDown("right")`
  if love.keyboard.isDown(key = "right") { ... }
}

@export("love.draw")
func draw() {
  love.graphics.clear(r = 0.1, g = 0.1, b = 0.1);

  // Transpiles to `love.graphics.setColor(1.0, 0.0, 0.0)`
  love.graphics.setColorRGBA(1.0, 0.0, 0.0);
}
```

## 15. Generics & parametric polymorphism

Sapphire supports zero-overhead parametric polymorphism (generics) for structures, implementation blocks, traits, and functions using angle bracket parameter syntax (`<T, U>`).

### Declaration syntax

* **Generic structs**: Structs can declare one or more type parameters:
  ```sapphire
  struct Stack<T> {
    var items: [T];
  }

  struct Pair<K, V> {
    var key: K;
    var value: V;
  }
  ```
* **Generic implementation blocks**: Implementation blocks declare type parameters directly on the target struct or trait:
  ```sapphire
  impl Stack<T> {
    func push(item: T) {
      // ...
    }
  }

  impl Container<T> for Stack<T> {
    func get(): T {
      // ...
    }
  }
  ```
* **Generic traits**: Traits specify type parameters for generic interface contracts:
  ```sapphire
  trait Container<T> {
    func get(): T;
  }
  ```
* **Generic functions**: Functions declare type parameters after the function name:
  ```sapphire
  func identity<T>(item: T): T {
    return item;
  }
  ```

### Call-site type inference & explicit arguments

* **Type-argument inference**: When invoking generic functions, type arguments are contextually inferred from argument types by default:
  ```sapphire
  let x = identity(42);  // Inferred as identity<int>(42)
  ```
* **Explicit type arguments**: Type arguments can be explicitly specified at call sites or struct initializations:
  ```sapphire
  let s = Stack<int> { items = [10, 20] };
  let y = identity<float>(3.14);
  ```

### Compile-time monomorphization

In accordance with Sapphire's zero-overhead design, generics do not incur any runtime performance or dynamic-dispatch penalty. During compilation:
1. The semantic analyzer tracks all concrete type argument combinations used in the codebase.
2. The compiler monomorphizes generic template AST nodes into specialized concrete structures (e.g. `Stack<int>` becomes `Stack__int`).
3. The transpiler emits direct, un-boxed concrete definitions for each monomorphized type and function.

## 16. Design decisions

This section outlines the architectural decisions and design trade-offs made in Sapphire.

### Avoiding virtual method tables (vtables)

Traditional class-based object-oriented languages rely on virtual method tables (vtables) to resolve dynamic dispatch. This introduces vtable pointer-chasing overhead and prevents compiler optimizations like function inlining. Sapphire eliminates vtables entirely:
* Static polymorphism is resolved entirely at compile-time via monomorphized traits, generating direct function calls.
* Dynamic behavior resolved via prototypal delegation (`clone`) is strictly restricted to data fields. Methods remain statically dispatched based on the concrete struct type, keeping method calls free of dynamic-dispatch overhead.

### Avoiding physical inheritance layouts

While single, flat physical inheritance avoids vtable overhead by organizing memory contiguously, it introduces severe bottlenecks for performance-critical systems like game engines:
* **Cache-line pollution**: Grouping parent and child fields together in a single contiguous block forces unrelated fields into CPU cache lines. In data-oriented design (like ECS), updates only needing a small subset of fields (e.g., `position` and `velocity`) are slowed down by reading unrelated fields.
* **Layout rigidity**: A rigid inheritance hierarchy prevents the compiler from reordering fields across the entire structure to minimize padding bytes and reduce memory footprint.
* **Tight coupling**: Flat physical layouts tightly couple structures to their base, meaning modifications to a base struct invalidate layout offsets across all descendants and trigger cascading recompilations.

Instead of binding developers to rigid memory layouts, Sapphire decouples the ergonomic syntax of structural inheritance from its physical representation using compile-time syntactic delegation and monomorphized traits.

### Avoiding throwable exceptions

Traditional exception mechanisms (`try`/`catch`/`throw`) introduce hidden
control-flow jumps and expensive runtime stack-unwinding overhead. Sapphire
intentionally omits throwable exceptions in favor of explicit, type-safe error
handling:
* **No hidden control flow**: Functions clearly express fallibility in their
  signatures (e.g., returning optional types `T?` or multiple return values
  `T, bool`). Callers are forced to handle error paths explicitly at call
  sites.
* **Deterministic performance**: Eliminating exception unwinding runtime
  machinery ensures predictable CPU execution paths and simplified
  transpilation targets across scripting host engines.
* **Exhaustive error handling**: Combining enums with `match` expressions
  allows the compiler to statically enforce that all error variants are
  handled.
* **Resource safety without `finally`**: Lexical RAII and arena destruction
  guarantee that allocations and resources are automatically torn down upon
  scope exit, eliminating the need for exception cleanup blocks.
