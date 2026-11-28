"""Transpiler driver facade for Sapphire programming language.

Provides the primary high-level compilation driver API (`transpile_file`)
which orchestrates lexing, parsing, AST building, type checking, and code
generation dispatch to target backends (Python or Lua 5.1).
"""

import os
import sys
from typing import Any

from antlr4 import CommonTokenStream, FileStream

from sapphire.code_gen.intrinsics import is_builtin_module
from sapphire.code_gen.lua_transpiler import (
  LUA_RUNTIME_MODULE_EXPORTS,
  LUA_RUNTIME_PREAMBLE,
  LuaTranspiler,
)
from sapphire.code_gen.python_transpiler import (
  PYTHON_RUNTIME_PREAMBLE,
  RUNTIME_PREAMBLE,
  PythonTranspiler,
  Transpiler,
)
from sapphire.code_gen.source_map import SourceMapBuilder
from sapphire.code_gen.transpiler_registry import TranspilerRegistry
from sapphire.common.errors import (
  SapphireError,
  SapphireSyntaxError,
  SapphireTranspileError,
  SapphireTypeError,
  SemanticError,
)
from sapphire.parser.ast_builder import ASTBuilder
from sapphire.parser.error_listener import (
  CustomErrorListener,
  format_syntax_error_message,
)
from sapphire.parser.gen.SapphireLexer import SapphireLexer
from sapphire.parser.gen.SapphireParser import SapphireParser
from sapphire.semantics.type_checker import TypeChecker

__all__ = [
  "CustomErrorListener",
  "LUA_RUNTIME_MODULE_EXPORTS",
  "LUA_RUNTIME_PREAMBLE",
  "LuaTranspiler",
  "PYTHON_RUNTIME_PREAMBLE",
  "PythonTranspiler",
  "RUNTIME_PREAMBLE",
  "SapphireError",
  "SapphireSyntaxError",
  "SapphireTranspileError",
  "SapphireTypeError",
  "SemanticError",
  "Transpiler",
  "emit_runtime_module",
  "format_syntax_error_message",
  "is_stdlib_stub",
  "transpile_file",
]


def emit_runtime_module(output_dir: str, target: str = "python") -> str:
  """Writes the shared Sapphire runtime module (`_sapphire_runtime.py` or
  `_sapphire_runtime.lua`) to `output_dir`.
  """
  os.makedirs(output_dir, exist_ok=True)
  target_lower = target.lower()
  if target_lower in ("lua", "lua5.1", "love2d", "love"):
    rt_path = os.path.join(output_dir, "_sapphire_runtime.lua")
    with open(rt_path, "w", encoding="utf-8") as f:
      f.write(LUA_RUNTIME_PREAMBLE + "\n" + LUA_RUNTIME_MODULE_EXPORTS)
    return rt_path
  rt_path = os.path.join(output_dir, "_sapphire_runtime.py")
  # Export all symbols including leading-underscore helpers so `from
  # _sapphire_runtime import *` imports them
  all_line = (
    "\n__all__ = [name for name in globals() if not name.startswith('__')]\n"
  )
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
  import_path: str, resolved_path: str | None = None
) -> bool:
  """Returns True if an import refers to a hand-written stdlib runtime stub."""
  if is_builtin_module(import_path) or import_path.startswith("std."):
    return True
  if not resolved_path:
    return False
  from sapphire.semantics.module_resolver import find_sapphire_lib_dir

  lib_dir = find_sapphire_lib_dir()
  if not lib_dir:
    return False
  std_dir = os.path.join(lib_dir, "std")
  if not _is_path_under(resolved_path, std_dir):
    return False
  stem = os.path.splitext(os.path.abspath(resolved_path))[0]
  return os.path.exists(stem + ".lua") or os.path.exists(stem + ".py")


def _is_prebuilt_lib_module(resolved_path: str, ext: str) -> bool:
  """Returns True if resolved_path is under Sapphire lib/ with a fresh prebuilt
  output.
  """
  from sapphire.semantics.module_resolver import find_sapphire_lib_dir

  lib_dir = find_sapphire_lib_dir()
  if not lib_dir or not _is_path_under(resolved_path, lib_dir):
    return False
  abs_src = os.path.abspath(resolved_path)
  prebuilt_path = os.path.splitext(abs_src)[0] + ext
  if not os.path.exists(prebuilt_path):
    return False
  try:
    return os.path.getmtime(prebuilt_path) >= os.path.getmtime(abs_src)
  except OSError:
    return False


