/*
 * E2E Test: maps_test.sp
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

enum MapDir {
  North = 1,
  South = 2,
}

@test
func test_enum_map_keys(): int {
  let weights: [MapDir: int] = {
    MapDir.North: 15,
    MapDir.South: 25,
  };
  let n = weights.get(MapDir.North) ?? 0;
  let s = weights.get(MapDir.South) ?? 0;
  return n + s;
}

@test
func test_nested_map_copy_out_write_back(): int {
  var grid: [int: [String: int]] = {
    1: {"hp": 10},
  };
  var row = grid.get(1) ?? {};
  row["hp"] = 50;
  row["mp"] = 20;
  grid[1] = row;
  let hp = grid.get(1)?.get("hp") ?? 0;
  let mp = grid.get(1)?.get("mp") ?? 0;
  return hp + mp;
}
