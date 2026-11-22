"""Unified CLI entry point for the Sapphire programming language.

Provides commands to compile Sapphire code (`build`) and compile & run in one
step (`run`).
"""

import argparse
import json
import os
import shutil
import sys
import subprocess
import time
from typing import Any, Dict, List, Optional, Set

src_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
root_dir = os.path.abspath(os.path.join(src_dir, ".."))
if root_dir not in sys.path:  # pragma: no cover
  sys.path.insert(0, root_dir)
if src_dir not in sys.path:  # pragma: no cover
  sys.path.insert(0, src_dir)

from antlr4 import FileStream, CommonTokenStream
from src.cli.diagnostics import Diagnostic, format_diagnostic
from src.code_gen.transpiler import _instantiate_transpiler, is_stdlib_stub, transpile_file
from src.code_gen.transpiler_registry import TranspilerRegistry
from src.common.errors import SapphireError, SapphireSyntaxError
from src.parser.ast_builder import ASTBuilder
from src.parser.error_listener import CustomErrorListener
from src.parser.gen.SapphireLexer import SapphireLexer
from src.parser.gen.SapphireParser import SapphireParser
from src.semantics.module_resolver import find_sapphire_lib_dir, resolve_module_path
from src.semantics.type_checker import TypeChecker, SemanticError

TARGET_CHOICES = ["python", "lua", "lua5.1", "love2d", "love"]


def _collect_sp_watch_files(root_path: str) -> Dict[str, float]:
  """Collects modification times for all .sp files in the project and source directory."""
  watch_files = {}
  paths_to_check = {
      os.path.dirname(os.path.abspath(root_path)) or ".",
      os.getcwd(),
  }
  for dir_path in paths_to_check:
    for root, _, files in os.walk(dir_path):
      for f in files:
        if f.endswith(".sp"):
          p = os.path.join(root, f)
          try:
            watch_files[p] = os.path.getmtime(p)
          except OSError:
            pass
  return watch_files


def _prepare_exec_env() -> Dict[str, str]:
  """Prepares execution environment with standard Sapphire library paths."""
  env = os.environ.copy()
  discovered_lib = find_sapphire_lib_dir()
  lib_dir = discovered_lib or os.path.join(root_dir, "lib")
  lib_parent = os.path.dirname(lib_dir)

  # Do NOT add `lib/std` directly to PYTHONPATH: `lib/std/math.py`,
  # `lib/std/os.py`, and `lib/std/time.py` would shadow Python's stdlib
  # modules whenever transpiled code or `@extern` bindings import them.
  py_paths = []
  for p in (root_dir, lib_parent, lib_dir):
    if p and p not in py_paths:
      py_paths.append(p)
  if "PYTHONPATH" in env and env["PYTHONPATH"]:
    py_paths.append(env["PYTHONPATH"])
  env["PYTHONPATH"] = os.pathsep.join(py_paths)

  lua_paths = [
      f"{lib_dir}/?.lua",
      f"{lib_dir}/?/init.lua",
      f"{lib_dir}/love2d/?.lua",
      f"{lib_parent}/?.lua",
  ]
  if "LUA_PATH" in env and env["LUA_PATH"]:
    lua_paths.append(env["LUA_PATH"])
  else:
    lua_paths.append(";;")
  env["LUA_PATH"] = ";".join(lua_paths)
  return env


