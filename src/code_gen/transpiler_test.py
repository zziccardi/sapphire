"""Tests for transpiler driver hygiene (stdlib stub protection and -o isolation)."""

import os
import tempfile
import unittest
from unittest.mock import patch

from src.code_gen.transpiler import (
    _is_prebuilt_lib_module,
    is_stdlib_stub,
    transpile_file,
)
from src.semantics.module_resolver import find_sapphire_lib_dir


class TranspilerHygieneTest(unittest.TestCase):
  """Tests stdlib stub protection and isolated output builds."""

  def test_is_stdlib_stub_detects_std_and_lib_std_paths(self):
    """Verifies is_stdlib_stub matches std.* and lib/std/*.sp stubs."""
    self.assertTrue(is_stdlib_stub("std.utf8"))
    self.assertTrue(is_stdlib_stub("std.math"))

    lib_dir = find_sapphire_lib_dir()
    self.assertIsNotNone(lib_dir)
    utf8_sp = os.path.join(lib_dir, "std", "utf8.sp")
    graphics_sp = os.path.join(lib_dir, "love2d", "graphics.sp")
    self.assertTrue(is_stdlib_stub("lib.std.utf8", utf8_sp))
    self.assertFalse(is_stdlib_stub("lib.love2d.graphics", graphics_sp))
    self.assertFalse(is_stdlib_stub("my_pkg.helper", "/tmp/helper.sp"))

  def test_lib_std_stub_not_overwritten_on_transpile(self):
    """Verifies importing lib.std.utf8 never overwrites lib/std/utf8.lua."""
    lib_dir = find_sapphire_lib_dir()
    self.assertIsNotNone(lib_dir)
    utf8_lua = os.path.join(lib_dir, "std", "utf8.lua")
    with open(utf8_lua, encoding="utf-8") as f:
      before = f.read()

    with tempfile.TemporaryDirectory() as tmpdir:
      main_sp = os.path.join(tmpdir, "main.sp")
      with open(main_sp, "w", encoding="utf-8") as f:
        f.write(
            "import lib.std.utf8;\n"
            "func main(): int? {\n"
            '  return utf8.size("hi");\n'
            "}\n"
        )
      out_lua = os.path.join(tmpdir, "main.lua")
      transpile_file(main_sp, output_file=out_lua, target="lua", quiet=True)
      self.assertTrue(os.path.exists(out_lua))

    with open(utf8_lua, encoding="utf-8") as f:
      after = f.read()
    self.assertEqual(before, after)

  def test_isolated_output_does_not_write_in_place_or_touch_prebuilt_lib(self):
    """Verifies -o outside source dir isolates transitive outputs."""
    lib_dir = find_sapphire_lib_dir()
    self.assertIsNotNone(lib_dir)
    enums_lua = os.path.join(lib_dir, "love2d", "enums.lua")
    had_enums_lua = os.path.exists(enums_lua)
    mtime_before = os.path.getmtime(enums_lua) if had_enums_lua else None

    with tempfile.TemporaryDirectory() as root:
      src_dir = os.path.join(root, "src")
      out_dir = os.path.join(root, "out")
      os.makedirs(src_dir)
      os.makedirs(out_dir)

      helper_sp = os.path.join(src_dir, "helper.sp")
      with open(helper_sp, "w", encoding="utf-8") as f:
        f.write("export { val } let val = 7;\n")

      main_sp = os.path.join(src_dir, "main.sp")
      with open(main_sp, "w", encoding="utf-8") as f:
        f.write(
            "import helper;\n"
            "import lib.love2d.enums;\n"
            "func main(): int {\n"
            "  let k = enums.KeyCode.Escape;\n"
            "  return helper.val;\n"
            "}\n"
        )

      out_lua = os.path.join(out_dir, "main.lua")
      transpile_file(main_sp, output_file=out_lua, target="lua", quiet=True)

      self.assertTrue(os.path.exists(out_lua))
      self.assertTrue(os.path.exists(os.path.join(out_dir, "helper.lua")))
      self.assertFalse(os.path.exists(os.path.join(src_dir, "helper.lua")))
      if had_enums_lua:
        self.assertEqual(mtime_before, os.path.getmtime(enums_lua))
      else:
        self.assertFalse(os.path.exists(enums_lua))
        self.assertTrue(
            os.path.exists(os.path.join(out_dir, "lib", "love2d", "enums.lua"))
        )

  def test_transpile_file_visited_returns_default_output_path(self):
    with tempfile.TemporaryDirectory() as tmpdir:
      src = os.path.join(tmpdir, "dup.sp")
      with open(src, "w", encoding="utf-8") as f:
        f.write("let x = 1;\n")
      visited = {os.path.abspath(src)}
      out = transpile_file(src, output_file=None, target="python", visited=visited, quiet=True)
      self.assertEqual(out, os.path.join(tmpdir, "dup.py"))

  def test_transpile_file_llvm_target_instantiation(self):
    import src.code_gen.llvm_transpiler  # noqa: F401 — registers LLVM target

    with tempfile.TemporaryDirectory() as tmpdir:
      src = os.path.join(tmpdir, "add.sp")
      out_ll = os.path.join(tmpdir, "add.ll")
      with open(src, "w", encoding="utf-8") as f:
        f.write("func add(a: int, b: int): int { return a + b; }\n")
      res = transpile_file(src, output_file=out_ll, target="llvm", quiet=True)
      self.assertEqual(res, out_ll)
      self.assertTrue(os.path.exists(out_ll))
      with open(out_ll, encoding="utf-8") as f:
        self.assertIn('define i64 @"add"', f.read())

  def test_is_prebuilt_lib_module_checks_mtime_freshness(self):
    """Verifies stale prebuilt lib/ outputs are not treated as reusable."""
    with tempfile.TemporaryDirectory() as fake_lib:
      pkg_dir = os.path.join(fake_lib, "love2d")
      os.makedirs(pkg_dir)
      src_sp = os.path.join(pkg_dir, "sample.sp")
      out_lua = os.path.join(pkg_dir, "sample.lua")
      with open(src_sp, "w", encoding="utf-8") as f:
        f.write("export { x } let x = 1;\n")

      with patch(
          "src.semantics.module_resolver.find_sapphire_lib_dir",
          return_value=fake_lib,
      ):
        self.assertFalse(_is_prebuilt_lib_module(src_sp, ".lua"))

        with open(out_lua, "w", encoding="utf-8") as f:
          f.write("return { x = 1 }\n")
        os.utime(src_sp, (100, 100))
        os.utime(out_lua, (200, 200))
        self.assertTrue(_is_prebuilt_lib_module(src_sp, ".lua"))

        # Mark source newer than prebuilt output -> stale.
        os.utime(src_sp, (300, 300))
        self.assertFalse(_is_prebuilt_lib_module(src_sp, ".lua"))

  def test_isolated_output_retranspiles_stale_prebuilt_lib_module(self):
    """Verifies isolated builds transpile stale lib/ modules into out_dir."""
    with tempfile.TemporaryDirectory() as root:
      fake_lib = os.path.join(root, "lib")
      pkg_dir = os.path.join(fake_lib, "love2d")
      src_dir = os.path.join(root, "src")
      out_dir = os.path.join(root, "out")
      os.makedirs(pkg_dir)
      os.makedirs(src_dir)
      os.makedirs(out_dir)

      mod_sp = os.path.join(pkg_dir, "freshmod.sp")
      stale_lua = os.path.join(pkg_dir, "freshmod.lua")
      with open(mod_sp, "w", encoding="utf-8") as f:
        f.write("export { ANSWER } let ANSWER = 42;\n")
      with open(stale_lua, "w", encoding="utf-8") as f:
        f.write("-- stale output\nreturn {}\n")
      os.utime(stale_lua, (100, 100))
      os.utime(mod_sp, (200, 200))

      main_sp = os.path.join(src_dir, "main.sp")
      with open(main_sp, "w", encoding="utf-8") as f:
        f.write(
            "import lib.love2d.freshmod;\n"
            "func main(): int { return freshmod.ANSWER; }\n"
        )

      with patch(
          "src.semantics.module_resolver.find_sapphire_lib_dir",
          return_value=fake_lib,
      ):
        out_lua = os.path.join(out_dir, "main.lua")
        transpile_file(main_sp, output_file=out_lua, target="lua", quiet=True)

      isolated_mod = os.path.join(out_dir, "lib", "love2d", "freshmod.lua")
      self.assertTrue(os.path.exists(isolated_mod))
      with open(isolated_mod, encoding="utf-8") as f:
        self.assertIn("42", f.read())
      # Original stale file under lib/ is left untouched.
      with open(stale_lua, encoding="utf-8") as f:
        self.assertIn("-- stale output", f.read())

  def test_isolated_python_lib_extend_path_shadows_stale_regular_package(self):
    """Verifies isolated Python lib/ writes extend_path __init__.py markers."""
    import importlib.util
    import sys

    with tempfile.TemporaryDirectory() as root:
      fake_lib = os.path.join(root, "lib")
      pkg_dir = os.path.join(fake_lib, "love2d")
      std_dir = os.path.join(fake_lib, "std")
      src_dir = os.path.join(root, "src")
      out_dir = os.path.join(root, "out")
      os.makedirs(pkg_dir)
      os.makedirs(std_dir)
      os.makedirs(src_dir)
      os.makedirs(out_dir)

      # Regular package markers in fake_lib mimicking Sapphire's lib/.
      with open(os.path.join(fake_lib, "__init__.py"), "w", encoding="utf-8") as f:
        f.write("# pkg\n")
      with open(os.path.join(pkg_dir, "__init__.py"), "w", encoding="utf-8") as f:
        f.write("# love2d pkg\n")
      with open(os.path.join(std_dir, "__init__.py"), "w", encoding="utf-8") as f:
        f.write("# std pkg\n")
      with open(os.path.join(std_dir, "stubmod.py"), "w", encoding="utf-8") as f:
        f.write("STD_MARKER = 99\n")

      mod_sp = os.path.join(pkg_dir, "pyfresh.sp")
      stale_py = os.path.join(pkg_dir, "pyfresh.py")
      with open(mod_sp, "w", encoding="utf-8") as f:
        f.write("export { ANSWER } let ANSWER = 123;\n")
      with open(stale_py, "w", encoding="utf-8") as f:
        f.write("ANSWER = 0\n")
      os.utime(stale_py, (100, 100))
      os.utime(mod_sp, (200, 200))

      main_sp = os.path.join(src_dir, "main.sp")
      with open(main_sp, "w", encoding="utf-8") as f:
        f.write(
            "import lib.love2d.pyfresh;\n"
            "func main(): int { return pyfresh.ANSWER; }\n"
        )

      with patch(
          "src.semantics.module_resolver.find_sapphire_lib_dir",
          return_value=fake_lib,
      ):
        out_py = os.path.join(out_dir, "main.py")
        transpile_file(main_sp, output_file=out_py, target="python", quiet=True)

      self.assertTrue(os.path.exists(os.path.join(out_dir, "lib", "__init__.py")))
      self.assertTrue(
          os.path.exists(os.path.join(out_dir, "lib", "love2d", "__init__.py"))
      )

      orig_path = list(sys.path)
      saved_lib = {
          k: sys.modules.pop(k)
          for k in list(sys.modules.keys())
          if k == "lib" or k.startswith("lib.")
      }
      sys.path.insert(0, root)
      sys.path.insert(0, out_dir)
      try:
        spec = importlib.util.spec_from_file_location("isolated_main_test", out_py)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        # Fresh transpiled module wins over stale regular package.
        self.assertEqual(mod.main(), 123)
        # Hand-written stdlib submodule still resolves via pkgutil.extend_path.
        import lib.std.stubmod as stubmod
        self.assertEqual(stubmod.STD_MARKER, 99)
      finally:
        sys.path[:] = orig_path
        for k in [
            k for k in list(sys.modules.keys()) if k == "lib" or k.startswith("lib.")
        ]:
          sys.modules.pop(k, None)
        sys.modules.update(saved_lib)

  def test_transpile_file_verbose_controls_stdout(self):
    """Verifies transpile_file only emits phase logs when verbose=True and not quiet."""
    import io
    from contextlib import redirect_stdout

    with tempfile.TemporaryDirectory() as tmpdir:
      src = os.path.join(tmpdir, "sample.sp")
      with open(src, "w", encoding="utf-8") as f:
        f.write("let x: int = 1;\n")

      # Default (verbose=False) produces no stdout.
      buf_default = io.StringIO()
      with redirect_stdout(buf_default):
        transpile_file(src, os.path.join(tmpdir, "default.py"), target="python")
      self.assertEqual(buf_default.getvalue(), "")

      # verbose=True emits detailed progress to stdout.
      buf_verbose = io.StringIO()
      with redirect_stdout(buf_verbose):
        transpile_file(
            src, os.path.join(tmpdir, "verbose.py"), target="python", verbose=True
        )
      self.assertIn("Reading source file:", buf_verbose.getvalue())
      self.assertIn("Compilation successful!", buf_verbose.getvalue())

      # quiet=True overrides verbose=True.
      buf_quiet = io.StringIO()
      with redirect_stdout(buf_quiet):
        transpile_file(
            src,
            os.path.join(tmpdir, "quiet.py"),
            target="python",
            quiet=True,
            verbose=True,
        )
      self.assertEqual(buf_quiet.getvalue(), "")


if __name__ == "__main__":
  unittest.main()
