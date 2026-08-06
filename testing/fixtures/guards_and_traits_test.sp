/*
 * Fixture: guards_and_traits_test.sp
 * Tests guard statements with scope promotion, trait declarations, and impl Trait for Struct.
 */

trait Evaluator {
  func evaluate(): int;
}

struct SimpleEvaluator {
  var value: int;
}

impl Evaluator for SimpleEvaluator {
  func evaluate(): int {
    return self.value * 2;
  }
}

func run_guard_test(opt_val: int?): int {
  guard let v ?= opt_val;
        v > 5
  else {
    return -1;
  }
  return v * 10;
}

@test
func test_guard_taken(): int {
  return run_guard_test(8);
}

@test
func test_guard_else_branch(): int {
  return run_guard_test(3);
}

@test
func test_trait_implementation(): int {
  let ev = SimpleEvaluator { value = 25 };
  return ev.evaluate();
}
