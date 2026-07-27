"""Transpiler driver facade for Sapphire programming language.

Provides the primary high-level compilation driver API (`transpile_file`)
which orchestrates lexing, parsing, AST building, type checking, and code generation
dispatch to target backends (Python or Lua 5.1).
"""

import os
import sys
from typing import Optional

from antlr4 import FileStream, CommonTokenStream
from antlr4.error.ErrorListener import ErrorListener

try:
  from parser.ast import *
  from parser.gen.SapphireLexer import SapphireLexer
  from parser.gen.SapphireParser import SapphireParser
  from parser.ast_builder import ASTBuilder
  from semantics.type_checker import TypeChecker, SemanticError
  from code_gen.python_transpiler import PythonTranspiler, PYTHON_RUNTIME_PREAMBLE, Transpiler, RUNTIME_PREAMBLE
  from code_gen.lua_transpiler import LuaTranspiler
except ModuleNotFoundError:  # pragma: no cover
  from src.parser.ast import *
  from src.parser.gen.SapphireLexer import SapphireLexer
  from src.parser.gen.SapphireParser import SapphireParser
  from src.parser.ast_builder import ASTBuilder
  from src.semantics.type_checker import TypeChecker, SemanticError
  from src.code_gen.python_transpiler import PythonTranspiler, PYTHON_RUNTIME_PREAMBLE, Transpiler, RUNTIME_PREAMBLE
  from src.code_gen.lua_transpiler import LuaTranspiler


def format_syntax_error_message(recognizer, offendingSymbol, msg: str) -> str:
  """Customizes ANTLR syntax error messages for better developer ergonomics."""
  if recognizer and offendingSymbol and hasattr(offendingSymbol, "tokenIndex"):
    try:
      stream = recognizer.getTokenStream()
      if stream:
        idx = offendingSymbol.tokenIndex
        prev_idx = idx - 1
        while prev_idx >= 0 and stream.get(prev_idx).channel != 0:
          prev_idx -= 1

        if prev_idx >= 0 and stream.get(prev_idx).text == "}":
          depth = 1
          curr = prev_idx - 1
          while curr >= 0 and depth > 0:
            tok_text = stream.get(curr).text
            if tok_text == "}":
              depth += 1
            elif tok_text == "{":
              depth -= 1
            curr -= 1

          search_limit = max(0, curr - 30)
          while curr >= search_limit:
            tok = stream.get(curr)
            if tok.text == "match":
              return (
                  f"Missing semicolon ';' after closing brace '}}' of match expression. "
                  f"Match expressions used as statements must end with a semicolon ';' (e.g. 'match ... }};')."
              )
            curr -= 1
    except Exception:
      pass
  return msg


class CustomErrorListener(ErrorListener):
  """Custom ANTLR error listener to track and report syntax errors."""

  def __init__(self):
    super().__init__()
    self.errors = 0

  def syntaxError(self, recognizer, offendingSymbol, line, column, msg, e):
    self.errors += 1
    custom_msg = format_syntax_error_message(recognizer, offendingSymbol, msg)
    print(f"Syntax Error: Line {line}:{column} - {custom_msg}", file=sys.stderr)


def transpile_file(
    input_file: str,
    output_file: Optional[str] = None,
    target: str = "python",
    visited: Optional[set] = None,
) -> str:
  """Transpiles Sapphire source file into target language (Python or Lua 5.1).

  Args:
    input_file: Path to the Sapphire source file (.sp).
    output_file: Optional output path for generated code (.py or .lua). If None,
      defaults to input_file with .py or .lua extension depending on target.
    target: Code generation target ("python" or "lua" / "lua5.1").
    visited: Set of already processed file paths to prevent recursion loops.

  Returns:
    The path to the generated output file.
  """

  target_lower = target.lower()
  ext = ".lua" if target_lower in ("lua", "lua5.1") else ".py"

  if not output_file:
    base_path, _ = os.path.splitext(input_file)
    output_file = base_path + ext

  if visited is None:
    visited = set()

  input_abs = os.path.abspath(input_file)
  if input_abs in visited:
    return output_file
  visited.add(input_abs)

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
  checker = TypeChecker(source_file_path=input_file)
  try:
    checker.check(ast)
  except SemanticError as e:
    print(f"\nSemantic Analysis failed with errors:\n{e}", file=sys.stderr)
    sys.exit(1)

  # 5. Transitive Module Dependencies Transpilation
  for imp in getattr(ast, "imports", []):
    rel_path = imp.path.replace(".", "/") + ".sp"
    possible_sources = [
        rel_path,
        os.path.join(os.path.dirname(input_file), rel_path),
        os.path.join(os.getcwd(), rel_path),
    ]
    sub_source = None
    for p in possible_sources:
      if os.path.exists(p):
        sub_source = p
        break
    if sub_source:
      sub_output = os.path.splitext(sub_source)[0] + ext
      transpile_file(sub_source, sub_output, target=target, visited=visited)

  # 6. Transpile
  if target_lower in ("lua", "lua5.1"):
    print("Transpiling to Lua 5.1...")
    transpiler = LuaTranspiler()
    generated_code = transpiler.transpile(ast)
    target_name = "Lua 5.1"
  else:
    print("Transpiling to Python...")
    transpiler = PythonTranspiler()
    generated_code = transpiler.transpile(ast)
    target_name = "Python"

  # Write generated code
  try:
    with open(output_file, "w", encoding="utf-8") as f:
      f.write(generated_code)
    print(f"\nCompilation successful! {target_name} output written to:\n"
          f"{output_file}")
    return output_file
  except Exception as e:
    print(f"Failed to write output file: {e}", file=sys.stderr)
    sys.exit(1)
