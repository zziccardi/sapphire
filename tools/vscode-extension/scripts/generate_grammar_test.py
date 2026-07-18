import unittest
import os
import sys
from unittest.mock import patch, mock_open

# Ensure local directory is in path for imports
local_dir = os.path.dirname(__file__)
if local_dir not in sys.path:
  sys.path.insert(0, local_dir)

from generate_grammar import parse_antlr_grammar, main


class TestGenerateGrammar(unittest.TestCase):

  def test_parse_antlr_grammar_real(self):
    """Verifies parsing of the actual grammar/Sapphire.g4 file."""
    data = parse_antlr_grammar()
    self.assertIn("let", data["modifiers"])
    self.assertIn("struct", data["modifiers"])
    self.assertIn("int", data["types"])
    self.assertIn("none", data["constants"])

  def test_parse_antlr_grammar_missing_file(self):
    """Verifies FileNotFoundError is raised if grammar file is missing."""
    with patch("os.path.exists", return_value=False):
      with self.assertRaises(FileNotFoundError):
        parse_antlr_grammar()

  @patch("builtins.open", new_callable=mock_open)
  @patch("os.makedirs")
  @patch("generate_grammar.parse_antlr_grammar")
  def test_main_execution(self, mock_parse, mock_makedirs, mock_file):
    """Verifies main executes, creates output directory and writes JSON file."""
    mock_parse.return_value = {
        "control": ["if", "else"],
        "modifiers": ["let", "var"],
        "types": ["int", "float"],
        "constants": ["true", "false"],
    }
    main()
    mock_makedirs.assert_called_once()
    mock_file.assert_called_once()


if __name__ == "__main__":
  unittest.main()
