"""Runner script to parse a Sapphire file and print its Abstract Syntax Tree (AST).

This script uses the ANTLR lexer and parser to generate a concrete parse tree,
then runs the ASTBuilder visitor to construct and output the structured AST in
JSON format.
"""

import json
import os
import sys

from antlr4 import FileStream, CommonTokenStream
from antlr4.error.ErrorListener import ErrorListener

from src.parser.gen.SapphireLexer import SapphireLexer
from src.parser.gen.SapphireParser import SapphireParser
from src.parser.ast_builder import ASTBuilder



from src.parser.error_listener import CustomErrorListener



def main():
  # Determine input file path
  if len(sys.argv) > 1:
    input_file = sys.argv[1]
  else:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    input_file = os.path.normpath(os.path.join(script_dir, "..", "samples", "game_loop.sp"))

  print(f"Reading source file: {input_file}...")

  try:
    input_stream = FileStream(input_file, encoding="utf-8")
  except Exception as e:
    print(f"Failed to read file: {e}", file=sys.stderr)
    sys.exit(1)

  error_listener = CustomErrorListener()

  # 1. Lexical Analysis
  lexer = SapphireLexer(input_stream)
  lexer.removeErrorListeners()
  lexer.addErrorListener(error_listener)

  stream = CommonTokenStream(lexer)

  # 2. Parsing
  parser = SapphireParser(stream)
  parser.removeErrorListeners()
  parser.addErrorListener(error_listener)

  print("Parsing program to Parse Tree...")
  tree = parser.program()

  if error_listener.errors > 0:
    print(f"\nParsing completed with {error_listener.errors} error(s). AST build aborted.", file=sys.stderr)
    sys.exit(1)

  print("Parse Tree generated successfully.")
  print("Building AST...")

  # 3. Build AST using visitor
  builder = ASTBuilder()
  ast = builder.visit(tree)

  print("AST built successfully!")
  print("\nAST JSON Representation (Preview):")

  # Format AST as pretty JSON
  ast_dict = ast.to_dict()
  ast_json = json.dumps(ast_dict, indent=2)

  # Truncate output to avoid flooding console, write full JSON to a scratch file
  if len(ast_json) > 1000:
    print(ast_json[:1000] + "\n\n... [TRUNCATED] ...")
  else:
    print(ast_json)


if __name__ == "__main__":
  main()
