/*
 * E2E Test: traits_polymorphism_test.sp
 * Tests trait implementation, heterogeneous dispatch, and trait arguments.
 */

trait Greeter {
  func greet(): int;
}

struct FriendlyBot {
  var code: int = 100;
}

impl Greeter for FriendlyBot {
  func greet(): int {
    return self.code + 1;
  }
}

struct FormalBot {
  var code: int = 200;
}

impl Greeter for FormalBot {
  func greet(): int {
    return self.code + 2;
  }
}

func execute_greeting(g: Greeter): int {
  return g.greet();
}

@test
func test_polymorphic_trait_call(): int {
  let f = FriendlyBot {};
  let b = FormalBot {};
  return execute_greeting(f) + execute_greeting(b);
}

trait Counter {
  var func bump(delta: int);
  func value(): int;
}

struct StepCounter {
  var count: int = 0;
}

impl Counter for StepCounter {
  var func bump(delta: int) {
    self.count += delta;
  }
  func value(): int {
    return self.count;
  }
}

struct DoubleCounter {
  var count: int = 10;
}

impl Counter for DoubleCounter {
  var func bump(delta: int) {
    self.count += delta * 2;
  }
  func value(): int {
    return self.count;
  }
}

struct Squad {
  var leader: Greeter?;
}

@test
func test_heterogeneous_trait_array(): int {
  let bots: [Greeter] = [FriendlyBot { code = 10 }, FormalBot { code = 20 }];
  var sum = 0;
  for bot in bots {
    sum += bot.greet();
  }
  return sum;
}

@test
func test_trait_array_mutating_method(): int {
  var counters: [Counter] = [StepCounter {}, DoubleCounter {}];
  counters[0].bump(5);
  counters[1].bump(3);
  return counters[0].value() + counters[1].value();
}

@test
func test_trait_in_nested_map(): int {
  var grid: [int: [int: Greeter]] = {};
  var r1: [int: Greeter] = {};
  r1[2] = FriendlyBot { code = 30 };
  var r2: [int: Greeter] = {};
  r2[4] = FormalBot { code = 40 };
  grid[1] = r1;
  grid[3] = r2;
  let g1 = grid.get(1)?.get(2);
  let g2 = grid.get(3)?.get(4);
  let a = g1?.greet() ?? 0;
  let b = g2?.greet() ?? 0;
  return a + b;
}

@test
func test_optional_trait_field(): int {
  let empty = Squad { leader = none };
  let active = Squad { leader = FriendlyBot { code = 50 } };
  let v1 = empty.leader?.greet() ?? -1;
  let v2 = active.leader?.greet() ?? -1;
  return v1 + v2;
}

@test
func test_nested_trait_map_literal(): int {
  let grid: [int: [int: Greeter]] = {
    1: {2: FriendlyBot { code = 30 }},
    3: {4: FormalBot { code = 40 }},
  };
  let a = grid.get(1)?.get(2)?.greet() ?? 0;
  let b = grid.get(3)?.get(4)?.greet() ?? 0;
  return a + b;
}
