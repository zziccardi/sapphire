"""Unit tests for bounded module path resolution in module_resolver.py."""

import os
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from src.semantics.module_resolver import (
    find_sapphire_lib_dir,
    resolve_module_path,
)


class ModuleResolverTest(unittest.TestCase):
  """Verifies bounded module resolution and library path discovery."""

  def setUp(self):
    self.temp_dir = tempfile.TemporaryDirectory()
    self.base_dir = self.temp_dir.name
    # Create parent and nested child directories:
    # <base_dir>/
    #   parent_mod.sp
    #   child/
    #     main.sp
    #     child_mod.sp
    self.child_dir = os.path.join(self.base_dir, "child")
    os.makedirs(self.child_dir, exist_ok=True)

    self.parent_mod = os.path.join(self.base_dir, "parent_mod.sp")
    with open(self.parent_mod, "w", encoding="utf-8") as f:
      f.write("let parent_val: int = 100;\n")

    self.main_file = os.path.join(self.child_dir, "main.sp")
    with open(self.main_file, "w", encoding="utf-8") as f:
      f.write("let main_val: int = 1;\n")

    self.child_mod = os.path.join(self.child_dir, "child_mod.sp")
    with open(self.child_mod, "w", encoding="utf-8") as f:
      f.write("let child_val: int = 2;\n")

  def tearDown(self):
    self.temp_dir.cleanup()

  def test_resolves_in_source_directory(self):
    """Verifies sibling modules in source directory resolve successfully."""
    resolved = resolve_module_path(
        "child_mod", source_file_path=self.main_file
    )
    self.assertIsNotNone(resolved)
    self.assertEqual(os.path.abspath(resolved), os.path.abspath(self.child_mod))

  def test_does_not_traverse_to_parent_directory(self):
    """Verifies module resolution does not climb to parent directories."""
    resolved = resolve_module_path(
        "parent_mod", source_file_path=self.main_file
    )
    # parent_mod is only in the parent directory, so it should not be found
    self.assertIsNone(resolved)

  def test_resolves_built_in_standard_library(self):
    """Verifies standard library modules in lib/std are resolvable."""
    resolved = resolve_module_path("testing", source_file_path=self.main_file)
    self.assertIsNotNone(resolved)
    self.assertTrue(resolved.endswith("testing.sp"))

  def test_resolves_package_qualified_import_from_subdirectory(self):
    """Verifies package-qualified imports resolve from subdirectories."""
    sub_dir = os.path.join(self.child_dir, "systems")
    os.makedirs(sub_dir, exist_ok=True)
    nested_file = os.path.join(sub_dir, "combat.sp")
    with open(nested_file, "w", encoding="utf-8") as f:
      f.write("import child.child_mod;\n")

    resolved = resolve_module_path(
        "child.child_mod", source_file_path=nested_file
    )
    self.assertIsNotNone(resolved)
    self.assertEqual(os.path.abspath(resolved), os.path.abspath(self.child_mod))

  def test_find_sapphire_lib_dir_default(self):
    """Verifies that default lib directory is discovered in workspace."""
    lib_dir = find_sapphire_lib_dir()
    self.assertIsNotNone(lib_dir)
    self.assertTrue(os.path.isdir(lib_dir))
    self.assertTrue(os.path.exists(os.path.join(lib_dir, "std", "testing.sp")))

  def test_find_sapphire_lib_dir_env_override(self):
    """Verifies SAPPHIRE_LIB_DIR environment variable takes precedence."""
    custom_lib = os.path.join(self.base_dir, "custom_lib")
    os.makedirs(custom_lib, exist_ok=True)
    with patch.dict(os.environ, {"SAPPHIRE_LIB_DIR": custom_lib}):
      lib_dir = find_sapphire_lib_dir()
      self.assertEqual(lib_dir, os.path.abspath(custom_lib))

  def test_find_sapphire_lib_dir_fallback_prefix(self):
    """Verifies fallback to sys.prefix paths when local repo lib is absent."""
    prefix_lib = os.path.join(self.base_dir, "prefix_lib")
    os.makedirs(prefix_lib, exist_ok=True)
    with patch("os.path.isdir") as mock_isdir:
      def isdir_side_effect(path):
        if path == os.path.join(sys.prefix, "lib", "sapphire"):
          return True
        return False
      mock_isdir.side_effect = isdir_side_effect
      with patch.dict(os.environ, {}, clear=True):
        with patch("importlib.util.find_spec", return_value=None):
          lib_dir = find_sapphire_lib_dir()
          self.assertEqual(
              lib_dir,
              os.path.abspath(os.path.join(sys.prefix, "lib", "sapphire")),
          )

  def test_resolves_std_qualified_imports(self):
    """Verifies imports qualified with 'std.' resolve correctly."""
    resolved = resolve_module_path(
        "std.testing", source_file_path=self.main_file
    )
    self.assertIsNotNone(resolved)
    self.assertTrue(resolved.endswith(os.path.join("std", "testing.sp")))

  def test_resolves_lib_prefixed_imports(self):
    """Verifies imports qualified with 'lib.' resolve correctly."""
    resolved = resolve_module_path(
        "lib.love2d.enums", source_file_path=self.main_file
    )
    self.assertIsNotNone(resolved)
    self.assertTrue(resolved.endswith(os.path.join("love2d", "enums.sp")))

  def test_find_sapphire_lib_dir_importlib_origin(self):
    """Verifies importlib spec.origin discovery when repo lib is absent."""
    fake_lib = os.path.join(self.base_dir, "site", "lib")
    fake_std_init = os.path.join(fake_lib, "std", "__init__.py")
    os.makedirs(os.path.dirname(fake_std_init), exist_ok=True)
    mock_spec = MagicMock()
    mock_spec.origin = fake_std_init

    def isdir_side_effect(path):
      return path == fake_lib

    with patch("os.path.isdir", side_effect=isdir_side_effect):
      with patch.dict(os.environ, {}, clear=True):
        with patch("importlib.util.find_spec", return_value=mock_spec):
          self.assertEqual(find_sapphire_lib_dir(), os.path.abspath(fake_lib))

  def test_find_sapphire_lib_dir_importlib_namespace(self):
    """Verifies importlib submodule_search_locations discovery."""
    fake_lib = os.path.join(self.base_dir, "ns", "lib")
    fake_std_dir = os.path.join(fake_lib, "std")
    os.makedirs(fake_std_dir, exist_ok=True)
    mock_spec = MagicMock()
    mock_spec.origin = None
    mock_spec.submodule_search_locations = [fake_std_dir]

    def isdir_side_effect(path):
      return path == fake_lib

    with patch("os.path.isdir", side_effect=isdir_side_effect):
      with patch.dict(os.environ, {}, clear=True):
        with patch("importlib.util.find_spec", return_value=mock_spec):
          self.assertEqual(find_sapphire_lib_dir(), os.path.abspath(fake_lib))

  def test_find_sapphire_lib_dir_none_when_unavailable(self):
    """Verifies None is returned when no library directory exists."""
    with patch("os.path.isdir", return_value=False):
      with patch.dict(os.environ, {}, clear=True):
        with patch(
            "importlib.util.find_spec", side_effect=ImportError("no mod")
        ):
          self.assertIsNone(find_sapphire_lib_dir())

  def test_resolve_module_path_adds_lib_parent_from_different_cwd(self):
    """Verifies lib_parent is added to search_dirs when cwd differs."""
    with patch("os.getcwd", return_value=self.base_dir):
      resolved = resolve_module_path(
          "lib.std.math", source_file_path=self.main_file
      )
      self.assertIsNotNone(resolved)
      self.assertTrue(resolved.endswith(os.path.join("std", "math.sp")))


if __name__ == "__main__":
  unittest.main()
