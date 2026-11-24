"""Golden snapshot tests for Sapphire CLI diagnostics and source-map demangling.

Fixtures live in `testing/diagnostics/*.sp.fixture` (using `.sp.fixture` rather
than `.sp` so `sapphire test` workspace discovery does not treat intentionally
failing diagnostic fixtures as passing test suites).

Run with `UPDATE_GOLDENS=1` to regenerate `.expected` files after intentional
diagnostic formatting changes:

    UPDATE_GOLDENS=1 pipenv run python -m unittest src/cli/diagnostics_golden_test.py
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

_REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)
_FIXTURE_DIR = os.path.join(_REPO_ROOT, "testing", "diagnostics")
_UPDATE_GOLDENS = os.environ.get("UPDATE_GOLDENS") == "1"


def _normalize_output(text: str, tmp_dir: str) -> str:
  """Normalizes temp paths and elapsed durations for deterministic snapshot diffs."""
  norm = text.replace(os.path.realpath(tmp_dir), "<TMP>")
  norm = norm.replace(tmp_dir, "<TMP>")
  norm = norm.replace(_REPO_ROOT, "<ROOT>")
  norm = re.sub(r" in \d+\.\d+s\b", " in <TIME>", norm)
  # Strip trailing whitespace on each line while preserving trailing newline
  lines = [line.rstrip() for line in norm.splitlines()]
  return "\n".join(lines) + ("\n" if lines else "")


class TestDiagnosticsGolden(unittest.TestCase):
  """Verifies exact CLI diagnostic formatting, spans, exit codes, and source maps."""

  def _run_cli_on_fixture(
      self, fixture_name: str, cli_args: list[str]
  ) -> tuple[int, str]:
    src_fixture = os.path.join(_FIXTURE_DIR, f"{fixture_name}.sp.fixture")
    self.assertTrue(
        os.path.isfile(src_fixture), f"Missing fixture: {src_fixture}"
    )

    with tempfile.TemporaryDirectory() as tmp_dir:
      sp_name = f"{fixture_name}.sp"
      sp_path = os.path.join(tmp_dir, sp_name)
      shutil.copyfile(src_fixture, sp_path)

      env = os.environ.copy()
      env["PYTHONPATH"] = _REPO_ROOT + (
          os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
      )
      cmd = [sys.executable, "-m", "sapphire.cli.sapphire"] + [
          sp_name if a == "<FILE>" else a for a in cli_args
      ]
      proc = subprocess.run(
          cmd,
          cwd=tmp_dir,
          env=env,
          capture_output=True,
          text=True,
          timeout=30,
      )
      combined = []
      combined.append(f"EXIT_CODE: {proc.returncode}")
      if proc.stdout:
        combined.append("--- STDOUT ---")
        combined.append(_normalize_output(proc.stdout, tmp_dir).rstrip("\n"))
      if proc.stderr:
        combined.append("--- STDERR ---")
        combined.append(_normalize_output(proc.stderr, tmp_dir).rstrip("\n"))
      return proc.returncode, "\n".join(combined) + "\n"

  def _assert_golden(
      self,
      fixture_name: str,
      golden_name: str,
      cli_args: list[str],
      expected_exit_code: int,
  ) -> None:
    rc, actual = self._run_cli_on_fixture(fixture_name, cli_args)
    self.assertEqual(rc, expected_exit_code, f"Unexpected exit code:\n{actual}")

    golden_path = os.path.join(_FIXTURE_DIR, f"{golden_name}.expected")
    if _UPDATE_GOLDENS:
      with open(golden_path, "w", encoding="utf-8") as f:
        f.write(actual)
      return

    self.assertTrue(
        os.path.isfile(golden_path),
        f"Missing golden snapshot {golden_path}. Re-run with UPDATE_GOLDENS=1.",
    )
    with open(golden_path, encoding="utf-8") as f:
      expected = f.read()
    self.assertEqual(
        actual,
        expected,
        f"Golden snapshot mismatch for {golden_name}.expected.\n"
        f"If intentional, re-run with UPDATE_GOLDENS=1.",
    )

  def test_golden_syntax_error(self):
    """Locks down syntax error message, caret span, and exit code."""
    self._assert_golden(
        "syntax_error",
        "syntax_error",
        ["check", "<FILE>"],
        expected_exit_code=1,
    )

  def test_golden_multi_type_error_recovery(self):
    """Locks down multi-error type checking recovery and exact line/column spans."""
    self._assert_golden(
        "type_error_multi",
        "type_error_multi",
        ["check", "<FILE>"],
        expected_exit_code=1,
    )

  def test_golden_lint_warning(self):
    """Locks down semantic lint warning formatting while exiting 0."""
    self._assert_golden(
        "lint_warning",
        "lint_warning",
        ["check", "<FILE>"],
        expected_exit_code=0,
    )

  def test_golden_runtime_failure_python(self):
    """Locks down Python test runner source-map demangled failure output."""
    self._assert_golden(
        "runtime_failure",
        "runtime_failure_python",
        ["test", "<FILE>"],
        expected_exit_code=1,
    )

  def test_golden_runtime_failure_lua(self):
    """Locks down Lua 5.1 test runner source-map demangled failure output."""
    if not (shutil.which("lua") or shutil.which("lua5.1") or shutil.which("luajit")):
      self.skipTest("Lua runtime not found on PATH")
    self._assert_golden(
        "runtime_failure",
        "runtime_failure_lua",
        ["test", "<FILE>", "-t", "lua"],
        expected_exit_code=1,
    )


if __name__ == "__main__":
  unittest.main()
