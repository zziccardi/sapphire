"""Domain-specific exception hierarchy for the Sapphire compiler and runtime."""

from typing import Optional


class SapphireError(Exception):
  """Base exception class for all Sapphire compiler and tooling errors."""

  def __init__(
      self,
      message: str,
      file_path: Optional[str] = None,
      line: Optional[int] = None,
      column: Optional[int] = None,
  ):
    super().__init__(message)
    self.message = message
    self.file_path = file_path
    self.line = line
    self.column = column

  def __str__(self) -> str:
    loc = ""
    if self.file_path or self.line:
      file_str = self.file_path or ""
      line_str = f":{self.line}" if self.line is not None else ""
      col_str = f":{self.column}" if self.column is not None else ""
      loc = f" at {file_str}{line_str}{col_str}"
    return f"{self.message}{loc}"


class SapphireSyntaxError(SapphireError):
  """Raised for lexer and parser syntax failures."""

  pass


class SapphireTypeError(SapphireError):
  """Raised for compile-time type checking and semantic analysis violations."""

  pass


# Backward compatibility alias for SemanticError
SemanticError = SapphireTypeError


class SapphireTranspileError(SapphireError):
  """Raised during code generation or backend emission failures."""

  pass


class SapphireLSPError(SapphireError):
  """Raised during Language Server Protocol message handling or document processing."""

  pass
