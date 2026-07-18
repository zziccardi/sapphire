"""Unit tests for Sapphire semantic tokens extraction and encoding.

This module validates that positioning coordinates are correctly extracted from AST
nodes and delta-encoded into standard LSP 5-integer arrays.
"""

import unittest
import sys
import os

# Insert workspace src directory into python path to allow direct imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from antlr4 import InputStream, CommonTokenStream
try:
  from parser.gen.SapphireLexer import SapphireLexer
  from parser.gen.SapphireParser import SapphireParser
  from parser.ast_builder import ASTBuilder
  from lsp.semantic_tokens import (
      SemanticTokensTypeChecker,
      encode_semantic_tokens,
  )
except ImportError:
  from src.parser.gen.SapphireLexer import SapphireLexer
  from src.parser.gen.SapphireParser import SapphireParser
  from src.parser.ast_builder import ASTBuilder
  from src.lsp.semantic_tokens import (
      SemanticTokensTypeChecker,
      encode_semantic_tokens,
  )


class TestSemanticTokens(unittest.TestCase):
  """Unit tests for Sapphire semantic tokens extraction and encoding."""

  def test_delta_encoding_single_line(self):
    """Verifies relative encoding of multiple tokens on the same line."""
    # Format: (line, col, length, type_str, mods)
    # Note: ANTLR lines are 1-based, columns are 0-based
    raw = [
        (1, 4, 3, "struct", 1),    # line 1 (0 in LSP), col 4, len 3
        (1, 12, 6, "variable", 0),  # line 1 (0 in LSP), col 12, len 6
    ]
    # Expected:
    # 1. line 0, col 4, len 3, struct(2), declaration(1)
    # 2. line 0, col 8 (12-4), len 6, variable(5), none(0)
    encoded = encode_semantic_tokens(raw)
    self.assertEqual(encoded, [0, 4, 3, 2, 1, 0, 8, 6, 5, 0])

  def test_delta_encoding_multi_line(self):
    """Verifies relative encoding of tokens across multiple lines."""
    raw = [
        (1, 2, 3, "keyword", 0),  # line 1 (0 in LSP), col 2, len 3
        (2, 5, 4, "variable", 4), # line 2 (1 in LSP), col 5, len 4 (readonly=4)
    ]
    # Expected:
    # 1. line 0, col 2, len 3, keyword(9), none(0)
    # 2. line 1 (2-1), col 5 (absolute since line changed), len 4, variable(5), readonly(4)
    encoded = encode_semantic_tokens(raw)
    self.assertEqual(encoded, [0, 2, 3, 9, 0, 1, 5, 4, 5, 4])

  def test_delta_encoding_sorting(self):
    """Verifies tokens are sorted correctly before delta encoding."""
    raw = [
        (2, 5, 4, "variable", 0),
        (1, 2, 3, "keyword", 0),
    ]
    # Should sort first: line 1, then line 2
    encoded = encode_semantic_tokens(raw)
    self.assertEqual(encoded, [0, 2, 3, 9, 0, 1, 5, 4, 5, 0])

  def test_token_extraction(self):
    """Verifies that parsing a program extracts correct semantic tokens."""
    code = "let speed: int = 42;"
    input_stream = InputStream(code)
    lexer = SapphireLexer(input_stream)
    stream = CommonTokenStream(lexer)
    parser = SapphireParser(stream)
    tree = parser.program()

    builder = ASTBuilder()
    ast = builder.visit(tree)

    checker = SemanticTokensTypeChecker()
    checker.check(ast)

    # We expect:
    # - 'speed' variable declaration (line 1, col 4, len 5, variable, mods=5 (declaration=1 | readonly=4))
    # - 'int' type reference (line 1, col 11, len 3, type, mods=0)
    raw = checker.raw_tokens

    # Check that we got our expected tokens
    var_token = next((t for t in raw if t[3] == "variable"), None)
    self.assertIsNotNone(var_token)
    self.assertEqual(var_token[0], 1)
    self.assertEqual(var_token[1], 4)
    self.assertEqual(var_token[2], 5)
    self.assertEqual(var_token[4], 5)  # declaration (1) + readonly (4) = 5

    type_token = next((t for t in raw if t[3] == "type"), None)
    self.assertIsNotNone(type_token)
    self.assertEqual(type_token[0], 1)
    self.assertEqual(type_token[1], 11)
    self.assertEqual(type_token[2], 3)
