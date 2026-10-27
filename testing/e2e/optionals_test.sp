/*
 * E2E Test: optionals_test.sp
 * Tests optional types, ?= unwrapping, and ?? null-coalescing.
 */

@test
func test_coalesce_none(): int {
  let x: int? = none;
  return x ?? 42;
}

@test
func test_coalesce_value(): int {
  let x: int? = 7;
  return x ?? 42;
}

@test
func test_optional_unwrap_taken(): int {
  let x: int? = 10;
  if let v ?= x {
    return v;
  }
  return -1;
}

@test
func test_optional_unwrap_missed(): int {
  let x: int? = none;
  if let v ?= x {
    return v;
  }
  return -1;
}

@test
func test_multi_optional_unwrap(): int {
  let a: int? = 10;
  let b: int? = 20;
  if let x ?= a; let y ?= b; x + y == 30 {
    return x + y;
  }
  return -1;
}

@test
func test_multi_optional_unwrap_failure(): int {
  let a: int? = 10;
  let b: int? = none;
  if let x ?= a; let y ?= b; x > 0 {
    return 1;
  }
  return 0;
}
