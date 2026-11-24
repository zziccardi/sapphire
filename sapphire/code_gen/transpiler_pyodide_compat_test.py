"""Regression tests ensuring the transpiler works without LSP/LLVM optional deps.

The browser playground runs the Sapphire compiler in Pyodide WebAssembly where
`pygls` and `llvmlite` are not installed.
"""

import os
import subprocess
import sys
import tempfile
import unittest


class TranspilerPyodideCompatTest(unittest.TestCase):
  """Verifies transpile_file runs when pygls and llvmlite are unavailable."""

  def test_transpile_without_pygls_or_llvmlite(self):
    repo_root = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..")
    )
    with tempfile.TemporaryDirectory() as tmp_dir:
      out_py = os.path.join(tmp_dir, "out.py")
      out_lua = os.path.join(tmp_dir, "out.lua")
      script = (
          "import sys\n"
          "sys.modules['pygls'] = None\n"
          "sys.modules['pygls.uris'] = None\n"
          "sys.modules['llvmlite'] = None\n"
          "from sapphire.code_gen.transpiler import transpile_file\n"
          f"transpile_file('samples/overview.sp', {out_py!r}, target='python', "
          "quiet=True, raise_on_error=True, use_runtime_module=False)\n"
          f"transpile_file('samples/overview.sp', {out_lua!r}, target='lua', "
          "quiet=True, raise_on_error=True, use_runtime_module=False)\n"
      )
      proc = subprocess.run(
          [sys.executable, "-c", script],
          cwd=repo_root,
          capture_output=True,
          text=True,
          check=False,
      )
      self.assertEqual(
          proc.returncode,
          0,
          f"Transpiler failed without pygls/llvmlite:\n{proc.stderr}",
      )
      self.assertTrue(os.path.exists(out_py))
      self.assertTrue(os.path.exists(out_lua))


if __name__ == "__main__":
  unittest.main()
