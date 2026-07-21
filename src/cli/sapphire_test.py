import os
import sys
import tempfile
import unittest
from unittest.mock import patch

from src.cli.sapphire import main


class SapphireCLITest(unittest.TestCase):

  def setUp(self):
    self.temp_dir = tempfile.TemporaryDirectory()
    self.sp_file = os.path.join(self.temp_dir.name, "test.sp")
    with open(self.sp_file, "w", encoding="utf-8") as f:
      f.write("let x: int = 42;\n")

  def tearDown(self):
    self.temp_dir.cleanup()

  def test_build_subcommand(self):
    py_file = os.path.join(self.temp_dir.name, "output.py")
    test_args = ["sapphire", "build", self.sp_file, "-o", py_file]
    with patch.object(sys, "argv", test_args):
      main()
    self.assertTrue(os.path.exists(py_file))

  def test_build_file_not_found(self):
    non_existent = os.path.join(self.temp_dir.name, "does_not_exist.sp")
    test_args = ["sapphire", "build", non_existent]
    with patch.object(sys, "argv", test_args):
      with self.assertRaises(SystemExit) as cm:
        main()
      self.assertEqual(cm.exception.code, 1)

  def test_run_subcommand(self):
    test_args = ["sapphire", "run", self.sp_file]
    with patch.object(sys, "argv", test_args):
      with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        with self.assertRaises(SystemExit) as cm:
          main()
        self.assertEqual(cm.exception.code, 0)
        mock_run.assert_called_once()

  def test_run_file_not_found(self):
    non_existent = os.path.join(self.temp_dir.name, "does_not_exist.sp")
    test_args = ["sapphire", "run", non_existent]
    with patch.object(sys, "argv", test_args):
      with self.assertRaises(SystemExit) as cm:
        main()
      self.assertEqual(cm.exception.code, 1)

  def test_shortcut_invocation(self):
    test_args = ["sapphire", self.sp_file]
    with patch.object(sys, "argv", test_args):
      with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        with self.assertRaises(SystemExit) as cm:
          main()
        self.assertEqual(cm.exception.code, 0)
        mock_run.assert_called_once()

  def test_no_args_prints_help(self):
    test_args = ["sapphire"]
    with patch.object(sys, "argv", test_args):
      main()

  def test_game_loop_sample_execution(self):
    game_loop_sp = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "../../samples/game_loop.sp")
    )
    self.assertTrue(os.path.exists(game_loop_sp))

    test_args = ["sapphire", "run", game_loop_sp]
    with patch.object(sys, "argv", test_args):
      with self.assertRaises(SystemExit) as cm:
        main()
      self.assertEqual(cm.exception.code, 0)


if __name__ == "__main__":
  unittest.main()
