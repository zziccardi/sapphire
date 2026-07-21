"""Unified CLI entry point for the Sapphire programming language.

Provides commands to compile Sapphire code (`build`) and compile & run in one
step (`run`).
"""

import argparse
import os
import sys
import subprocess

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

  output_file = args.output or (os.path.splitext(source_file)[0] + ".py")
  out_path = transpile_file(source_file, output_file)

  print("\n--- Executing Sapphire Program ---")
  if args.demo:
    # Convert file path to module path for import (e.g. samples/overview.py ->
    # samples.overview)
    rel_path = os.path.relpath(out_path)
    module_name = os.path.splitext(rel_path)[0].replace(os.sep, ".")
    cmd = [sys.executable, "-c",
           f"import {module_name} as sample; sample.run_demo()"]
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

  output_file = args.output or (os.path.splitext(source_file)[0] + ".py")
  transpile_file(source_file, output_file)


def main():
  parser = argparse.ArgumentParser(
      prog="sapphire",
      description="Sapphire compiler & runner CLI")

  subparsers = parser.add_subparsers(dest="command", help="Available commands")

  # `build` subcommand
  build_parser = subparsers.add_parser(
      "build", help="Transpile Sapphire source (.sp) to Python (.py)")
  build_parser.add_argument("source", help="Path to Sapphire source file (.sp)")
  build_parser.add_argument(
      "-o", "--output", help="Optional output path for generated Python file")
  build_parser.set_defaults(func=build_command)

  # `run` subcommand
  run_parser = subparsers.add_parser(
      "run", help="Transpile and immediately execute Sapphire source (.sp)")
  run_parser.add_argument("source", help="Path to Sapphire source file (.sp)")
  run_parser.add_argument(
      "-o", "--output", help="Optional output path for generated Python file")
  run_parser.add_argument(
      "--demo",
      action="store_true",
      help="Invoke the run_demo() function after importing generated module")
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
