# Style guide

This document establishes the official style, formatting, naming, and idiomatic
design conventions for the Sapphire programming language. All standard library
modules, samples, and Sapphire source files should adhere to these guidelines.

## 1. Formatting & layout

* **Line length**: Lines should be kept to a maximum of 80 characters.
* **Indentation & line wrapping**:
  * The bodies of blocks should generally be indented **2 spaces**.
  * When continuing a statement on a subsequent line, indent with **4 spaces**.
  * When continuing a function definition's parameter list or a function call
    site across lines, either align parameters with the opening parenthesis `(`,
    or break immediately after `(` using a **4-space hanging indent** when
    aligning with `(` would exceed 80 characters. Keep the closing `)` (or
    `): ReturnType {`) on the final parameter/argument line. When an
    `in <arena>` suffix follows a multi-line call or struct initializer, attach
    `in <arena>;` directly after the closing `)` or `}`.
  * Omit parentheses around conditions in `if`, `while`, `guard`, and `match`
    headers. When wrapping a multi-line `if` condition or `;`-delimited `?=`
    binding list, align subsequent lines under the first expression after `if `
    (**3 spaces** relative to `if`) so the header remains visually distinct
    from the 2-space block body.
  * Keep binary operators (`||`, `&&`, `+`) at the **end** of wrapped lines;
    break fluent method chains **before `.`** using a 4-space continuation
    indent:
    ```sapphire
    func send_request(
        url: String, method: String = "GET",
        timeout_ms: int = 5000): String {
      return f"{method} {url} ({timeout_ms}ms)";
    }

    func demo_wrapping(numbers: [int], is_ready: bool, has_quota: bool): int {
      if is_ready &&
         has_quota {
        let response = send_request(
            url = "https://api.example.com/v1/users",
            method = "POST",
            timeout_ms = 10000);
        print(response);
      }

      return numbers
          .filter(x -> x % 2 == 0)
          .map(x -> x * x)
          .reduce(0, (acc, x) -> acc + x);
    }
    ```
* **Statement termination**:
  * All statements must be explicitly terminated with a semicolon (`;`), with
    the exception of standalone blocks ending in `}` where permitted (`if`,
    `while`, `for`, standalone side-effect `match` statements, and bare
    `{ ... }` lexical RAII blocks). This prevents syntax parsing ambiguities
    with multi-line statements and expressions.
  * Value-producing brace expressions inside statements—such as
    `let x = match ... { ... };`, `Struct { ... };`, map literals, multi-line
    block lambdas, and `clone base { self.hp = 30; };` (or
    `clone base { ... } in arena;`)—must terminate the enclosing statement with
    `;`. Note that `clone` blocks contain `;`-terminated `self.field = val;`
    statements, unlike comma-separated `Struct { field = val, }` initializers.
* **Brace spacing & trailing commas**:
  * Single-line plain struct initializers pad inside braces
    (`Vector2D { x = 0.0, y = 0.0 }`), whereas single-line map literals do not
    (`{"north": 1, "south": 2}`, `{}`).
  * Include trailing commas on multi-line `enum` variants, `export { ... }`
    manifests, `match` arms (including the final `... ->` arm), multi-line
    `Struct { ... }` initializers, and multi-line array/map literals. Omit
    trailing commas on single-line literals (function parameter lists and call
    argument lists do not accept trailing commas):
    ```sapphire
    enum Direction {
      North,
      East,
      South,
      West,
    }

    struct Vector2D {
      var x: float;
      var y: float;
    }

    proto Unit {
      var hp: int;
      var pos: Vector2D;
    }

    func demo_braces(dir: Direction) {
      let origin = Vector2D { x = 0.0, y = 0.0 };
      let weights = {"north": 1, "south": 2};

      // Standalone side-effect match omits trailing ';'
      match dir {
        Direction.North -> {
          print(f"Presets: {weights.size()}");
        },
        ... -> {},
      }

      // Value-producing match & clone expressions require trailing ';'
      let label = match dir {
        Direction.North -> "North",
        ... -> "Other",
      };

      // Bare lexical block scopes arena lifetime without trailing ';'
      {
        var temp_arena = Arena();
        let base_unit = Unit {
          hp = 100,
          pos = origin,
        } in temp_arena;
        var scout = clone base_unit {
          self.hp = 60;
        };
        print(f"{label}: {scout.hp}");
      }
    }
    ```
