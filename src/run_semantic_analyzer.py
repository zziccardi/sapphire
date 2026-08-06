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



class CustomErrorListener(ErrorListener):
  """Custom ANTLR error listener to track and report syntax errors."""

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
        error_type="Syntax Error",
        message=msg,
        file_path=self.file_path,
        line=line,
        column=column,
        length=length,
        source_content=source_content,
    )
    print(diag, file=sys.stderr)


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
