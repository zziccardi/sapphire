import os
import sys
import tempfile
import unittest
from unittest.mock import patch

from src.run_transpiler import transpile_file, main


class RunTranspilerTest(unittest.TestCase):

  def setUp(self):
    self.temp_dir = tempfile.TemporaryDirectory()
    self.sp_file = os.path.join(self.temp_dir.name, "test.sp")
    with open(self.sp_file, "w", encoding="utf-8") as f:
      f.write("let x: int = 42;\n")

  def tearDown(self):
    self.temp_dir.cleanup()

  def test_transpile_file_default_output(self):
    """Verifies transpile_file defaults output to input file with .py extension."""
    out_path = transpile_file(self.sp_file)
    expected_out = os.path.join(self.temp_dir.name, "test.py")
    self.assertEqual(out_path, expected_out)
    self.assertTrue(os.path.exists(out_path))

  def test_transpile_file_read_error(self):
    """Verifies file reading failure triggers sys.exit(1)."""
    non_existent = os.path.join(self.temp_dir.name, "does_not_exist.sp")
    with self.assertRaises(SystemExit) as cm:
      transpile_file(non_existent)
    self.assertEqual(cm.exception.code, 1)

  def test_transpile_file_syntax_error(self):
    """Verifies syntax error triggers error listener and sys.exit(1)."""
    bad_sp = os.path.join(self.temp_dir.name, "syntax_error.sp")
    with open(bad_sp, "w", encoding="utf-8") as f:
      f.write("let x: int = ;\n")
    with self.assertRaises(SystemExit) as cm:
      transpile_file(bad_sp)
    self.assertEqual(cm.exception.code, 1)

  def test_transpile_file_semantic_error(self):
    """Verifies semantic error triggers sys.exit(1)."""
    semantic_sp = os.path.join(self.temp_dir.name, "semantic_error.sp")
    with open(semantic_sp, "w", encoding="utf-8") as f:
      f.write("return 42;\n")
    with self.assertRaises(SystemExit) as cm:
      transpile_file(semantic_sp)
    self.assertEqual(cm.exception.code, 1)

  def test_transpile_file_write_error(self):
    """Verifies file output write failure triggers sys.exit(1)."""
    with self.assertRaises(SystemExit) as cm:
      transpile_file(self.sp_file, output_file="/non_existent_directory_xyz/out.py")
    self.assertEqual(cm.exception.code, 1)

  def test_main_with_arguments(self):
    """Verifies main() execution with explicit file argument."""
    out_file = os.path.join(self.temp_dir.name, "custom.py")
    test_args = ["run_transpiler.py", self.sp_file]
    with patch.object(sys, "argv", test_args):
      main()
    self.assertTrue(os.path.exists(os.path.join(self.temp_dir.name, "test.py")))

  def test_main_without_arguments(self):
    """Verifies main() execution defaulting to sample.sp when no args passed."""
    test_args = ["run_transpiler.py"]
    with patch.object(sys, "argv", test_args):
      with patch("src.run_transpiler.transpile_file") as mock_transpile:
        main()
        mock_transpile.assert_called_once()


if __name__ == "__main__":
  unittest.main()