* **Constructor chaining (base initializers)**: When a struct constructor
  invokes parent constructors (`: Parent1(...), Parent2(...)`):
  * **Single-line layout**: If the constructor signature, base initializer
    list, and opening brace `{` fit within the 80-character line length limit,
    they may remain on a single line:
    ```sapphire
    struct Position {
      var x: float;
      var y: float;
    }

    impl Position {
      func __init__(x: float, y: float) {
        self.x = x;
        self.y = y;
      }
    }

    struct Player: Position {
      var name: String;
    }

    impl Player {
      func __init__(name: String, x: float, y: float): Position(x, y) {
        self.name = name;
      }
    }
    ```
  * **Multi-line layout**: If the declaration exceeds 80
    characters or spans multiple parent initializers, the colon must remain on
    the constructor signature line, each parent initializer must be placed on
    its own line indented **4 spaces** (2 extra spaces beyond standard body
    indentation), and the opening brace `{` is placed on the final parent
    initializer line. Child property assignments in the constructor body use
    standard **2-space** indentation:
    ```sapphire
    struct Transform2D {
      var x: float;
      var y: float;
    }

    impl Transform2D {
      func __init__(x: float, y: float) {
        self.x = x;
        self.y = y;
      }
    }

    struct Health {
      var max_hp: int;
    }

    impl Health {
      func __init__(max_hp: int) {
        self.max_hp = max_hp;
      }
    }

    struct Player: Transform2D, Health {
      var name: String;
    }

    impl Player {
      func __init__(name: String, x: float, y: float, hp: int):
          Transform2D(x = x, y = y),
          Health(max_hp = hp) {
        self.name = name;
      }
    }

    struct NamelessEnemy: Transform2D, Health {}

    // Also okay
    impl NamelessEnemy {
      func __init__(x: float, y: float, hp: int): Transform2D(x, y),
                                                  Health(max_hp = hp) {
        if hp < 0 {
          print(f"Got HP below zero: {hp}");
        }
      }
    }
    ```
* **Parameter ordering**: Constant params should generally precede mutable
  (`var`) params in function definitions. The exception is params with default
  values, which must come last.

## 2. Naming conventions

* **Variables & fields**: All variable names, parameters, and struct/proto
  fields—including function-typed variables and callbacks (`on_click`,
  `is_alive`)—should use `snake_case`.
* **Booleans & predicates**: Prefix boolean bindings, fields, and predicate
  functions/methods with `is_`, `has_`, or clear adjectival stems (e.g.,
  `is_active`, `is_open`, `has_path_to`).
* **Functions & methods**: Built-in and user-defined Sapphire functions and
  methods should use `snake_case`. Avoid `PascalCase` function names, which can
  collide with type names in Sapphire's shared per-scope identifier namespace.
  Foreign `camelCase` or `PascalCase` method names should appear only on
  `@extern` / `@export` host FFI bindings mirroring external APIs.
* **Types**:
  * **Primitive types**: Lowercase naming (e.g., `int`, `float`, `bool`, `none`,
    `void`).
  * **Concrete & prototypal types**: `PascalCase` nouns (e.g., `String`,
    `Player`, `Vector2D`, `Arena`) for built-in and user-defined `struct`,
    `proto`, and `enum` types.
  * **Traits**: `PascalCase` `-able` adjectives for single behavioral
    capabilities (`Updatable`, `Drawable`, `Renderable`, `Damageable`), and
    `PascalCase` nouns for domain roles or opaque host handles (`Combatant`,
    `Widget`, `TestCase`, `BytesHandle`).
  * **Generic type parameters**: Single uppercase letters (`T`, `K`, `V`).
* **Constants**: Global or compile-time constant expressions should use
  `SCREAMING_SNAKE_CASE` (e.g., `MAX_SPEED`).