def _run_dev_watcher(source_file: str, output_file: str, target: str, sourcemap: bool, cmd: List[str]):
  """Spawns process and watches source files for live hot-reloading."""
  print(f"\n[Sapphire Dev Mode] Starting process with live hot-reloading: {' '.join(cmd)}")
  print("[Sapphire Dev Mode] Watching for file changes... (Press Ctrl+C to stop)")

  exec_env = _prepare_exec_env()
  proc = subprocess.Popen(cmd, env=exec_env)
  watch_files = _collect_sp_watch_files(source_file)

  try:
    while True:
      time.sleep(0.3)
      if proc.poll() is not None:
        if target in ("love2d", "love"):
          sys.exit(proc.returncode)

      current_watch_files = _collect_sp_watch_files(source_file)
      changed = False
      for path, mtime in current_watch_files.items():
        if path not in watch_files or watch_files[path] != mtime:
          changed = True
          break

      if changed:
        watch_files = current_watch_files
        print("\n[Sapphire Dev Mode] File change detected, re-transpiling...")
        try:
          transpile_file(source_file, output_file, target=target, sourcemap=sourcemap, dev_mode=True, quiet=False)
          if target in ("love2d", "love"):
            run_dir = os.path.dirname(os.path.abspath(output_file)) or "."
            marker_path = os.path.join(run_dir, ".sapphire_reload")
            rel_out = os.path.relpath(output_file, run_dir)
            with open(marker_path, "w", encoding="utf-8") as mf:
              mf.write(f"{rel_out}\n")
          print("[Sapphire Dev Mode] Re-compilation complete.")
          if target not in ("love2d", "love"):
            if proc.poll() is None:
              proc.terminate()
              try:
                proc.wait(timeout=1.0)
              except subprocess.TimeoutExpired:
                proc.kill()
            print("\n--- Re-executing Sapphire Program ---")
            proc = subprocess.Popen(cmd, env=exec_env)
        except Exception as err:
          print(f"[Sapphire Dev Mode Error] Compilation failed: {err}", file=sys.stderr)

  except KeyboardInterrupt:
    print("\n[Sapphire Dev Mode] Shutting down...")
    if proc.poll() is None:
      proc.terminate()
      try:
        proc.wait(timeout=1.0)
      except subprocess.TimeoutExpired:
        proc.kill()
    sys.exit(0)


def _find_love_binary() -> Optional[str]:
  """Locates Love2D executable across PATH and standard OS installation paths."""
  binary = shutil.which("love") or shutil.which("love2d")
  if binary:
    return binary

  mac_candidates = [
      "/Applications/love.app/Contents/MacOS/love",
      os.path.expanduser("~/Applications/love.app/Contents/MacOS/love"),
      "/opt/homebrew/bin/love",
      "/usr/local/bin/love",
  ]
  for candidate in mac_candidates:
    if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
      return candidate

  return None


def _find_lua_binary() -> Optional[str]:
  """Locates Lua interpreter across PATH and standard OS installation paths."""
  binary = shutil.which("lua") or shutil.which("luajit") or shutil.which("lua5.1")
  if binary:
    return binary

  candidates = [
      "/opt/homebrew/bin/lua",
      "/opt/homebrew/bin/luajit",
      "/usr/local/bin/lua",
      "/usr/local/bin/luajit",
      "/usr/bin/lua",
  ]
  for candidate in candidates:
    if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
      return candidate

  return None


def run_command(args):
  """Handles `run` subcommand: compiles and executes a Sapphire file."""

  source_file = args.source
  if not os.path.exists(source_file):
    print(f"Error: File '{source_file}' not found.", file=sys.stderr)
    sys.exit(1)

  target = getattr(args, "target", "python").lower()
  dev_mode = getattr(args, "dev", False)
  ext = ".lua" if target in ("lua", "lua5.1", "love2d", "love") else ".py"
  output_file = args.output or (os.path.splitext(source_file)[0] + ext)
  sourcemap = not getattr(args, "no_sourcemap", False)
  try:
    out_path = transpile_file(source_file, output_file, target=target, sourcemap=sourcemap, dev_mode=dev_mode)
  except SapphireError as e:
    print(f"Error: {e}", file=sys.stderr)
    sys.exit(1)

  exec_env = _prepare_exec_env()

  if target in ("love2d", "love"):
    love_bin = _find_love_binary()
    if not love_bin:
      print("Error: Love2D executable ('love') not found in PATH or standard installation directories (/Applications/love.app).", file=sys.stderr)
      sys.exit(1)
    run_dir = os.path.dirname(os.path.abspath(output_file)) or "."
    cmd = [love_bin, run_dir]
    if dev_mode:
      _run_dev_watcher(source_file, output_file, target, sourcemap, cmd)
      return
    else:
      print("\n--- Executing Love2D Engine ---")
      result = subprocess.run(cmd, env=exec_env)
      sys.exit(result.returncode)

  print("\n--- Executing Sapphire Program ---")
  if target in ("lua", "lua5.1"):
    lua_bin = _find_lua_binary()
    if not lua_bin:
      print("Error: Lua interpreter ('lua', 'luajit', or 'lua5.1')"
            " not found in PATH.", file=sys.stderr)
      sys.exit(1)
    cmd = [lua_bin, out_path]
  else:
    cmd = [sys.executable, out_path]

  if dev_mode:
    _run_dev_watcher(source_file, output_file, target, sourcemap, cmd)
  else:
    result = subprocess.run(cmd, env=exec_env)
    sys.exit(result.returncode)


