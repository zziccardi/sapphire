# pyright: reportMissingModuleSource=false

import sys
import os

from antlr4 import *
from antlr4.error.ErrorListener import ErrorListener

from src.parser.gen.SapphireLexer import SapphireLexer
from src.parser.gen.SapphireParser import SapphireParser
from src.cli.diagnostics import format_diagnostic



from src.parser.error_listener import CustomErrorListener



def main():
  if len(sys.argv) > 1:
    input_file = sys.argv[1]
  else:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    input_file = os.path.normpath(os.path.join(script_dir, "..", "samples", "game_loop.sp"))

  print(f"Reading source file: {input_file}...")

  try:
    input_stream = FileStream(input_file, encoding='utf-8')
  except Exception as e:
    print(f"Failed to read file: {e}", file=sys.stderr)
    sys.exit(1)

  error_listener = CustomErrorListener(file_path=input_file, source_content=input_stream)

  lexer = SapphireLexer(input_stream)
  lexer.removeErrorListeners()
  lexer.addErrorListener(error_listener)

  stream = CommonTokenStream(lexer)

  parser = SapphireParser(stream)
  parser.removeErrorListeners()
  parser.addErrorListener(error_listener)

  print("Parsing program...")

  tree = parser.program()

  if error_listener.errors > 0:
    print(f"\nParsing completed with {error_listener.errors} error(s).",
          file=sys.stderr)
    sys.exit(1)
  else:
    print("\nParsing completed successfully with 0 errors!")
    print("\nParse Tree Preview:")

    # Print a truncated version of the tree so it doesn't flood the console.
    tree_str = tree.toStringTree(recog=parser)

    if len(tree_str) > 500:
      print(tree_str[:500] + " ... [TRUNCATED]")
    else:
      print(tree_str)


if __name__ == '__main__':
  main()
