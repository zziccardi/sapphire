/*
 * E2E Test: std_fs_test.sp
 * Tests std.fs standard library functions.
 */

import std.fs as fs;

@test
func test_file_roundtrip(): int {
  let path = "test_sapphire_fs_roundtrip.txt";
  let write_ok = fs.write_file(path, "sapphire filesystem test content");
  if !write_ok {
    return 0;
  }
  if !fs.exists(path) {
    return 0;
  }
  guard let content ?= fs.read_file(path) else {
    return 0;
  }
  if content != "sapphire filesystem test content" {
    return 0;
  }
  let rem_ok = fs.remove_file(path);
  if !rem_ok || fs.exists(path) {
    return 0;
  }
  return 1;
}

@test
func test_nonexistent_file(): int {
  let missing_path = "nonexistent_file_sapphire_xyz_987.txt";
  let does_exist = fs.exists(missing_path);
  let read_res = fs.read_file(missing_path);
  if !does_exist && read_res == none {
    return 1;
  }
  return 0;
}
