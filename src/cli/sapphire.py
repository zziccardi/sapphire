"""Unified CLI entry point for the Sapphire programming language.

Provides commands to compile Sapphire code (`build`) and compile & run in one
step (`run`).
"""

import argparse
import os
import shutil
import sys
import subprocess

# Ensure `src` directory is in `sys.path` so submodules like `code_gen`, `parser`,
# and `semantics` can be imported when running `sapphire` directly.
src_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if src_dir not in sys.path:
  sys.path.insert(0, src_dir)

try:
  from code_gen.transpiler import transpile_file
except ModuleNotFoundError:  # pragma: no cover
  from src.code_gen.transpiler import transpile_file


def run_command(args):
  """Handles `run` subcommand: compiles and executes a Sapphire file."""

  source_file = args.source
  if not os.path.exists(source_file):
    print(f"Error: File '{source_file}' not found.", file=sys.stderr)
    sys.exit(1)

  target = getattr(args, "target", "python").lower()
  ext = ".lua" if target in ("lua", "lua5.1") else ".py"
  output_file = args.output or (os.path.splitext(source_file)[0] + ext)
  sourcemap = not getattr(args, "no_sourcemap", False)
  out_path = transpile_file(source_file, output_file, target=target, sourcemap=sourcemap)

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

  result = subprocess.run(cmd)
  sys.exit(result.returncode)


def build_command(args):
  """Handles `build` subcommand: compiles a Sapphire file without executing."""

  source_file = args.source
  if not os.path.exists(source_file):
    print(f"Error: File '{source_file}' not found.", file=sys.stderr)
    sys.exit(1)

  target = getattr(args, "target", "python").lower()
  ext = ".lua" if target in ("lua", "lua5.1") else ".py"
  output_file = args.output or (os.path.splitext(source_file)[0] + ext)
  sourcemap = not getattr(args, "no_sourcemap", False)
  transpile_file(source_file, output_file, target=target, sourcemap=sourcemap)


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
      "-t", "--target", choices=["python", "lua", "lua5.1"], default="python",
      help="Code generation target (default: python)")
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
      "-t", "--target", choices=["python", "lua", "lua5.1"], default="python",
      help="Code generation target (default: python)")
  run_parser.add_argument(
      "--no_sourcemap", action="store_true",
      help="Disable source map generation (.lua.map) for Lua targets")
  run_parser.set_defaults(func=run_command)

  # Handle shortcut invocation: if first argument is a file (e.g.
  # `sapphire samples/overview.sp`)
  if (len(sys.argv) > 1 and not sys.argv[1].startswith("-") and
      sys.argv[1] not in ["build", "run"]):
    sys.argv.insert(1, "run")

  args = parser.parse_args()

  if hasattr(args, "func"):
    args.func(args)
  else:
    parser.print_help()


if __name__ == "__main__":  # pragma: no cover
  main()
