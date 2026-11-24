"""Zero-dependency Lua 5.1 line-coverage reporter for Sapphire's `lib/std/*.lua`.

Uses Lua 5.1's built-in `LUA_INIT=@<hook.lua>` and `debug.sethook(..., "l")`
to record every executed line in `lib/std/*.lua` while running
`sapphire test -t lua`, then prints a per-file coverage summary.
"""

import argparse
import os
import re
import subprocess
import sys
import tempfile
from typing import Dict, Set


_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_STD_DIR = os.path.join(_REPO_ROOT, "sapphire", "lib", "std")

_LUA_HOOK_TEMPLATE = r"""
local _cov_out = os.getenv("SAPPHIRE_LUA_COV_LOG")
if _cov_out and _cov_out ~= "" then
  local _seen = {}
  local _fh = io.open(_cov_out, "a")
  if _fh then
    debug.sethook(function(_, line)
      local info = debug.getinfo(2, "S")
      if not info or not info.source then return end
      local src = info.source
      if src:sub(1, 1) == "@" then
        src = src:sub(2)
      end
      if src:find("std[/\\][^/\\]+%.lua$") then
        local key = src .. ":" .. tostring(line)
        if not _seen[key] then
          _seen[key] = true
          _fh:write(key .. "\n")
          _fh:flush()
        end
      end
    end, "l")
  end
end
"""

_NON_EXEC_RE = re.compile(
    r"^\s*(?:--.*|end|else|\}|\)|\]|\},|\),|local\s+function\s+\w+.*|function\s+.*|return\s+\w+\s*)?$"
)


def _executable_lines(lua_path: str) -> Set[int]:
  """Approximates executable line numbers in a Lua 5.1 source file."""
  exec_lines: Set[int] = set()
  in_block_comment = False
  with open(lua_path, "r", encoding="utf-8") as f:
    for idx, raw in enumerate(f, 1):
      line = raw.strip()
      if in_block_comment:
        if "]]" in line:
          in_block_comment = False
        continue
      if line.startswith("--[["):
        if "]]" not in line[4:]:
          in_block_comment = True
        continue
      if not line or line.startswith("--"):
        continue
      if line in ("end", "else", "}", ")", "},", "),", "then", "do"):
        continue
      if re.match(r"^(?:local\s+)?function\b", line) and "end" not in line:
        continue
      exec_lines.add(idx)
  return exec_lines


def run_lua_coverage(fail_under: float = 0.0) -> int:
  """Runs `sapphire test -t lua` with line-hook collection and prints a report."""
  with tempfile.TemporaryDirectory() as tmp_dir:
    hook_path = os.path.join(tmp_dir, "cov_hook.lua")
    log_path = os.path.join(tmp_dir, "cov_hits.log")
    with open(hook_path, "w", encoding="utf-8") as f:
      f.write(_LUA_HOOK_TEMPLATE)

    env = os.environ.copy()
    env["LUA_INIT"] = f"@{hook_path}"
    env["SAPPHIRE_LUA_COV_LOG"] = log_path
    env["PYTHONPATH"] = _REPO_ROOT + (
        os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
    )

    proc = subprocess.run(
        [sys.executable, "-m", "sapphire.cli.sapphire", "test", "-t", "lua"],
        cwd=_REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
      sys.stdout.write(proc.stdout)
      sys.stderr.write(proc.stderr)
      return proc.returncode

    hits_by_file: Dict[str, Set[int]] = {}
    if os.path.isfile(log_path):
      with open(log_path, "r", encoding="utf-8") as f:
        for raw in f:
          raw = raw.strip()
          if ":" not in raw:
            continue
          path_part, line_str = raw.rsplit(":", 1)
          base = os.path.basename(path_part)
          try:
            hits_by_file.setdefault(base, set()).add(int(line_str))
          except ValueError:
            pass

  lua_files = sorted(
      f for f in os.listdir(_STD_DIR) if f.endswith(".lua")
  )
  total_stmts = 0
  total_miss = 0

  print(f"{'Name':<28} {'Stmts':>6} {'Miss':>6} {'Cover':>6}")
  print("-" * 50)
  for fname in lua_files:
    full_path = os.path.join(_STD_DIR, fname)
    exec_lines = _executable_lines(full_path)
    hit_lines = hits_by_file.get(fname, set()) & exec_lines
    stmts = len(exec_lines)
    miss = stmts - len(hit_lines)
    pct = (100.0 * len(hit_lines) / stmts) if stmts else 100.0
    total_stmts += stmts
    total_miss += miss
    print(f"sapphire/lib/std/{fname:<11} {stmts:>6} {miss:>6} {pct:>5.0f}%")

  total_pct = (
      100.0 * (total_stmts - total_miss) / total_stmts if total_stmts else 100.0
  )
  print("-" * 50)
  print(f"{'TOTAL':<28} {total_stmts:>6} {total_miss:>6} {total_pct:>5.0f}%")

  if fail_under > 0 and total_pct < fail_under:
    print(
        f"FAIL: Lua stdlib coverage {total_pct:.1f}% < required {fail_under:.1f}%",
        file=sys.stderr,
    )
    return 1
  return 0


def main() -> int:
  parser = argparse.ArgumentParser(
      description="Collect Lua 5.1 line coverage for lib/std/*.lua."
  )
  parser.add_argument(
      "--fail-under",
      type=float,
      default=0.0,
      help="Exit non-zero if total coverage percentage is below this threshold.",
  )
  args = parser.parse_args()
  return run_lua_coverage(fail_under=args.fail_under)


if __name__ == "__main__":
  sys.exit(main())
