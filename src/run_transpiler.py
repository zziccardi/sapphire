"""CLI runner script to compile a Sapphire source file into executable Python.

This script parses a Sapphire source file, performs semantic analysis /
type-checking, and calls the transpiler to generate executable Python output.
"""

import os
import sys
from typing import Optional

from antlr4 import FileStream, CommonTokenStream
from antlr4.error.ErrorListener import ErrorListener

# Ensure `src` directory is in sys.path for relative imports
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:  # pragma: no cover
  sys.path.insert(0, script_dir)

try:
  from parser.gen.SapphireLexer import SapphireLexer
  from parser.gen.SapphireParser import SapphireParser
  from parser.ast_builder import ASTBuilder
  from semantics.type_checker import TypeChecker, SemanticError
  from code_gen.transpiler import Transpiler
except ModuleNotFoundError:  # pragma: no cover
  from src.parser.gen.SapphireLexer import SapphireLexer
  from src.parser.gen.SapphireParser import SapphireParser
  from src.parser.ast_builder import ASTBuilder
  from src.semantics.type_checker import TypeChecker, SemanticError
  from src.code_gen.transpiler import Transpiler


class CustomErrorListener(ErrorListener):
  """Custom ANTLR error listener to track and report syntax errors."""

  def __init__(self):
    super().__init__()
    self.errors = 0

  def syntaxError(self, recognizer, offendingSymbol, line, column, msg, e):
    self.errors += 1
    print(f"Syntax Error: Line {line}:{column} - {msg}", file=sys.stderr)


def transpile_file(input_file: str, output_file: Optional[str] = None) -> str:
  """Transpiles a Sapphire source file into Python.

  Args:
    input_file: Path to the Sapphire source file (.sp).
    output_file: Optional output path for generated Python code (.py).
      If None, defaults to input_file with .py extension.

  Returns:
    The path to the generated Python file.
  """

  if not output_file:
    base_path, _ = os.path.splitext(input_file)
    output_file = base_path + ".py"

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
    print(f"\nParsing failed with {error_listener.errors} syntax error(s).", file=sys.stderr)
    sys.exit(1)

  # 3. Build AST
  print("Building AST...")
  builder = ASTBuilder()
  ast = builder.visit(tree)

  # 4. Semantic Analysis & Type Checking
  print("Running Semantic Analysis & Type Checker...")
  checker = TypeChecker()
  try:
    checker.check(ast)
  except SemanticError as e:
    print(f"\nSemantic Analysis failed with errors:\n{e}", file=sys.stderr)
    sys.exit(1)

  # 5. Transpile
  print("Transpiling to Python...")
  transpiler = Transpiler()
  python_code = transpiler.transpile(ast)

  # Write generated code
  try:
    with open(output_file, "w", encoding="utf-8") as f:
      f.write(python_code)
    print(f"\nCompilation successful! Python output written to:\n{output_file}")
    return output_file
  except Exception as e:
    print(f"Failed to write output file: {e}", file=sys.stderr)
    sys.exit(1)


def main():
  # Determine input and output file paths
  if len(sys.argv) > 1:
    input_file = sys.argv[1]
  else:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    input_file = os.path.normpath(os.path.join(script_dir, "..", "sample.sp"))

  transpile_file(input_file)


if __name__ == "__main__":  # pragma: no cover
  main()
