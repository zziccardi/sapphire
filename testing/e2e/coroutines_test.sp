/*
 * E2E Test: coroutines_test.sp
 * Tests coroutine creation, stepping, yield values, termination, and reset.
 */

func count_sequence(limit: int): Coroutine<int> {
  var curr = 1;
  while curr <= limit {
    yield curr * 10;
    curr += 1;
  }
}

@test
func test_coroutine_stepping(): int {
  var co = count_sequence(3);
  let v1 = co.step() ?? 0;
  let v2 = co.step() ?? 0;
  let v3 = co.step() ?? 0;
  return v1 + v2 + v3;
}

@test
func test_coroutine_is_done(): int {
  var co = count_sequence(1);
  let v = co.step() ?? 0;
  let d1 = co.is_done() ? 1 : 0;
  let v2 = co.step() ?? -1;
  let d2 = co.is_done() ? 1 : 0;
  return v + d1 * 10 + d2 * 100 + (v2 == -1 ? 1 : 0);
}

@test
func test_coroutine_reset(): int {
  var co = count_sequence(2);
  let first = co.step() ?? 0;
  co.reset();
  let restarted = co.step() ?? 0;
  return first * 10 + restarted;
}
