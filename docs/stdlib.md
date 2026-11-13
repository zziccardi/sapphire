# Standard library reference

This document provides a reference for Sapphire's standard-library modules,
their exported functions, types, semantics, and target platform behavior.

## Overview

Sapphire's standard library is distributed under the `lib/` directory and
organized into the `std` namespace, alongside engine bindings such as
`lib.love2d`. Modules provide cross-backend parity across both Python and
Lua 5.1 runtime targets.

Standard library modules are imported using qualified import statements:

```sapphire
import std.fs;
import std.math;
import std.os;
import std.testing;
import std.time;
```

By default, Sapphire binds the terminal component of the import path directly
into scope (e.g. `import std.os;` binds `os`). The `as <alias>` clause is
optional and used primarily for abbreviations or to avoid name collisions:

```sapphire
import lib.love2d.graphics as gfx;
import std.math as m;
```

Module resolution checks the active toolchain distribution path, local
workspace directories, and installed `site-packages` packaging automatically.

## Filesystem module (`std.fs`)

The `std.fs` module provides basic filesystem read, write, existence checking,
and file removal operations.

### Exported functions

* `func read_file(path: String): String?`
  Reads the entire contents of a file at `path` as a UTF-8 string. Returns
  `none` if the file does not exist or if a read error occurs.
* `func write_file(path: String, content: String): bool`
  Writes string content to a file at `path` (overwriting existing contents).
  Returns `true` on success and `false` on failure.
* `func remove_file(path: String): bool`
  Deletes the file at `path`. Returns `true` on success and `false` if the file
  does not exist or cannot be removed.
* `func exists(path: String): bool`
  Checks whether a file or directory exists at `path`. Returns `true` if it
  exists, and `false` otherwise.

### Usage example

```sapphire
import std.fs;

func main() {
  let path = "config.txt";
  let ok = fs.write_file(path, "key=value");
  if !ok {
    print("Failed to write config file.");
    return;
  }

  if fs.exists(path) {
    guard let content ?= fs.read_file(path) else {
      print("Could not read file.");
      return;
    }
    print("Config contents: " + content);
    fs.remove_file(path);
  }
}
```

## Math module (`std.math`)

The `std.math` module provides generic mathematical functions for numeric
types (`int` and `float`), monomorphized automatically across backends.

### Exported functions

* `func abs<T>(x: T): T`
  Returns the absolute value of `x`.
* `func sqrt<T>(x: T): float?`
  Computes the square root of `x`. Returns `none` if `x < 0`.
* `func min<T>(a: T, b: T): T`
  Returns the smaller of two numeric values `a` and `b`.
* `func max<T>(a: T, b: T): T`
  Returns the larger of two numeric values `a` and `b`.
* `func safe_div<T>(a: T, b: T): T?`
  Performs safe division. Returns `none` if the divisor `b == 0`.
* `func log<T>(x: T, base: float? = none): float?`
  Computes the logarithm of `x`. Defaults to the natural logarithm if `base` is
  omitted. Returns `none` if `x <= 0` or if the base is invalid (`<= 0` or `1`).
* `func pow<T>(base: T, exp: T): float`
  Computes `base` raised to the power of `exp`.
* `func ceil<T>(x: T): int`
  Returns the smallest integer greater than or equal to `x`.
* `func floor<T>(x: T): int`
  Returns the largest integer less than or equal to `x`.

### Usage example

```sapphire
import std.math;

func main() {
  let root = math.sqrt(64.0) ?? 0.0;
  let clamped = math.min(100, math.max(10, 50));
  let quotient = math.safe_div(100, 4) ?? 0;
  print("Root: " + root + ", Clamped: " + clamped + ", Div: " + quotient);
}
```

## Operating system module (`std.os`)

The `std.os` module provides low-level operating system and process primitives.

### Exported functions

* `func args(): [String]`
  Returns command-line arguments passed to the current process. The first
  entry (`args()[0]`) contains the program or script name.
* `func get_env(name: String): String?`
  Retrieves the value of an environment variable. Returns `none` if the
  variable is unset.
* `func set_env(name: String, value: String)`
  Sets or updates the specified environment variable for the current process.
* `func exit(code: int = 0)`
  Terminates the current process immediately with the specified exit status.

### Usage example

```sapphire
import std.os;

func main() {
  let cmd_args = os.args();
  if cmd_args.size() > 1 {
    print("Received argument: " + cmd_args[1]);
  }

  os.set_env("APP_ENV", "production");
  guard let env_val ?= os.get_env("APP_ENV") else {
    os.exit(1);
    return;
  }
  print("Environment: " + env_val);
}
```

## Testing module (`std.testing`)

The `std.testing` module provides native test discovery, assertion primitives,
and test suite lifecycle management.

For comprehensive documentation on testing conventions, assertion helpers, and
the test runner, refer to [testing.md](testing.md).

### Key components

* `trait TestCase`: Defines optional `set_up()` and `tear_down()` hooks for
  stateful test suites.
* Fatal assertions (`assert_*`): Abort test execution on failure (`assert_eq`,
  `assert_ne`, `assert_true`, `assert_false`, `assert_none`, `assert_not_none`,
  `assert_almost_eq`).
* Soft assertions (`expect_*`): Record failure diagnostics while allowing the
  test case to continue execution.

### Usage example

```sapphire
import std.testing;

struct CalculatorTest {
  var count: int;
}

impl testing.TestCase for CalculatorTest {
  var func set_up() {
    self.count = 0;
  }

  var func tear_down() {}

  @test
  var func test_increment() {
    self.count = self.count + 1;
    self.assert_eq(self.count, 1, "Counter should be 1 after increment");
  }
}
```

## Time module (`std.time`)

The `std.time` module provides system epoch time querying and execution delay
primitives.

### Exported functions

* `func now(): float`
  Returns current system timestamp in seconds since the Unix Epoch (January 1,
  1970 UTC) as a floating-point number.
* `func sleep(seconds: float)`
  Suspends execution of the current thread or process for the given duration
  in fractional seconds. When running under the Love2D engine target, it
  delegates automatically to `love.timer.sleep`.

### Usage example

```sapphire
import std.time;

func main() {
  let start_time = time.now();
  time.sleep(0.05);
  let elapsed = time.now() - start_time;
  if elapsed >= 0.05 {
    print("Sleep completed successfully.");
  }
}
```

## Love2D game engine bindings (`lib.love2d`)

Sapphire provides first-class bindings for the Love2D framework under
`lib.love2d`. These bindings allow compiling Sapphire source directly to
Lua 5.1 / Love2D game packages.

### Submodules

* `lib.love2d.graphics`: Canvas, Color, Font, Graphics, Image, Quad.
* `lib.love2d.keyboard`: Keyboard input handling and key repeat controls.
* `lib.love2d.mouse`: Cursor and mouse position/button polling.
* `lib.love2d.timer`: Frame delta time, FPS reporting, and timer sleeping.
* `lib.love2d.enums`: Typed string enums for draw modes, filter modes, key
  codes, and alignment.
* `lib.love2d.love2d`: Master engine binding providing the `@extern var love`
  runtime context.

### Usage example

```sapphire
import lib.love2d.enums;
import lib.love2d.graphics;
import lib.love2d.love2d;

let love = love2d.love;

@export("love.draw")
func draw() {
  love.graphics.setColorRgba(1.0, 1.0, 1.0, 1.0);
  love.graphics.rectangle(enums.DrawMode.Fill, 100.0, 100.0, 200.0, 150.0);
  love.graphics.print("Hello from Sapphire on Love2D!", 110.0, 120.0);
}
```