def _parse_and_check(
  input_file: str,
  quiet: bool,
  raise_on_error: bool,
  verbose: bool = False,
) -> tuple[Any, str, Any]:
  """Lexes, parses, builds AST, and runs semantic analysis on *input_file*."""
  if verbose and not quiet:
    print(f"Reading source file: {input_file}...")

  try:
    input_stream = FileStream(input_file, encoding="utf-8")
  except Exception as e:
    if raise_on_error:
      raise SapphireError(
        f"Failed to read file: {e}", file_path=input_file
      ) from e
    if not quiet:  # pragma: no cover
      print(f"Failed to read file: {e}", file=sys.stderr)
    sys.exit(1)

  error_listener = CustomErrorListener(
    file_path=input_file,
    source_content=input_stream,
    quiet=quiet or raise_on_error,
  )

  lexer = SapphireLexer(input_stream)
  lexer.removeErrorListeners()
  lexer.addErrorListener(error_listener)

  parser = SapphireParser(CommonTokenStream(lexer))
  parser.removeErrorListeners()
  parser.addErrorListener(error_listener)

  if verbose and not quiet:
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

  if verbose and not quiet:
    print("Building AST...")
  src_content = str(input_stream)
  try:
    ast: Any = ASTBuilder().visit(tree)
  except SapphireSyntaxError as e:
    if not e.file_path:
      e.file_path = input_file
    if raise_on_error:
      raise
    if not quiet:
      print(f"\nSyntax Error: {e}", file=sys.stderr)
    sys.exit(1)

  if verbose and not quiet:
    print("Running Semantic Analysis & Type Checker...")
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

  return ast, src_content, checker.context


def _ensure_isolated_python_packages(
  isolated_root: str, sub_output: str
) -> None:
  """Writes pkgutil.extend_path __init__.py markers for isolated Python
  packages.

  Regular packages (with __init__.py) take precedence over namespace packages
  under PEP 420 regardless of sys.path order. Emitting extend_path markers lets
  freshly transpiled modules under isolated_root (e.g. tmp_dir/lib/love2d/)
  shadow stale prebuilt files in the repo's regular lib/ package while still
  allowing hand-written stdlib modules (e.g. lib/std/testing.py) to resolve.
  """
  abs_root = os.path.abspath(isolated_root)
  curr = os.path.dirname(os.path.abspath(sub_output))
  while curr != abs_root and _is_path_under(curr, abs_root):
    init_py = os.path.join(curr, "__init__.py")
    if not os.path.exists(init_py):
      with open(init_py, "w", encoding="utf-8") as f:
        f.write(
          "from pkgutil import extend_path\n"
          "__path__ = extend_path(__path__, __name__)\n"
        )
    parent = os.path.dirname(curr)
    if parent == curr:
      break
    curr = parent


def _transpile_imports(
  ast: Any,
  input_file: str,
  target: str,
  ext: str,
  isolated_root: str | None,
  visited: set,
  sourcemap: bool,
  test_mode: bool,
  dev_mode: bool,
  quiet: bool,
  raise_on_error: bool,
  use_runtime_module: bool,
  verbose: bool = False,
) -> None:
  """Recursively transpiles non-stdlib imported Sapphire modules."""
  from sapphire.semantics.module_resolver import resolve_module_path

  for imp in getattr(ast, "imports", []):
    sub_source = resolve_module_path(imp.path, source_file_path=input_file)
    if is_stdlib_stub(imp.path, sub_source) or not sub_source:
      continue
    if isolated_root is not None:
      if _is_prebuilt_lib_module(sub_source, ext):
        continue
      sub_output = os.path.join(isolated_root, *imp.path.split(".")) + ext
      os.makedirs(os.path.dirname(sub_output), exist_ok=True)
      if ext == ".py":
        _ensure_isolated_python_packages(isolated_root, sub_output)
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
      verbose=verbose,
    )