def build_command(args):
  """Handles `build` subcommand: compiles a Sapphire file without executing."""

  source_file = args.source
  if not os.path.exists(source_file):
    print(f"Error: File '{source_file}' not found.", file=sys.stderr)
    sys.exit(1)

  target = getattr(args, "target", "python").lower()
  dev_mode = getattr(args, "dev", False)
  ext = ".lua" if target in ("lua", "lua5.1", "love2d", "love") else ".py"
  output_file = args.output or (os.path.splitext(source_file)[0] + ext)
  sourcemap = not getattr(args, "no_sourcemap", False)
  try:
    transpile_file(source_file, output_file, target=target, sourcemap=sourcemap, dev_mode=dev_mode)
  except SapphireError as e:
    print(f"Error: {e}", file=sys.stderr)
    sys.exit(1)


def parse_command(args):
  """Handles `parse` subcommand: parses source and prints parse tree preview."""
  source_file = args.source
  if not os.path.exists(source_file):
    print(f"Error: File '{source_file}' not found.", file=sys.stderr)
    sys.exit(1)

  print(f"Reading source file: {source_file}...")
  try:
    input_stream = FileStream(source_file, encoding="utf-8")
  except Exception as e:  # pragma: no cover
    print(f"Failed to read file: {e}", file=sys.stderr)
    sys.exit(1)

  error_listener = CustomErrorListener(file_path=source_file, source_content=input_stream)
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
    print(f"\nParsing completed with {error_listener.errors} error(s).", file=sys.stderr)
    sys.exit(1)
  else:
    print("\nParsing completed successfully with 0 errors!")
    print("\nParse Tree Preview:")
    tree_str = tree.toStringTree(recog=parser)
    if len(tree_str) > 500:
      print(tree_str[:500] + " ... [TRUNCATED]")
    else:
      print(tree_str)


def dump_ast_command(args):
  """Handles `dump-ast` subcommand: parses source and outputs formatted JSON AST."""
  import json
  source_file = args.source
  if not os.path.exists(source_file):
    print(f"Error: File '{source_file}' not found.", file=sys.stderr)
    sys.exit(1)

  print(f"Reading source file: {source_file}...")
  try:
    input_stream = FileStream(source_file, encoding="utf-8")
  except Exception as e:  # pragma: no cover
    print(f"Failed to read file: {e}", file=sys.stderr)
    sys.exit(1)

  error_listener = CustomErrorListener(file_path=source_file, source_content=input_stream)
  lexer = SapphireLexer(input_stream)
  lexer.removeErrorListeners()
  lexer.addErrorListener(error_listener)
  stream = CommonTokenStream(lexer)

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
  builder = ASTBuilder()
  try:
    ast = builder.visit(tree)
  except SapphireError as e:
    print(f"Error: {e}", file=sys.stderr)
    sys.exit(1)

  print("AST built successfully!")
  print("\nAST JSON Representation (Preview):")
  ast_dict = ast.to_dict()
  ast_json = json.dumps(ast_dict, indent=2)
  if len(ast_json) > 1000:
    print(ast_json[:1000] + "\n\n... [TRUNCATED] ...")
  else:
    print(ast_json)


