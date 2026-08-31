# Testing framework

## 1. Overview
The `std.testing` module provides a lightweight, robust, and extensible testing framework built natively into Sapphire's standard library. It supports both:
1. **Struct-based test suites** implementing the `TestCase` trait (for tests requiring state management, setup, and teardown).
2. **Standalone `@test` annotated functions** (for simple, stateless unit tests).

It features both **fatal (`assert_*`)** assertions (aborts test execution on failure) and **soft (`expect_*`)** assertions (logs failures and continues execution to catch multiple errors in a single run).

## 2. Module import & namespace
The module is part of Sapphire's standard library and is imported via:

```sapphire
import std.testing;

// Or with an alias:
import std.testing as t;
```

## 3. Core trait & struct-based test suites

### 3.1 The `TestCase` trait
The `TestCase` trait defines optional lifecycle hooks for test suites:

```sapphire
trait TestCase {
  func set_up();
  func tear_down();
}
```

*Note: `set_up()` and `tear_down()` have default empty implementations, so test suites only implement them when needed.*

### 3.2 Struct-based test suites
Test suites are implemented using Sapphire's trait implementation syntax
(`impl Trait for Struct`). Method signatures omit explicit `self` parameters;
`self` is implicitly accessible inside method bodies.

```sapphire
import std.testing;

struct UserDatabaseTest {
  var db: DatabaseConnection;
  var test_user_id: int;
}

impl testing.TestCase for UserDatabaseTest {
  // Lifecycle hook: executed before each test method in this struct
  func set_up() {
    self.db = DatabaseConnection.connect_memory();
    self.test_user_id = self.db.insert_user("Alice");
  }

  // Lifecycle hook: executed after each test method in this struct
  func tear_down() {
    self.db.close();
  }

  // Test method (prefixed with test_)
  func test_user_retrieval() {
    let user = self.db.find_user(self.test_user_id);

    // Soft assertion: logs failure if user is None, but lets execution continue
    self.expect_not_none(user, "User should exist in database");

    if let u ?= user {
      self.expect_eq(u.name, "Alice");
      self.expect_true(u.is_active);
    }
  }

  func test_user_deletion() {
    self.db.delete_user(self.test_user_id);

    let deleted = self.db.find_user(self.test_user_id);

    // Fatal assertion: stops test method immediately if condition fails
    self.assert_none(deleted, "Deleted user must return None");
  }
}
```

## 4. Standalone `@test` functions

For tests that do not require fixture state, functions can be annotated with `@test` and use `std.testing` helper functions directly:

```sapphire
import std.testing as t;

@test
func test_math_addition() {
  t.assert_eq(2 + 2, 4);
}

@test
func test_optional_parsing() {
  let val = String.to_int("123");

  t.expect_not_none(val, "Expected valid integer parse");
  t.expect_eq(val ?? 0, 123);
}
```

## 5. Assertion API reference

### 5.1 Fatal assertions (`assert_*`)
Fatal assertions halt execution of the current test method immediately when a failure occurs.

| Method | Signature | Description |
| :--- | :--- | :--- |
| `assert_true` | `assert_true(cond: bool, msg: String = "")` | Asserts `cond` is `true`. |
| `assert_false` | `assert_false(cond: bool, msg: String = "")` | Asserts `cond` is `false`. |
| `assert_eq` | `assert_eq<T>(actual: T, expected: T, msg: String = "")` | Asserts `actual == expected`. |
| `assert_ne` | `assert_ne<T>(actual: T, expected: T, msg: String = "")` | Asserts `actual != expected`. |
| `assert_almost_eq` | `assert_almost_eq(a: float, b: float, eps: float = 1e-5, msg: String = "")` | Asserts float equality within tolerance. |
| `assert_none` | `assert_none<T>(opt: T?, msg: String = "")` | Asserts optional is `None` (`nil`). |
| `assert_not_none` | `assert_not_none<T>(opt: T?, msg: String = "")` | Asserts optional is not `None`. |

### 5.2 Soft assertions (`expect_*`)
Soft assertions log the failure and allow test execution to continue so multiple failures can be reported in a single test run.

| Method | Signature | Description |
| :--- | :--- | :--- |
| `expect_true` | `expect_true(cond: bool, msg: String = "")` | Softly expects `cond` to be `true`. |
| `expect_false` | `expect_false(cond: bool, msg: String = "")` | Softly expects `cond` to be `false`. |
| `expect_eq` | `expect_eq<T>(actual: T, expected: T, msg: String = "")` | Softly expects `actual == expected`. |
| `expect_ne` | `expect_ne<T>(actual: T, expected: T, msg: String = "")` | Softly expects `actual != expected`. |
| `expect_almost_eq` | `expect_almost_eq(a: float, b: float, eps: float = 1e-5, msg: String = "")` | Softly expects float equality within tolerance. |
| `expect_none` | `expect_none<T>(opt: T?, msg: String = "")` | Softly expects optional to be `None` (`nil`). |
| `expect_not_none` | `expect_not_none<T>(opt: T?, msg: String = "")` | Softly expects optional to not be `None`. |

## 6. Prototypal fixture isolation

For test suites initialized via prototypes, Sapphire's copy-on-write (CoW) prototypal delegation provides isolated state per test case without manual cleanup:

```sapphire
import std.testing;

proto ServerFixture {
  var port: int;
  var status: String;
}

let test_arena = Arena();
let base_server_proto = ServerFixture {
    port = 8080,
    status = "IDLE"
} in test_arena;

struct ServerTest {
  var fixture: ServerFixture;
}

impl testing.TestCase for ServerTest {
  func set_up() {
    // Clone baseline prototype (inherits test_arena); CoW guarantees mutations do not pollute
    // prototype state
    self.fixture = clone base_server_proto;
  }

  func test_server_start() {
    self.fixture.status = "RUNNING";

    self.expect_eq(self.fixture.status, "RUNNING");
  }
}
```

## 7. Test runner CLI (`sapphire test`)

### 7.1 CLI invocation
```bash
# Run all tests in the workspace
sapphire test

# Run tests in a specific directory or file
sapphire test testing/e2e/

# Filter tests by substring matching test name
sapphire test --filter user_retrieval

# Select target backend (Python or Lua 5.1)
sapphire test -t lua
```

### 7.2 Source-map stack-demangling output
When assertions fail in transpiled target code (Python or Lua 5.1), the test runner demangles error locations using Sapphire's source-map engine:

```text
[ FAIL ] UserDatabaseTest.test_user_retrieval (user_test.sp:24)
  Expected: "Alice"
  Actual:   "Bob"
  Line 24:  self.expect_eq(u.name, "Alice");
            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

[ PASS ] UserDatabaseTest.test_user_deletion (user_test.sp:30)
[ PASS ] test_math_addition (math_test.sp:6)

Test Result: 2 passed, 1 failed in 0.03s
```
