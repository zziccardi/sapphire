/*
 * Fixture: closures_test.sp
 * Tests single-parameter lambda expressions and closures over captured variables.
 * (Multi-parameter typed lambdas require a block body which currently produces
 * invalid Python output — tracked separately.)
 */

@test
func test_single_param_lambda(): int {
  let double = x -> x * 2;
  return double(5);
}

@test
func test_lambda_arithmetic(): int {
  let square = x -> x * x;
  let cube = x -> x * x * x;
  return square(3) + cube(2);
}

@test
func test_lambda_captures_call(): int {
  let offset = 10;
  let shift = x -> x + offset;
  return shift(5);
}
