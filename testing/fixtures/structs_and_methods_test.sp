/*
 * Fixture: structs_and_methods_test.sp
 * Tests struct declaration, default field values, impl blocks, and method calls.
 */

struct Counter {
  var count: int = 0;
}

impl Counter {
  func increment() {
    self.count += 1;
  }

  func get(): int {
    return self.count;
  }

  static func create_at(n: int): Counter {
    let c = Counter {};
    c.count = n;
    return c;
  }
}

@test
func test_default_fields(): int {
  let c = Counter {};
  return c.count;
}

@test
func test_method_call(): int {
  let c = Counter {};
  c.increment();
  c.increment();
  return c.get();
}

@test
func test_static_method(): int {
  let c = Counter.create_at(7);
  return c.get();
}
