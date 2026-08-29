"""Unified CLI entry point for the Sapphire programming language.

Provides commands to compile Sapphire code (`build`) and compile & run in one
step (`run`).
"""

import argparse
import os
import shutil
import sys
import subprocess
import time
from typing import Dict, List

src_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
root_dir = os.path.abspath(os.path.join(src_dir, ".."))
if root_dir not in sys.path:  # pragma: no cover
  sys.path.insert(0, root_dir)
if src_dir not in sys.path:  # pragma: no cover
  sys.path.insert(0, src_dir)

from src.code_gen.transpiler import transpile_file

TARGET_CHOICES = ["python", "lua", "lua5.1", "love2d", "love"]


def _collect_sp_watch_files(root_path: str) -> Dict[str, float]:
  """Collects modification times for all .sp files in the project / directory of root_path."""
  watch_files = {}
  dir_path = os.path.dirname(os.path.abspath(root_path)) or "."
  for root, _, files in os.walk(dir_path):
    for f in files:
      if f.endswith(".sp"):
        p = os.path.join(root, f)
        try:
          watch_files[p] = os.path.getmtime(p)
        except OSError:
          pass
  return watch_files


def _run_dev_watcher(source_file: str, output_file: str, target: str, sourcemap: bool, cmd: List[str]):
  """Spawns process and watches source files for live hot-reloading."""
  print(f"\n[Sapphire Dev Mode] Starting process with live hot-reloading: {' '.join(cmd)}")
  print("[Sapphire Dev Mode] Watching for file changes... (Press Ctrl+C to stop)")

  proc = subprocess.Popen(cmd)
  watch_files = _collect_sp_watch_files(source_file)

  try:
    while True:
      time.sleep(0.3)
      if proc.poll() is not None:
        if target in ("love2d", "love"):
          sys.exit(proc.returncode)

      current_watch_files = _collect_sp_watch_files(source_file)
      changed = False
      for path, mtime in current_watch_files.items():
        if path not in watch_files or watch_files[path] != mtime:
          changed = True
          break

      if changed:
        watch_files = current_watch_files
        print("\n[Sapphire Dev Mode] File change detected, re-transpiling...")
        try:
          transpile_file(source_file, output_file, target=target, sourcemap=sourcemap, dev_mode=True, quiet=False)
          print("[Sapphire Dev Mode] Re-compilation complete.")
          if target not in ("love2d", "love"):
            if proc.poll() is None:
              proc.terminate()
              try:
                proc.wait(timeout=1.0)
              except subprocess.TimeoutExpired:
                proc.kill()
            print("\n--- Re-executing Sapphire Program ---")
            proc = subprocess.Popen(cmd)
        except Exception as err:
          print(f"[Sapphire Dev Mode Error] Compilation failed: {err}", file=sys.stderr)

  except KeyboardInterrupt:
    print("\n[Sapphire Dev Mode] Shutting down...")
    if proc.poll() is None:
      proc.terminate()
      try:
        proc.wait(timeout=1.0)
      except subprocess.TimeoutExpired:
        proc.kill()
    sys.exit(0)


def run_command(args):
  """Handles `run` subcommand: compiles and executes a Sapphire file."""

  source_file = args.source
  if not os.path.exists(source_file):
    print(f"Error: File '{source_file}' not found.", file=sys.stderr)
    sys.exit(1)

  target = getattr(args, "target", "python").lower()
  dev_mode = getattr(args, "dev", False)
  ext = ".lua" if target in ("lua", "lua5.1", "love2d", "love") else ".py"
  output_file = args.output or (os.path.splitext(source_file)[0] + ext)
  sourcemap = not getattr(args, "no_sourcemap", False)
  out_path = transpile_file(source_file, output_file, target=target, sourcemap=sourcemap, dev_mode=dev_mode)

  if target in ("love2d", "love"):
    love_bin = shutil.which("love")
    if not love_bin:
      print("Error: Love2D executable ('love') not found in PATH.", file=sys.stderr)
      sys.exit(1)
    run_dir = os.path.dirname(os.path.abspath(output_file)) or "."
    cmd = [love_bin, run_dir]
    if dev_mode:
      _run_dev_watcher(source_file, output_file, target, sourcemap, cmd)
    else:
      print("\n--- Executing Love2D Engine ---")
      result = subprocess.run(cmd)
      sys.exit(result.returncode)

  print("\n--- Executing Sapphire Program ---")
  if target in ("lua", "lua5.1"):
    lua_bin = (shutil.which("lua") or shutil.which("luajit") or
               shutil.which("lua5.1"))
    if not lua_bin:
      print("Error: Lua interpreter ('lua', 'luajit', or 'lua5.1')"
            " not found in PATH.", file=sys.stderr)
      sys.exit(1)
    cmd = [lua_bin, out_path]
  else:
    cmd = [sys.executable, out_path]

  if dev_mode:
    _run_dev_watcher(source_file, output_file, target, sourcemap, cmd)
  else:
    result = subprocess.run(cmd)
    sys.exit(result.returncode)


