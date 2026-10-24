/*
 * E2E Test: raii_and_cleanup_test.sp
 * Tests struct destructor invocation on block exit and early return.
 */

var LOG: [int] = [0, 0];

struct Tracer {
  var id: int;
  var slot: int;
}

impl Tracer {
  func __del__() {
    LOG[self.slot] = self.id;
  }
}

func run_scoped_block(): int {
  {
    let t1 = Tracer { id = 1, slot = 1 };
    let t2 = Tracer { id = 2, slot = 0 };
  }
  return LOG[0] * 10 + LOG[1];
}

func run_early_return(trigger: bool): int {
  let t = Tracer { id = 5, slot = 0 };
  if trigger {
    return 100;
  }
  return 0;
}

@test
func test_destructor_lifo_order(): int {
  return run_scoped_block();
}

@test
func test_destructor_early_return(): int {
  LOG[0] = 0;
  let res = run_early_return(true);
  return res + LOG[0];
}
