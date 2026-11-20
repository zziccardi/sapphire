/*
 * E2E Test: std_utf8_test.sp
 * Tests std.utf8 size, offset, and sub across ASCII and multi-byte strings.
 */

import std.utf8 as utf8;

@test
func test_utf8_size(): int {
  let ascii_len = utf8.size("hello") ?? -1;
  let accent_len = utf8.size("héllo") ?? -1;
  let cjk_len = utf8.size("日本語") ?? -1;
  let emoji_len = utf8.size("a💡b") ?? -1;
  if ascii_len == 5 && accent_len == 5 && cjk_len == 3 && emoji_len == 3 {
    return 1;
  }
  return 0;
}

@test
func test_utf8_sub(): String {
  let s = "héllo💡world";
  return utf8.sub(s, 2, 6);
}

@test
func test_utf8_sub_to_end(): String {
  let s = "日本語abc";
  return utf8.sub(s, 3);
}

@test
func test_utf8_offset(): int {
  let s = "a💡b";
  let o1 = utf8.offset(s, 1) ?? -1;
  let o2 = utf8.offset(s, 2) ?? -1;
  let o3 = utf8.offset(s, 3) ?? -1;
  if o1 == 1 && o2 == 2 && o3 == 6 {
    return 1;
  }
  return 0;
}
