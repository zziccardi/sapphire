/*
 * Fixture: enums_test.sp
 * Tests integer-backed and string-backed enum declarations and member access.
 */

enum Direction {
  North = 0,
  East = 1,
  South = 2,
  West = 3,
}

enum Color {
  Red = "red",
  Green = "green",
  Blue = "blue",
}

@test
func test_int_enum_value(): int {
  return Direction.South;
}

@test
func test_int_enum_comparison(): int {
  let d = Direction.East;
  if d == Direction.East {
    return 1;
  }
  return 0;
}

@test
func test_string_enum_value(): String {
  return Color.Green;
}
