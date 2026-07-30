"""Unit tests for standalone runner scripts (run_ast, run_parser, run_semantic_analyzer, run_transpiler)."""

import os
import sys
import tempfile
import unittest
from unittest.mock import patch

from src.run_ast import main as run_ast_main
from src.run_parser import main as run_parser_main
from src.run_semantic_analyzer import main as run_semantic_analyzer_main
from src.run_transpiler import main as run_transpiler_main


class TestRunnerScripts(unittest.TestCase):

  def setUp(self):
    self.sample_sp = os.path.join(os.path.dirname(__file__), "..", "samples", "game_loop.sp")

  def test_run_ast(self):
    with patch.object(sys, "argv", ["run_ast.py", self.sample_sp]):
      run_ast_main()

  def test_run_ast_default_args(self):
    with patch.object(sys, "argv", ["run_ast.py"]):
      with patch("os.path.abspath", return_value=os.path.join(os.path.dirname(__file__), "run_ast.py")):
        run_ast_main()

  def test_run_ast_missing_file(self):
    with patch.object(sys, "argv", ["run_ast.py", "/non_existent_file.sp"]):
      with self.assertRaises(SystemExit):
        run_ast_main()

  def test_run_ast_syntax_error(self):
    with tempfile.NamedTemporaryFile("w", suffix=".sp", delete=False) as f:
      f.write("let x: int = ;")
      temp_path = f.name
    try:
      with patch.object(sys, "argv", ["run_ast.py", temp_path]):
        with self.assertRaises(SystemExit):
          run_ast_main()
    finally:
      os.remove(temp_path)

  def test_run_parser(self):
    with patch.object(sys, "argv", ["run_parser.py", self.sample_sp]):
      run_parser_main()

  def test_run_parser_default_args(self):
    with patch.object(sys, "argv", ["run_parser.py"]):
      run_parser_main()

  def test_run_parser_missing_file(self):
    with patch.object(sys, "argv", ["run_parser.py", "/non_existent_file.sp"]):
      with self.assertRaises(SystemExit):
        run_parser_main()

  def test_run_parser_syntax_error(self):
    with tempfile.NamedTemporaryFile("w", suffix=".sp", delete=False) as f:
      f.write("let x: int = ;")
      temp_path = f.name
    try:
      with patch.object(sys, "argv", ["run_parser.py", temp_path]):
        with self.assertRaises(SystemExit):
          run_parser_main()
    finally:
      os.remove(temp_path)

  def test_run_semantic_analyzer(self):
    with patch.object(sys, "argv", ["run_semantic_analyzer.py", self.sample_sp]):
      run_semantic_analyzer_main()

  def test_run_semantic_analyzer_default_args(self):
    with patch.object(sys, "argv", ["run_semantic_analyzer.py"]):
      run_semantic_analyzer_main()

  def test_run_semantic_analyzer_missing_file(self):
    with patch.object(sys, "argv", ["run_semantic_analyzer.py", "/non_existent_file.sp"]):
      with self.assertRaises(SystemExit):
        run_semantic_analyzer_main()

  def test_run_semantic_analyzer_syntax_error(self):
    with tempfile.NamedTemporaryFile("w", suffix=".sp", delete=False) as f:
      f.write("let x: int = ;")
      temp_path = f.name
    try:
      with patch.object(sys, "argv", ["run_semantic_analyzer.py", temp_path]):
        with self.assertRaises(SystemExit):
          run_semantic_analyzer_main()
    finally:
      os.remove(temp_path)

  def test_run_semantic_analyzer_semantic_error(self):
    with tempfile.NamedTemporaryFile("w", suffix=".sp", delete=False) as f:
      f.write("func test() { return 123; }")
      temp_path = f.name
    try:
      with patch.object(sys, "argv", ["run_semantic_analyzer.py", temp_path]):
        with self.assertRaises(SystemExit):
          run_semantic_analyzer_main()
    finally:
      os.remove(temp_path)

  def test_run_transpiler(self):
    with patch.object(sys, "argv", ["run_transpiler.py", self.sample_sp, "python"]):
      run_transpiler_main()

  def test_run_transpiler_default_args(self):
    with patch.object(sys, "argv", ["run_transpiler.py"]):
      run_transpiler_main()


if __name__ == "__main__":
  unittest.main()
