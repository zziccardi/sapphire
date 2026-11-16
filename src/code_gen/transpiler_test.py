"""Tests for transpiler driver hygiene (stdlib stub protection and -o isolation)."""

import os
import tempfile
import unittest

from src.code_gen.transpiler import is_stdlib_stub, transpile_file
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
    with open(utf8_lua, "r", encoding="utf-8") as f:
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

    with open(utf8_lua, "r", encoding="utf-8") as f:
      after = f.read()
    self.assertEqual(before, after)

  def test_isolated_output_does_not_write_in_place_or_touch_prebuilt_lib(self):
    """Verifies -o outside source dir isolates transitive outputs."""
    lib_dir = find_sapphire_lib_dir()
    self.assertIsNotNone(lib_dir)
    enums_lua = os.path.join(lib_dir, "love2d", "enums.lua")
    mtime_before = os.path.getmtime(enums_lua)

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
      self.assertEqual(mtime_before, os.path.getmtime(enums_lua))


if __name__ == "__main__":
  unittest.main()
