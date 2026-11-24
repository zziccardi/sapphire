"""Unit tests for centralized CustomErrorListener in src/parser/error_listener.py."""

import unittest
from unittest.mock import MagicMock

from sapphire.parser.error_listener import (
  CustomErrorListener,
  format_syntax_error_message,
)


class TestErrorListener(unittest.TestCase):
  """Unit tests for ANTLR error listener and syntax error formatting."""

  def test_format_syntax_error_message_match_expression(self):
    tokens = [
        MagicMock(text="match", channel=0),
        MagicMock(text="x", channel=0),
        MagicMock(text="{", channel=0),
        MagicMock(text="}", channel=0),
        MagicMock(text="let", channel=0, tokenIndex=4),
    ]
    mock_stream = MagicMock()
    mock_stream.get.side_effect = lambda i: tokens[i]

    mock_recognizer = MagicMock()
    mock_recognizer.getTokenStream.return_value = mock_stream

    msg = format_syntax_error_message(mock_recognizer, tokens[4], "mismatched input")
    self.assertIn("Missing semicolon ';'", msg)

  def test_match_expression_missing_semicolon_real_parser(self):
    from antlr4 import CommonTokenStream, InputStream

    from sapphire.parser.gen.SapphireLexer import SapphireLexer
    from sapphire.parser.gen.SapphireParser import SapphireParser

    code = """
    func test(v: int) {
      let x = match v {
        1 -> "one",
        ... -> "other"
      }
      let y = 2;
    }
    """
    listener = CustomErrorListener(file_path="test.sp", source_content=code, quiet=True)
    lexer = SapphireLexer(InputStream(code))
    lexer.removeErrorListeners()
    lexer.addErrorListener(listener)
    parser = SapphireParser(CommonTokenStream(lexer))
    parser.removeErrorListeners()
    parser.addErrorListener(listener)
    parser.program()

    self.assertGreater(listener.errors, 0)
    self.assertTrue(
        any("Missing semicolon ';'" in d.message for d in listener.diagnostics),
        f"Expected match semicolon hint, got: {[d.message for d in listener.diagnostics]}",
    )

  def test_missing_comma_after_match_arm_block_not_misreported(self):
    from antlr4 import CommonTokenStream, InputStream

    from sapphire.parser.gen.SapphireLexer import SapphireLexer
    from sapphire.parser.gen.SapphireParser import SapphireParser

    code = """
    func test(v: int): int {
      let x = match v {
        1 -> { let a = 1; yield a; }
        2 -> 3
      };
      return x;
    }
    """
    listener = CustomErrorListener(file_path="test.sp", source_content=code, quiet=True)
    lexer = SapphireLexer(InputStream(code))
    lexer.removeErrorListeners()
    lexer.addErrorListener(listener)
    parser = SapphireParser(CommonTokenStream(lexer))
    parser.removeErrorListeners()
    parser.addErrorListener(listener)
    parser.program()

    self.assertGreater(listener.errors, 0)
    self.assertFalse(
        any("Missing semicolon ';'" in d.message for d in listener.diagnostics),
        f"Unexpected match semicolon hint on missing arm comma: {[d.message for d in listener.diagnostics]}",
    )

  def test_struct_initializer_missing_semicolon_after_match_not_misreported(self):
    from antlr4 import CommonTokenStream, InputStream

    from sapphire.parser.gen.SapphireLexer import SapphireLexer
    from sapphire.parser.gen.SapphireParser import SapphireParser

    code = """
    func test(v: int) {
      match v {
        1 -> print("a"),
        ... -> print("b")
      }
      let p = Point { x = 1 }
      let q = 2;
    }
    """
    listener = CustomErrorListener(file_path="test.sp", source_content=code, quiet=True)
    lexer = SapphireLexer(InputStream(code))
    lexer.removeErrorListeners()
    lexer.addErrorListener(listener)
    parser = SapphireParser(CommonTokenStream(lexer))
    parser.removeErrorListeners()
    parser.addErrorListener(listener)
    parser.program()

    self.assertGreater(listener.errors, 0)
    self.assertFalse(
        any("Missing semicolon ';'" in d.message for d in listener.diagnostics),
        f"Unexpected match semicolon hint on struct init: {[d.message for d in listener.diagnostics]}",
    )

  def test_custom_error_listener_quiet_and_verbose(self):
    listener = CustomErrorListener(file_path="sample.sp", source_content="let x = 5;", quiet=True)
    mock_symbol = MagicMock()
    mock_symbol.text = "x"

    listener.syntaxError(None, mock_symbol, 1, 4, "unexpected token", None)
    self.assertEqual(listener.errors, 1)
    self.assertEqual(len(listener.error_messages), 1)
    self.assertIn("Syntax Error", listener.error_messages[0])

  def test_eof_token_length_is_one(self):
    listener = CustomErrorListener(file_path="eof.sp", source_content="let x = 1", quiet=True)
    mock_eof = MagicMock()
    mock_eof.text = "<EOF>"

    listener.syntaxError(None, mock_eof, 1, 9, "missing ';'", None)
    self.assertEqual(len(listener.diagnostics), 1)
    self.assertEqual(listener.diagnostics[0].length, 1)
