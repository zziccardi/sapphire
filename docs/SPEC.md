# Sapphire language specification
{: .no_toc }

This document establishes the foundational design, syntax rules, and
architectural specifications for **Sapphire**, a general-purpose programming
language. Sapphire prioritizes predictability, type safety, explicit function
signatures, and highly ergonomic prototypal inheritance without traditional
class-based OOP boilerplate or virtual method table (vtable) performance
penalties.

For code style, formatting, and naming guidelines, see the separate
[style guide](style_guide.md).

<!-- Used by Jekyll -->
<details markdown="block">
  <summary>
    Table of contents
  </summary>
  {: .text-delta }
1. TOC
{:toc}
</details>

## Design philosophy & value proposition

Sapphire occupies a unique niche in the language ecosystem: it combines the
**safety and bare-metal performance of a systems language** (incorporating
zero-cost abstractions and monomorphization similar to Rust) with the
**rapid prototyping ergonomics** of dynamic languages (like JavaScript or Lua)
and the **expressive API clarity** of modern languages (like Swift). While
designed as a general-purpose systems language, Sapphire's deterministic
performance, lexical memory arenas, and live-reload capabilities make it
especially well-suited for interactive applications, simulation, and game
engines.

Unlike other performance-oriented languages, Sapphire distinguishes itself
through five key pillars:
* **Zero-overhead static & dynamic reuse**: Inheritance is treated as
  compile-time syntactic delegation (composition and generated forwarding),
  completely eliminating virtual-method tables (vtables), pointer-chasing, and
  object-slicing risks. Dynamic prototypal delegation is opt-in and data-only,
  and uses copy-on-write (CoW) to protect prototypes.
* **Scope-bound memory safety**: Non-primitive types are passed by **constant
  reference** by default. Call-site reference exclusivity (aliasing rules)
  eliminates data corruption from unexpected mutations without lifetime
  annotations or borrow-checker gymnastics.
* **Deterministic resource management**: Structs support deterministic RAII via
  `__del__()` destructors with return-value optimization (RVO).
  Dynamic prototypes and managed objects reside in explicit, lexically scoped
  `Arena`s with escape-checking.
* **Ergonomic, expressive API clarity**: Functions feature explicit signatures
  with named arguments and default values. Control flow emphasizes safety
  through Swift-style optionals (`?`), safe unwrapping (`if let ?=`), guard
  clauses (`guard ... else`), and exhaustive pattern-matching (`match`).
* **Predictable multi-target compilation**: Sapphire compiles to efficient,
  readable code across multiple execution targets (defaulting to Python and
  Lua 5.1/LuaJIT for game frameworks like Love2D), while enforcing strict
  compile-time type checks and deterministic semantics across all backends.

## Program entry & top-level script execution

Sapphire supports top-level script-style execution. Programs do not require a
mandatory `func main()` entry point. Top-level statements (variable
initializations, function calls, conditional branches, and loops) are
executed sequentially upon program execution. If a `func main()` function is
defined, it will be automatically invoked after any top-level statements
execute. Return statements (`return`) at top-level module scope are prohibited
and produce a compile-time error.

## Types, literals, & string interpolation

### Primitive scalar types

Sapphire provides a core set of statically verified primitive scalar types.
All primitive scalars are passed by value:

* **`int`**: 64-bit signed two's complement integer (`int64`).
* **`float`**: 64-bit IEEE-754 double-precision floating-point number
  (`float64`).
* **`bool`**: Boolean logical values, either `true` or `false`.
* **`none`**: The unit value literal representing the absence of a value or an
  empty optional state (`let x: int? = none;`). In type annotations, `none`
  is a reserved literal token.
* **`void`**: The semantic unit type designating functions and coroutines that
  return no value (`func f(): void`, `Coroutine<void>`).

### String literals & interpolation

Strings are immutable UTF-8 text sequences. Sapphire supports Python-style
string interpolation using the `f"..."` prefix and binary `+` concatenation:

* **Syntax**: `f"literal {expression} literal"`
* **String concatenation**: Expressions evaluate string concatenation via `+`
  whenever either operand is a `String` (e.g. `"Hello " + name`).
* **Nested quotes**: Expressions inside interpolation braces support nested
  quotes (e.g. `f"Hello {user.get(\"name\")}"`).
* **Brace escaping**: Double curly braces `{{` and `}}` within an f-string
  evaluate to literal `{` and `}` characters.
* **Automatic type coercion**: Primitive types (`int`, `float`, `bool`),
  `none`, and `enum` variants are automatically coerced to strings inside
  `{expression}`.
* **Structs**: User-defined `struct` types cannot be interpolated directly and
  cause a compile-time error; explicit conversion methods (e.g.
  `{player.to_string()}`) must be called.
