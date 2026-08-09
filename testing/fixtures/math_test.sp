/*
 * Fixture: math_test.sp
 * Tests std.math standard library functions across int and float types.
 */

import std.math as math;

@test
func test_abs(): int {
  let val_int = math.abs(-42);
  let val_float = math.abs(-3.14);
  if val_int == 42 && val_float > 3.13 {
    return 1;
  }
  return 0;
}

@test
func test_sqrt(): float {
  let val = math.sqrt(16.0);
  return val ?? 0.0;
}

@test
func test_min_max(): int {
  let min_val = math.min(10, 20);
  let max_val = math.max(10, 20);
  if min_val == 10 && max_val == 20 {
    return 1;
  }
  return 0;
}

@test
func test_safe_div(): int {
  let valid = math.safe_div(10, 2);
  let invalid = math.safe_div(10, 0);
  if valid == 5 && invalid == none {
    return 1;
  }
  return 0;
}

@test
func test_log(): float {
  let ln_val = math.log(2.718281828459045);
  let log10_val = math.log(100.0, 10.0);
  let invalid = math.log(-5.0);
  if invalid == none && ln_val != none && log10_val != none {
    return log10_val ?? 0.0;
  }
  return 0.0;
}

@test
func test_pow_ceil_floor(): int {
  let p = math.pow(2.0, 3.0);
  let c = math.ceil(3.14);
  let f = math.floor(3.89);
  if p == 8.0 && c == 4 && f == 3 {
    return 1;
  }
  return 0;
}
