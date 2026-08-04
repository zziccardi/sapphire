/*
 * Fixture: control_flow_test.sp
 * Tests if/else, while, for, break, continue, and range iteration.
 */

@test
func test_if_else(): int {
  let x = 10;
  if x > 5 {
    return 1;
  } else {
    return 0;
  }
}

@test
func test_while_loop(): int {
  var sum = 0;
  var i = 0;
  while i < 5 {
    sum += i;
    i += 1;
  }
  return sum;
}

@test
func test_for_loop(): int {
  var sum = 0;
  let items: [int] = [10, 20, 30];
  for item in items {
    sum += item;
  }
  return sum;
}

@test
func test_break(): int {
  var i = 0;
  while i < 100 {
    i += 1;
    if i == 5 {
      break;
    }
  }
  return i;
}

@test
func test_continue(): int {
  var sum = 0;
  var i = 0;
  while i < 6 {
    i += 1;
    if i % 2 != 0 {
      continue;
    }
    sum += i;
  }
  return sum;
}

@test
func test_range(): int {
  var sum = 0;
  for i in range(0, 5, 1) {
    sum += i;
  }
  return sum;
}