* **Enum values**: Prefer `PascalCase` for enum variants (`Direction.North`,
  `HttpStatus.NotFound`). `SCREAMING_SNAKE_CASE` may be used when matching
  external domain constants, provided casing is kept consistent.
* **Modules & test suites**: Module filenames use `snake_case.sp`. Unit test
  files use `*_test.sp`, `testing.TestCase` structs end in `Test`
  (e.g. `MathTest`), and test methods or `@test` functions begin with `test_`.
* **Identifier namespace**: Variables, functions, and structs share the same
  identifier namespace per scope (e.g., a function and a struct cannot share a
  name in the same scope).

## 3. Types, annotations, & inference

* **Collection & unit type syntax**:
  * Always prefer `[T]` and `[K: V]` shorthand over `Array<T>` and `Map<K, V>`.
  * Omit `: void` on named functions and methods that return no value
    (`func render()`, not `func render(): void`).
  * Prefer `-> void` in non-returning function type annotations
    (`(String) -> void`) and `Coroutine<void>` for stateful non-yielding
    coroutines so unit types stay uniform across signatures.
* **Type inference vs. explicit annotations**:
  * Rely on type inference for `let` and `var` bindings whenever the right-hand
    side makes the type unambiguous (`let max_players = 100;`,
    `var engine = GameEngine();`).
  * Provide explicit `: Type` annotations when required for empty collection
    literals (`let empty_ids: [int] = [];`), `none`-initialized or widened
    optionals (`var target: Sprite?;`), heterogeneous trait collections
    (`let scene: [Renderable] = [sprite];`), intentional numeric widening
    (`var coord_x: float = 10;`), and `@extern` declarations:
    ```sapphire
    trait Renderable {
      func render();
    }

    struct Sprite {
      let id: String;
      var on_click: ((String) -> void)?;
    }

    impl Renderable for Sprite {
      func render() {}
    }

    func run_cutscene(): Coroutine<void> {
      yield;
    }

    func demo_types() {
      let sprite = Sprite { id = "hero", on_click = none };

      let empty_ids: [int] = [];
      var visited: [String: bool] = {};
      var active_sprite: Sprite?;  // Avoid unneeded ` = none`
      let scene: [Renderable] = [sprite];
      active_sprite = sprite;
      print(f"{empty_ids.size()} {visited.size()} {scene.size()}");
    }
    ```

## 4. Idiomatic patterns & API design

* **Named vs. positional arguments at call sites**:
  * Use positional arguments for single-parameter calls and obvious mathematical
    or collection operations (`enemy.take_damage(10)`,
    `scores.contains("alice")`, `pos.move_by(5.0, -2.0)`).
  * Prefer **named arguments** for boolean or behavioral flags
    (`items.sort(reverse = true)`, `values.map(x -> x * 10, in_place = true)`,
    `"FF".to_int(radix = 16)`), multi-field constructors and factories, and
    calls with adjacent same-typed parameters
    (`execute_attack(attacker = hero, defender = slime, is_critical = true)`).
* **Plain data structs vs. `__init__` vs. fallible factories**:
  * **Plain data structs**: Omit `func __init__` (and specify inline field
    defaults) on transparent data records, configs, and components. Defining
    `__init__` disables `Struct { ... }` literal syntax and locks fields
    against direct mutation outside the defining module.
  * **Constructors (`func __init__`)**: Define `__init__` when computing
    derived state, initializing an owned `Arena`, or enforcing invariants.
  * **Fallible factory functions**: Because Sapphire omits throwable exceptions
    and `__init__` cannot return `none`, expose fallible initialization via a
    `static func` or module factory returning `T?`.
* **`impl` organization & `Arena` LIFO ordering**:
  * Place a type's inherent `impl Type` block directly below its `struct` or
    `proto` declaration (`__init__` first, `__del__` second, then methods),
    followed by separate `impl Trait for Type` blocks—one per trait.
  * On structs owning an `Arena` alongside `proto` fields, declare
    `var arena: Arena;` **before** dependent `proto` fields (and declare local
    `var arena = Arena();` bindings before variables that store into them) so
    reverse-declaration LIFO teardown destroys handles before the arena.
