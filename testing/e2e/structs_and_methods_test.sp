/*
 * E2E Test: structs_and_methods_test.sp
 * Tests struct declaration, default field values, impl blocks, and method calls.
 */

struct Counter {
  var count: int = 0;
}

impl Counter {
  var func increment() {
    self.count += 1;
  }

  func get(): int {
    return self.count;
  }

  static func create_at(n: int): Counter {
    var c = Counter {};
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
  var c = Counter {};
  c.increment();
  c.increment();
  return c.get();
}

@test
func test_static_method(): int {
  let c = Counter.create_at(7);
  return c.get();
}

struct InnerStats {
  var hp: int = 20;
}

struct MidStats {
  var inner: InnerStats = InnerStats {};
  var tags: [int] = [1, 2];
}

struct OuterUnit {
  var mid: MidStats = MidStats {};
}

let TEMPLATE_UNIT = OuterUnit {};

@test
func test_nested_value_struct_deep_copy_isolation(): int {
  var copy_a = TEMPLATE_UNIT;
  copy_a.mid.inner.hp = 3;
  copy_a.mid.tags.push(99);

  let copy_b = TEMPLATE_UNIT;
  // copy_a.mid.inner.hp (3) + copy_b.mid.inner.hp (20) +
  // TEMPLATE_UNIT.mid.inner.hp (20) + copy_b.mid.tags.size() (2) = 45
  return copy_a.mid.inner.hp + copy_b.mid.inner.hp +
         TEMPLATE_UNIT.mid.inner.hp + copy_b.mid.tags.size();
}
