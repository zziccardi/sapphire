# pyright: reportMissingModuleSource=false

import sys
import os

from antlr4 import *
from antlr4.error.ErrorListener import ErrorListener

from src.parser.gen.SapphireLexer import SapphireLexer
from src.parser.gen.SapphireParser import SapphireParser
from src.cli.diagnostics import format_diagnostic



class CustomErrorListener(ErrorListener):
  def __init__(self, file_path=None, source_content=None):
    super().__init__()
    self.errors = 0
    self.file_path = file_path
    self.source_content = source_content

  def syntaxError(self, recognizer, offendingSymbol, line, column, msg, e):
    self.errors += 1
    length = len(offendingSymbol.text) if (offendingSymbol and hasattr(offendingSymbol, "text") and offendingSymbol.text) else 1
    source_content = str(self.source_content) if self.source_content is not None else None
    diag = format_diagnostic(
        error_type="Error",
        message=msg,
        file_path=self.file_path,
        line=line,
        column=column,
        length=length,
        source_content=source_content,
    )
    print(diag, file=sys.stderr)


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
