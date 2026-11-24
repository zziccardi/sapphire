"""CLI diagnostic presentation facade for Sapphire compiler and test runner.

Re-exports the core `Diagnostic` model and formatting helpers from
`src.common.diagnostics` for CLI entry points.
"""

from sapphire.common.diagnostics import (
  Diagnostic,
  format_diagnostic,
  get_source_line,
)

__all__ = [
  "Diagnostic",
  "format_diagnostic",
  "get_source_line",
]
