/*
 * E2E Test: module_constants_test.sp
 * Verifies compile-time constant expressions and module-level bindings.
 */

let MAX_USERS: int = 100 * 2 + 50;
let PI: float = 3.14159;
let APP_NAME = "Sapphire";
let GREETING = f"Welcome to {APP_NAME}!";
let IS_ENABLED = true;
let STATUS = IS_ENABLED ? "ACTIVE" : "INACTIVE";
let NUMBERS = [10, 20, 30];
let CONFIG = {"port": 8080};

struct Vector2 {
  var x: float;
  var y: float;
}

let ORIGIN = Vector2 { x = 0.0, y = 0.0 };
let STANDING_FRAME: int = 1;
let DOUBLE_FRAME = STANDING_FRAME * 2;

struct AnimatedSprite {
  var frame: int = STANDING_FRAME;
  var double_frame = DOUBLE_FRAME;
  var pos: Vector2 = ORIGIN;
  var label: String = GREETING;
}

impl AnimatedSprite {
  func compute(bonus: int = STANDING_FRAME, scale: int = 2): int {
    return (self.frame + self.double_frame + bonus) * scale;
  }
}

func use_default_const(limit: int = MAX_USERS): int {
  return limit;
}

var module_counter = 100;

@test
func test_integer_constant_expr(): bool {
  return MAX_USERS == 250;
}

@test
func test_float_constant_expr(): bool {
  return PI > 3.14 && PI < 3.15;
}

@test
func test_string_constant_expr(): bool {
  return APP_NAME == "Sapphire" && GREETING == "Welcome to Sapphire!";
}

@test
func test_ternary_constant_expr(): bool {
  return STATUS == "ACTIVE";
}

@test
func test_array_constant_expr(): bool {
  return NUMBERS.size() == 3 && NUMBERS[0] == 10 && NUMBERS[2] == 30;
}

@test
func test_map_constant_expr(): bool {
  let port = CONFIG.get("port");
  return port == 8080;
}

@test
func test_struct_constant_expr(): bool {
  return ORIGIN.x == 0.0 && ORIGIN.y == 0.0;
}

@test
func test_module_var_state(): bool {
  module_counter += 25;
  return module_counter == 125;
}

@test
func test_const_in_struct_and_method_defaults(): bool {
  let sprite = AnimatedSprite {};
  return sprite.frame == 1 &&
         sprite.double_frame == 2 &&
         sprite.pos.x == 0.0 &&
         sprite.label == "Welcome to Sapphire!" &&
         sprite.compute() == 8;
}

@test
func test_const_in_func_default(): bool {
  return use_default_const() == 250;
}
