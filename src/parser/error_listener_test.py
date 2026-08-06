"""Unit tests for centralized CustomErrorListener in src/parser/error_listener.py."""

import unittest
from unittest.mock import MagicMock
from src.parser.error_listener import CustomErrorListener, format_syntax_error_message


class TestErrorListener(unittest.TestCase):
  """Unit tests for ANTLR error listener and syntax error formatting."""

  def test_format_syntax_error_message_match_expression(self):
    mock_token = MagicMock()
    mock_token.tokenIndex = 5
    mock_token.text = "}"

    t_match = MagicMock(text="match", channel=0)
    t_open = MagicMock(text="{", channel=0)
    t_close = MagicMock(text="}", channel=0)

    def get_token(i):
      if i == 0:
        return t_match
      elif i == 3:
        return t_open
      else:
        return t_close

    mock_stream = MagicMock()
    mock_stream.get.side_effect = get_token


    mock_recognizer = MagicMock()
    mock_recognizer.getTokenStream.return_value = mock_stream


    msg = format_syntax_error_message(mock_recognizer, mock_token, "mismatched input")
    self.assertIn("Missing semicolon ';'", msg)

  def test_custom_error_listener_quiet_and_verbose(self):
    listener = CustomErrorListener(file_path="sample.sp", source_content="let x = 5;", quiet=True)
    mock_symbol = MagicMock()
    mock_symbol.text = "x"

    listener.syntaxError(None, mock_symbol, 1, 4, "unexpected token", None)
    self.assertEqual(listener.errors, 1)
    self.assertEqual(len(listener.error_messages), 1)
    self.assertIn("Syntax Error", listener.error_messages[0])
