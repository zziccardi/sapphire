/*
 * Fixture: functions_and_returns_test.sp
 * Tests multiple return values, call-site destructuring, named arguments, and default parameters.
 */

func calc_stats(base: int, mult: int = 2): int {
  return base * mult;
}

func get_coordinates(): int, int {
  return 15, 25;
}

@test
func test_default_parameter(): int {
  return calc_stats(10);
}

@test
func test_override_default_parameter(): int {
  return calc_stats(10, 3);
}

@test
func test_named_parameters(): int {
  return calc_stats(mult = 4, base = 5);
}

@test
func test_multiple_returns_destructuring(): int {
  let x, y = get_coordinates();
  return x + y;
}
