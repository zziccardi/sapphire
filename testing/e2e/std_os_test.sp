/*
 * E2E Test: std_os_test.sp
 * Tests std.os standard library functions.
 */

import std.os as os;

@test
func test_args(): int {
  let cmd_args = os.args();
  if cmd_args.size() >= 1 {
    return 1;
  }
  return 0;
}

@test
func test_env(): int {
  os.set_env("SAPPHIRE_VAR", "hello_sapphire");
  guard let val ?= os.get_env("SAPPHIRE_VAR") else {
    return 0;
  }
  let missing = os.get_env("SAPPHIRE_NONEXISTENT_XYZ_123");
  if val == "hello_sapphire" && missing == none {
    return 1;
  }
  return 0;
}
