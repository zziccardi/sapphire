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

  def test_run_demo_flag(self):
    test_args = ["sapphire", "run", self.sp_file, "--demo"]
    with patch.object(sys, "argv", test_args):
      with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        with self.assertRaises(SystemExit) as cm:
          main()
        self.assertEqual(cm.exception.code, 0)
        mock_run.assert_called_once()

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


if __name__ == "__main__":
  unittest.main()
