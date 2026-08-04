"""Unit tests for Sapphire test runner engine (src/cli/test_runner.py)."""

import os
import shutil
import tempfile
import unittest

from src.cli.test_runner import find_sp_files, parse_ast, discover_tests, run_tests
from src.code_gen.transpiler import transpile_file


class TestRunnerEngineTest(unittest.TestCase):

  def setUp(self):
    self.temp_dir = tempfile.mkdtemp()
    self.sample_sp = os.path.join(self.temp_dir, "test_sample.sp")
    with open(self.sample_sp, "w", encoding="utf-8") as f:
      f.write("""
import std.testing as t;

struct SuiteTest {
  var count: int;
}

impl TestCase for SuiteTest {
  func set_up() {
    self.count = 5;
  }

  func test_suite_pass() {
    self.expect_eq(self.count, 5);
  }
}

@test
func test_standalone_pass() {
  t.assert_true(true);
}

func normal_function() {
  let x = 1;
}
""")

  def tearDown(self):
    shutil.rmtree(self.temp_dir, ignore_errors=True)

  def test_find_sp_files(self):
    files = find_sp_files(self.sample_sp)
    self.assertEqual(files, [self.sample_sp])

  def test_discover_tests(self):
    ast = parse_ast(self.sample_sp)
    standalone, suites = discover_tests(ast)
    self.assertIn("test_standalone_pass", standalone)
    self.assertIn("SuiteTest", suites)
    self.assertIn("test_suite_pass", suites["SuiteTest"])

  def test_at_test_conditional_compilation(self):
    # Normal transpile: @test function should be omitted
    out_normal = os.path.join(self.temp_dir, "normal.py")
    transpile_file(self.sample_sp, out_normal, target="python", test_mode=False)
    with open(out_normal, "r", encoding="utf-8") as f:
      content = f.read()
    self.assertNotIn("def test_standalone_pass", content)
    self.assertIn("def normal_function", content)

    # Test transpile: @test function should be emitted
    out_test = os.path.join(self.temp_dir, "test_mode.py")
    transpile_file(self.sample_sp, out_test, target="python", test_mode=True)
    with open(out_test, "r", encoding="utf-8") as f:
      content = f.read()
    self.assertIn("def test_standalone_pass", content)

  def test_run_tests_success(self):
    code = run_tests(self.sample_sp, target="python")
    self.assertEqual(code, 0)


if __name__ == "__main__":
  unittest.main()
