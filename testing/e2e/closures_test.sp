/*
 * E2E Test: closures_test.sp
 * Tests single-parameter lambdas, closures over captured variables, and
 * multi-parameter typed lambdas with block bodies.
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

@test
func test_block_body_lambda(): int {
  let add = (a: int, b: int) -> int {
    let sum = a + b;
    return sum * 2;
  };
  return add(3, 4);
}
