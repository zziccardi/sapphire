import importlib
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from testing.test_utils import suppress_output


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
      with suppress_output():
        main()
    self.assertTrue(os.path.exists(py_file))

  def test_build_subcommand_lua(self):
    lua_file = os.path.join(self.temp_dir.name, "output.lua")
    map_file = lua_file + ".map"
    test_args = ["sapphire", "build", self.sp_file, "-t", "lua", "-o", lua_file]
    with patch.object(sys, "argv", test_args):
      with suppress_output():
        main()
    self.assertTrue(os.path.exists(lua_file))
    self.assertTrue(os.path.exists(map_file))

  def test_build_subcommand_lua_no_sourcemap(self):
    lua_file = os.path.join(self.temp_dir.name, "output_nosm.lua")
    map_file = lua_file + ".map"
    test_args = ["sapphire", "build", self.sp_file, "-t", "lua", "-o", lua_file, "--no_sourcemap"]
    with patch.object(sys, "argv", test_args):
      with suppress_output():
        main()
    self.assertTrue(os.path.exists(lua_file))
    self.assertFalse(os.path.exists(map_file))

  def test_build_file_not_found(self):
    non_existent = os.path.join(self.temp_dir.name, "does_not_exist.sp")
    test_args = ["sapphire", "build", non_existent]
    with patch.object(sys, "argv", test_args):
      with self.assertRaises(SystemExit) as cm:
        with suppress_output():
          main()
      self.assertEqual(cm.exception.code, 1)

  def test_test_subcommand(self):
    test_args = ["sapphire", "test", self.sp_file]
    with patch.object(sys, "argv", test_args):
      with self.assertRaises(SystemExit) as cm:
        with suppress_output():
          main()
      self.assertEqual(cm.exception.code, 0)

  def test_run_file_not_found(self):
    non_existent = os.path.join(self.temp_dir.name, "does_not_exist.sp")
    test_args = ["sapphire", "run", non_existent]
    with patch.object(sys, "argv", test_args):
      with self.assertRaises(SystemExit) as cm:
        with suppress_output():
          main()
      self.assertEqual(cm.exception.code, 1)

  def test_run_subcommand_lua(self):
    test_args = ["sapphire", "run", self.sp_file, "-t", "lua"]
    with patch.object(sys, "argv", test_args):
      with patch("shutil.which", return_value="/usr/bin/lua"):
        with patch("subprocess.run") as mock_run:
          mock_run.return_value.returncode = 0
          with self.assertRaises(SystemExit) as cm:
            with suppress_output():
              main()
          self.assertEqual(cm.exception.code, 0)
          mock_run.assert_called_once()

  def test_run_subcommand_lua_not_found(self):
    test_args = ["sapphire", "run", self.sp_file, "-t", "lua"]
    with patch.object(sys, "argv", test_args):
      with patch("shutil.which", return_value=None):
        with self.assertRaises(SystemExit) as cm:
          with suppress_output():
            main()
        self.assertEqual(cm.exception.code, 1)

  def test_shortcut_invocation(self):
    test_args = ["sapphire", self.sp_file]
    with patch.object(sys, "argv", test_args):
      with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        with self.assertRaises(SystemExit) as cm:
          with suppress_output():
            main()
        self.assertEqual(cm.exception.code, 0)
        mock_run.assert_called_once()

  def test_no_args_prints_help(self):
    test_args = ["sapphire"]
    with patch.object(sys, "argv", test_args):
      with suppress_output():
        main()

  def test_game_loop_sample_execution(self):
    game_loop_sp = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "../../samples/game_loop.sp")
    )
    self.assertTrue(os.path.exists(game_loop_sp))

    test_args = ["sapphire", "run", game_loop_sp]
    with patch.object(sys, "argv", test_args):
      with self.assertRaises(SystemExit) as cm:
        with suppress_output():
          main()
      self.assertEqual(cm.exception.code, 0)

  def test_sys_path_auto_injection(self):
    """Ensures src/cli/sapphire.py injects the src directory into sys.path when absent."""
    src_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    with patch.object(sys, "path", [p for p in sys.path if p != src_dir]):
      import src.cli.sapphire as sapphire_cli

      importlib.reload(sapphire_cli)
      self.assertIn(src_dir, sys.path)

  def test_isolated_pythonpath_execution(self):
    """Verifies that running sapphire CLI without PYTHONPATH succeeds without ModuleNotFoundError."""
    repo_root = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "../..")
    )
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)

    res = subprocess.run(
        [sys.executable, "-m", "src.cli.sapphire", "build", self.sp_file],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
    )
    self.assertEqual(res.returncode, 0)
    self.assertNotIn("ModuleNotFoundError", res.stderr)


if __name__ == "__main__":
  unittest.main()
