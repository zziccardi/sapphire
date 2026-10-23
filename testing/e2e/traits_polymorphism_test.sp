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
