"""Diagnostic error formatting utility for Sapphire compiler and test runner.

Provides standardized formatting for syntax, semantic, and runtime errors by
including file location, line numbers, source snippets, and caret pointers (^).
"""

import os
from typing import List, Optional, Union


def get_source_line(
    source: Union[str, List[str]], lineno: int
) -> Optional[str]:
  """Reads a 1-indexed line from a file path, multi-line string, or list of lines."""
  if lineno < 1:
    return None

  if isinstance(source, list):
    if 1 <= lineno <= len(source):
      return source[lineno - 1]
    return None

  if isinstance(source, str):
    # If source is a valid existing file path
    if os.path.isfile(source):
      try:
        with open(source, "r", encoding="utf-8") as f:
          lines = f.readlines()
          if 1 <= lineno <= len(lines):
            return lines[lineno - 1]
      except Exception:
        pass
      return None

    # Otherwise treat source as multi-line content
    lines = source.splitlines()
    if 1 <= lineno <= len(lines):
      return lines[lineno - 1]

  return None


def format_diagnostic(
    error_type: str,
    message: str,
    file_path: Optional[str] = None,
    line: Optional[int] = None,
    column: Optional[int] = None,
    length: Optional[int] = None,
    source_content: Optional[Union[str, List[str]]] = None,
) -> str:
  """Formats a diagnostic error message with source line snippet, line numbers, and caret pointers (^).

  Args:
    error_type: Diagnostic prefix (e.g. 'Syntax Error', 'Semantic Error',
      'Error').
    message: Main diagnostic message text.
    file_path: Optional filename or file path.
    line: Optional 1-indexed line number.
    column: Optional 0-indexed column offset within the line.
    length: Optional token/expression character length for caret span.
    source_content: Optional source file path, multi-line string, or list of
      lines.

  Returns:
    Formatted multi-line diagnostic string.
  """
  lines_out = []

  # Header line construction
  loc_parts = []
  if file_path:
    loc_parts.append(os.path.basename(file_path))
  if line and line > 0:
    if column is not None and column >= 0:
      loc_parts.append(f"{line}:{column}")
    else:
      loc_parts.append(str(line))

  if loc_parts:
    loc_str = ":".join(loc_parts)
    header = f"{error_type}: {loc_str} - {message}"
  else:
    header = f"{error_type}: {message}"

  lines_out.append(header)

  # Source line snippet construction
  if line and line > 0:
    source_ref = source_content if source_content is not None else file_path
    if source_ref:
      raw_line = get_source_line(source_ref, line)
      if raw_line is not None:
        # Expand tabs to 4 spaces to maintain column alignment in terminal
        expanded_line = raw_line.rstrip("\r\n").expandtabs(4)
        line_str = str(line)
        lines_out.append(f"  Line {line_str}:  {expanded_line}")

        indent_pad = " " * (len(line_str) + 8)

        if column is not None and column >= 0:
          # Compute expanded column index if original line contained tabs
          prefix_before_col = raw_line[:column].expandtabs(4)
          col_offset = len(prefix_before_col)

          caret_span = length if (length is not None and length > 0) else 1
          # Cap span so it doesn't exceed line length
          available_chars = max(1, len(expanded_line) - col_offset)
          caret_span = min(caret_span, available_chars)

          caret_line = f"  {indent_pad}{' ' * col_offset}{'^' * caret_span}"
        else:
          # Underline non-whitespace portion of line
          indent_len = len(expanded_line) - len(expanded_line.lstrip())
          stripped_len = max(1, len(expanded_line.strip()))
          caret_line = f"  {indent_pad}{' ' * indent_len}{'^' * stripped_len}"

        lines_out.append(caret_line)

  return "\n".join(lines_out)
