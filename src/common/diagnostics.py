"""Core compiler diagnostic model and source-line formatting utilities.

Provides the structured `Diagnostic` dataclass and plain-text snippet
formatting shared across the parser, semantic analyzer, and CLI. Terminal
styling and CLI-specific presentation live in `src.cli.diagnostics`.
"""

import os
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any


@dataclass
class Diagnostic:
  """Structured compiler or tooling diagnostic."""

  severity: str
  message: str
  file_path: str | None = None
  line: int | None = None
  column: int | None = None
  length: int | None = None
  hint: str | None = None
  code: str | None = None

  def to_dict(self) -> dict[str, Any]:
    """Serializes the diagnostic to a JSON-compatible dictionary."""
    return {
      "severity": self.severity,
      "code": self.code,
      "message": self.message,
      "hint": self.hint,
      "file": self.file_path,
      "line": self.line,
      "column": self.column,
      "length": self.length,
    }


@lru_cache(maxsize=64)
def _read_file_lines_cached(
  path_str: str, mtime_ns: int, size: int
) -> tuple[str, ...]:
  """Reads and caches all lines of a source file keyed by (path, mtime, size).
  """
  del mtime_ns, size
  with open(path_str, "r", encoding="utf-8") as f:
    return tuple(f.readlines())


def get_source_line(
  lineno: int,
  *,
  file_path: str | Path | None = None,
  source_text: str | None = None,
  source_lines: Sequence[str] | None = None,
) -> str | None:
  """Reads a 1-indexed line from explicit source lines, text, or a file path.

  Args:
    lineno: 1-indexed line number to retrieve.
    file_path: Optional path to a source file on disk.
    source_text: Optional raw multi-line source string.
    source_lines: Optional pre-split sequence of source lines.

  Returns:
    The requested line, or None if out of bounds or unreadable.
  """
  if lineno < 1:
    return None

  if source_lines is not None:
    if 1 <= lineno <= len(source_lines):
      return source_lines[lineno - 1]
    return None

  if source_text is not None:
    lines = source_text.splitlines()
    if 1 <= lineno <= len(lines):
      return lines[lineno - 1]
    return None

  if file_path is not None:
    path = Path(file_path)
    try:
      stat = path.stat()
      if not path.is_file():
        return None
      cached_lines = _read_file_lines_cached(
        str(path), stat.st_mtime_ns, stat.st_size
      )
      if 1 <= lineno <= len(cached_lines):
        return cached_lines[lineno - 1]
    except OSError:
      return None

  return None


def format_diagnostic(
  error_type: str,
  message: str,
  file_path: str | None = None,
  line: int | None = None,
  column: int | None = None,
  length: int | None = None,
  source_content: str | Sequence[str] | None = None,
  hint: str | None = None,
) -> str:
  """Formats a diagnostic with source snippet, line numbers, and carets (^).

  Args:
    error_type: Diagnostic prefix (e.g. 'Syntax Error', 'Semantic Error').
    message: Main diagnostic message text.
    file_path: Optional filename or file path.
    line: Optional 1-indexed line number.
    column: Optional 0-indexed column offset within the line.
    length: Optional token/expression character length for caret span.
    source_content: Optional raw multi-line source string or sequence of lines.
    hint: Optional actionable fix-it hint displayed after the caret underline.

  Returns:
    Formatted multi-line diagnostic string.
  """
  lines_out = []

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

  if line and line > 0:
    if isinstance(source_content, str):
      raw_line = get_source_line(line, source_text=source_content)
    elif source_content is not None:
      raw_line = get_source_line(line, source_lines=source_content)
    elif file_path:
      raw_line = get_source_line(line, file_path=file_path)
    else:
      raw_line = None

    if raw_line is not None:
      # Strip line endings before column slicing so past-EOL columns do not
      # shift carets past the end of the displayed line.
      clean_line = raw_line.rstrip("\r\n")
      # Expand tabs to 4 spaces to maintain column alignment in terminal
      expanded_line = clean_line.expandtabs(4)
      line_str = str(line)
      lines_out.append(f"  Line {line_str}:  {expanded_line}")

      indent_pad = " " * (len(line_str) + 8)

      if column is not None and column >= 0:
        prefix_before_col = clean_line[:column].expandtabs(4)
        col_offset = len(prefix_before_col)

        caret_span = length if (length is not None and length > 0) else 1
        available_chars = max(1, len(expanded_line) - col_offset)
        caret_span = min(caret_span, available_chars)

        caret_line = f"  {indent_pad}{' ' * col_offset}{'^' * caret_span}"
      else:
        indent_len = len(expanded_line) - len(expanded_line.lstrip())
        stripped_len = max(1, len(expanded_line.strip()))
        caret_line = f"  {indent_pad}{' ' * indent_len}{'^' * stripped_len}"

      lines_out.append(caret_line)

  if hint:
    lines_out.append(f"  Hint: {hint}")

  return "\n".join(lines_out)