* **Scoped RAII & temporary arenas**:
  * Use bare `{ ... }` lexical blocks (never dummy `if true { ... }` blocks) to
    bound the lifetime of `__del__()` resources and transient `Arena`s that
    should clean up before the enclosing function returns.
* **Optionals & string formatting**:
  * Prefer `guard let x ?= opt else { return ...; }` for preconditions to keep
    the happy path flat, `??` for default fallbacks, and `;`-chained
    multi-bindings (`if let p ?= node.parent; let up ?= p.upgrade()`) over
    nested `if let` blocks or redundant `!= none` checks before `if let ?=`.
  * Prefer `f"..."` string interpolation over chained `+` concatenations when
    formatting text, relying on built-in primitive and `enum` coercion inside
    `{...}` rather than redundant `String.from(...)` calls:
    ```sapphire
    struct FileHandle {
      var path: String;
      var is_open = true;
    }

    impl FileHandle {
      func __del__() {
        if self.is_open {
          self.is_open = false;
        }
      }
    }

    func open_file(path: String, read_only: bool = true): FileHandle? {
      if path.empty() {
        return none;
      }
      let mode = read_only ? "r" : "rw";
      print(f"Opening {path} ({mode})");
      return FileHandle { path = path };
    }

    func process_config(config_path: String?): bool {
      guard let path ?= config_path; !path.empty() else {
        return false;
      }

      {
        guard let file ?= open_file(path = path, read_only = true) else {
          return false;
        }
        print(f"Reading {file.path}");
      }  // `file` is deterministically closed here via `__del__()`

      return true;
    }
    ```

## 5. Module layout, interop, & entry points

* **Top-of-file ordering**: Organize `.sp` files in the following sequence:
  1. File-level overview comment (`/* ... */` or `// ...`).
  2. `import` statements, sorted alphabetically. All standard-library imports
     should be listed before all project-specific imports, with an empty line
     between them.
  3. Module `export { ... }` manifest (for library modules), listing one symbol
     per line with a trailing comma.
  4. Module-level constants (`let DEFAULT_PORT = 8080;`).
  5. Type definitions (`enum`, `trait`, and `struct`/`proto` declarations with
     their `impl` blocks).
  6. Any `@extern` host bindings depending on preceding trait declarations.
  7. Module functions and program entry point.
* **Annotations & host interop (`@extern`, `@export`, `@test`, `@on_reload`)**:
  * Place annotations on their own line directly above the declaration they
    decorate, at the same indentation level, with no blank line between them.
  * Write explicit `self` in parameter lists **only** on `@extern` host-handle
    trait methods (`func decode(self): String;`), where it distinguishes
    instance dispatch from stateless module functions (`static func`).
    Everywhere else in Sapphire, `self` is implicit.
  * Use `@export("hostName")` on host trait methods to expose idiomatic
    `snake_case` names in Sapphire while emitting the target host symbol.
* **Program entry points (`func main()` vs. top-level scripts)**:
  * Because Sapphire automatically invokes `func main()` after executing any
    top-level statements, programs defining `func main()` must **not** also call
    `main();` at top level (which executes `main()` twice).
  * Prefer `func main()` for standalone applications and multi-function demos
    so execution state stays function-scoped; reserve top-level executable
    statements for short scripts that omit `main()`:
    ```sapphire
    /*
     * Module demonstrating declaration ordering, host annotations,
     * and automatic `main()` entry-point invocation.
     */

    import std.math;

    export {
      BytesHandle,
      clamp_port,
    }

    let DEFAULT_PORT = 8080;

    trait BytesHandle {
      func decode(self): String;
    }

    trait StrEncoder {
      @export("encode")
      func to_bytes(text: String, encoding: String = "utf-8"): BytesHandle;
    }

    @extern
    var str: StrEncoder;

    func clamp_port(port: int): int {
      return math.max(port, DEFAULT_PORT);
    }

    func main() {
      let bound_port = clamp_port(80);
      print(f"Listening on port {bound_port}");
    }
    ```

## 6. Comments

* Comments on the same line as code should have two spaces before the `//`.
* Sapphire supports both single-line and multi-line block comments:

```sapphire
// This is a single-line comment

/*
 * This is a multi-line
 * block comment.
 */
```
