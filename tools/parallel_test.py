"""Zero-dependency parallel unittest runner for Sapphire (`pipenv run test-fast`).

Discovers `*_test.py` modules under `src/` and `tools/vscode-extension/scripts/`
and executes each test module in an isolated worker process via
`concurrent.futures.ProcessPoolExecutor`.
"""

import argparse
import os
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import List, Tuple


_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_SEARCH_ROOTS = ("sapphire", os.path.join("tools", "vscode-extension", "scripts"))


def _discover_test_files() -> List[str]:
  files: List[str] = []
  for rel_root in _SEARCH_ROOTS:
    abs_root = os.path.join(_REPO_ROOT, rel_root)
    if not os.path.isdir(abs_root):
      continue
    for root, dirs, names in os.walk(abs_root):
      dirs[:] = [d for d in dirs if d not in ("__pycache__", "gen")]
      for name in sorted(names):
        if name.endswith("_test.py"):
          files.append(os.path.relpath(os.path.join(root, name), _REPO_ROOT))
  files.sort()
  return files


def _run_test_file(rel_path: str) -> Tuple[str, int, str, float]:
  t0 = time.monotonic()
  env = os.environ.copy()
  env["PYTHONPATH"] = _REPO_ROOT + (
      os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
  )
  proc = subprocess.run(
      [sys.executable, "-m", "unittest", rel_path],
      cwd=_REPO_ROOT,
      env=env,
      capture_output=True,
      text=True,
  )
  elapsed = time.monotonic() - t0
  output = (proc.stdout + proc.stderr).strip()
  return rel_path, proc.returncode, output, elapsed


def main() -> int:
  parser = argparse.ArgumentParser(
      description="Run Sapphire Python unit test modules in parallel."
  )
  parser.add_argument(
      "-j",
      "--jobs",
      type=int,
      default=max(1, min(os.cpu_count() or 2, 8)),
      help="Maximum number of parallel worker processes.",
  )
  args = parser.parse_args()

  test_files = _discover_test_files()
  t_start = time.monotonic()
  failures: List[Tuple[str, str]] = []
  passed_modules = 0

  with ProcessPoolExecutor(max_workers=args.jobs) as pool:
    futures = {pool.submit(_run_test_file, tf): tf for tf in test_files}
    for fut in as_completed(futures):
      rel_path, rc, output, elapsed = fut.result()
      if rc == 0:
        passed_modules += 1
        print(f"[ PASS ] {rel_path} ({elapsed:.2f}s)", flush=True)
      else:
        failures.append((rel_path, output))
        print(f"[ FAIL ] {rel_path} ({elapsed:.2f}s)", flush=True)

  total_elapsed = time.monotonic() - t_start
  if failures:
    print("\n" + "=" * 70)
    for rel_path, output in sorted(failures):
      print(f"\n--- FAILURE: {rel_path} ---\n{output}")
    print("=" * 70)
    print(
        f"\nParallel test result: {passed_modules} passed, {len(failures)} failed"
        f" ({len(test_files)} modules in {total_elapsed:.2f}s)"
    )
    return 1

  print(
      f"\nParallel test result: {passed_modules} passed, 0 failed"
      f" ({len(test_files)} modules in {total_elapsed:.2f}s)"
  )
  return 0


if __name__ == "__main__":
  sys.exit(main())