def build_command(args):
  """Handles `build` subcommand: compiles a Sapphire file without executing."""

  source_file = args.source
  if not os.path.exists(source_file):
    print(f"Error: File '{source_file}' not found.", file=sys.stderr)
    sys.exit(1)

  target = getattr(args, "target", "python").lower()
  dev_mode = getattr(args, "dev", False)
  ext = ".lua" if target in ("lua", "lua5.1", "love2d", "love") else ".py"
  output_file = args.output or (os.path.splitext(source_file)[0] + ext)
  sourcemap = not getattr(args, "no_sourcemap", False)
  transpile_file(source_file, output_file, target=target, sourcemap=sourcemap, dev_mode=dev_mode)


def test_command(args):
  """Handles `test` subcommand: discovers and executes Sapphire tests."""
  from src.cli.test_runner import run_tests

  target = getattr(args, "target", "python").lower()
  source_path = getattr(args, "source", ".")
  filter_pattern = getattr(args, "filter", None)
  sourcemap = not getattr(args, "no_sourcemap", False)
  exit_code = run_tests(source_path, target=target, filter_pattern=filter_pattern, sourcemap=sourcemap)
  sys.exit(exit_code)


def lsp_command(args):
  """Handles `lsp` subcommand: starts the Sapphire LSP server over stdio."""
  from src.lsp.server import main as lsp_main
  lsp_main()


def main():
  parser = argparse.ArgumentParser(
      prog="sapphire",
      description="Sapphire compiler & runner CLI")

  subparsers = parser.add_subparsers(dest="command", help="Available commands")

  # `build` subcommand
  build_parser = subparsers.add_parser(
      "build", help="Transpile Sapphire source (.sp) to Python or Lua")
  build_parser.add_argument("source", help="Path to Sapphire source file (.sp)")
  build_parser.add_argument(
      "-o", "--output", help="Optional output path for generated target file")
  build_parser.add_argument(
      "-t", "--target", choices=TARGET_CHOICES, default="python",
      help="Code generation target (default: python)")
  build_parser.add_argument(
      "--dev", action="store_true",
      help="Enable development mode with in-place hot-reloading")
  build_parser.add_argument(
      "--no_sourcemap", action="store_true",
      help="Disable source map generation (.lua.map) for Lua targets")
  build_parser.set_defaults(func=build_command)

  # `run` subcommand
  run_parser = subparsers.add_parser(
      "run", help="Transpile and immediately execute Sapphire source (.sp)")
  run_parser.add_argument("source", help="Path to Sapphire source file (.sp)")
  run_parser.add_argument(
      "-o", "--output", help="Optional output path for generated target file")
  run_parser.add_argument(
      "-t", "--target", choices=TARGET_CHOICES, default="python",
      help="Code generation target (default: python)")
  run_parser.add_argument(
      "--dev", action="store_true",
      help="Enable development mode with file watching and live hot-reloading")
  run_parser.add_argument(
      "--no_sourcemap", action="store_true",
      help="Disable source map generation (.lua.map) for Lua targets")
  run_parser.set_defaults(func=run_command)

  # `test` subcommand
  test_parser = subparsers.add_parser(
      "test", help="Discover and execute Sapphire tests")
  test_parser.add_argument(
      "source", nargs="?", default=".", help="Path to Sapphire source file (.sp) or directory (default: .)")
  test_parser.add_argument(
      "-t", "--target", choices=TARGET_CHOICES, default="python",
      help="Code generation target (default: python)")
  test_parser.add_argument(
      "--filter", help="Filter tests by substring matching test name")
  test_parser.add_argument(
      "--no_sourcemap", action="store_true",
      help="Disable source map generation (.lua.map) for Lua targets")
  test_parser.set_defaults(func=test_command)

  # `lsp` subcommand
  lsp_parser = subparsers.add_parser(
      "lsp", help="Start the Sapphire Language Server over stdio")
  lsp_parser.set_defaults(func=lsp_command)

  # Handle shortcut invocation: if first argument is a file (e.g.
  # `sapphire samples/overview.sp`)
  if (len(sys.argv) > 1 and not sys.argv[1].startswith("-") and
      sys.argv[1] not in ["build", "run", "test", "lsp"]):
    sys.argv.insert(1, "run")

  args = parser.parse_args()

  if hasattr(args, "func"):
    args.func(args)
  else:
    parser.print_help()


if __name__ == "__main__":  # pragma: no cover
  main()
