/*
 * E2E Test: heap_smart_refs_test.sp
 * Tests Ref<T>, SharedRef<T>, and WeakRef<T> with move semantics.
 */

struct Node {
  var val: int;
}

impl Node {
  func double_val(self): int {
    return self.val * 2;
  }
}

@test
func test_unique_ref(): int {
  let r = Ref(Node { val = 21 });
  return r.double_val();
}

@test
func test_shared_ref_cycle_breaking(): int {
  let s1 = SharedRef(Node { val = 42 });
  let s2 = s1.share();
  let w = s1.downgrade();
  if let active ?= w.upgrade() {
    return active.val;
  }
  return 0;
}

@test
func test_shared_from_move(): int {
  var r = Ref(Node { val = 99 });
  let s = SharedRef(move r);
  return s.val;
}
