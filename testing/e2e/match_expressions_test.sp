/*
 * E2E Test: match_expressions_test.sp
 * Tests match used as a statement, match used as an expression, and wildcards.
 * Arms use the `pattern -> expr,` form with a trailing semicolon after the
 * closing brace when used as a statement.
 */

@test
func test_match_statement(): int {
  let x = 2;
  var result = 0;
  result = match x {
    1 -> 10,
    2 -> 20,
    ... -> 99,
  };
  return result;
}

@test
func test_match_expression(): int {
  let x = 3;
  let r = match x {
    1 -> 100,
    2 -> 200,
    ... -> 300,
  };
  return r;
}

@test
func test_match_wildcard(): int {
  let x = 99;
  let r = match x {
    0 -> 0,
    ... -> 1,
  };
  return r;
}

@test
func test_match_first_arm(): int {
  let x = 1;
  let r = match x {
    1 -> 111,
    ... -> 0,
  };
  return r;
}

@test
func test_match_multi_pattern_arm(): int {
  let x = 3;
  return match x {
    1, 2 -> 10,
    3, 4 -> 20,
    ... -> 0,
  };
}

func dir_delta(dir: int): int, int {
  return match dir {
    0 -> {
      yield 0, -1;
    },
    1 -> {
      yield 1, 0;
    },
    ... -> {
      yield 0, 0;
    },
  };
}

@test
func test_match_block_arm_multi_yield(): int {
  let dx, dy = dir_delta(0);
  let ex, ey = dir_delta(1);
  return (dx + ex) * 10 + (dy + ey);
}

struct MatchMover {
  var x: int = 0;
}

impl MatchMover {
  var func step(mode: int, boost: bool): int {
    return match mode {
      1 -> {
        if boost {
          self.x += 10;
          yield 2;
        } else {
          self.x += 5;
          yield 1;
        }
      },
      ... -> {
        yield 0;
      },
    };
  }
}

@test
func test_match_block_arm_with_if_mutation(): int {
  var m = MatchMover {};
  let r1 = m.step(1, true);
  let r2 = m.step(1, false);
  return m.x * 10 + r1 + r2;
}

@test
func test_nested_match(): int {
  let a = 2;
  let b = 1;
  return match a {
    1 -> 10,
    2 -> match b {
      1 -> 21,
      ... -> 29,
    },
    ... -> 0,
  };
}
