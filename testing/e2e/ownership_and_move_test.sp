/*
 * E2E Test: ownership_and_move_test.sp
 * Tests the `move` keyword, ownership transfer, and re-initialization.
 */

struct Point {
  var x: int;
  var y: int;
}

func consume_point(p: Point): int {
  return p.x + p.y;
}

@test
func test_move_assignment(): int {
  var p = Point { x = 10, y = 20 };
  let p2 = move p;
  return p2.x + p2.y;
}

@test
func test_move_into_function(): int {
  var p = Point { x = 3, y = 7 };
  let sum = consume_point(move p);
  return sum;
}

@test
func test_move_reinitialization(): int {
  var p = Point { x = 5, y = 5 };
  let first = move p;
  p = Point { x = 10, y = 10 };
  let second = move p;
  return first.x + second.x;
}