def _validate_target_lowering(
    ast: Any,
    file_path: str,
    target: str,
    error_diags: List[Diagnostic],
    formatted_errors: List[str],
) -> None:
  """Runs in-memory target lowering (e.g. `-t lua`) to catch backend errors."""
  target_info = TranspilerRegistry.get(target)
  src_filename = os.path.basename(file_path)
  transpiler = _instantiate_transpiler(
      target_info,
      src_filename=src_filename,
      sm_builder=None,
      test_mode=False,
      dev_mode=False,
      use_runtime_module=False,
  )

  try:
    transpiler.transpile(ast)
  except Exception as e:
    msg = f"Target '{target}' lowering failed: {e}"
    error_diags.append(
        Diagnostic(
            severity="error",
            code="E_TRANSPILE",
            message=msg,
            file_path=file_path,
        )
    )
    formatted_errors.append(msg)


def _check_file_recursive(
    file_path: str,
    visited: Set[str],
    files_checked: List[str],
    error_diags: List[Diagnostic],
    warning_diags: List[Diagnostic],
    formatted_errors: List[str],
    formatted_warnings: List[str],
    target: Optional[str],
    quiet: bool,
    check_transitive: bool,
    is_root: bool = False,
) -> None:
  """Checks a Sapphire file and optionally its transitive non-stdlib imports."""
  # Guard against cyclic imports using canonicalized absolute paths.
  abs_path = os.path.abspath(file_path)
  if abs_path in visited:
    return
  visited.add(abs_path)
  files_checked.append(file_path)

  if is_root and not quiet:
    print(f"Reading source file: {file_path}...")

  try:
    input_stream = FileStream(file_path, encoding="utf-8")
  except Exception as e:  # pragma: no cover
    msg = f"Failed to read file: {e}"
    error_diags.append(
        Diagnostic(
            severity="error", code="E_IO", message=msg, file_path=file_path
        )
    )
    formatted_errors.append(msg)
    return

  # Always collect syntax errors quietly; `check_command` prints `formatted_errors`
  # once so root-file syntax errors are never duplicated on stderr.
  error_listener = CustomErrorListener(
      file_path=file_path, source_content=input_stream, quiet=True
  )
  lexer = SapphireLexer(input_stream)
  lexer.removeErrorListeners()
  lexer.addErrorListener(error_listener)

  parser = SapphireParser(CommonTokenStream(lexer))
  parser.removeErrorListeners()
  parser.addErrorListener(error_listener)

  if is_root and not quiet:
    print("Parsing program to Parse Tree...")
  tree = parser.program()

  if error_listener.errors > 0:
    error_diags.extend(error_listener.diagnostics)
    formatted_errors.extend(error_listener.error_messages)
    return

  if is_root and not quiet:
    print("Building AST...")
  try:
    ast = ASTBuilder().visit(tree)
  except SapphireSyntaxError as e:
    diag = Diagnostic(
        severity="error",
        code="E_SYNTAX",
        message=e.message,
        file_path=file_path,
        line=e.line,
        column=e.column,
    )
    error_diags.append(diag)
    formatted_errors.append(
        format_diagnostic(
            error_type="Syntax Error",
            message=e.message,
            file_path=file_path,
            line=e.line,
            column=e.column,
            source_content=str(input_stream),
        )
    )
    return

  if check_transitive:
    for imp in getattr(ast, "imports", []):
      sub_source = resolve_module_path(imp.path, source_file_path=file_path)
      if is_stdlib_stub(imp.path, sub_source) or not sub_source:
        continue
      _check_file_recursive(
          sub_source,
          visited,
          files_checked,
          error_diags,
          warning_diags,
          formatted_errors,
          formatted_warnings,
          target=target,
          quiet=True,
          check_transitive=True,
          is_root=False,
      )

  if is_root and not quiet:
    print("Running Semantic Analysis & Type Checker...")
  checker = TypeChecker(
      source_file_path=file_path, source_content=str(input_stream)
  )
  has_semantic_errors = False
  try:
    checker.check(ast)
  except SemanticError:
    has_semantic_errors = True

  for d in checker.diagnostics:
    if d.severity == "warning":
      warning_diags.append(d)
    else:
      error_diags.append(d)
  formatted_warnings.extend(checker.warnings)
  formatted_errors.extend(checker.errors)

  if not has_semantic_errors and target:
    _validate_target_lowering(
        ast, file_path, target, error_diags, formatted_errors
    )


