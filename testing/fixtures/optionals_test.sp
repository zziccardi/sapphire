/*
 * Fixture: optionals_test.sp
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
