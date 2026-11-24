"""Unit tests for the diagnostic error formatting module (diagnostics.py)."""

import unittest

from sapphire.cli.diagnostics import (
  Diagnostic,
  format_diagnostic,
  get_source_line,
)


class TestDiagnostics(unittest.TestCase):
  """Tests for get_source_line and format_diagnostic utilities."""

  def test_get_source_line_string(self):
    content = "first line\nsecond line\nthird line"
    self.assertEqual(get_source_line(1, source_text=content), "first line")
    self.assertEqual(get_source_line(2, source_text=content), "second line")
    self.assertEqual(get_source_line(3, source_text=content), "third line")
    self.assertIsNone(get_source_line(0, source_text=content))
    self.assertIsNone(get_source_line(4, source_text=content))

  def test_get_source_line_list(self):
    lines = ["let a = 1;", "let b = 2;", "let c = 3;"]
    self.assertEqual(get_source_line(1, source_lines=lines), "let a = 1;")
    self.assertEqual(get_source_line(2, source_lines=lines), "let b = 2;")
    self.assertIsNone(get_source_line(0, source_lines=lines))
    self.assertIsNone(get_source_line(5, source_lines=lines))
    self.assertIsNone(get_source_line(1))

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

  def test_get_source_line_filepath_exception_and_bounds(self):
    import os
    import tempfile
    from unittest.mock import patch

    from sapphire.common.diagnostics import _read_file_lines_cached

    with tempfile.NamedTemporaryFile("w+", delete=False) as f:
      f.write("line 1\nline 2\n")
      temp_path = f.name

    try:
      _read_file_lines_cached.cache_clear()
      self.assertEqual(get_source_line(1, file_path=temp_path), "line 1\n")
      # Test line out of bounds for existing file
      self.assertIsNone(get_source_line(10, file_path=temp_path))
      # Test directory path is rejected
      self.assertIsNone(
          get_source_line(1, file_path=os.path.dirname(temp_path))
      )

      # Test open() raising OSError after clearing cache
      _read_file_lines_cached.cache_clear()
      with patch("builtins.open", side_effect=PermissionError("Denied")):
        self.assertIsNone(get_source_line(1, file_path=temp_path))
    finally:
      if os.path.exists(temp_path):
        os.remove(temp_path)

  def test_format_diagnostic_no_loc(self):
    diag = format_diagnostic(
        error_type="Error",
        file_path=None,
        line=None,
        column=None,
        message="Global failure",
    )
    self.assertEqual(diag, "Error: Global failure")

  def test_format_diagnostic_with_hint(self):
    source = "let x = enemy as Character;"
    diag = format_diagnostic(
        error_type="Semantic Error",
        file_path="main.sp",
        line=1,
        column=8,
        length=18,
        message="Cannot cast struct 'Enemy' to 'Character'.",
        source_content=source,
        hint="Define a behavioral 'trait' instead.",
    )
    self.assertIn("  Hint: Define a behavioral 'trait' instead.", diag)

  def test_diagnostic_to_dict(self):
    d = Diagnostic(
        severity="error",
        code="E_NO_STRUCT_UPCAST",
        message="Cannot cast struct 'Enemy' to 'Character'.",
        hint="Define a trait.",
        file_path="main.sp",
        line=3,
        column=4,
        length=10,
    )
    self.assertEqual(
        d.to_dict(),
        {
            "severity": "error",
            "code": "E_NO_STRUCT_UPCAST",
            "message": "Cannot cast struct 'Enemy' to 'Character'.",
            "hint": "Define a trait.",
            "file": "main.sp",
            "line": 3,
            "column": 4,
            "length": 10,
        },
    )

  def test_format_diagnostic_crlf_past_eol_caret_not_shifted(self):
    diag = format_diagnostic(
        error_type="Syntax Error",
        message="msg",
        file_path="test.sp",
        line=1,
        column=15,
        length=1,
        source_content=["let x = 1\r\n"],
    )
    lines = diag.splitlines()
    # Line 1: "  Line 1:  let x = 1" -> len("  Line 1:  ") == 11, len("let x = 1") == 9 -> col 20
    self.assertEqual(lines[1], "  Line 1:  let x = 1")
    self.assertEqual(lines[2], " " * 20 + "^")

  def test_format_diagnostic_source_content_not_treated_as_filename(self):
    # "LICENSE" exists in repo root; passing it as source_content must treat it as text.
    diag = format_diagnostic(
        error_type="Error",
        message="bad",
        file_path="inline.sp",
        line=1,
        column=0,
        length=7,
        source_content="LICENSE",
    )
    self.assertIn("  Line 1:  LICENSE", diag)


if __name__ == "__main__":
  unittest.main()