def check_command(args):
  """Handles `check` subcommand: runs semantic analysis and type checking."""
  source_file = args.source
  json_output = getattr(args, "json", False)
  target = getattr(args, "target", None)
  check_transitive = not getattr(args, "no_transitive", False)

  if not os.path.exists(source_file):
    msg = f"Error: File '{source_file}' not found."
    if json_output:
      diag = Diagnostic(
          severity="error", code="E_FILE_NOT_FOUND", message=msg, file_path=source_file
      )
      print(
          json.dumps(
              {
                  "ok": False,
                  "files_checked": [],
                  "errors": [diag.to_dict()],
                  "warnings": [],
              },
              indent=2,
          )
      )
    else:
      print(msg, file=sys.stderr)
    sys.exit(1)

  visited: Set[str] = set()
  files_checked: List[str] = []
  error_diags: List[Diagnostic] = []
  warning_diags: List[Diagnostic] = []
  formatted_errors: List[str] = []
  formatted_warnings: List[str] = []

  _check_file_recursive(
      source_file,
      visited=visited,
      files_checked=files_checked,
      error_diags=error_diags,
      warning_diags=warning_diags,
      formatted_errors=formatted_errors,
      formatted_warnings=formatted_warnings,
      target=target,
      quiet=json_output,
      check_transitive=check_transitive,
      is_root=True,
  )

  if json_output:
    payload = {
        "ok": len(error_diags) == 0,
        "files_checked": files_checked,
        "errors": [d.to_dict() for d in error_diags],
        "warnings": [d.to_dict() for d in warning_diags],
    }
    print(json.dumps(payload, indent=2))
    if error_diags:
      sys.exit(1)
    return

  if formatted_warnings:
    print("\nWarnings:\n" + "\n".join(formatted_warnings), file=sys.stderr)

  if error_diags:
    if formatted_errors:
      all_syntax = all(d.code == "E_SYNTAX" for d in error_diags)
      header = (
          "\nSyntax Analysis failed with errors:\n"
          if all_syntax
          else "\nSemantic Analysis failed with errors:\n"
      )
      print(header + "\n".join(formatted_errors), file=sys.stderr)
    sys.exit(1)

  print("\nSemantic Analysis completed successfully with 0 errors!")


def test_command(args):
  """Handles `test` subcommand: discovers and executes Sapphire tests."""
  from src.cli.test_runner import run_tests

  target = getattr(args, "target", "python").lower()
  source_paths = getattr(args, "source", ["."]) or ["."]
  filter_pattern = getattr(args, "filter", None)
  sourcemap = not getattr(args, "no_sourcemap", False)
  json_output = getattr(args, "json", False)
  exit_code = run_tests(
      source_paths,
      target=target,
      filter_pattern=filter_pattern,
      sourcemap=sourcemap,
      json_output=json_output,
  )
  sys.exit(exit_code)


def lsp_command(args):
  """Handles `lsp` subcommand: starts the Sapphire LSP server over stdio."""
  from src.lsp.server import main as lsp_main
  lsp_main()


