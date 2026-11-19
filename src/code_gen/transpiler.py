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


def _is_path_under(path: str, parent_dir: str) -> bool:
  """Returns True if path is equal to or nested inside parent_dir."""
  abs_path = os.path.abspath(path)
  abs_parent = os.path.abspath(parent_dir)
  try:
    return os.path.commonpath([abs_parent, abs_path]) == abs_parent
  except ValueError:
    return False


def is_stdlib_stub(
    import_path: str, resolved_path: Optional[str] = None
) -> bool:
  """Returns True if an import refers to a hand-written stdlib runtime stub."""
  if is_builtin_module(import_path) or import_path.startswith("std."):
    return True
  if not resolved_path:
    return False
  from src.semantics.module_resolver import find_sapphire_lib_dir

  lib_dir = find_sapphire_lib_dir()
  if not lib_dir:
    return False
  std_dir = os.path.join(lib_dir, "std")
  if not _is_path_under(resolved_path, std_dir):
    return False
  stem = os.path.splitext(os.path.abspath(resolved_path))[0]
  return os.path.exists(stem + ".lua") or os.path.exists(stem + ".py")


def _is_prebuilt_lib_module(resolved_path: str, ext: str) -> bool:
  """Returns True if resolved_path is under Sapphire lib/ with a prebuilt output."""
  from src.semantics.module_resolver import find_sapphire_lib_dir

  lib_dir = find_sapphire_lib_dir()
  if not lib_dir or not _is_path_under(resolved_path, lib_dir):
    return False
  stem = os.path.splitext(os.path.abspath(resolved_path))[0]
  return os.path.exists(stem + ext)


def _parse_and_check(
    input_file: str, quiet: bool, raise_on_error: bool
) -> tuple[Any, str]:
  """Lexes, parses, builds AST, and runs semantic analysis on *input_file*."""
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

  error_listener = CustomErrorListener(
      file_path=input_file, source_content=input_stream, quiet=quiet
  )

  lexer = SapphireLexer(input_stream)
  lexer.removeErrorListeners()
  lexer.addErrorListener(error_listener)

  parser = SapphireParser(CommonTokenStream(lexer))
  parser.removeErrorListeners()
  parser.addErrorListener(error_listener)

  if not quiet:
    print("Parsing program to Parse Tree...")
  tree = parser.program()

  if error_listener.errors > 0:
    err_text = (
        "\n".join(error_listener.error_messages)
        if error_listener.error_messages
        else f"Parsing failed with {error_listener.errors} syntax error(s)."
    )
    if raise_on_error:
      raise SapphireSyntaxError(err_text, file_path=input_file)
    if not quiet:
      print(
          f"\nParsing failed with {error_listener.errors} syntax error(s).",
          file=sys.stderr,
      )
    sys.exit(1)

  if not quiet:
    print("Building AST...")
  ast = ASTBuilder().visit(tree)

  if not quiet:
    print("Running Semantic Analysis & Type Checker...")
  src_content = str(input_stream)
  checker = TypeChecker(source_file_path=input_file, source_content=src_content)
  try:
    checker.check(ast)
    if checker.warnings and not quiet:
      print("\nWarnings:\n" + "\n".join(checker.warnings), file=sys.stderr)
  except SemanticError as e:
    if checker.warnings and not quiet:
      print("\nWarnings:\n" + "\n".join(checker.warnings), file=sys.stderr)
    if raise_on_error:
      raise e
    if not quiet:  # pragma: no cover
      print(f"\nSemantic Analysis failed with errors:\n{e}", file=sys.stderr)
    sys.exit(1)

  return ast, src_content


def _transpile_imports(
    ast: Any,
    input_file: str,
    target: str,
    ext: str,
    isolated_root: Optional[str],
    visited: set,
    sourcemap: bool,
    test_mode: bool,
    dev_mode: bool,
    quiet: bool,
    raise_on_error: bool,
    use_runtime_module: bool,
) -> None:
  """Recursively transpiles non-stdlib imported Sapphire modules."""
  from src.semantics.module_resolver import resolve_module_path

  for imp in getattr(ast, "imports", []):
    sub_source = resolve_module_path(imp.path, source_file_path=input_file)
    if is_stdlib_stub(imp.path, sub_source) or not sub_source:
      continue
    if isolated_root is not None:
      if _is_prebuilt_lib_module(sub_source, ext):
        continue
      sub_output = os.path.join(isolated_root, *imp.path.split(".")) + ext
      os.makedirs(os.path.dirname(sub_output), exist_ok=True)
    else:
      sub_output = os.path.splitext(sub_source)[0] + ext
    transpile_file(
        sub_source,
        sub_output,
        target=target,
        visited=visited,
        sourcemap=sourcemap,
        test_mode=test_mode,
        dev_mode=dev_mode,
        quiet=quiet,
        raise_on_error=raise_on_error,
        use_runtime_module=use_runtime_module,
        _output_root=isolated_root,
    )


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
    _output_root: Optional[str] = None,
) -> str:
  """Transpiles Sapphire source file into target language (Python or Lua 5.1)."""
  if visited is None:
    visited = set()

  abs_input_file = os.path.abspath(input_file)
  if abs_input_file in visited:
    return output_file or ""
  visited.add(abs_input_file)

  target_info = TranspilerRegistry.get(target)
  ext = target_info.default_extension

  # Isolate build outputs when writing outside the input file's directory tree.
  isolated_root = _output_root
  if isolated_root is None and output_file is not None:
    input_dir = os.path.dirname(abs_input_file)
    output_dir = os.path.dirname(os.path.abspath(output_file))
    if not _is_path_under(output_dir, input_dir):
      isolated_root = output_dir

  if not output_file:
    output_file = os.path.splitext(input_file)[0] + ext

  ast, src_content = _parse_and_check(input_file, quiet, raise_on_error)
  _transpile_imports(
      ast,
      input_file,
      target,
      ext,
      isolated_root,
      visited,
      sourcemap,
      test_mode,
      dev_mode,
      quiet,
      raise_on_error,
      use_runtime_module,
  )

  sm_builder = None
  src_filename = os.path.basename(input_file)
  if target_info.name in ("lua", "love2d", "love"):
    if sourcemap:
      sm_builder = SourceMapBuilder(src_filename, src_content)
    transpiler = target_info.factory(
        source_file=src_filename,
        source_map_builder=sm_builder,
        test_mode=test_mode,
        dev_mode=dev_mode,
        use_runtime_module=use_runtime_module,
    )
  elif target_info.name == "python":
    transpiler = target_info.factory(
        test_mode=test_mode, use_runtime_module=use_runtime_module
    )
  else:
    transpiler = target_info.factory(test_mode=test_mode)

  if not quiet:
    print(f"Transpiling to {target_info.display_name}...")
  generated_code = transpiler.transpile(ast)
  target_name = target_info.display_name

  try:
    if use_runtime_module and target_info.name in (
        "python",
        "lua",
        "love2d",
        "love",
    ):
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
      print(
          f"\nCompilation successful! {target_name} output written to:\n"
          f"{output_file}"
      )
    return output_file
  except Exception as e:
    if raise_on_error:
      raise SapphireTranspileError(
          f"Failed to write output file: {e}", file_path=output_file
      )
    if not quiet:  # pragma: no cover
      print(f"Failed to write output file: {e}", file=sys.stderr)
    sys.exit(1)
