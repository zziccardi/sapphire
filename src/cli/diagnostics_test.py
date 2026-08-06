"""Unit tests for the diagnostic error formatting module (diagnostics.py)."""

import unittest
try:
  from cli.diagnostics import get_source_line, format_diagnostic
except ModuleNotFoundError:
  from src.cli.diagnostics import get_source_line, format_diagnostic


class TestDiagnostics(unittest.TestCase):
  """Tests for get_source_line and format_diagnostic utilities."""

  def test_get_source_line_string(self):
    content = "first line\nsecond line\nthird line"
    self.assertEqual(get_source_line(content, 1), "first line")
    self.assertEqual(get_source_line(content, 2), "second line")
    self.assertEqual(get_source_line(content, 3), "third line")
    self.assertIsNone(get_source_line(content, 0))
    self.assertIsNone(get_source_line(content, 4))

  def test_get_source_line_list(self):
    lines = ["let a = 1;", "let b = 2;", "let c = 3;"]
    self.assertEqual(get_source_line(lines, 1), "let a = 1;")
    self.assertEqual(get_source_line(lines, 2), "let b = 2;")
    self.assertIsNone(get_source_line(lines, 0))
    self.assertIsNone(get_source_line(lines, 5))

  def test_format_diagnostic_with_column_and_length(self):
    source = "func test() {\n  let x: int = \"hello\";\n}"
    diag = format_diagnostic(
        error_type="Semantic Error",
        file_path="sample.sp",
        line=2,
        column=15,
        length=7,
        message="Cannot assign expression of type 'String' to variable 'x' of type 'int'",
        source_content=source,
    )
    expected_lines = [
        "Semantic Error: sample.sp:2:15 - Cannot assign expression of type 'String' to variable 'x' of type 'int'",
        "  Line 2:    let x: int = \"hello\";",
        "                          ^^^^^^^",
    ]
    self.assertEqual(diag, "\n".join(expected_lines))

  def test_format_diagnostic_without_column(self):
    source = "func test() {\n  let x: int = 10;\n}"
    diag = format_diagnostic(
        error_type="Syntax Error",
        file_path="/path/to/main.sp",
        line=2,
        column=None,
        length=None,
        message="Mismatched input",
        source_content=source,
    )
    expected_lines = [
        "Syntax Error: main.sp:2 - Mismatched input",
        "  Line 2:    let x: int = 10;",
        "             ^^^^^^^^^^^^^^^^",
    ]
    self.assertEqual(diag, "\n".join(expected_lines))

  def test_format_diagnostic_no_source(self):
    diag = format_diagnostic(
        error_type="Error",
        file_path="test.sp",
        line=10,
        column=5,
        message="Generic failure",
    )
    self.assertEqual(diag, "Error: test.sp:10:5 - Generic failure")


if __name__ == "__main__":
  unittest.main()