def _instantiate_transpiler(
  target_info: Any,
  src_filename: str,
  sm_builder: SourceMapBuilder | None,
  test_mode: bool,
  dev_mode: bool,
  use_runtime_module: bool,
  semantic_context: Any = None,
) -> Any:
  """Constructs a target transpiler passing only kwargs accepted by its factory.
  """
  import inspect

  if target_info.name in ("lua", "love2d", "love"):
    return target_info.factory(
      source_file=src_filename,
      source_map_builder=sm_builder,
      test_mode=test_mode,
      dev_mode=dev_mode,
      use_runtime_module=use_runtime_module,
      semantic_context=semantic_context,
    )
  if target_info.name == "python":
    return target_info.factory(
      test_mode=test_mode,
      use_runtime_module=use_runtime_module,
      semantic_context=semantic_context,
    )

  try:
    sig = inspect.signature(target_info.factory)
    params = sig.parameters
    accepts_var_kw = any(
      p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()
    )
    if accepts_var_kw or "test_mode" in params:
      inst = target_info.factory(test_mode=test_mode)
      inst.semantic_context = semantic_context
      return inst
  except (TypeError, ValueError):
    pass
  inst = target_info.factory()
  inst.semantic_context = semantic_context
  return inst


def _has_local_sp_imports(
  ast: Any, input_file: str, ext: str, isolated_root: str | None
) -> bool:
  """Returns True if *ast* imports at least one non-stdlib local `.sp` file."""
  from sapphire.semantics.module_resolver import resolve_module_path

  for imp in getattr(ast, "imports", []):
    sub_source = resolve_module_path(imp.path, source_file_path=input_file)
    if is_stdlib_stub(imp.path, sub_source) or not sub_source:
      continue
    if isolated_root is not None and _is_prebuilt_lib_module(sub_source, ext):
      continue
    return True
  return False


def transpile_file(
  input_file: str,
  output_file: str | None = None,
  target: str = "python",
  visited: set | None = None,
  sourcemap: bool = True,
  test_mode: bool = False,
  dev_mode: bool = False,
  quiet: bool = False,
  raise_on_error: bool = True,
  use_runtime_module: bool | None = None,
  _output_root: str | None = None,
  verbose: bool = False,
) -> str:
  """Transpiles Sapphire source file into target language (Python or Lua 5.1).
  """
  if visited is None:
    visited = set()

  target_info = TranspilerRegistry.get(target)
  ext = target_info.default_extension

  # Isolate build outputs when writing outside the input file's directory tree.
  abs_input_file = os.path.abspath(input_file)
  isolated_root = _output_root
  if isolated_root is None and output_file is not None:
    input_dir = os.path.dirname(abs_input_file)
    output_dir = os.path.dirname(os.path.abspath(output_file))
    if not _is_path_under(output_dir, input_dir):
      isolated_root = output_dir

  if not output_file:
    output_file = os.path.splitext(input_file)[0] + ext

  if abs_input_file in visited:
    return output_file
  visited.add(abs_input_file)

  ast, src_content, semantic_context = _parse_and_check(
    input_file, quiet, raise_on_error, verbose=verbose
  )
  resolved_use_rt = (
    use_runtime_module
    if use_runtime_module is not None
    else (
      target_info.name in ("python", "lua", "love2d", "love")
      and _has_local_sp_imports(ast, input_file, ext, isolated_root)
    )
  )
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
    resolved_use_rt,
    verbose=verbose,
  )

  sm_builder = None
  src_filename = os.path.basename(input_file)
  if target_info.name in ("lua", "love2d", "love") and sourcemap:
    sm_builder = SourceMapBuilder(src_filename, src_content)
  transpiler = _instantiate_transpiler(
    target_info,
    src_filename,
    sm_builder,
    test_mode,
    dev_mode,
    resolved_use_rt,
    semantic_context=semantic_context,
  )

  if verbose and not quiet:
    print(f"Transpiling to {target_info.display_name}...")
  generated_code = transpiler.transpile(ast)
  target_name = target_info.display_name

  try:
    if resolved_use_rt and target_info.name in (
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
      if verbose and not quiet:
        print(f"Source map generated at: {map_output_file}")

    if verbose and not quiet:
      print(
        f"\nCompilation successful! {target_name} output written to:\n"
        f"{output_file}"
      )
    return output_file
  except Exception as e:
    if raise_on_error:
      raise SapphireTranspileError(
        f"Failed to write output file: {e}", file_path=output_file
      ) from e
    if not quiet:  # pragma: no cover
      print(f"Failed to write output file: {e}", file=sys.stderr)
    sys.exit(1)
