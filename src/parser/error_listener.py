"""Centralized ANTLR error listener and syntax diagnostic formatter for Sapphire."""

import sys
from typing import Any, Optional
from antlr4.error.ErrorListener import ErrorListener

from src.cli.diagnostics import format_diagnostic


def format_syntax_error_message(recognizer: Any, offendingSymbol: Any, msg: str) -> str:
  """Customizes ANTLR syntax error messages for better developer ergonomics."""
  if recognizer and offendingSymbol and hasattr(offendingSymbol, "tokenIndex"):
    try:
      stream = recognizer.getTokenStream()
      if stream:
        idx = offendingSymbol.tokenIndex
        prev_idx = idx - 1
        while prev_idx >= 0 and stream.get(prev_idx).channel != 0:
          prev_idx -= 1  # pragma: no cover

        if prev_idx >= 0 and stream.get(prev_idx).text == "}":
          depth = 1
          curr = prev_idx - 1
          while curr >= 0 and depth > 0:
            tok_text = stream.get(curr).text
            if tok_text == "}":
              depth += 1
            elif tok_text == "{":
              depth -= 1
            curr -= 1

          search_limit = max(0, curr - 30)
          while curr >= search_limit:
            tok = stream.get(curr)
            if tok.text == "match":
              return (
                  f"Missing semicolon ';' after closing brace '}}' of match expression. "
                  f"Match expressions used as statements must end with a semicolon ';' (e.g. 'match ... }};')."
              )
            curr -= 1
    except Exception:  # pragma: no cover
      pass
  return msg


class CustomErrorListener(ErrorListener):
  """Custom ANTLR error listener to track and report syntax errors."""

  def __init__(
      self,
      file_path: Optional[str] = None,
      source_content: Optional[Any] = None,
      quiet: bool = False,
  ):
    super().__init__()
    self.errors = 0
    self.file_path = file_path
    self.source_content = source_content
    self.quiet = quiet
    self.error_messages = []

  def syntaxError(self, recognizer, offendingSymbol, line, column, msg, e):
    self.errors += 1
    custom_msg = format_syntax_error_message(recognizer, offendingSymbol, msg)
    length = (
        len(offendingSymbol.text)
        if (offendingSymbol and hasattr(offendingSymbol, "text") and offendingSymbol.text)
        else 1
    )
    source_content = (
        str(self.source_content) if self.source_content is not None else None
    )
    diag = format_diagnostic(
        error_type="Syntax Error",
        message=custom_msg,
        file_path=self.file_path,
        line=line,
        column=column,
        length=length,
        source_content=source_content,
    )
    self.error_messages.append(diag)
    if not self.quiet:
      print(diag, file=sys.stderr)
