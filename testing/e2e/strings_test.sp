/*
 * E2E Test: strings_test.sp
 * Tests string interpolation and common string instance methods.
 */

@test
func test_interpolation(): String {
  let name = "World";
  return f"Hello, {name}!";
}

@test
func test_size(): int {
  let s = "hello";
  return s.size();
}

@test
func test_empty_false(): int {
  let s = "hi";
  if s.empty() {
    return 1;
  }
  return 0;
}

@test
func test_empty_true(): int {
  let s = "";
  if s.empty() {
    return 1;
  }
  return 0;
}

@test
func test_contains(): int {
  let s = "hello world";
  if s.contains("world") {
    return 1;
  }
  return 0;
}

@test
func test_upper(): String {
  return "hello".upper();
}

@test
func test_lower(): String {
  return "HELLO".lower();
}

@test
func test_nested_quotes(): String {
  let scores = {"alice": 100};
  return f"Alice: {scores.contains("alice")}";
}

@test
func test_to_int_valid(): int {
  let pos = "42".to_int() ?? -1;
  let neg = "-7".to_int() ?? 0;
  return pos + neg;
}

@test
func test_to_int_invalid(): int {
  let bad = "abc".to_int() ?? -1;
  let empty = "".to_int() ?? -1;
  return bad + empty;
}
