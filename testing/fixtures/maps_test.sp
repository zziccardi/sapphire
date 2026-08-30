/*
 * Fixture: maps_test.sp
 * Tests map literal creation, key lookup, and key-value iteration.
 * Note: map type is inferred from the literal (explicit type annotations
 * for map types use a different syntax not exercised here).
 */

@test
func test_map_lookup(): int {
  let m = {"a": 1, "b": 2, "c": 3};
  return m["b"];
}

@test
func test_map_iteration_sum(): int {
  let m = {"x": 10, "y": 20, "z": 30};
  var sum = 0;
  for k, v in m {
    sum = sum + v;
  }
  return sum;
}

@test
func test_map_get(): int {
  let m = {"a": 10, "b": 20};
  let val_found = m.get("a");
  let val_missing = m.get("z");
  if val_found == 10 && val_missing == none {
    return 1;
  }
  return 0;
}
