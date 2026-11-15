/*
 * E2E Test: functions_and_returns_test.sp
 * Tests multiple return values, call-site destructuring, named arguments, and default parameters.
 */

func calc_stats(base: int, mult: int = 2): int {
  return base * mult;
}

func get_coordinates(): int, int {
  return 15, 25;
}

@test
func test_default_parameter(): int {
  return calc_stats(10);
}

@test
func test_override_default_parameter(): int {
  return calc_stats(10, 3);
}

@test
func test_named_parameters(): int {
  return calc_stats(mult = 4, base = 5);
}

@test
func test_multiple_returns_destructuring(): int {
  let x, y = get_coordinates();
  return x + y;
}

func create_unit(id: int, hp: int = 10, unit_hp: int = 5): int {
  return id * 100 + hp + unit_hp;
}

var call_trace: int = 0;

func trace_step(factor: int, val: int): int {
  call_trace = call_trace * 10 + factor;
  return val;
}

func combine_triple(a: int, b: int = 2, c: int = 3): int, int {
  return a * 100 + b * 10 + c, call_trace;
}

struct BoxedConfig {
  var width: int;
  var height: int;
  var active: bool;
}

impl BoxedConfig {
  func __init__(width: int, height: int = 10, active: bool = true) {
    self.width = width;
    self.height = height;
    self.active = active;
  }

  func total(a: int, b: int = 4, c: int = 5): int {
    return self.width + self.height + a + b + c;
  }
}

@test
func test_skipped_middle_default_named_args(): int {
  return create_unit(id = 1, unit_hp = 19);
}

@test
func test_reordered_named_args_eval_order_and_destructuring(): int {
  call_trace = 0;
  let combined, trace = combine_triple(
    c = trace_step(9, 4),
    a = trace_step(1, 7)
  );
  return combined * 100 + trace;
}

@test
func test_optional_chain_named_args(): int {
  let cfg: BoxedConfig? = BoxedConfig(active = false, width = 20);
  let missing: BoxedConfig? = none;
  let a = cfg?.total(c = 1, a = 2) ?? 0;
  let b = missing?.total(c = 9, a = 9) ?? 100;
  let flag_penalty = (cfg?.active ?? true) ? 1000 : 0;
  return a + b + flag_penalty;
}

@test
func test_constructor_skipped_default_and_false_bool(): int {
  let cfg = BoxedConfig(active = false, width = 25);
  return cfg.width + cfg.height + (cfg.active ? 100 : 0);
}
