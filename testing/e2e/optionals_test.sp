/*
 * E2E Test: optionals_test.sp
 * Tests optional types, ?= unwrapping, and ?? null-coalescing.
 */

@test
func test_coalesce_none(): int {
  let x: int? = none;
  return x ?? 42;
}

@test
func test_coalesce_value(): int {
  let x: int? = 7;
  return x ?? 42;
}

@test
func test_optional_unwrap_taken(): int {
  let x: int? = 10;
  if let v ?= x {
    return v;
  }
  return -1;
}

@test
func test_optional_unwrap_missed(): int {
  let x: int? = none;
  if let v ?= x {
    return v;
  }
  return -1;
}

@test
func test_multi_optional_unwrap(): int {
  let a: int? = 10;
  let b: int? = 20;
  if let x ?= a; let y ?= b; x + y == 30 {
    return x + y;
  }
  return -1;
}

@test
func test_multi_optional_unwrap_failure(): int {
  let a: int? = 10;
  let b: int? = none;
  if let x ?= a; let y ?= b; x > 0 {
    return 1;
  }
  return 0;
}

struct OptBox {
  var val: int;
}

var global_opt_box: OptBox? = OptBox { val = 10 };

@test
func test_if_var_module_global(): int {
  if var b ?= global_opt_box {
    b.val += 5;
  }
  return global_opt_box?.val ?? -1;
}

func bump_opt_box(var box: OptBox?): int {
  if var b ?= box {
    b.val += 7;
    return b.val;
  }
  return -1;
}

@test
func test_if_var_optional_param(): int {
  let hit = bump_opt_box(OptBox { val = 20 });
  let miss = bump_opt_box(none);
  return hit + miss;
}

func update_nested_row(var grid: [int: [int]]): int {
  guard var row ?= grid.get(1) else {
    return -1;
  }
  row.push(99);
  return row.size();
}

@test
func test_guard_var_nested_map_get(): int {
  var grid: [int: [int]] = {1: [10, 20]};
  return update_nested_row(grid);
}

@test
func test_multi_binding_if_let_with_condition(): int {
  let grid: [int: [int]] = {1: [10, 20], 2: []};
  var total = 0;
  if let row1 ?= grid.get(1); row1.size() > 0 {
    total += row1[0];
  }
  if let row2 ?= grid.get(2); row2.size() > 0 {
    total += 100;
  }
  return total;
}

@test
func test_chained_optional_map_get(): int {
  let grid: [int: [String: int]] = {
    1: {"hp": 42},
  };
  let hit = grid.get(1)?.get("hp") ?? -1;
  let miss_inner = grid.get(1)?.get("mp") ?? -1;
  let miss_outer = grid.get(9)?.get("hp") ?? -1;
  return hit + miss_inner + miss_outer;
}