* **Built-in methods**: Strings provide built-in methods including `.size()`,
  `.empty()`, `.lower()`, `.upper()`, `.strip()`, `.split()`, `.contains()`,
  `.find()`, `.to_int()`, `.to_float()`, and `.to_bool()`. For full method
  specifications, see
  [built-in string methods](builtins.md#built-in-methods) and
  [string operations](builtins.md#operations-and-capabilities).

```sapphire
let name = "Hero";
let speed = 60;
let msg = f"Hello {name}, speed: {speed}!";
let escaped = f"Literal braces: {{count}}";
let concat = "Greetings, " + name;
```

### Collection types & literals

* **Array literals (`[T]`)**: Arrays are ordered, strongly typed, homogeneous
  sequences defined as comma-separated values inside square brackets:
  ```sapphire
  let numbers: [int] = [10, 20, 30];
  ```
  Arrays support functional transformations and mutating operations such as
  `.map()`, `.filter()`, `.reduce()`, `.push()`, `.pop()`, and `.sort()`. For
  the full method suite, see
  [built-in array methods](builtins.md#built-in-methods-1).
* **Map literals (`[K: V]`)**: Maps are strongly typed key-value dictionaries
  defined inside curly braces (`{key: value}`). Keys must be `String`, `int`,
  or an `enum` type:
  ```sapphire
  let scores: [String: int] = {"alice": 100, "bob": 95};
  ```
  For map operations and query methods, see
  [built-in map methods](builtins.md#built-in-methods-2).
* **Range type (`Range`)**: Created via the built-in `range()` function for
  numeric sequences in `for-in` loops:
  ```sapphire
  let r: Range = range(0, 10, step = 2);
  ```
  For full `range` signatures and iteration semantics, see
  [the range function](builtins.md#the-range-function).

## Variables, operators, & expressions

### Variable bindings (`let` and `var`)

Variables are immutable constants by default to encourage safety. Mutability
must be explicitly declared:

* **`let`**: Declares an immutable constant binding.
* **`var`**: Declares a mutable variable binding.
* **Type inference**: Variable types are inferred by default from their initial
  value expressions unless explicitly annotated with `: Type`.
* **Implicit type-widening**: The type system automatically coerces and widens
  `int` values to `float` where appropriate. An `int` expression can be assigned
  to a `float` variable or passed as a `float` parameter.
* **Multi-variable declarations & assignments**: Multiple variables can be
  declared or assigned simultaneously using comma separation:
  ```sapphire
  let x, y = 10.0, 20.0;
  x, y = 30.0, 40.0;
  ```

### Operator precedence & associativity

Sapphire operators follow standard mathematical precedence, evaluated from
highest to lowest:

| Category | Operators | Associativity |
| :--- | :--- | :--- |
| **Postfix / Primary** | `()`, `[]`, `.`, `?.` | Left-to-right |
| **Unary** | `-`, `+`, `!` | Right-to-left |
| **Type Cast** | `as` | Left-to-right |
| **Multiplicative** | `*`, `/`, `%` | Left-to-right |
| **Additive / Concat** | `+`, `-` | Left-to-right |
| **Relational** | `<`, `<=`, `>`, `>=` | Left-to-right |
| **Equality** | `==`, `!=` | Left-to-right |
| **Nil-Coalescing** | `??` | Left-to-right |
| **Logical AND** | `&&` | Left-to-right |
| **Logical OR** | `\|\|` | Left-to-right |
| **Ternary** | `? :` | Right-to-left |

Assignment statements use `=`, `+=`, `-=`, `*=`, `/=`, or `%=`. Assignments are
strictly statements in Sapphire rather than value-producing expressions.

### Core operators

* **Arithmetic**: `+` (addition), `-` (subtraction), `*` (multiplication),
  `/` (division), `%` (modulo). Division by zero raises a runtime panic.
* **Unary**: `-` (negation), `+` (unary plus), `!` (logical NOT).
* **Comparison**: `==` (equality), `!=` (inequality), `<` (less than),
  `<=` (less or equal), `>` (greater than), `>=` (greater or equal). Operands
  must have compatible types.
* **Logical**: `&&` (short-circuiting AND), `||` (short-circuiting OR).

### Ternary expressions (the `? :` operator)

Sapphire supports inline conditional expressions using `? :`:

```sapphire
let label = score >= 60 ? "Pass" : "Fail";
```

* **Expression context only**: Scoped strictly as an inline expression.
* **Condition type safety**: The condition must evaluate to a boolean.
* **Branch compatibility**: The true and false branches must evaluate to
  compatible types. If one branch evaluates to `none`, the result type is
  inferred as an optional `T?`.
* **Mandatory parentheses for nested ternaries**: Unparenthesized nested
  ternaries produce a compile-time `SemanticError`. Nested ternaries must be
  explicitly disambiguated with parentheses:
  ```sapphire
  let status = x > 0 ? "Positive" : (x < 0 ? "Negative" : "Zero");
  ```

### Type casting (the `as` operator)

The `as` operator performs infallible, compile-time guaranteed static
conversions between compatible scalar types:

* **Numeric conversions**: Widening and narrowing between numeric types
  (`int` to `float` and `float` to `int` via truncation toward zero).
* **Enum conversions**: Static conversion from an enum variant to its
  underlying primitive type (`Direction.North as int` or `DrawMode.Fill as
  String`).

#### Prohibited conversions with the `as` operator

The `as` operator is strictly restricted to infallible conversions:
1. **Fallible string parsing**: Parsing strings into primitive types (e.g.
   `"123" as int`) is rejected at compile time; use the `.to_int()`,
   `.to_float()`, or `.to_bool()` instance methods on `String` which return
   optionals (`int?`, `float?`, `bool?`). For complete API signatures, see
   [built-in string methods](builtins.md#built-in-methods).
2. **Struct up-casting**: Up-casting child struct instances to parent struct
   types (e.g. `cat as Animal`) is statically prohibited to eliminate object
   slicing and dispatch ambiguity.

### Collection access & indexing

* **Array indexing**:
  * **Standard indexing (`array[i]`)**: Reads element at index `i` (0-based)
    and returns `T`. Dynamic out-of-bounds indexing halts with a runtime panic.
  * **Safe lookup (`array.get(i)`)**: Returns optional `T?`, safely evaluating
    to `none` on out-of-bounds access.
* **Map indexing**:
  * **Standard indexing (`map[key]`)**: Reads value for `key` and returns `V`.
    Dynamic missing-key access panics at runtime.
  * **Safe lookup (`map.get(key)`)**: Returns optional `V?`, evaluating to
    `none` if the key is absent.
* **Collection built-in methods**: `Array` and `Map` instances support a rich
  set of querying and mutating methods (`size()`, `empty()`, `contains()`,
  `insert()`, `remove()`, `clear()`, `map()`, `filter()`, `reduce()`, etc.).
  For comprehensive documentation and signatures, see
  [built-in array methods](builtins.md#built-in-methods-1) and
  [built-in map methods](builtins.md#built-in-methods-2).

## Optionals & null safety

Sapphire completely forbids null pointers. Instead, it supports type-safe
optionals utilizing the `?` modifier and a `none` keyword representing the
empty state.

```sapphire
var target: Enemy? = none;
let damage: int? = 15;
```

### Safe unwrapping (`if let ?=`)

To unwrap optionals safely, Sapphire provides the conditional unwrapping
operator `?=` used within conditional headers:

```sapphire
if let active_target ?= target {
  // active_target is guaranteed to be non-optional Enemy within this block
} else {
  // Executed if target is none
}
```

### Optional chaining (`?.`)

To safely traverse properties or invoke methods on an optional instance without
manual unwrapping, Sapphire provides the optional chaining operator `?.`:

```sapphire
let name: String? = target?.get_name();
```

* **Short-circuiting**: If the receiver is `none`, property access and method
  calls are short-circuited, and the entire expression evaluates to `none`.
* **Static type rules**: Accessing a property or method of type `T` on an
  optional `Receiver?` evaluates to `T?`. If `T` is already an optional type,
  the result remains `T?` (optional types do not nest into `T??`).

### Nil-coalescing operator (`??`)

The binary coalescing operator `??` provides a default fallback value when
evaluating an optional:

```sapphire
let active_enemy: Enemy = target ?? default_enemy;
```

The right-hand operand must evaluate to a type compatible with the optional's
underlying base type.

### Pattern matching on optionals

Optional values can be matched directly using `match` expressions by pattern
matching on `none`, concrete literal values, or the default wildcard `...`:

```sapphire
let status = match target {
  none -> "No target",
  ... -> "Target acquired",
};
```

Match arm patterns evaluate expressions or the wildcard ellipsis (`...`). To
conditionally unwrap an optional and bind its inner non-optional value to a new
variable, use `if let ?=` or `guard let ?=`.

## Control flow & pattern matching

### Conditionals (`if`/`else`)

Sapphire supports conditional execution via `if`, `else if`, and `else`
blocks. Parentheses around conditions are optional:

```sapphire
let score = 85;
if score >= 90 {
  print("Grade: A");
} else if score >= 80 {
  print("Grade: B");
} else {
  print("Grade: C");
}
```

### Multi-binding `if` statements

`if` statement headers support declaring one or more variable bindings before
an optional boolean condition, separated by semicolons. Semicolons strictly
delimit variable bindings, while multiple condition checks must be composed
using boolean operators (`&&` or `||`):

```sapphire
if let active_target ?= target;
   let weapon ?= equipped_weapon;
   active_target.health > 50 && weapon.durability > 0 {
  // `active_target` and `weapon` unwrapped and verified against condition
}
```

Bindings and conditions evaluate sequentially from left to right. If any
unwrapping fails or the condition evaluates to `false`, evaluation immediately
short-circuits. If bindings in an `if` header do not use optional unwrapping
`?=`, they must be followed by a boolean condition expression. If partially
acquired resources define `__del__`, they are cleaned up in LIFO order upon
short-circuit failure.

### Guard statements (`guard ... else { ... }`)

Sapphire provides Swift-style `guard` statements to enforce function and loop
preconditions, avoid deeply nested blocks, and promote unwrapped variables
into the surrounding scope:

```sapphire
func process_user(users: [String: User], id: String): int {
  guard let user ?= users.get(id); user.is_active && user.score > 0 else {
    return -1;
  }

  // `user` is unwrapped as non-optional `User` in the outer scope
  return user.score * 10;
}
```

* **Semicolon binding separation**: Multiple variable bindings within a `guard`
  header are separated by semicolons (`let a ?= opt_a; let b ?= opt_b;`),
  followed by an optional boolean condition.
* **Scope promotion**: Variables unwrapped inside `guard` clauses are bound in
  the **surrounding outer scope** for all statements following the `guard`.
* **Control-flow termination**: The `else` block executes if any clause
  evaluates to `none` or `false`. The compiler statically verifies that every
  code path inside the `else` block terminates control flow via `return`,
  `break`, or `continue`.

### Match expressions

Sapphire provides a first-class `match` construct for pattern matching,
supporting both safe value transformation (expressions) and side-effect
control flow (statements).

* **Syntax**: `match subject { pattern -> body, ... }`
* **Single-expression cases**: Cases with a single expression implicitly
  evaluate to that expression's value.
* **Multi-statement blocks**: In a value-producing `match` expression, cases
  using a block `{ ... }` **must** explicitly use `yield <expr>;` to output a
  value. Omitting `yield` in a value-producing block is a compile-time error.
  Using `return` inside a match block returns from the enclosing function.
* **Type consistency**: All arms of a value-producing `match` must yield
  compatible types `T`. If an arm yields `none`, the overall expression type
  is inferred as `T?`.
* **Side-effect statements**: When used strictly as a statement (e.g. without
  variable assignment), blocks do not require `yield` statements.
* **Mandatory comma separators**: Every case branch (including multi-statement
  blocks ending in `}`) must be followed by a comma `,`.
* **Default case**: The wildcard pattern uses the ellipsis token `... ->`.
* **Exhaustiveness**: The compiler statically verifies that all variants of
  `enum`, `bool`, and `optional` subjects are handled or an ellipsis `...`
  default branch is present.

```sapphire
// Value-producing match expression
let label = match status {
  HttpStatus.Ok -> "Success",
  HttpStatus.NotFound -> {
    log("Not found");
    yield "Resource Missing";
  },
  ... -> "Unknown Error",
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
}
```

### Control-flow loops

#### `while` loop

Executes a block of code as long as the condition evaluates to `true`:

```sapphire
var count = 5;
while count > 0 {
  print(String.from(count));
  count -= 1;
}
```

#### `for-in` loop

Iterates over elements in an array, entries in a map, or numeric sequences
generated by `range()`:

* **Scoping & mutability**: By default, loop variables are implicitly declared
  as immutable constants scoped to the loop block.
* **Array iteration**: Uses a single variable (`for item in array`).
* **Map iteration**: Uses dual key-value variables (`for key, val in map`).
* **Range iteration**: Uses a single integer loop variable over a half-open
  range generated by `range(stop)` or `range(start, stop, step)`:
  ```sapphire
  for i in range(0, 10, step = 2) {
    print(String.from(i));
  }
  ```
* **Mutable loop variables**: Declared with `var`
  (e.g. `for var item in items`).

#### Loop control statements (`break` & `continue`)

* **`break;`**: Immediately terminates the innermost enclosing loop.
* **`continue;`**: Immediately terminates the current iteration and advances
  to the next iteration.
* **Scope restriction**: Using `break` or `continue` outside an enclosing loop
  produces a compile-time error.

## Functions, closures, & coroutines

### Function declarations & return types

Named functions must fully declare parameter types and explicit return types
using colon syntax:

```sapphire
func calculate_damage(attacker: Player, target: Enemy,
                      is_critical: bool = false): int {
  let base_dmg = attacker.attack_power - target.defense;
  let multiplier = is_critical ? 2 : 1;
  return base_dmg > 0 ? base_dmg * multiplier : 0;
}
```

* **Named parameters**: Callers may invoke functions using named arguments
  (e.g. `calculate_damage(attacker = p, target = e, is_critical = true)`).
* **Default parameters**: Parameters with default values must appear after
  positional parameters without defaults.
* **Void functions**: Functions returning nothing omit the return type or
  specify `: void`.

### Calling conventions vs. storage semantics

Sapphire distinguishes clearly between **storage semantics** and
**calling conventions**:

* **Primitive scalars** (`int`, `float`, `bool`, `none`) are passed by
  **value**.
* **Non-primitive types** (user-defined `struct`s, `proto`s, and collections
  `String`, `Array`, `Map`, `Arena`, `Range`) are passed by **constant
  reference (borrow)** by default to eliminate copy overhead without pointer
  syntax. The caller retains ownership, and the callee cannot mutate the value.
* **Value returns with RVO**: Returning a stack struct from a function is done
  by value with compiler-enforced Return-Value Optimization (RVO) copy elision,
  constructing the instance directly in the caller's stack frame. Returning
  borrowed references to local stack frames is statically prohibited.

### Call-site parameter modes: borrowing vs. moving

Callers have explicit control over parameter mutability and ownership transfer:

* **Constant borrow (default)**: Passing an identifier without modifiers passes
  it by constant reference. The caller retains ownership, and the callee cannot
  mutate the value.
* **Exclusive mutable borrow (`var`)**: Declared with `var` in the function
  signature (`func update(var target: Entity)`). Gives the callee exclusive
  mutable access. The caller retains ownership after the call completes. Callers
  cannot pass immutable `let` constants to `var` parameters.
* **Ownership transfer (`move`)**: Callers pass `move <identifier>` (e.g.
  `consume(move resource)`). Ownership is transferred into the function, and
  the caller's variable is statically invalidated in the current scope. Moving
  is permitted on both `let` constants and `var` variables.
  * **No moving out of parameters**: Borrowed function parameters cannot be
    moved out of (`Cannot move out of borrowed parameter`).
  * **Variable reinitialization**: Reassigning a moved mutable variable (`var`)
    reinstates it in the current scope, enabling subsequent moves or reads.
  * **Shared references**: `SharedRef<T>` instances are read-only shared
    borrows and cannot be passed to mutable `var` parameters.

### Scope-bound aliasing rules (call-site reference exclusivity)

To guarantee reference safety and eliminate data corruption without lifetime
annotations, the compiler enforces compile-time **reference exclusivity**:

* **Reference types only**: Evaluated across all reference paths (`String`,
  `Array`, `Map`, `Arena`, and user-defined `struct` and `proto` types).
* **Overlapping mutability restrictions**: Inside any single function or method
  call, a reference path (e.g. `player` or `player.pos`) cannot be passed as a
  mutable parameter (`var`) if it is already referenced (mutably or immutably)
  within the same call.
* **Implicit-receiver checking**: In a method call (`p.heal(...)`), the receiver
  is implicitly treated as an argument (passed mutably for `var func` methods).

```sapphire
// Rejected: 'player' is passed mutably as 'target' and as a const-ref as
// 'observer'.
execute_interaction(observer = player, target = player);

// Rejected: 'player' (receiver) is mutably passed, conflicting with its use
// as 'other'.
player.mutate(other = player);
```

### Multiple returns & destructuring

Functions can return multiple values separated by commas:

```sapphire
func get_player_status(): int, float, bool {
  return 100, 50.5, true;
}

let hp, mana, is_alive = get_player_status();
```

Multiple return values are unwrapped immediately via destructuring assignments
and cannot be stored directly as an anonymous tuple object.

### First-class functions

Functions are first-class citizens. Function types use the arrow token (`->`):

```sapphire
var math_op: (int, int) -> int;
var callback: (String) -> void;
```

### Anonymous functions & closure capture semantics

Sapphire supports lambda expressions with single-parameter shorthand or
multi-parameter blocks:

```sapphire
// Single-parameter shorthand
let doubled = numbers.map(x -> x * 2);

// Multi-parameter block lambda
let add = (a: int, b: int) -> int {
  return a + b;
};
```

* **Lexical capture**: Closures capture surrounding local variables by
  constant borrowed reference by default.
* **Escape safety**: Closures that escape their defining stack frame (e.g.
  returned from a function or stored in a long-lived arena structure) cannot
  capture local stack-allocated variables by reference; captured variables must
  be moved or allocated within an `Arena` or heap `Ref<T>`.

### Coroutines (`Coroutine<T>`)

Sapphire provides native stackless coroutines for cooperative multitasking,
generators, and stateful sequences:

```sapphire
// Stateful task coroutine
func task_runner(): Coroutine<void> {
  print("Step 1");
  yield;
  print("Step 2");
}

// Generator stream coroutine
func fibonacci(count: int): Coroutine<int> {
  var a = 0;
  var b = 1;
  for i in range(count) {
    yield a;
    let next = a + b;
    a = b;
    b = next;
  }
}
```

* **Type declaration**: Parameterized by their yield type (`Coroutine<T>` for
  generators yielding values of type `T`, or `Coroutine<void>` for stateful
  routines).
* **Yield statements**: `yield <expr>;` suspends execution and yields a value;
  `yield;` suspends execution for void coroutines.
* **Lifecycle methods**:
  * `.step()`: Advances the coroutine to the next yield or return. Returns `T?`
    for value-producing coroutines (evaluating to `none` once complete), or
    `none` for void routines.
  * `.is_done()`: Returns boolean indicating whether routine has terminated.
  * `.reset()`: Restarts the coroutine from the beginning.

  For further details, see [coroutines](builtins.md#coroutines) in
  `builtins.md`.

## Structs & implementation blocks

### Struct declaration & `impl` blocks

The primary data layout tool is the `struct` keyword. To strictly separate data
layout from behavior, all methods (including constructors and destructors)
**must** be defined inside an explicit implementation (`impl`) block:

```sapphire
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

  var func use() {
    self.durability -= 1;
  }

  static func create_legendary(): Weapon {
    return Weapon(dmg = 250);
  }

  func get_name(): String {
    return self.name;
  }
}
```

* **Implicit `self`**: The `self` token is implicitly available within instance
  methods.
* **Immutable `self` by default**: Instance methods have an immutable `self`
  reference by default.
* **Mutating methods (`var func`)**: Non-static methods that modify properties
  of `self` must be explicitly declared using `var func`.
* **Static methods**: Declared using the `static` keyword. Inside static
  functions, `self` is unavailable.

### Struct instantiation & constructor enforcement

1. **Constructor instantiation (`StructName(...)`)**: When a struct defines
   an `__init__` constructor inside its `impl` block, instantiation **must**
   use constructor call syntax matching the constructor's parameters:
   ```sapphire
   let sword = Weapon(dmg = 45, name = "Broadsword");
   ```
   To protect class invariants and ensure required initialization logic
   executes, direct curly-brace literal syntax `Weapon { ... }` is strictly
   disallowed for structs that define `__init__`.
2. **Curly-brace initializers (`StructName { ... }`)**: For plain data structs
   without custom `__init__` constructors, direct curly-brace initialization
   is the standard syntax:
   ```sapphire
   struct Point {
     var x: float;
     var y: float = 0.0;
   }

   let p = Point { x = 10.0 };
   ```

Fields declared with explicit default values, optional types (`T?`), or
primitive scalar types (`int`, `float`, `bool`, which default implicitly to
`0`, `0.0`, `false`) may be omitted during initialization. The compiler
verifies that all non-optional reference fields without defaults are
initialized.

### Member encapsulation via construction contract

Sapphire omits member-level access control keywords (`public`, `private`) in
favor of construction-contract encapsulation:
* **Module-level encapsulation**: Visibility is defined at the file/module
  boundary using the `export { ... }` manifest block.
* **Plain data structs**: Structs without `__init__` constructors expose their
  fields for direct reading and mutation on `var` bindings.
* **Constructed structs**: Structs declaring `__init__` constructors restrict
  field mutations outside their defining module, requiring callers to invoke
  explicit mutating methods (`var func`).

### Deterministic destructors (`__del__`)

Structs support deterministic RAII via destructors defined inside `impl` blocks:

```sapphire
impl FileHandle {
  func __del__() {
    if self.is_open {
      self.close();
    }
  }
}
```

* **LIFO destruction**: When variables exit their lexical block scope,
  destructors are invoked automatically in reverse order of declaration.
* **Early returns and loop exits**: The compiler injects destructor calls along
  all early return paths and loop control jumps (`break`, `continue`).
* **Copy elision**: When an instance is returned from a function by value, its
  destructor in the local frame is elided via Return-Value Optimization (RVO).

## Enums

Sapphire provides native support for integer-backed and string-backed
enumerations via the `enum` keyword:

```sapphire
enum Direction {
  North,
  East,
  South,
  West,
}

enum DrawMode {
  Fill = "fill",
  Line = "line",
  Default,  // Auto-assigned "Default"
}

enum HttpStatusCode {
  Ok = 200,
  Created = 201,
  BadRequest = 400,
  NotFound = 404,
  InternalError = 500,
}
```

* **Default values**: Integer enum members automatically increment starting at
  `0` unless explicitly assigned.
* **String enums**: Members can be assigned string literals. Subsequent
  unassigned members default to their identifier string.
* **Nominal typing**: Enums introduce named types into scope (`Direction`,
  `DrawMode`).
* **Strict primitive separation**: Implicit conversion to `int` or `String` is
  prohibited. Converting requires explicit static casting (`dir as int`,
  `mode as String`) or fallible conversion (`HttpStatusCode.from(200)`).

## Inheritance, traits, & polymorphism

### Static structural inheritance

Structures can inherit the field layout and methods of one or more parent
structures at compile time:

```sapphire
struct Position {
  var x: float;
  var y: float;
}

struct Health {
  var hp: int = 100;
  var max_hp: int = 100;
}

struct Player: Position, Health {
  var name: String;
}
```

#### Multi-parent delegation rules

* **Field layout inlining**: Fields from all parent structures are inlined into
  the child structure in order of declaration.
* **Conflict prevention**: Duplicate field names across parents or between
  parent and child produce a compile-time `SemanticError`.
* **Circular inheritance**: Circular struct delegation is strictly forbidden.

#### Constructor chaining & base initializers

When a child struct constructor initializes parents that define `__init__`,
it chains parent initializers using colon syntax on the constructor:

```sapphire
impl Player {
  func __init__(name: String, x: float, y: float, hp: int):
      Transform2D(x = x, y = y),
      Health(max_hp = hp) {
    self.name = name;
  }
}
```

* **Mandatory parent initialization**: If any parent struct defines an
  `__init__` constructor, the child constructor must explicitly chain-initialize
  that parent.
* **No `self` references**: Base initializer argument expressions cannot
  reference `self` (`References to 'self' are not allowed in base initializer
  arguments`).

#### Disallowed up-casting

Sapphire **strictly disallows up-casting** for statically inherited structures
(e.g. `let a: Animal = cat;` or `cat as Animal` is rejected at compile time).

* **Eliminates object slicing**: Child fields are never sliced away.
* **Eliminates method ambiguity**: Dispatches are statically known at compile
  time without vtables or dynamic lookups.
* **Separates concerns**: Static inheritance is strictly for *layout and code
  reuse*. Behavioral polymorphism is offloaded to **traits**.

#### Syntactic delegation (transparent forwarding)

Under the hood, structural inheritance compiles to **syntactic delegation**
(field composition + generated forwarding methods). This incurs **zero
runtime performance penalty**:
* **Direct static calls**: Calls are resolved at compile time to direct
  branch/jump instructions with zero pointer chasing.
* **Compiler inlining**: Forwarding methods are prime candidates for complete
  inlining, vanishing into zero instruction overhead.
* **Compile-time offset calculation**: Pointer adjustments to sub-objects are
  calculated at compile time.

### Traits (compile-time contracts & implicit subtyping)

Traits define behavioral contracts without prescribing physical memory layouts:

```sapphire
trait Actor {
  func update();
}

impl Actor for Cat {
  func update() { /* Cat update */ }
}

impl Actor for Dog {
  func update() { /* Dog update */ }
}

func update_actor(actor: Actor): Actor {
  actor.update();
  return actor;
}
```

* **Implicit subtyping**: Any struct implementing the trait's methods is
  implicitly assignable to targets expecting the trait type or `Trait?`.
* **Interface erasure**: Values viewed through a trait type can only access
  methods defined on that trait.

### Trait dispatch models & compilation strategies

Sapphire provides a tiered model for trait polymorphism:

1. **Compile-time trait contracts & runtime erasure (current toolchain)**:
   In the multi-target transpiler toolchain (Python, Lua), trait implementations
   are checked statically at compile time. Functions accepting trait types
   enforce method presence, and calls are emitted directly on underlying
   instances without runtime boxing or vtable overhead.
2. **Static monomorphization via direct trait parameters (zero-cost calls)**:
   Functions accepting trait types directly (e.g. `func render(a: Actor)`)
   enable specialize direct-call code for each concrete struct implementing the
   trait, enabling inlining and eliminating fat pointers.
3. **Closed-world tagged unions & dynamic trait objects (native AOT roadmap)**:
   In the planned native backend, heterogeneous trait collections (`[Trait]`)
   lower to closed tagged unions over contiguous memory with direct jump tables.
   For open dynamic library (`.so`/`.dylib`) boundaries, explicit dynamic trait
   objects (`Dynamic<Trait>`) provide 2-word fat pointers with immutable static
   vtables:
   ```sapphire
   // Native AOT roadmap syntax
   let plugin = Dynamic<PluginHook>(my_hook);
   ```

### Explicit composition (data-oriented design)

Structs can explicitly compose other structs without inheritance, ideal for
Entity-Component-System (ECS) architectures:

```sapphire
struct PhysicsComponent {
  var velocity: Vector2;
  var mass: float;
}

struct Player {
  var physics: PhysicsComponent;
  var health: int;
}
```

## Generics & parametric polymorphism

Sapphire supports zero-overhead parametric polymorphism for structures,
implementation blocks, traits, and functions using angle brackets (`<T, U>`).

### Generic declaration syntax

```sapphire
struct Stack<T> {
  var items: [T];
}

impl Stack<T> {
  func push(item: T) { /* ... */ }
}

trait Container<T> {
  func get(): T;
}

func identity<T>(item: T): T {
  return item;
}
```

### Call-site type inference & explicit arguments

* **Type-argument inference**: Type arguments are contextually inferred from
  arguments: `let x = identity(42);` (inferred as `identity<int>(42)`).
* **Explicit type arguments**: Type arguments can be explicitly specified:
  `let s = Stack<int> { items = [10, 20] };`.

### Compile-time monomorphization

Generics incur zero runtime overhead. During compilation, the compiler tracks
concrete type combinations, monomorphizes generic AST nodes into specialized
concrete definitions, and emits unboxed concrete definitions for each type.

## Memory architecture, arenas, & smart references

Sapphire combines stack allocation, explicit lexical arenas, prototypal state
delegation, and smart references into a unified memory model.

### Stack-first memory model & deterministic RAII

1. **Stack allocation by default**: Standard `struct` instances are allocated
   directly on the stack with deterministic LIFO teardown. Destructors
   (`__del__()`) execute in reverse declaration order upon exiting lexical
   blocks.
2. **RVO value returns**: Structs returned from functions are constructed
   directly in the caller's stack frame via Return-Value Optimization (RVO)
   copy elision, eliding local destructors.
3. **Static use-after-free prevention**: Returning borrowed references to
   local stack structs is rejected at compile time.

### Explicit arena management

For managed objects and dynamic lifecycles, Sapphire provides explicit lexical
arenas instantiated via `Arena()`:

```sapphire
let level_arena = Arena();
let p = Point { x = 10.0, y = 20.0 } in level_arena;
```

* **Lexical RAII teardown**: When an `Arena` binding goes out of scope, the
  runtime tears down the arena and deallocates all allocated instances.
* **The `in` allocation suffix**: Both `struct` and `proto` allocations can be
  targeted to an arena using the `in <arena>` suffix.

### Prototypal state delegation (`proto` & `clone`)

Prototypal inheritance allows objects to delegate state to other objects at
runtime. Clones dynamically delegate field lookups to their prototype: changes
to the prototype propagate live to clones, while clones can selectively shadow
values.

Prototypal inheritance is opt-in and requires the `proto` keyword:

```sapphire
let my_arena = Arena();

proto Enemy {
  var damage: int;
  var health: int;
}

// Protos require allocation within an explicit arena
var base_goblin = Enemy { damage = 10, health = 100 } in my_arena;

// Clones delegate state live to base_goblin
let elite_goblin = clone base_goblin {
  self.health = 200;  // Shadowed locally
};

print(String.from(elite_goblin.damage));  // 10 (delegated to base_goblin)
base_goblin.damage = 15;
print(String.from(elite_goblin.damage));  // 15 (reflected live)
```

#### The `__proto__` property

Every `proto` instance exposes a read-only `__proto__` property:
* For instances created via `clone base`, `__proto__` evaluates to `base`
  (typed as optional `T?`).
* For root instances created directly in an arena, `__proto__` evaluates to
  `none`.
* Standard `struct` instances do not possess prototype tables or a `__proto__`
  property.

#### Copy-on-Write (CoW) state isolation

To prevent unexpected cross-instance mutations, mutating a property within a
nested reference field of a cloned instance triggers **Copy-on-Write (CoW)**:
the runtime shallow-copies the immediate nested reference locally on the clone
before applying the mutation, isolating the prototype from mutations.

### Smart heap references (`Ref<T>`, `SharedRef<T>`, `WeakRef<T>`)

For long-lived objects, recursive data structures (trees, graphs), or instances
that must outlive lexical scopes, Sapphire provides first-class smart pointers:

* **Unique heap allocation (`Ref<T>`)**: Instantiated via `Ref(value)`.
  Exclusive owner of underlying heap memory. Strictly move-only (`let b = move
  a;`). Bypasses arena escape analysis, allowing instances to be returned
  freely from functions.
* **Shared heap allocation (`SharedRef<T>`)**: Instantiated via `SharedRef(val)`
  or `SharedRef(move r)`. Reference-counted. Duplicate handles are created
  explicitly via `s.share()`.
* **Weak observer (`WeakRef<T>`)**: Non-owning reference created via
  `s.downgrade()`. Prevents cycles. Safely upgraded to `SharedRef<T>?` via
  `if let active ?= w.upgrade() { ... }`.
* **Transparent dereferencing**: Member access (`r.field`) and method calls
  (`r.method()`) automatically dereference to the inner value.

### Arena escape analysis & static safety

The compiler enforces static scope-bound escape rules for arenas:
* **Outer-scope variable escape**: A variable in an outer scope cannot be
  assigned a reference to an object allocated in an inner/nested arena.
* **Function-return escape**: A function cannot return a reference to an object
  allocated in an arena local to that function.

## Module system & encapsulation

### Private by default

All top-level declarations (`struct`, `enum`, `trait`, `func`, `let`, `var`)
are **module-private by default** and cannot be accessed outside their defining
file unless explicitly listed in an `export` manifest.

### Explicit export manifest (`export { ... }`)

A module defines its public API using an `export` manifest block:

```sapphire
// lib/graphics.sp
import lib.enums;

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

* **Single-block enforcement**: Exactly one `export { ... }` block is permitted
  per file.
* **Top-level placement**: May be placed at the top or bottom of the module.
  Forward references to symbols defined later in the file are fully supported.
* **Aliasing & re-exporting**: Symbols can be exported under aliases using `as`,
  and imported symbols can be re-exported via dot paths.

### Module imports (`import`)

```sapphire
import lib.graphics;
import lib.graphics as gfx;

let img = gfx.new_image("hero.png");
```

### Transpilation semantics

* **Python target**: Imports transpile to native `import ...`. Export manifests
  emit `__all__ = [...]`.
* **Lua 5.1 target**: Imports transpile to `local mod = require(...)`. Export
  manifests emit a module table `local _M = {}` and append `return _M`.

## Host runtime interoperability & annotations

Sapphire supports native interoperability with scripting host engines (such as
**Love2D** in Lua 5.1 / LuaJIT environments):

### `@extern` (host variable binding)

Binds Sapphire variables to external host symbols provided by the runtime
environment without generating variable declarations:

```sapphire
@extern
var love: LoveEngine;
```

* **Declaration requirements**: Variable declarations marked with `@extern`
  must specify an explicit type annotation and cannot have an initializer
  expression (`@extern var x = 5;` is rejected).

### `@export` (transpiled symbol renaming)

* **Global callback export**: `@export("love.update") func update(dt: float)`
  emits direct global callback paths (e.g. `function love.update(dt) ... end`).
* **Trait method aliasing**: `@export("native_name")` placed on a trait method
  configures the transpiler to emit `native_name` instead of the Sapphire
  method identifier.

### Trait-based host interfaces & resource handles

External host APIs are defined cleanly using traits:

```sapphire
// Instance methods take explicit `self` (transpiles to Lua colon syntax)
trait Image {
  func getWidth(self): float;
}

// Module functions omit `self` (transpiles to Lua dot syntax)
trait Graphics {
  @export("setColor")
  static func setColorRgba(r: float, g: float, b: float, a: float = 1.0);

  static func rectangle(mode: String, x: float, y: float, w: float, h: float);
}
```

### Live hot-reloading & `@on_reload` lifecycle hook

Sapphire provides development hot-reloading (`sapphire run --dev`) under the
Lua / Love2D backend:
* **In-place patching**: Structures and prototype metatables persist across
  reloads, updating method definitions without resetting application state.
* **`@on_reload` hook**: Functions annotated with `@on_reload` are automatically
  invoked whenever the containing module is reloaded:
  ```sapphire
  @on_reload
  func handle_reload() {
    print("[Hot Reload] Game state patched successfully!");
  }
  ```

## Compiler pipeline & toolchain architecture

### Source map generation & runtime stack trace demangling

When transpiling Sapphire code, the compiler tracks AST node position metadata
to generate source-map sidecars and runtime demanglers:

1. **Standard V3 source maps (`.lua.map`)**: Generated using Base64 VLQ encoding
   with embedded `sourcesContent` strings for IDE debugging.
2. **Runtime stack-trace demangling**: Embedded `_SP_LINE_MAP` lookup tables
   pair generated line numbers with original Sapphire lines and snippets.
3. **Love2D error-handler hook**: Intercepts uncaught runtime errors and
   translates host call stacks into original `.sp` filenames and line numbers on
   terminal logs and graphical crash screens.

## Architectural design decisions & trade-offs

### Isolating and minimizing virtual method tables (vtables)

Traditional object-oriented languages rely on virtual method tables (vtables)
for all dynamic dispatch, introducing pointer-chasing overhead (`this -> vptr
-> vtable -> func`) and inhibiting cross-module inlining.

Sapphire avoids vtables in standard operations:
* **Zero-vtable structural inheritance**: Struct inheritance is treated as
  compile-time syntactic delegation (composition + forwarding).
* **Compile-time trait contracts**: Behavioral polymorphism is statically
  verified at compile time and erased at runtime in the multi-target transpiler.
* **Closed-world tagged unions (native roadmap)**: Heterogeneous trait
  collections (`[Trait]`) are planned to compile into contiguous tagged unions
  with direct jump tables in the native backend.
* **Data-only prototypal delegation**: Dynamic delegation (`clone`) delegates
  data fields in an `Arena`. Methods remain statically dispatched.
* **Explicit opt-in vtables (`Dynamic<Trait>`, native roadmap)**: Virtual
  method tables are never generated implicitly. In the native compilation
  architecture, they are reserved strictly for explicit open dynamic library
  or plugin boundaries via `Dynamic<Trait>`.

### Avoiding physical inheritance layouts

Flat physical inheritance forces parent and child fields together into a single
contiguous block, introducing:
* **Cache-line pollution**: Reading a subset of fields in data-oriented loops
  pulls in unrelated inherited fields.
* **Layout rigidity**: Rigid hierarchies prevent compilers from reordering
  fields across structures to minimize padding.
* **Tight coupling**: Modifying a base struct invalidates layout offsets across
  all descendants.

Sapphire decouples ergonomic structural inheritance from physical memory
representation via syntactic delegation and monomorphized traits.

### Avoiding throwable exceptions

Traditional exception mechanisms (`try`/`catch`/`throw`) introduce hidden
control-flow jumps and expensive stack-unwinding machinery. Sapphire omits
throwable exceptions in favor of:
* **Explicit fallibility**: Functions express fallibility in signatures using
  optionals (`T?`) or multiple return values (`T, bool`).
* **Deterministic performance**: Eliminating exception unwinding runtime
  machinery ensures predictable CPU execution paths.
* **Exhaustive error handling**: Combining enums with `match` expressions
  allows the compiler to enforce that all error variants are handled.
* **Resource safety without `finally`**: Lexical RAII and arena destruction
  guarantee that resources are automatically cleaned up on scope exit.

### Module-level and construction-contract encapsulation

Rather than fine-grained access modifier keywords (`public`, `private`),
Sapphire relies on:
* **Single encapsulation boundary**: Visibility is defined at the file/module
  level using `export { ... }`.
* **Construction-contract safety**: Invariants are protected through
  constructors. Structs declaring `__init__` restrict field mutations outside
  their defining module, requiring mutations to invoke explicit methods.

### Anonymous tuples vs. lightweight named structs

Sapphire intentionally omits general-purpose anonymous tuple types
(`(int, String, bool)`) in favor of:
1. **Multiple return values for function returns**: `func pos(): float, float`
   destructured immediately at call sites via `let x, y = pos();`.
2. **Lightweight named structs for persistent compound data**: Defining a
   dedicated `struct Point { var x: float; var y: float; }`.

Unnamed positional elements (`tuple[0]`) degrade code readability and introduce
fragile indexing assumptions across refactors. Because Sapphire structs compile
to zero-cost contiguous memory, named structs provide superior clarity with
zero performance penalty.

### Future considerations & exploratory directions

* **Call-site mutability markers**: Mandatory call-site markers (such as
  `modify(var target)`) are under evaluation to alert code reviewers to mutating
  arguments.
* **Standard `Result<T, E>` sum type**: While optionals (`T?`) and multi-value
  returns handle common failure states, a standard algebraic `Result<T, E>`
  type with associated error payloads may be introduced for rich error
  reporting.
