/*
 * E2E Test: raii_and_cleanup_test.sp
 * Tests struct destructor invocation on block exit and early return.
 */

var LOG: [int] = [0, 0];
var DROP_SUM: int = 0;

struct Tracer {
  var id: int;
  var slot: int;
}

impl Tracer {
  func __del__() {
    LOG[self.slot] = self.id;
    DROP_SUM = DROP_SUM * 10 + self.id;
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

func run_conditional_move(take: bool): int {
  DROP_SUM = 0;
  {
    let t = Tracer { id = 7, slot = 0 };
    if take {
      let inner = move t;
      DROP_SUM = DROP_SUM * 10 + 1;
    }
    DROP_SUM = DROP_SUM * 10 + 2;
  }
  return DROP_SUM;
}

func run_match_move(code: int): int {
  DROP_SUM = 0;
  {
    let t = Tracer { id = 3, slot = 0 };
    let chosen = match code {
      1 -> move t,
      ... -> Tracer { id = 9, slot = 1 },
    };
    DROP_SUM = chosen.id;
  }
  return DROP_SUM;
}

@test
func test_conditional_move_drop_flag_taken(): int {
  return run_conditional_move(true);
}

@test
func test_conditional_move_drop_flag_untaken(): int {
  return run_conditional_move(false);
}

@test
func test_match_move_drop_flag(): int {
  return run_match_move(1) * 1000 + run_match_move(2);
}

@test
func test_live_var_reassignment_destroys_old(): int {
  DROP_SUM = 0;
  {
    var t = Tracer { id = 4, slot = 0 };
    t = Tracer { id = 8, slot = 1 };
    DROP_SUM = DROP_SUM * 10 + 5;
  }
  return DROP_SUM;
}

@test
func test_borrowed_unwrap_single_drop(): int {
  DROP_SUM = 0;
  {
    let opt: Tracer? = Tracer { id = 6, slot = 0 };
    if let borrowed ?= opt {
      DROP_SUM = borrowed.id;
    }
    DROP_SUM = DROP_SUM * 10 + 1;
  }
  return DROP_SUM;
}

proto ArenaNode {
  var id: int;
}

impl ArenaNode {
  func __del__() {
    DROP_SUM = DROP_SUM * 10 + self.id;
  }
}

struct ArenaHolder {
  var arena: Arena;
  var node: ArenaNode?;
  var res: Tracer;
}

impl ArenaHolder {
  func __init__() {
    self.arena = Arena();
    self.node = ArenaNode { id = 8 } in self.arena;
    self.res = Tracer { id = 6, slot = 0 };
  }
}

@test
func test_arena_lifo_proto_destructors(): int {
  DROP_SUM = 0;
  {
    var a = Arena();
    let n1 = ArenaNode { id = 2 } in a;
    let n2 = clone n1 {
      self.id = 5;
    };
    let n3 = ArenaNode { id = 7 } in a;
  }
  return DROP_SUM;
}

@test
func test_arena_reassignment_destroys_old(): int {
  DROP_SUM = 0;
  {
    var a = Arena();
    let n1 = ArenaNode { id = 3 } in a;
    a = Arena();
    DROP_SUM = DROP_SUM * 10 + 9;
    let n2 = ArenaNode { id = 4 } in a;
  }
  return DROP_SUM;
}

@test
func test_struct_owned_arena_and_field_teardown(): int {
  DROP_SUM = 0;
  {
    let holder = ArenaHolder();
  }
  return DROP_SUM;
}
