/*
 * E2E Test: std_time_test.sp
 * Tests std.time standard library functions.
 */

import std.time as time;

@test
func test_now(): int {
  let t = time.now();
  if t > 0.0 {
    return 1;
  }
  return 0;
}

@test
func test_sleep(): int {
  let t1 = time.now();
  time.sleep(0.01);
  let t2 = time.now();
  if t2 >= t1 {
    return 1;
  }
  return 0;
}
