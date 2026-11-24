/*
 * E2E Test: closures_test.sp
 * Tests single-parameter lambdas, closures over captured variables, and
 * multi-parameter typed lambdas with block bodies.
 */

@test
func test_single_param_lambda(): int {
  let double = x -> x * 2;
  return double(5);
}

@test
func test_lambda_arithmetic(): int {
  let square = x -> x * x;
  let cube = x -> x * x * x;
  return square(3) + cube(2);
}

@test
func test_lambda_captures_call(): int {
  let offset = 10;
  let shift = x -> x + offset;
  return shift(5);
}

@test
func test_block_body_lambda(): int {
  let add = (a: int, b: int) -> int {
    let sum = a + b;
    return sum * 2;
  };
  return add(3, 4);
}

func apply_with_default(
    x: int,
    y: int,
    cb: ((int, int) -> int)? = none
): int {
  if let fn ?= cb {
    return fn(x, y);
  }
  return x + y;
}

@test
func test_optional_callback_default_param(): int {
  let a = apply_with_default(3, 4);
  let b = apply_with_default(3, 4, (x: int, y: int) -> int {
    return x * y;
  });
  return a * 100 + b;
}

@test
func test_closures_stored_in_map(): int {
  let handlers: [String: [(int) -> int]] = {
    "inc": [x -> x + 1, x -> x + 2],
    "dbl": [x -> x * 2],
  };
  var total = 0;
  if let list ?= handlers.get("inc") {
    for fn in list {
      total += fn(10);
    }
  }
  if let list2 ?= handlers.get("dbl") {
    for fn in list2 {
      total += fn(5);
    }
  }
  return total;
}

struct Accumulator {
  var base: int = 10;
}

impl Accumulator {
  func run_with(cb: (int) -> int): int {
    return cb(5);
  }

  func compute(scale: int): int {
    let offset = 3;
    return self.run_with((v: int) -> int {
      return (self.base + v) * scale + offset;
    });
  }
}

@test
func test_lambda_capturing_self_and_local(): int {
  let acc = Accumulator {};
  return acc.compute(2);
}

struct CanvasRenderer {
  var scale: int = 2;
}

impl CanvasRenderer {
  func render(overlay: (int, int) -> int): int {
    return overlay(3, 4) * self.scale;
  }
}

struct SceneView {
  var offset: int = 10;
}

impl SceneView {
  func draw_scene(renderer: CanvasRenderer,
                  extra: ((int, int) -> int)? = none): int {
    let combined = (x: int, y: int) -> int {
      var val = x + y + self.offset;
      if let fn ?= extra {
        val += fn(x, y);
      }
      return val;
    };
    return renderer.render(combined);
  }
}

@test
func test_closure_capturing_self_and_optional_callback_forwarded(): int {
  let r = CanvasRenderer { scale = 2 };
  let view = SceneView { offset = 10 };
  let without_extra = view.draw_scene(r);
  let with_extra = view.draw_scene(r, (a: int, b: int) -> int {
    return a * b;
  });
  // without_extra: (3 + 4 + 10) * 2 = 34
  // with_extra: (3 + 4 + 10 + 12) * 2 = 58
  return without_extra * 100 + with_extra;
}
