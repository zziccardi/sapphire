"""Automated compilation test suite for all sample programs in samples/.

This module dynamically discovers all Sapphire (.sp) source files in the
samples/ directory and verifies that each compiles cleanly across both primary
target backends (Python and Lua 5.1).

Compilation executes the complete pipeline:
  1. Lexical analysis & parsing (syntax checking)
  2. AST construction
  3. Semantic analysis & type checking
  4. Module import resolution
  5. Target code generation (Python / Lua 5.1)

All output is generated into isolated temporary directories so that the
repository workspace remains clean.
"""

import os
import pathlib
import tempfile
import unittest

from src.code_gen.transpiler import transpile_file
from src.code_gen.transpiler_registry import TranspilerRegistry

_REPO_ROOT = pathlib.Path(__file__).parent.parent.parent
_SAMPLES_DIR = _REPO_ROOT / "samples"
_TARGETS = ["python", "lua"]


class TestSamplesCompilation(unittest.TestCase):
  """Ensures every .sp program in samples/ compiles cleanly across backends."""

  def _assert_compiles(self, sample_path: pathlib.Path, target: str):
    """Compiles a single sample file into a temporary output file."""
    self.assertTrue(sample_path.exists(), f"Sample file not found: {sample_path}")
    ext = TranspilerRegistry.get(target).default_extension

    with tempfile.TemporaryDirectory() as tmp_dir:
      out_file = os.path.join(tmp_dir, f"{sample_path.stem}{ext}")
      transpile_file(
          str(sample_path),
          output_file=out_file,
          target=target,
          quiet=True,
          raise_on_error=True,
      )
      self.assertTrue(os.path.exists(out_file), f"Output file was not generated: {out_file}")
      self.assertGreater(os.path.getsize(out_file), 0, f"Generated empty output file: {out_file}")

  def test_missing_sample_path_raises(self):
    """Verifies that attempting to compile a nonexistent file fails."""
    nonexistent = _SAMPLES_DIR / "nonexistent_sample_xyz.sp"
    with self.assertRaises(AssertionError):
      self._assert_compiles(nonexistent, "python")

  def test_syntax_error_in_sample_fails(self):
    """Verifies that syntax errors prevent compilation."""
    from src.common.errors import SapphireSyntaxError
    with tempfile.TemporaryDirectory() as tmp_dir:
      bad_sp = pathlib.Path(tmp_dir) / "broken.sp"
      bad_sp.write_text("let x: int = ;\n", encoding="utf-8")
      with self.assertRaises(SapphireSyntaxError):
        self._assert_compiles(bad_sp, "python")

  def test_semantic_error_in_sample_fails(self):
    """Verifies that semantic type errors prevent compilation."""
    from src.common.errors import SemanticError
    with tempfile.TemporaryDirectory() as tmp_dir:
      bad_sp = pathlib.Path(tmp_dir) / "type_mismatch.sp"
      bad_sp.write_text("let x: int = \"hello\";\n", encoding="utf-8")
      with self.assertRaises(SemanticError):
        self._assert_compiles(bad_sp, "python")


def _register_sample_tests():
  """Dynamically attach individual test methods for every sample and target."""
  if not _SAMPLES_DIR.exists():
    return

  sample_files = sorted(_SAMPLES_DIR.glob("**/*.sp"))
  for sample in sample_files:
    rel_stem = sample.relative_to(_SAMPLES_DIR).with_suffix("").as_posix().replace("/", "_").replace(".", "_")
    for target in _TARGETS:
      method_name = f"test_compile_{rel_stem}_{target}"

      def make_test(s=sample, t=target):
        def test_method(self):
          self._assert_compiles(s, t)
        return test_method

      test_fn = make_test()
      test_fn.__name__ = method_name
      test_fn.__doc__ = f"Verifies samples/{sample.name} compiles to {target}"
      setattr(TestSamplesCompilation, method_name, test_fn)


_register_sample_tests()


if __name__ == "__main__":
  unittest.main()
