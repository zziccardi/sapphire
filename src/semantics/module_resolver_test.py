"""Unit tests for bounded module path resolution in src/semantics/module_resolver.py."""

import os
import tempfile
import unittest

from src.semantics.module_resolver import resolve_module_path


class ModuleResolverTest(unittest.TestCase):
  """Verifies that module resolution is strictly bounded and does not crawl up parent paths."""

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
    """Verifies that sibling modules in the source file's directory resolve successfully."""
    resolved = resolve_module_path("child_mod", source_file_path=self.main_file)
    self.assertIsNotNone(resolved)
    self.assertEqual(os.path.abspath(resolved), os.path.abspath(self.child_mod))

  def test_does_not_traverse_to_parent_directory(self):
    """Verifies that module resolution does NOT climb to parent directories above the source root."""
    resolved = resolve_module_path("parent_mod", source_file_path=self.main_file)
    # parent_mod is only in the parent directory, so it should not be found
    self.assertIsNone(resolved)

  def test_resolves_built_in_standard_library(self):
    """Verifies that standard library modules in lib/std are still resolvable."""
    resolved = resolve_module_path("testing", source_file_path=self.main_file)
    self.assertIsNotNone(resolved)
    self.assertTrue(resolved.endswith("testing.sp"))

  def test_resolves_package_qualified_import_from_subdirectory(self):
    """Verifies that package-qualified imports (e.g. 'child.child_mod') resolve from nested subdirectories."""
    sub_dir = os.path.join(self.child_dir, "systems")
    os.makedirs(sub_dir, exist_ok=True)
    nested_file = os.path.join(sub_dir, "combat.sp")
    with open(nested_file, "w", encoding="utf-8") as f:
      f.write("import child.child_mod;\n")

    resolved = resolve_module_path("child.child_mod", source_file_path=nested_file)
    self.assertIsNotNone(resolved)
    self.assertEqual(os.path.abspath(resolved), os.path.abspath(self.child_mod))


if __name__ == "__main__":
  unittest.main()
