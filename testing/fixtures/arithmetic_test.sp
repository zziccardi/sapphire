/*
 * Fixture: arithmetic_test.sp
 * Tests basic integer and float arithmetic, operator precedence, and modulo.
 */

@test
func test_integer_arithmetic(): int {
  let a = 10;
  let b = 3;
  return a + b * 2 - 1;
}

@test
func test_integer_division(): int {
  let a = 17;
  let b = 4;
  return a / b;
}

@test
func test_modulo(): int {
  let a = 17;
  let b = 5;
  return a % b;
}

@test
func test_negative_arithmetic(): int {
  let x = -4;
  let y = 3;
  return x * y + 10;
}
