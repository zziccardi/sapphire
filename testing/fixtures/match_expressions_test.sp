/*
 * Fixture: match_expressions_test.sp
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
