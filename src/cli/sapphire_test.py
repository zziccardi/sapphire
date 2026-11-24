import importlib
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from src.cli.sapphire import (
  _collect_sp_watch_files,
  _prepare_exec_env,
  _run_dev_watcher,
  main,
)
from testing.test_utils import suppress_output


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
      with patch("src.cli.sapphire._find_lua_binary", return_value="/usr/bin/lua"):
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
      with patch("src.cli.sapphire._find_lua_binary", return_value=None):
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

  def test_no_sys_path_mutation_on_import(self):
    """Ensures importing src/cli/sapphire.py does not mutate sys.path."""
    src_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    original_path = [p for p in sys.path if p != src_dir]
    with patch.object(sys, "path", list(original_path)):
      import src.cli.sapphire as sapphire_cli

      importlib.reload(sapphire_cli)
      self.assertEqual(sys.path, original_path)

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

  def test_lsp_subcommand(self):
    """Verifies that `sapphire lsp` invokes the LSP server entrypoint."""
    test_args = ["sapphire", "lsp"]
    with patch.object(sys, "argv", test_args):
      with patch("src.lsp.server.main") as mock_lsp_main:
        main()
        mock_lsp_main.assert_called_once()

  def test_build_subcommand_love2d(self):
    lua_file = os.path.join(self.temp_dir.name, "output_love.lua")
    test_args = ["sapphire", "build", self.sp_file, "-t", "love2d", "-o", lua_file]
    with patch.object(sys, "argv", test_args):
      with suppress_output():
        main()
    self.assertTrue(os.path.exists(lua_file))

  def test_build_subcommand_dev_mode(self):
    lua_file = os.path.join(self.temp_dir.name, "output_dev.lua")
    test_args = ["sapphire", "build", self.sp_file, "-t", "lua", "--dev", "-o", lua_file]
    with patch.object(sys, "argv", test_args):
      with suppress_output():
        main()
    self.assertTrue(os.path.exists(lua_file))
    with open(lua_file) as f:
      content = f.read()
    self.assertIn("_SP_DEV_WATCHER", content)

  def test_run_subcommand_love2d(self):
    test_args = ["sapphire", "run", self.sp_file, "-t", "love2d"]
    with patch.object(sys, "argv", test_args):
      with patch("src.cli.sapphire._find_love_binary", return_value="/usr/local/bin/love"):
        with patch("subprocess.run") as mock_run:
          mock_run.return_value.returncode = 0
          with self.assertRaises(SystemExit) as cm:
            with suppress_output():
              main()
          self.assertEqual(cm.exception.code, 0)
          mock_run.assert_called_once()

  def test_run_subcommand_love2d_not_found(self):
    test_args = ["sapphire", "run", self.sp_file, "-t", "love2d"]
    with patch.object(sys, "argv", test_args):
      with patch("src.cli.sapphire._find_love_binary", return_value=None):
        with self.assertRaises(SystemExit) as cm:
          with suppress_output():
            main()
        self.assertEqual(cm.exception.code, 1)

  def test_run_subcommand_dev_mode_invokes_watcher(self):
    test_args = ["sapphire", "run", self.sp_file, "--dev"]
    with patch.object(sys, "argv", test_args):
      with patch("src.cli.sapphire._run_dev_watcher") as mock_watcher:
        with suppress_output():
          main()
        mock_watcher.assert_called_once()

  def test_run_subcommand_love2d_dev_mode_invokes_watcher(self):
    test_args = ["sapphire", "run", self.sp_file, "-t", "love2d", "--dev"]
    with patch.object(sys, "argv", test_args):
      with patch("shutil.which", return_value="/usr/local/bin/love"):
        with patch("src.cli.sapphire._run_dev_watcher") as mock_watcher:
          with suppress_output():
            main()
          mock_watcher.assert_called_once()

  def test_collect_sp_watch_files(self):
    files = _collect_sp_watch_files(self.sp_file)
    self.assertIn(os.path.abspath(self.sp_file), files)

    # Test OSError handling when reading mtime
    with patch("os.path.getmtime", side_effect=OSError("Permission denied")):
      files_err = _collect_sp_watch_files(self.sp_file)
      self.assertEqual(files_err, {})

  def test_run_dev_watcher_love2d_process_exit(self):
    proc = MagicMock()
    proc.poll.return_value = 0
    proc.returncode = 0
    with patch("subprocess.Popen", return_value=proc):
      with patch("time.sleep"):
        with self.assertRaises(SystemExit) as cm:
          with suppress_output():
            _run_dev_watcher(self.sp_file, "out.lua", "love2d", True, ["love", "."])
        self.assertEqual(cm.exception.code, 0)

  def test_run_dev_watcher_file_change_and_restart(self):
    proc1 = MagicMock()
    proc1.poll.side_effect = [None, None, None]
    proc1.wait.side_effect = subprocess.TimeoutExpired(["python", "out.py"], 1.0)
    proc2 = MagicMock()
    proc2.poll.return_value = 0
    with patch("subprocess.Popen", side_effect=[proc1, proc2]):
      with patch("time.sleep", side_effect=[None, KeyboardInterrupt]):
        with patch("src.cli.sapphire.transpile_file") as mock_transpile:
          with patch("src.cli.sapphire._collect_sp_watch_files", side_effect=[
              {self.sp_file: 1.0},
              {self.sp_file: 2.0},
              {self.sp_file: 2.0},
          ]):
            with self.assertRaises(SystemExit) as cm:
              with suppress_output():
                _run_dev_watcher(self.sp_file, "out.py", "python", False, ["python", "out.py"])
            self.assertEqual(cm.exception.code, 0)
            mock_transpile.assert_called_once()
            proc1.terminate.assert_called()
            proc1.kill.assert_called()

  def test_run_dev_watcher_compilation_error_and_shutdown(self):
    proc = MagicMock()
    proc.poll.return_value = 0
    with patch("subprocess.Popen", return_value=proc):
      with patch("time.sleep", side_effect=[None, KeyboardInterrupt]):
        with patch("src.cli.sapphire.transpile_file", side_effect=RuntimeError("Compilation error")):
          with patch("src.cli.sapphire._collect_sp_watch_files", side_effect=[
              {self.sp_file: 1.0},
              {self.sp_file: 2.0},
          ]):
            with self.assertRaises(SystemExit) as cm:
              with suppress_output():
                _run_dev_watcher(self.sp_file, "out.py", "python", False, ["python", "out.py"])
            self.assertEqual(cm.exception.code, 0)

  def test_run_dev_watcher_love2d_file_change_marker(self):
    proc = MagicMock()
    proc.poll.side_effect = [None, None]
    proc.returncode = 0
    with patch("subprocess.Popen", return_value=proc):
      with patch("time.sleep", side_effect=[None, KeyboardInterrupt]):
        with patch("src.cli.sapphire.transpile_file") as mock_transpile:
          with patch("src.cli.sapphire._collect_sp_watch_files", side_effect=[
              {self.sp_file: 1.0},
              {self.sp_file: 2.0},
          ]):
            out_lua = os.path.join(self.temp_dir.name, "main.lua")
            with self.assertRaises(SystemExit) as cm:
              with suppress_output():
                _run_dev_watcher(self.sp_file, out_lua, "love2d", False, ["love", "."])
            self.assertEqual(cm.exception.code, 0)
            mock_transpile.assert_called_once()
            marker_path = os.path.join(self.temp_dir.name, ".sapphire_reload")
            self.assertTrue(os.path.exists(marker_path))
            with open(marker_path, encoding="utf-8") as f:
              self.assertIn("main.lua", f.read())

  def test_run_dev_watcher_keyboard_interrupt_timeout(self):
    proc = MagicMock()
    proc.poll.return_value = None
    proc.wait.side_effect = subprocess.TimeoutExpired(["python", "out.py"], 1.0)
    with patch("subprocess.Popen", return_value=proc):
      with patch("time.sleep", side_effect=KeyboardInterrupt):
        with self.assertRaises(SystemExit) as cm:
          with suppress_output():
            _run_dev_watcher(self.sp_file, "out.py", "python", False, ["python", "out.py"])
        self.assertEqual(cm.exception.code, 0)
        proc.terminate.assert_called_once()
        proc.kill.assert_called_once()

  def test_find_love_binary_lookup(self):
    from src.cli.sapphire import _find_love_binary
    # 1. When shutil.which finds love
    with patch("shutil.which", return_value="/usr/local/bin/love"):
      self.assertEqual(_find_love_binary(), "/usr/local/bin/love")

    # 2. When shutil.which fails but macOS App bundle exists
    with patch("shutil.which", return_value=None):
      with patch("os.path.isfile", side_effect=lambda p: p == "/Applications/love.app/Contents/MacOS/love"):
        with patch("os.access", return_value=True):
          self.assertEqual(_find_love_binary(), "/Applications/love.app/Contents/MacOS/love")

    # 3. When nothing exists
    with patch("shutil.which", return_value=None):
      with patch("os.path.isfile", return_value=False):
        self.assertIsNone(_find_love_binary())

  def test_find_lua_binary_lookup(self):
    from src.cli.sapphire import _find_lua_binary
    # 1. When shutil.which finds lua
    with patch("shutil.which", return_value="/usr/bin/lua"):
      self.assertEqual(_find_lua_binary(), "/usr/bin/lua")

    # 2. When shutil.which fails but fallback exists
    with patch("shutil.which", return_value=None):
      with patch("os.path.isfile", side_effect=lambda p: p == "/opt/homebrew/bin/lua"):
        with patch("os.access", return_value=True):
          self.assertEqual(_find_lua_binary(), "/opt/homebrew/bin/lua")

    # 3. When nothing exists
    with patch("shutil.which", return_value=None):
      with patch("os.path.isfile", return_value=False):
        self.assertIsNone(_find_lua_binary())

  def test_parse_subcommand_success(self):
    test_args = ["sapphire", "parse", self.sp_file]
    with patch.object(sys, "argv", test_args):
      with suppress_output():
        main()

  def test_parse_subcommand_file_not_found(self):
    test_args = ["sapphire", "parse", "non_existent_file.sp"]
    with patch.object(sys, "argv", test_args):
      with self.assertRaises(SystemExit) as cm:
        with suppress_output():
          main()
      self.assertEqual(cm.exception.code, 1)

  def test_parse_subcommand_syntax_error(self):
    bad_sp = os.path.join(self.temp_dir.name, "bad_syntax.sp")
    with open(bad_sp, "w", encoding="utf-8") as f:
      f.write("let x = ;\n")
    test_args = ["sapphire", "parse", bad_sp]
    with patch.object(sys, "argv", test_args):
      with self.assertRaises(SystemExit) as cm:
        with suppress_output():
          main()
      self.assertEqual(cm.exception.code, 1)

  def test_dump_ast_subcommand_success(self):
    test_args = ["sapphire", "dump-ast", self.sp_file]
    with patch.object(sys, "argv", test_args):
      with suppress_output():
        main()

  def test_dump_ast_subcommand_file_not_found(self):
    test_args = ["sapphire", "dump-ast", "non_existent_file.sp"]
    with patch.object(sys, "argv", test_args):
      with self.assertRaises(SystemExit) as cm:
        with suppress_output():
          main()
      self.assertEqual(cm.exception.code, 1)

  def test_dump_ast_subcommand_syntax_error(self):
    bad_sp = os.path.join(self.temp_dir.name, "bad_ast.sp")
    with open(bad_sp, "w", encoding="utf-8") as f:
      f.write("let x = ;\n")
    test_args = ["sapphire", "dump-ast", bad_sp]
    with patch.object(sys, "argv", test_args):
      with self.assertRaises(SystemExit) as cm:
        with suppress_output():
          main()
      self.assertEqual(cm.exception.code, 1)

  def test_check_subcommand_success(self):
    test_args = ["sapphire", "check", self.sp_file]
    with patch.object(sys, "argv", test_args):
      with suppress_output():
        main()

  def test_check_subcommand_file_not_found(self):
    test_args = ["sapphire", "check", "non_existent_file.sp"]
    with patch.object(sys, "argv", test_args):
      with self.assertRaises(SystemExit) as cm:
        with suppress_output():
          main()
      self.assertEqual(cm.exception.code, 1)

  def test_check_subcommand_syntax_error(self):
    bad_sp = os.path.join(self.temp_dir.name, "bad_syntax_check.sp")
    with open(bad_sp, "w", encoding="utf-8") as f:
      f.write("let x = ;\n")
    test_args = ["sapphire", "check", bad_sp]
    with patch.object(sys, "argv", test_args):
      with self.assertRaises(SystemExit) as cm:
        with suppress_output():
          main()
      self.assertEqual(cm.exception.code, 1)

  def test_check_subcommand_semantic_error(self):
    bad_sem = os.path.join(self.temp_dir.name, "bad_sem_check.sp")
    with open(bad_sem, "w", encoding="utf-8") as f:
      f.write("let x: int = \"hello\";\n")
    test_args = ["sapphire", "check", bad_sem]
    with patch.object(sys, "argv", test_args):
      with self.assertRaises(SystemExit) as cm:
        with suppress_output():
          main()
      self.assertEqual(cm.exception.code, 1)

  def test_check_subcommand_imported_semantic_error(self):
    import io
    from contextlib import redirect_stderr, redirect_stdout

    dep_sp = os.path.join(self.temp_dir.name, "dep_sem_err.sp")
    with open(dep_sp, "w", encoding="utf-8") as f:
      f.write("export { state }\nvar state: int = 0;\n")
    entry_sp = os.path.join(self.temp_dir.name, "entry_sem_err.sp")
    with open(entry_sp, "w", encoding="utf-8") as f:
      f.write("import dep_sem_err;\nfunc main() {}\n")

    test_args = ["sapphire", "check", entry_sp]
    stderr_buf = io.StringIO()
    with patch.object(sys, "argv", test_args):
      with redirect_stdout(io.StringIO()), redirect_stderr(stderr_buf):
        with self.assertRaises(SystemExit) as cm:
          main()
      self.assertEqual(cm.exception.code, 1)
    self.assertIn("dep_sem_err.sp", stderr_buf.getvalue())

  def test_check_subcommand_imported_syntax_error(self):
    import io
    from contextlib import redirect_stderr, redirect_stdout

    dep_sp = os.path.join(self.temp_dir.name, "dep_syn_err.sp")
    with open(dep_sp, "w", encoding="utf-8") as f:
      f.write("func broken( {\n")
    entry_sp = os.path.join(self.temp_dir.name, "entry_syn_err.sp")
    with open(entry_sp, "w", encoding="utf-8") as f:
      f.write("import dep_syn_err;\nfunc main() {}\n")

    test_args = ["sapphire", "check", entry_sp]
    stderr_buf = io.StringIO()
    with patch.object(sys, "argv", test_args):
      with redirect_stdout(io.StringIO()), redirect_stderr(stderr_buf):
        with self.assertRaises(SystemExit) as cm:
          main()
      self.assertEqual(cm.exception.code, 1)
    self.assertIn("Syntax Error:", stderr_buf.getvalue())
    self.assertIn("dep_syn_err.sp", stderr_buf.getvalue())

  def test_build_subcommand_compiler_error(self):
    bad_sp = os.path.join(self.temp_dir.name, "bad_build.sp")
    with open(bad_sp, "w", encoding="utf-8") as f:
      f.write("let x = ;\n")
    test_args = ["sapphire", "build", bad_sp]
    with patch.object(sys, "argv", test_args):
      with self.assertRaises(SystemExit) as cm:
        with suppress_output():
          main()
      self.assertEqual(cm.exception.code, 1)

  def test_run_subcommand_compiler_error(self):
    bad_sp = os.path.join(self.temp_dir.name, "bad_run.sp")
    with open(bad_sp, "w", encoding="utf-8") as f:
      f.write("let x = ;\n")
    test_args = ["sapphire", "run", bad_sp]
    with patch.object(sys, "argv", test_args):
      with self.assertRaises(SystemExit) as cm:
        with suppress_output():
          main()
      self.assertEqual(cm.exception.code, 1)

  def test_prepare_exec_env_contains_library_paths(self):
    env = _prepare_exec_env()
    self.assertIn("PYTHONPATH", env)
    self.assertIn("LUA_PATH", env)
    pythonpath = env["PYTHONPATH"]
    self.assertTrue(any("lib" in p for p in pythonpath.split(os.pathsep)))
    luapath = env["LUA_PATH"]
    self.assertTrue("?.lua" in luapath)
    self.assertNotIn(os.path.join("std", "?.lua"), luapath)

  def test_prepare_exec_env_preserves_custom_paths(self):
    custom_py = "/custom/python/path"
    custom_lua = "/custom/lua/path/?.lua"
    with patch.dict(
        os.environ, {"PYTHONPATH": custom_py, "LUA_PATH": custom_lua}
    ):
      env = _prepare_exec_env()
      self.assertIn(custom_py, env["PYTHONPATH"])
      self.assertIn(custom_lua, env["LUA_PATH"])

  def test_check_subcommand_json_success_and_error(self):
    import io
    import json
    from contextlib import redirect_stderr, redirect_stdout
    test_args = ["sapphire", "check", self.sp_file, "--json"]
    stdout_buf = io.StringIO()
    with patch.object(sys, "argv", test_args):
      with redirect_stdout(stdout_buf), redirect_stderr(io.StringIO()):
        main()
    data = json.loads(stdout_buf.getvalue())
    self.assertTrue(data["ok"])
    self.assertEqual(data["errors"], [])
    self.assertIn(self.sp_file, data["files_checked"])

    bad_sem = os.path.join(self.temp_dir.name, "bad_json_check.sp")
    with open(bad_sem, "w", encoding="utf-8") as f:
      f.write('let x: int = "hello";\n')
    test_args_err = ["sapphire", "check", bad_sem, "--json"]
    stdout_err = io.StringIO()
    with patch.object(sys, "argv", test_args_err):
      with redirect_stdout(stdout_err), redirect_stderr(io.StringIO()):
        with self.assertRaises(SystemExit) as cm:
          main()
      self.assertEqual(cm.exception.code, 1)
    err_data = json.loads(stdout_err.getvalue())
    self.assertFalse(err_data["ok"])
    self.assertEqual(len(err_data["errors"]), 1)
    self.assertEqual(err_data["errors"][0]["severity"], "error")
    self.assertEqual(err_data["errors"][0]["file"], bad_sem)

  def test_check_subcommand_target_lua_no_disk_emit(self):
    import io
    import json
    from contextlib import redirect_stderr, redirect_stdout
    lua_out = os.path.splitext(self.sp_file)[0] + ".lua"
    if os.path.exists(lua_out):
      os.remove(lua_out)
    test_args = ["sapphire", "check", self.sp_file, "-t", "lua", "--json"]
    stdout_buf = io.StringIO()
    with patch.object(sys, "argv", test_args):
      with redirect_stdout(stdout_buf), redirect_stderr(io.StringIO()):
        main()
    data = json.loads(stdout_buf.getvalue())
    self.assertTrue(data["ok"])
    self.assertFalse(os.path.exists(lua_out))

  def test_prepare_exec_env_does_not_shadow_python_stdlib(self):
    env = _prepare_exec_env()
    py_entries = [os.path.abspath(p) for p in env["PYTHONPATH"].split(os.pathsep) if p]
    std_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "../../lib/std")
    )
    self.assertNotIn(std_dir, py_entries)

  def test_check_syntax_error_printed_once_with_syntax_header(self):
    import io
    from contextlib import redirect_stderr, redirect_stdout

    bad_sp = os.path.join(self.temp_dir.name, "single_syn.sp")
    with open(bad_sp, "w", encoding="utf-8") as f:
      f.write("let x = ;\n")

    stderr_buf = io.StringIO()
    with patch.object(sys, "argv", ["sapphire", "check", bad_sp]):
      with redirect_stdout(io.StringIO()), redirect_stderr(stderr_buf):
        with self.assertRaises(SystemExit) as cm:
          main()
      self.assertEqual(cm.exception.code, 1)

    err_out = stderr_buf.getvalue()
    self.assertEqual(err_out.count("no viable alternative"), 1)
    self.assertIn("Syntax Analysis failed with errors:", err_out)
    self.assertNotIn("Semantic Analysis failed with errors:", err_out)

  def test_duplicate_export_block_handled_in_check_json_and_dump_ast(self):
    import io
    import json
    from contextlib import redirect_stderr, redirect_stdout

    dup_sp = os.path.join(self.temp_dir.name, "dup_export.sp")
    with open(dup_sp, "w", encoding="utf-8") as f:
      f.write("let a = 1;\nexport { a }\nexport { a }\n")

    stdout_buf = io.StringIO()
    with patch.object(sys, "argv", ["sapphire", "check", dup_sp, "--json"]):
      with redirect_stdout(stdout_buf), redirect_stderr(io.StringIO()):
        with self.assertRaises(SystemExit) as cm:
          main()
      self.assertEqual(cm.exception.code, 1)
    payload = json.loads(stdout_buf.getvalue())
    self.assertFalse(payload["ok"])
    self.assertEqual(payload["errors"][0]["code"], "E_SYNTAX")
    self.assertIn("Only a single export block", payload["errors"][0]["message"])

    stderr_buf = io.StringIO()
    with patch.object(sys, "argv", ["sapphire", "dump-ast", dup_sp]):
      with redirect_stdout(io.StringIO()), redirect_stderr(stderr_buf):
        with self.assertRaises(SystemExit) as cm:
          main()
      self.assertEqual(cm.exception.code, 1)
    self.assertIn("Only a single export block", stderr_buf.getvalue())

  def test_shortcut_invocation_with_leading_flags_preserves_sys_argv(self):
    orig_argv = ["sapphire", "-t", "lua", self.sp_file]
    argv_copy = list(orig_argv)
    with patch.object(sys, "argv", argv_copy):
      with patch("src.cli.sapphire._find_lua_binary", return_value="/usr/bin/lua"):
        with patch("subprocess.run") as mock_run:
          mock_run.return_value.returncode = 0
          with self.assertRaises(SystemExit) as cm:
            with suppress_output():
              main()
          self.assertEqual(cm.exception.code, 0)
          mock_run.assert_called_once()
      self.assertEqual(sys.argv, orig_argv)

  def test_version_flag(self):
    import io
    from contextlib import redirect_stdout

    for flag in ("--version", "-V"):
      buf = io.StringIO()
      with patch.object(sys, "argv", ["sapphire", flag]):
        with redirect_stdout(buf):
          with self.assertRaises(SystemExit) as cm:
            main()
      self.assertEqual(cm.exception.code, 0)
      self.assertRegex(buf.getvalue().strip(), r"^sapphire \d+\.\d+\.\d+")

  def test_build_default_output_is_concise(self):
    import io
    from contextlib import redirect_stderr, redirect_stdout

    dep_sp = os.path.join(self.temp_dir.name, "helper.sp")
    with open(dep_sp, "w", encoding="utf-8") as f:
      f.write("export { VAL }\nlet VAL: int = 7;\n")
    entry_sp = os.path.join(self.temp_dir.name, "entry.sp")
    with open(entry_sp, "w", encoding="utf-8") as f:
      f.write("import helper;\nfunc main(): int { return helper.VAL; }\n")
    out_py = os.path.join(self.temp_dir.name, "entry.py")

    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    with patch.object(sys, "argv", ["sapphire", "build", entry_sp, "-o", out_py]):
      with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
        main()

    self.assertEqual(stdout_buf.getvalue(), f"Built {out_py}\n")
    self.assertEqual(stderr_buf.getvalue(), "")

  def test_build_verbose_flag_prints_detailed_output(self):
    import io
    from contextlib import redirect_stderr, redirect_stdout

    for flag in ("--verbose", "-v"):
      lua_file = os.path.join(self.temp_dir.name, f"verbose_{flag.lstrip('-')}.lua")
      stdout_buf = io.StringIO()
      stderr_buf = io.StringIO()
      with patch.object(
          sys,
          "argv",
          ["sapphire", "build", self.sp_file, "-t", "lua", "-o", lua_file, flag],
      ):
        with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
          main()
      out = stdout_buf.getvalue()
      self.assertIn("Reading source file:", out)
      self.assertIn("Parsing program to Parse Tree...", out)
      self.assertIn("Building AST...", out)
      self.assertIn("Running Semantic Analysis & Type Checker...", out)
      self.assertIn("Transpiling to Lua", out)
      self.assertIn("Source map generated at:", out)
      self.assertIn("Compilation successful!", out)
      self.assertEqual(stderr_buf.getvalue(), "")

  def test_build_default_still_emits_warnings_to_stderr(self):
    import io
    from contextlib import redirect_stderr, redirect_stdout

    warn_sp = os.path.join(self.temp_dir.name, "warn.sp")
    with open(warn_sp, "w", encoding="utf-8") as f:
      f.write(
          "func double_lookup(m: Map<String, int>, k: String): int {\n"
          "  if m.contains(k) {\n"
          "    return m[k];\n"
          "  }\n"
          "  return 0;\n"
          "}\n"
      )
    out_py = os.path.join(self.temp_dir.name, "warn.py")

    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    with patch.object(sys, "argv", ["sapphire", "build", warn_sp, "-o", out_py]):
      with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
        main()

    self.assertEqual(stdout_buf.getvalue(), f"Built {out_py}\n")
    self.assertIn("Warnings:", stderr_buf.getvalue())

  def test_build_syntax_error_printed_once_to_stderr(self):
    import io
    from contextlib import redirect_stderr, redirect_stdout

    bad_sp = os.path.join(self.temp_dir.name, "bad_once.sp")
    with open(bad_sp, "w", encoding="utf-8") as f:
      f.write("let x = ;\n")

    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    with patch.object(sys, "argv", ["sapphire", "build", bad_sp]):
      with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
        with self.assertRaises(SystemExit) as cm:
          main()
      self.assertEqual(cm.exception.code, 1)

    self.assertEqual(stdout_buf.getvalue(), "")
    self.assertEqual(stderr_buf.getvalue().count("no viable alternative"), 1)

  def test_run_default_and_verbose_output(self):
    import io
    from contextlib import redirect_stderr, redirect_stdout

    # Default `sapphire run` suppresses transpilation noise and execution banner.
    stdout_buf = io.StringIO()
    with patch.object(sys, "argv", ["sapphire", "run", self.sp_file]):
      with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        with redirect_stdout(stdout_buf), redirect_stderr(io.StringIO()):
          with self.assertRaises(SystemExit) as cm:
            main()
        self.assertEqual(cm.exception.code, 0)
    self.assertEqual(stdout_buf.getvalue(), "")

    # `sapphire run -v` and shortcut `sapphire -v <file>` restore detailed output.
    for argv in (
        ["sapphire", "run", "-v", self.sp_file],
        ["sapphire", "run", "--verbose", self.sp_file],
        ["sapphire", "-v", self.sp_file],
    ):
      stdout_v = io.StringIO()
      with patch.object(sys, "argv", argv):
        with patch("subprocess.run") as mock_run:
          mock_run.return_value.returncode = 0
          with redirect_stdout(stdout_v), redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as cm:
              main()
          self.assertEqual(cm.exception.code, 0)
      out = stdout_v.getvalue()
      self.assertIn("Reading source file:", out)
      self.assertIn("Compilation successful!", out)
      self.assertIn("--- Executing Sapphire Program ---", out)


if __name__ == "__main__":
  unittest.main()
