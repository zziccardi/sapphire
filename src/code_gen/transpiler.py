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

from src.parser.ast import *
from src.parser.gen.SapphireLexer import SapphireLexer
from src.parser.gen.SapphireParser import SapphireParser
from src.parser.ast_builder import ASTBuilder
from src.semantics.type_checker import TypeChecker, SemanticError
from src.code_gen.python_transpiler import PythonTranspiler, PYTHON_RUNTIME_PREAMBLE, Transpiler, RUNTIME_PREAMBLE
from src.code_gen.lua_transpiler import LuaTranspiler
from src.code_gen.source_map import SourceMapBuilder
from src.code_gen.transpiler_registry import TranspilerRegistry
from src.parser.error_listener import CustomErrorListener, format_syntax_error_message




def transpile_file(
    input_file: str,
    output_file: Optional[str] = None,
    target: str = "python",
    visited: Optional[set] = None,
    sourcemap: bool = True,
    test_mode: bool = False,
    quiet: bool = False,
) -> str:
  """Transpiles Sapphire source file into target language (Python or Lua 5.1).

  Args:
    input_file: Path to the Sapphire source file (.sp).
  """
  if visited is None:

    visited = set()

  abs_input_file = os.path.abspath(input_file)
  if abs_input_file in visited:
    return output_file or ""
  visited.add(abs_input_file)

  target_info = TranspilerRegistry.get(target)
  ext = target_info.default_extension

  if not output_file:
    base_name = os.path.splitext(input_file)[0]
    output_file = base_name + ext

  # 1. Lexical Analysis
  if not quiet:
    print(f"Reading source file: {input_file}...")

  try:
    input_stream = FileStream(input_file, encoding="utf-8")
  except Exception as e:
    if not quiet:  # pragma: no cover
      print(f"Failed to read file: {e}", file=sys.stderr)
    sys.exit(1)

  error_listener = CustomErrorListener(file_path=input_file, source_content=input_stream, quiet=quiet)

  lexer = SapphireLexer(input_stream)
  lexer.removeErrorListeners()
  lexer.addErrorListener(error_listener)

  stream = CommonTokenStream(lexer)

  # 2. Parsing
  parser = SapphireParser(stream)
  parser.removeErrorListeners()
  parser.addErrorListener(error_listener)

  if not quiet:
    print("Parsing program to Parse Tree...")
  tree = parser.program()

  if error_listener.errors > 0:
    if not quiet:
      print(f"\nParsing failed with {error_listener.errors} syntax error(s).", file=sys.stderr)
    sys.exit(1)

  # 3. Build AST
  if not quiet:
    print("Building AST...")
  builder = ASTBuilder()
  ast = builder.visit(tree)

  # 4. Semantic Analysis & Type Checking
  if not quiet:
    print("Running Semantic Analysis & Type Checker...")
  checker = TypeChecker(source_file_path=input_file, source_content=str(input_stream))
  try:
    checker.check(ast)
  except SemanticError as e:
    if not quiet:  # pragma: no cover
      print(f"\nSemantic Analysis failed with errors:\n{e}", file=sys.stderr)
    sys.exit(1)

  # 5. Transitive Module Dependencies Transpilation
  from src.semantics.module_resolver import resolve_module_path

  for imp in getattr(ast, "imports", []):
    if imp.path == "std.testing" or imp.path.startswith("std.testing"):
      continue
    sub_source = resolve_module_path(imp.path, source_file_path=input_file)
    if sub_source:
      sub_output = os.path.splitext(sub_source)[0] + ext
      transpile_file(sub_source, sub_output, target=target, visited=visited, sourcemap=sourcemap, test_mode=test_mode, quiet=quiet)

  # 6. Transpile via TranspilerRegistry
  sm_builder = None
  src_filename = os.path.basename(input_file)
  src_content = str(input_stream)

  if target_info.name == "lua":
    if sourcemap:
      sm_builder = SourceMapBuilder(src_filename, src_content)
    transpiler = target_info.factory(source_file=src_filename, source_map_builder=sm_builder, test_mode=test_mode)
  else:
    transpiler = target_info.factory(test_mode=test_mode)

  if not quiet:
    print(f"Transpiling to {target_info.display_name}...")
  generated_code = transpiler.transpile(ast)
  target_name = target_info.display_name


  # Write generated code
  try:
    with open(output_file, "w", encoding="utf-8") as f:
      f.write(generated_code)

    if sm_builder and sourcemap:
      map_output_file = output_file + ".map"
      with open(map_output_file, "w", encoding="utf-8") as f:
        f.write(sm_builder.to_v3_json(os.path.basename(output_file)))
      if not quiet:
        print(f"Source map generated at: {map_output_file}")

    if not quiet:
      print(f"\nCompilation successful! {target_name} output written to:\n"
            f"{output_file}")
    return output_file
  except Exception as e:
    if not quiet:  # pragma: no cover
      print(f"Failed to write output file: {e}", file=sys.stderr)
    sys.exit(1)
