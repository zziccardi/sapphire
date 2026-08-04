/*
 * Sample test suite illustrating Sapphire's std.testing framework.
 */

import std.testing as t;

struct MathSuiteTest {
  var initial_val: int;
}

impl TestCase for MathSuiteTest {
  func set_up() {
    self.initial_val = 10;
  }

  func tear_down() {
    self.initial_val = 0;
  }

  func test_addition() {
    let result = self.initial_val + 5;
    self.expect_eq(result, 15, "Initial value + 5 should equal 15");
    self.expect_true(result > 10);
  }

  func test_subtraction() {
    let result = self.initial_val - 3;
    self.assert_eq(result, 7);
    self.assert_false(result == 10);
  }
}

@test
func test_standalone_assertions() {
  let val: int? = 42;
  t.expect_not_none(val, "Val should not be none");
  t.assert_eq(val ?? 0, 42);
}
