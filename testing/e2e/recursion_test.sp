/*
 * E2E Test: recursion_test.sp
 * Tests direct, branching, mutual, accumulator, and method recursion.
 */

func factorial(n: int): int {
  if n <= 1 {
    return 1;
  }
  return n * factorial(n - 1);
}

func fibonacci(n: int): int {
  if n <= 0 {
    return 0;
  }
  if n == 1 {
    return 1;
  }
  return fibonacci(n - 1) + fibonacci(n - 2);
}

func sum_to(n: int, acc: int = 0): int {
  if n <= 0 {
    return acc;
  }
  return sum_to(n - 1, acc + n);
}

func is_even(n: int): int {
  if n == 0 {
    return 1;
  }
  return is_odd(n - 1);
}

func is_odd(n: int): int {
  if n == 0 {
    return 0;
  }
  return is_even(n - 1);
}

struct Countdown {
  var count: int;
}

impl Countdown {
  var func run(steps: int): int {
    if steps <= 0 {
      return self.count;
    }
    self.count += 1;
    return self.run(steps - 1);
  }
}

@test
func test_direct_recursion(): int {
  return factorial(5);
}

@test
func test_branching_recursion(): int {
  return fibonacci(7);
}

@test
func test_accumulator_recursion(): int {
  return sum_to(10, 0);
}

@test
func test_mutual_recursion(): int {
  if is_even(6) == 1 && is_odd(7) == 1 && is_even(5) == 0 {
    return 1;
  }
  return 0;
}

@test
func test_struct_method_recursion(): int {
  var c = Countdown { count = 10 };
  return c.run(5);
}