def main():
  parser = argparse.ArgumentParser(
      prog="sapphire",
      description="Sapphire compiler & runner CLI")

  subparsers = parser.add_subparsers(dest="command", help="Available commands")

  # `build` subcommand
  build_parser = subparsers.add_parser(
      "build", help="Transpile Sapphire source (.sp) to Python or Lua")
  build_parser.add_argument("source", help="Path to Sapphire source file (.sp)")
  build_parser.add_argument(
      "-o", "--output", help="Optional output path for generated target file")
  build_parser.add_argument(
      "-t", "--target", choices=TARGET_CHOICES, default="python",
      help="Code generation target (default: python)")
  build_parser.add_argument(
      "--dev", action="store_true",
      help="Enable development mode with in-place hot-reloading")
  build_parser.add_argument(
      "--no_sourcemap", action="store_true",
      help="Disable source map generation (.lua.map) for Lua targets")
  build_parser.set_defaults(func=build_command)

  # `run` subcommand
  run_parser = subparsers.add_parser(
      "run", help="Transpile and immediately execute Sapphire source (.sp)")
  run_parser.add_argument("source", help="Path to Sapphire source file (.sp)")
  run_parser.add_argument(
      "-o", "--output", help="Optional output path for generated target file")
  run_parser.add_argument(
      "-t", "--target", choices=TARGET_CHOICES, default="python",
      help="Code generation target (default: python)")
  run_parser.add_argument(
      "--dev", action="store_true",
      help="Enable development mode with file watching and live hot-reloading")
  run_parser.add_argument(
      "--no_sourcemap", action="store_true",
      help="Disable source map generation (.lua.map) for Lua targets")
  run_parser.set_defaults(func=run_command)

  # `test` subcommand
  test_parser = subparsers.add_parser(
      "test", help="Discover and execute Sapphire tests")
  test_parser.add_argument(
      "source", nargs="*", default=["."],
      help="Path(s) to Sapphire source file(s) (.sp) or directories (default: .)")
  test_parser.add_argument(
      "-t", "--target", choices=TARGET_CHOICES, default="python",
      help="Code generation target (default: python)")
  test_parser.add_argument(
      "--filter", help="Filter tests by substring matching test name")
  test_parser.add_argument(
      "--no_sourcemap", action="store_true",
      help="Disable source map generation (.lua.map) for Lua targets")
  test_parser.add_argument(
      "--json", action="store_true",
      help="Emit machine-readable JSON test summary")
  test_parser.set_defaults(func=test_command)

  # `lsp` subcommand
  lsp_parser = subparsers.add_parser(
      "lsp", help="Start the Sapphire Language Server over stdio")
  lsp_parser.set_defaults(func=lsp_command)

  # `parse` subcommand
  parse_parser = subparsers.add_parser(
      "parse", help="Parse Sapphire source (.sp) and print concrete parse tree")
  parse_parser.add_argument("source", help="Path to Sapphire source file (.sp)")
  parse_parser.set_defaults(func=parse_command)

  # `dump-ast` subcommand
  dump_ast_parser = subparsers.add_parser(
      "dump-ast", help="Parse Sapphire source (.sp) and dump AST in JSON format")
  dump_ast_parser.add_argument("source", help="Path to Sapphire source file (.sp)")
  dump_ast_parser.set_defaults(func=dump_ast_command)

  # `check` subcommand
  check_parser = subparsers.add_parser(
      "check", help="Run semantic analysis and type checking without generating code")
  check_parser.add_argument("source", help="Path to Sapphire source file (.sp)")
  check_parser.add_argument(
      "-t", "--target", choices=TARGET_CHOICES, default=None,
      help="Optional target backend to validate in-memory lowering")
  check_parser.add_argument(
      "--no-transitive", action="store_true",
      help="Skip checking transitive non-stdlib imported modules")
  check_parser.add_argument(
      "--json", action="store_true",
      help="Emit machine-readable JSON diagnostic report")
  check_parser.set_defaults(func=check_command)

  # Handle shortcut invocation (e.g. `sapphire samples/overview.sp` or
  # `sapphire -t lua samples/overview.sp`) without mutating sys.argv.
  known_commands = {"build", "run", "test", "lsp", "parse", "dump-ast", "check"}
  argv = list(sys.argv[1:])
  if (
      argv
      and argv[0] not in known_commands
      and "-h" not in argv
      and "--help" not in argv
  ):
    argv = ["run"] + argv

  args = parser.parse_args(argv)

  if hasattr(args, "func"):
    args.func(args)
  else:
    parser.print_help()


if __name__ == "__main__":  # pragma: no cover
  main()
