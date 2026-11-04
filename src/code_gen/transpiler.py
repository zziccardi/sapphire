"""Transpiler driver facade for Sapphire programming language.

Provides the primary high-level compilation driver API (`transpile_file`)
which orchestrates lexing, parsing, AST building, type checking, and code
generation dispatch to target backends (Python or Lua 5.1).
"""

import os
import sys
from typing import Optional

from antlr4 import FileStream, CommonTokenStream
from antlr4.error.ErrorListener import ErrorListener

from src.common.errors import (
    SapphireError,
    SapphireSyntaxError,
    SapphireTypeError,
    SapphireTranspileError,
    SemanticError,
)
from src.parser.ast import *
from src.parser.gen.SapphireLexer import SapphireLexer
from src.parser.gen.SapphireParser import SapphireParser
from src.parser.ast_builder import ASTBuilder
from src.semantics.type_checker import TypeChecker
from src.code_gen.python_transpiler import PythonTranspiler, PYTHON_RUNTIME_PREAMBLE, Transpiler, RUNTIME_PREAMBLE
from src.code_gen.lua_transpiler import LuaTranspiler, LUA_RUNTIME_PREAMBLE, LUA_RUNTIME_MODULE_EXPORTS
from src.code_gen.source_map import SourceMapBuilder
from src.code_gen.transpiler_registry import TranspilerRegistry
from src.code_gen.intrinsics import is_builtin_module
from src.parser.error_listener import CustomErrorListener, format_syntax_error_message


def emit_runtime_module(output_dir: str, target: str = "python") -> str:
  """Writes the shared Sapphire runtime module (`_sapphire_runtime.py` or `_sapphire_runtime.lua`) to `output_dir`."""
  os.makedirs(output_dir, exist_ok=True)
  target_lower = target.lower()
  if target_lower in ("lua", "lua5.1", "love2d", "love"):
    rt_path = os.path.join(output_dir, "_sapphire_runtime.lua")
    with open(rt_path, "w", encoding="utf-8") as f:
      f.write(LUA_RUNTIME_PREAMBLE + "\n" + LUA_RUNTIME_MODULE_EXPORTS)
    return rt_path
  rt_path = os.path.join(output_dir, "_sapphire_runtime.py")
  # Export all symbols including leading-underscore helpers so `from _sapphire_runtime import *` imports them
  all_line = "\n__all__ = [name for name in globals() if not name.startswith('__')]\n"
  with open(rt_path, "w", encoding="utf-8") as f:
    f.write(PYTHON_RUNTIME_PREAMBLE + all_line)
  return rt_path


def transpile_file(
    input_file: str,
    output_file: Optional[str] = None,
    target: str = "python",
    visited: Optional[set] = None,
    sourcemap: bool = True,
    test_mode: bool = False,
    dev_mode: bool = False,
    quiet: bool = False,
    raise_on_error: bool = True,
    use_runtime_module: bool = False,
) -> str:
  """Transpiles Sapphire source file into target language (Python or Lua 5.1).

  Args:
    input_file: Path to the Sapphire source file (.sp).
    output_file: Path to write transpiled target file.
    target: Target language backend.
    visited: Set of visited file paths for circular dependency tracking.
    sourcemap: Whether to generate source map.
    test_mode: Whether to transpile in test mode (@test inclusion).
    dev_mode: Whether to enable dev hot-reloading hooks.
    quiet: Suppress informational logs.
    raise_on_error: Raise SapphireError exceptions instead of sys.exit(1).
    use_runtime_module: Emit a shared `_sapphire_runtime` file and import it instead of inlining preamble.
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
    if raise_on_error:
      raise SapphireError(f"Failed to read file: {e}", file_path=input_file)
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
    err_text = "\n".join(error_listener.error_messages) if error_listener.error_messages else f"Parsing failed with {error_listener.errors} syntax error(s)."
    if raise_on_error:
      raise SapphireSyntaxError(err_text, file_path=input_file)
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
    if raise_on_error:
      raise e
    if not quiet:  # pragma: no cover
      print(f"\nSemantic Analysis failed with errors:\n{e}", file=sys.stderr)
    sys.exit(1)

  # 5. Transitive Module Dependencies Transpilation
  from src.semantics.module_resolver import resolve_module_path

  for imp in getattr(ast, "imports", []):
    if is_builtin_module(imp.path):
      continue
    sub_source = resolve_module_path(imp.path, source_file_path=input_file)
    if sub_source:
      sub_output = os.path.splitext(sub_source)[0] + ext
      transpile_file(sub_source, sub_output, target=target, visited=visited, sourcemap=sourcemap, test_mode=test_mode, dev_mode=dev_mode, quiet=quiet, raise_on_error=raise_on_error, use_runtime_module=use_runtime_module)

  # 6. Transpile via TranspilerRegistry
  sm_builder = None
  src_filename = os.path.basename(input_file)
  src_content = str(input_stream)

  if target_info.name in ("lua", "love2d", "love"):
    if sourcemap:
      sm_builder = SourceMapBuilder(src_filename, src_content)
    transpiler = target_info.factory(source_file=src_filename, source_map_builder=sm_builder, test_mode=test_mode, dev_mode=dev_mode, use_runtime_module=use_runtime_module)
  elif target_info.name == "python":
    transpiler = target_info.factory(test_mode=test_mode, use_runtime_module=use_runtime_module)
  else:
    transpiler = target_info.factory(test_mode=test_mode)

  if not quiet:
    print(f"Transpiling to {target_info.display_name}...")
  generated_code = transpiler.transpile(ast)
  target_name = target_info.display_name

  # Write generated code
  try:
    if use_runtime_module and target_info.name in ("python", "lua", "love2d", "love"):
      out_dir = os.path.dirname(os.path.abspath(output_file)) or "."
      emit_runtime_module(out_dir, target=target)

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
    if raise_on_error:
      raise SapphireTranspileError(f"Failed to write output file: {e}", file_path=output_file)
    if not quiet:  # pragma: no cover
      print(f"Failed to write output file: {e}", file=sys.stderr)
    sys.exit(1)
