"""Command-line tool to run the Sapphire semantic analyzer and type checker.

This script parses a Sapphire source file, builds the Abstract Syntax Tree (AST),
runs the semantic analysis/type checking pass, and prints diagnostic messages.
"""

import sys
import os

from antlr4 import FileStream, CommonTokenStream
from antlr4.error.ErrorListener import ErrorListener

from src.parser.gen.SapphireLexer import SapphireLexer
from src.parser.gen.SapphireParser import SapphireParser
from src.parser.ast_builder import ASTBuilder
from src.semantics.type_checker import TypeChecker, SemanticError
from src.cli.diagnostics import format_diagnostic



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

  error_listener = CustomErrorListener(file_path=input_file, source_content=input_stream)

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
    print(f"\nParsing failed with {error_listener.errors} syntax error(s).", file=sys.stderr)
    sys.exit(1)

  # 3. Build AST
  print("Building AST...")
  builder = ASTBuilder()
  ast = builder.visit(tree)

  # 4. Semantic Analysis & Type Checking
  print("Running Semantic Analysis & Type Checker...")
  checker = TypeChecker(source_file_path=input_file, source_content=str(input_stream))
  try:
    checker.check(ast)
    print("\nSemantic Analysis completed successfully with 0 errors!")
  except SemanticError as e:
    print(f"\nSemantic Analysis failed with errors:\n{e}", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
  main()
