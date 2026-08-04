/*
 * Fixture: strings_test.sp
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
