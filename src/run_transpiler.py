"""CLI runner script to compile a Sapphire source file into executable Python.

This script delegates to the transpiler module (`src/code_gen/transpiler.py`)
to compile a Sapphire source file into executable Python.
"""

import os
import sys

# Ensure `src` directory is in sys.path for relative imports
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:  # pragma: no cover
  sys.path.insert(0, script_dir)

from src.code_gen.transpiler import transpile_file



def main():
  target = "python"
  if len(sys.argv) > 1:
    input_file = sys.argv[1]
    if len(sys.argv) > 2:
      target = sys.argv[2]
  else:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    input_file = os.path.normpath(os.path.join(script_dir, "..", "samples", "game_loop.sp"))

  transpile_file(input_file, target=target)


if __name__ == "__main__":  # pragma: no cover
  main()
