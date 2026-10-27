# Style guide

This document establishes the official style, formatting, and naming conventions
for the Sapphire programming language. All standard library modules, samples,
and Sapphire source files should adhere to these guidelines.

## 1. Formatting & layout

* **Line length**: Lines should be kept to a maximum of 80 characters.
* **Indentation**:
  * The bodies of blocks should generally be indented two spaces.
  * When continuing a statement on a subsequent line, indent with four spaces.
  * When continuing a function definition's parameter list or function call site
    on a subsequent line, params should be indented to align with the opening
    parenthesis.
* **Statement termination**: All statements must be explicitly terminated with a
  semicolon (`;`), with the exception of blocks ending in `}` where permitted
  (such as standalone `if`, `while`, `for`, and `match` statements). This
  prevents syntax parsing ambiguities with multi-line statements and
  expressions.
* **Constructor chaining (base initializers)**: When a struct constructor
  invokes parent constructors (`: Parent1(...), Parent2(...)`):
  * **Single-line layout**: If the constructor signature, base initializer
    list, and opening brace `{` fit within the 80-character line length limit,
    they may remain on a single line:
    ```sapphire
    impl Player {
      func __init__(name: String, x: float, y: float): Position(x, y) {
        self.name = name;
      }
    }
    ```
  * **Multi-line layout (Layout Variation A)**: If the declaration exceeds 80
    characters or spans multiple parent initializers, the colon must remain on
    the constructor signature line, each parent initializer must be placed on
    its own line indented **4 spaces** (2 extra spaces beyond standard body
    indentation), and the opening brace `{` is placed on the final parent
    initializer line. Child property assignments in the constructor body use
    standard **2-space** indentation:
    ```sapphire
    impl Player {
      func __init__(name: String, x: float, y: float, hp: int):
          Transform2D(x = x, y = y),
          Health(max_hp = hp) {
        self.name = name;
      }
    }
    ```
* **Parameter ordering**: Constant params should generally precede mutable
  params in function definitions. The exception is params with default values,
  which should come last.

## 2. Naming conventions

* **Variables**: All variable names should use `snake_case`.
* **Functions and methods**: Built-in functions use `snake_case`. User-defined
  functions and methods can use either `snake_case` or `PascalCase`, but should
  be consistent within a codebase.
* **Types**:
  * **Primitive types**: Lowercase naming (e.g., `int`, `float`, `bool`, `none`,
    `void`).
  * **Non-primitive types**: `PascalCase` naming (e.g., `String`, `Player`,
    `Vector2`, `Arena`) for built-in and user-defined `struct`, `proto`, and
    `trait` types.
* **Constants**: Global or compile-time constant expressions should use
  `SCREAMING_SNAKE_CASE` (e.g., `MAX_SPEED`).
* **Enum values**: Enum variants may use either `PascalCase` or
  `SCREAMING_SNAKE_CASE`, but should be kept consistent.
* **Identifier namespace**: Variables, functions, and structs share the same
  identifier namespace per scope (e.g., a function and a struct cannot share
  a name in the same scope).

## 3. Comments

* Comments on the same line as code should have two spaces before the `//`.
* Sapphire supports both single-line and multi-line block comments:

```sapphire
// This is a single-line comment

/*
 * This is a multi-line
 * block comment.
 */
```
