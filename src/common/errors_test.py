"""Unit tests for Sapphire exception hierarchy in src/common/errors.py."""

import unittest
from src.common.errors import (
    SapphireError,
    SapphireSyntaxError,
    SapphireTypeError,
    SapphireTranspileError,
    SapphireLSPError,
    SemanticError,
)


class TestErrors(unittest.TestCase):
  """Unit tests verifying exception string formatting and inheritance."""

  def test_sapphire_error_formatting(self):
    err1 = SapphireError("Base error message")
    self.assertEqual(str(err1), "Base error message")

    err2 = SapphireError("Syntax issue", file_path="main.sp", line=10, column=5)
    self.assertEqual(str(err2), "Syntax issue at main.sp:10:5")

    err3 = SapphireError("Type issue", line=42)
    self.assertEqual(str(err3), "Type issue at :42")

  def test_exception_inheritance(self):
    syn_err = SapphireSyntaxError("Unexpected token")
    self.assertIsInstance(syn_err, SapphireError)

    type_err = SapphireTypeError("Type mismatch")
    self.assertIsInstance(type_err, SapphireError)
    self.assertEqual(SapphireTypeError, SemanticError)

    trans_err = SapphireTranspileError("Codegen failed")
    self.assertIsInstance(trans_err, SapphireError)

    lsp_err = SapphireLSPError("LSP sync error")
    self.assertIsInstance(lsp_err, SapphireError)
