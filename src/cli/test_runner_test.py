"""Comprehensive unit tests for Sapphire test runner engine (src/cli/test_runner.py)."""

import os
import shutil
import tempfile
import unittest

from src.cli.test_runner import (
    find_sp_files,
    parse_ast,
    discover_tests,
    get_source_line,
    run_tests_python,
    run_tests_lua,
    run_tests,
)
from src.code_gen.transpiler import transpile_file
from src.code_gen.python_transpiler import PythonTranspiler
from src.code_gen.lua_transpiler import LuaTranspiler
from src.parser.ast import FuncDeclNode, StructDeclNode, AnnotationNode, BlockNode
from src.semantics.symbol_table import PrimitiveType
from src.semantics.type_checker import SemanticError


class TestRunnerEngineTest(unittest.TestCase):

  def setUp(self):
    self.temp_dir = tempfile.mkdtemp()
    self.sample_sp = os.path.join(self.temp_dir, "test_sample.sp")
    with open(self.sample_sp, "w", encoding="utf-8") as f:
      f.write("""
import std.testing as t;

struct Parent {}

struct SuiteTest : Parent {
  var count: int;
}

impl t.TestCase for SuiteTest {
  func set_up() {
    self.count = 5;
  }

  func tear_down() {
    self.count = 0;
  }

  func test_suite_pass() {
    self.expect_eq(self.count, 5);
  }

  func test_suite_fail() {
    self.expect_eq(self.count, 999, "Expected 999");
    self.assert_eq(self.count, 999, "Fatal 999");
  }
}

@test
func test_standalone_pass() {
  t.assert_true(true);
}

@test
func test_standalone_fail() {
  t.expect_false(true, "Expected false");
  t.assert_false(true, "Fatal false");
}

func normal_function() {
  let x = 1;
}
""")

    self.fail_setup_sp = os.path.join(self.temp_dir, "test_fail_setup.sp")
    with open(self.fail_setup_sp, "w", encoding="utf-8") as f:
      f.write("""
import std.testing as t;

struct BadSetupTest {}

impl t.TestCase for BadSetupTest {
  func set_up() {
    t.assert_true(false, "Setup failed");
  }

  func test_dummy() {
    t.assert_true(true);
  }
}
""")

    self.syntax_error_sp = os.path.join(self.temp_dir, "bad_syntax.sp")
    with open(self.syntax_error_sp, "w", encoding="utf-8") as f:
      f.write("struct InvalidSyntax {")

    self.no_tests_sp = os.path.join(self.temp_dir, "no_tests.sp")
    with open(self.no_tests_sp, "w", encoding="utf-8") as f:
      f.write("func foo() { let x = 1; }")

  def tearDown(self):
    shutil.rmtree(self.temp_dir, ignore_errors=True)

  def test_find_sp_files(self):
    # File path
    files = find_sp_files(self.sample_sp)
    self.assertEqual(files, [self.sample_sp])

    # Directory path
    dir_files = find_sp_files(self.temp_dir)
    self.assertIn(self.sample_sp, dir_files)

    # Non-existent path
    with self.assertRaises(SystemExit):
      find_sp_files(os.path.join(self.temp_dir, "non_existent"))

  def test_get_source_line(self):
    line1 = get_source_line(self.sample_sp, 2)
    self.assertEqual(line1, "import std.testing as t;")

    # Out of bounds
    line_out = get_source_line(self.sample_sp, 999)
    self.assertIsNone(line_out)

    # Invalid file
    line_inv = get_source_line(os.path.join(self.temp_dir, "invalid.sp"), 1)
    self.assertIsNone(line_inv)

  def test_discover_tests(self):
    ast = parse_ast(self.sample_sp)
    standalone, suites = discover_tests(ast)
    self.assertIn("test_standalone_pass", standalone)
    self.assertIn("test_standalone_fail", standalone)
    self.assertIn("SuiteTest", suites)
    self.assertIn("test_suite_pass", suites["SuiteTest"])
    self.assertIn("test_suite_fail", suites["SuiteTest"])

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

  def test_run_tests_python_full(self):
    ast = parse_ast(self.sample_sp)
    standalone, suites = discover_tests(ast)

    # Test passing filter
    passed, failed, _ = run_tests_python(
        self.sample_sp, standalone, suites, filter_pattern="pass"
    )
    self.assertGreater(passed, 0)
    self.assertEqual(failed, 0)

    # Test failing run
    passed, failed, _ = run_tests_python(self.sample_sp, standalone, suites)
    self.assertGreater(passed, 0)
    self.assertGreater(failed, 0)

  def test_run_tests_python_setup_failure(self):
    ast = parse_ast(self.fail_setup_sp)
    standalone, suites = discover_tests(ast)
    passed, failed, _ = run_tests_python(self.fail_setup_sp, standalone, suites)
    self.assertEqual(passed, 0)
    self.assertGreater(failed, 0)

  def test_run_tests_lua_full(self):
    ast = parse_ast(self.sample_sp)
    standalone, suites = discover_tests(ast)

    # Test passing filter
    p_fail, p_pass, _ = run_tests_lua(
        self.sample_sp, standalone, suites, filter_pattern="pass"
    )
    self.assertEqual(p_fail, 0)

    # Test full run with failures
    p_fail, p_pass, _ = run_tests_lua(self.sample_sp, standalone, suites)
    self.assertGreater(p_fail, 0)

  def test_run_tests_cli_facade(self):
    # Test directory run
    res_dir = run_tests(self.temp_dir, target="python", filter_pattern="pass")
    self.assertEqual(res_dir, 0)

    # Test file with no tests
    res_no_tests = run_tests(self.no_tests_sp, target="python")
    self.assertEqual(res_no_tests, 0)

    # Test syntax error file
    res_syntax = run_tests(self.syntax_error_sp, target="python")
    self.assertEqual(res_syntax, 0)

    # Test Lua target run
    res_lua_pass = run_tests(self.sample_sp, target="lua", filter_pattern="pass")
    self.assertEqual(res_lua_pass, 0)

    res_lua_fail = run_tests(self.sample_sp, target="lua")
    self.assertEqual(res_lua_fail, 1)

  def test_transpiler_edge_cases(self):
    # Test LuaTranspiler @test function filtering & declared_symbols
    lua_tr = LuaTranspiler(test_mode=False)
    fn_node = FuncDeclNode(
        name="my_test_fn",
        parameters=[],
        body=BlockNode([]),
        annotations=[AnnotationNode("test", None)],
    )
    lua_tr.visit_FuncDeclNode(fn_node)
    self.assertNotIn("function my_test_fn", lua_tr.get_output())

    lua_tr_test = LuaTranspiler(test_mode=True)
    lua_tr_test.visit_FuncDeclNode(fn_node)
    self.assertIn("my_test_fn", lua_tr_test.declared_symbols)

    # Test PythonTranspiler struct parent inheritance with test_base
    py_tr = PythonTranspiler(test_mode=True)
    py_tr.struct_traits["ChildStruct"] = {"TestCase"}
    struct_node = StructDeclNode(
        name="ChildStruct", fields=[], parent_names=["BaseStruct"]
    )
    py_tr.visit_StructDeclNode(struct_node)
    self.assertIn("class ChildStruct(BaseStruct, testing.TestCase):", py_tr.get_output())

  def test_unimported_testcase_trait_raises_error(self):
    unimported_sp = os.path.join(self.temp_dir, "unimported_testcase.txt")
    with open(unimported_sp, "w", encoding="utf-8") as f:
      f.write("""
struct UnimportedSuite {}

impl TestCase for UnimportedSuite {
  func test_something() {}
}
""")
    from src.semantics.type_checker import TypeChecker
    with self.assertRaises(SemanticError):
      checker = TypeChecker(source_file_path=unimported_sp)
      ast = parse_ast(unimported_sp)
      checker.check(ast)

  def test_caret_alignment(self):
    """Verifies carets align exactly under the source code snippet.

    The header prefix is '  Line <N>:  ' (2 + 5 + len(N) + 3 = 10 + len(N) chars).
    The caret line prefix is '  ' + ' ' * (len(N) + 8) = 2 + len(N) + 8 = 10 + len(N) chars.
    So the first caret must land in the same column as the first character of the
    stripped source snippet.
    """
    import io
    import sys
    import os as _os
    from contextlib import redirect_stdout

    workspace_root = _os.path.abspath(
        _os.path.join(_os.path.dirname(__file__), "..", "..")
    )
    lib_dir = _os.path.join(workspace_root, "lib")
    if lib_dir not in sys.path:
      sys.path.insert(0, lib_dir)

    def _check_alignment(output: str):
      """Assert that every caret line is properly indented under its source line."""
      lines = output.splitlines()
      for i, line in enumerate(lines):
        # Identify source-line rows: '  Line <N>:  <code>'
        import re
        m = re.match(r"^  Line (\d+):  (.+)$", line)
        if m:
          lineno_str = m.group(1)
          code = m.group(2)
          expected_indent = 2 + len("Line ") + len(lineno_str) + len(":  ")
          if i + 1 < len(lines):
            caret_line = lines[i + 1]
            # Count leading spaces in caret line
            actual_indent = len(caret_line) - len(caret_line.lstrip(" "))
            self.assertEqual(
                actual_indent, expected_indent,
                f"Caret indent {actual_indent} != expected {expected_indent} "
                f"for line-number length {len(lineno_str)}.\n"
                f"  source line: {line!r}\n"
                f"  caret line:  {caret_line!r}"
            )
            # The caret line should consist only of spaces then carets
            stripped_carets = caret_line.lstrip()
            self.assertRegex(
                stripped_carets, r"^\^+$",
                f"Caret line contains unexpected characters: {caret_line!r}"
            )
            # Caret span should match the length of the code
            self.assertEqual(
                len(stripped_carets), len(code),
                f"Caret count {len(stripped_carets)} != code length {len(code)}"
            )

    # --- Python runner ---
    ast = parse_ast(self.sample_sp)
    standalone, suites = discover_tests(ast)
    buf = io.StringIO()
    with redirect_stdout(buf):
      run_tests_python(self.sample_sp, standalone, suites)
    _check_alignment(buf.getvalue())

    # --- Lua runner ---
    buf_lua = io.StringIO()
    with redirect_stdout(buf_lua):
      run_tests_lua(self.sample_sp, standalone, suites)
    _check_alignment(buf_lua.getvalue())

  def test_failure_format_none_and_not_none_kinds(self):
    """Covers none/not_none failure kinds and generic kind via format_failure branches."""
    import io
    import sys
    import os as _os
    from unittest.mock import patch
    from contextlib import redirect_stdout

    workspace_root = _os.path.abspath(
        _os.path.join(_os.path.dirname(__file__), "..", "..")
    )
    lib_dir = _os.path.join(workspace_root, "lib")
    if lib_dir not in sys.path:
      sys.path.insert(0, lib_dir)

    import std.testing as testing
    from src.code_gen.transpiler import transpile_file

    none_sp = _os.path.join(self.temp_dir, "test_none_kinds.sp")
    with open(none_sp, "w", encoding="utf-8") as f:
      f.write("""
import std.testing as t;
struct NoneKindTest {}
impl t.TestCase for NoneKindTest {
  func test_none_fail() {
    let x: int? = 42;
    self.expect_not_none(x);
  }
}
""")
    ast = parse_ast(none_sp)
    standalone, suites = discover_tests(ast)
    out_py = transpile_file(none_sp, target="python", test_mode=True)

    # Use a helper to test the formatting logic directly
    patched_py2 = _os.path.join(self.temp_dir, "none_direct.py")
    with open(patched_py2, "w") as f:
      f.write("""import std.testing as testing
class NoneKindTest(testing.TestCase):
  def __init__(self, *args, **kwargs):
    for k, v in kwargs.items():
      setattr(self, k, v)
  def test_none_fail(self):
    testing.expect_none(42)
    testing.expect_not_none(None)
_SP_LINE_MAP = {}
""")

    buf4 = io.StringIO()
    with redirect_stdout(buf4):
      with patch("src.cli.test_runner.transpile_file", return_value=patched_py2):
        passed4, failed4, _ = run_tests_python(
            none_sp, [], {"NoneKindTest": ["test_none_fail"]}
        )
    out4 = buf4.getvalue()

    self.assertIn("Expected:", out4)
    self.assertIn("Actual:", out4)
    self.assertGreater(failed4, 0)

  def test_failure_header_without_source_line(self):
    """Covers first_sp_line returning 0 (fallback walk fails) -> header without :LINE."""
    import io
    import sys
    import os as _os
    from unittest.mock import patch
    from contextlib import redirect_stdout

    workspace_root = _os.path.abspath(
        _os.path.join(_os.path.dirname(__file__), "..", "..")
    )
    lib_dir = _os.path.join(workspace_root, "lib")
    if lib_dir not in sys.path:
      sys.path.insert(0, lib_dir)

    from src.code_gen.transpiler import transpile_file

    bare_sp = _os.path.join(self.temp_dir, "test_bare.sp")
    with open(bare_sp, "w", encoding="utf-8") as f:
      f.write("""
import std.testing as t;

@test
func test_bare_fail() {
  t.expect_eq(1, 2);
}
""")
    ast = parse_ast(bare_sp)
    standalone, suites = discover_tests(ast)

    out_py = transpile_file(bare_sp, target="python", test_mode=True)
    with open(out_py, "r") as f:
      content = f.read()
    content_no_map = "\n".join(
        line for line in content.splitlines()
        if "_SP_LINE_MAP" not in line
    )
    patched_py = _os.path.join(self.temp_dir, "bare_no_map.py")
    with open(patched_py, "w") as f:
      f.write(content_no_map)

    buf = io.StringIO()
    with redirect_stdout(buf):
      with patch("src.cli.test_runner.transpile_file", return_value=patched_py):
        passed, failed, _ = run_tests_python(bare_sp, standalone, suites)
    out = buf.getvalue()

    self.assertIn("[ FAIL ] test_bare_fail (test_bare.sp)", out)
    self.assertNotIn("test_bare.sp:", out)
    self.assertGreater(failed, 0)


if __name__ == "__main__":
  unittest.main()
