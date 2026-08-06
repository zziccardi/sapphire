/*
 * Fixture: expressions_and_casting_test.sp
 * Tests type casting with `as`, ternary expressions (`? :`), and optional chaining (`?.`).
 */

enum Status {
  Inactive = 0,
  Active = 1,
}

struct Profile {
  var id: int = 42;
}

struct UserAccount {
  var profile: Profile?;
}

@test
func test_float_to_int_cast(): int {
  let pi: float = 9.85;
  return pi as int;
}

@test
func test_enum_to_int_cast(): int {
  let s = Status.Active;
  return s as int;
}

@test
func test_ternary_expression(): int {
  let val = 10;
  return val > 5 ? 100 : 0;
}

@test
func test_optional_chaining(): int {
  let user = UserAccount { profile = Profile {} };
  let pid = user.profile?.id;
  return pid ?? -1;
}

@test
func test_optional_chaining_none(): int {
  let user = UserAccount { profile = none };
  let pid = user.profile?.id;
  return pid ?? -1;
}
