/*
 * E2E Test: negative_runtime_test.sp
 * Validates runtime safety invariants, bounds handling, and nil fallbacks.
 */

struct Node {
  var score: int;
}

func gen(): Coroutine<int> {
  yield 1;
}

@test
func test_array_out_of_bounds_safe_get(): int {
  let arr = [10, 20];
  let v = arr.get(5);
  if v == none {
    return 1;
  }
  return 0;
}

@test
func test_map_missing_key_safe_get(): int {
  let m = {"a": 10};
  let v = m.get("b");
  if v == none {
    return 1;
  }
  return 0;
}

@test
func test_optional_chaining_none(): int {
  var opt_node: Node? = none;
  let res = opt_node?.score;
  if res == none {
    return 1;
  }
  return 0;
}

@test
func test_coroutine_exhaustion(): int {
  let c = gen();
  let first = c.step();
  let second = c.step();
  if first == 1 && second == none && c.is_done() {
    return 1;
  }
  return 0;
}

@test
func test_guard_unwrapping_rejection(): int {
  var opt_val: int? = none;
  guard let unwrapped ?= opt_val else {
    return 42;
  }
  return unwrapped;
}

@test
func test_nil_coalescing_fallback(): int {
  var opt_val: int? = none;
  let val = opt_val ?? 99;
  return val;
}
