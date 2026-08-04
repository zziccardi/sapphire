"""Test discovery and execution engine for Sapphire (`sapphire test`)."""

import glob
import importlib.util
import os
import shutil
import subprocess
import sys
import time
from typing import List, Tuple, Dict, Any, Optional

from antlr4 import FileStream, CommonTokenStream
from antlr4.error.ErrorListener import ErrorListener

try:
  from parser.gen.SapphireLexer import SapphireLexer
  from parser.gen.SapphireParser import SapphireParser
  from parser.ast_builder import ASTBuilder
  from parser.ast import FuncDeclNode, ImplBlockNode, IdentifierNode
  from code_gen.transpiler import transpile_file
  from code_gen.source_map import SourceMapBuilder
except ModuleNotFoundError:  # pragma: no cover
  from src.parser.gen.SapphireLexer import SapphireLexer
  from src.parser.gen.SapphireParser import SapphireParser
  from src.parser.ast_builder import ASTBuilder
  from src.parser.ast import FuncDeclNode, ImplBlockNode, IdentifierNode
  from src.code_gen.transpiler import transpile_file
  from src.code_gen.source_map import SourceMapBuilder


class TestDiscoveryError(Exception):
  pass


def find_sp_files(path: str) -> List[str]:
  """Finds all .sp files in a path (file or directory)."""
  if os.path.isfile(path):
    return [path]
  elif os.path.isdir(path):
    results = []
    for root, _, files in os.walk(path):
      for f in files:
        if f.endswith(".sp"):
          results.append(os.path.join(root, f))
    results.sort()
    return results
  else:
    print(f"Error: Path '{path}' not found.", file=sys.stderr)
    sys.exit(1)


def parse_ast(sp_file: str):
  """Parses a Sapphire file and returns its AST root node."""
  input_stream = FileStream(sp_file, encoding="utf-8")
  lexer = SapphireLexer(input_stream)
  stream = CommonTokenStream(lexer)
  parser = SapphireParser(stream)
  tree = parser.program()
  builder = ASTBuilder()
  return builder.visit(tree)


def discover_tests(ast) -> Tuple[List[str], Dict[str, List[str]]]:
  """Discovers standalone @test functions and struct-based TestCase methods.

  Returns:
    (standalone_test_funcs, {struct_name: [test_methods]})
  """
  standalone_tests = []
  suite_tests = {}

  # Check imports to ensure std.testing is referenced
  has_testing_import = False
  for imp in getattr(ast, "imports", []):
    if imp.path == "std.testing" or imp.path.startswith("std.testing"):
      has_testing_import = True
      break

  # Discover standalone @test functions
  for stmt in getattr(ast, "declarations", []):
    if isinstance(stmt, FuncDeclNode):
      for ann in getattr(stmt, "annotations", []):
        if ann.name == "test":
          standalone_tests.append(stmt.name)

    # Discover impl blocks for structs implementing TestCase
    elif isinstance(stmt, ImplBlockNode):
      trait_name = stmt.trait_name
      if trait_name and ("TestCase" in trait_name or trait_name == "TestCase"):
        struct_name = stmt.struct_name
        test_methods = []
        for member in stmt.members:
          func_decl = getattr(member, "func_decl", member)
          if isinstance(func_decl, FuncDeclNode) and func_decl.name.startswith("test_"):
            test_methods.append(func_decl.name)
        if test_methods:
          suite_tests[struct_name] = test_methods

  return standalone_tests, suite_tests


def get_source_line(sp_file: str, lineno: int) -> Optional[str]:
  """Reads a specific 1-indexed line from a source file."""
  try:
    with open(sp_file, "r", encoding="utf-8") as f:
      lines = f.readlines()
      if 1 <= lineno <= len(lines):
        return lines[lineno - 1].rstrip("\r\n")
  except Exception:
    pass
  return None


def run_tests_python(
    sp_file: str,
    standalone_tests: List[str],
    suite_tests: Dict[str, List[str]],
    filter_pattern: Optional[str] = None,
) -> Tuple[int, int, List[str]]:
  """Executes discovered tests in Python target backend."""
  out_py = transpile_file(sp_file, target="python", test_mode=True)

  # Ensure workspace root and lib directory are in sys.path
  workspace_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
  lib_dir = os.path.join(workspace_root, "lib")
  if lib_dir not in sys.path:
    sys.path.insert(0, lib_dir)
  if workspace_root not in sys.path:
    sys.path.insert(0, workspace_root)

  try:
    import std.testing as testing
  except ImportError:  # pragma: no cover
    try:
      from lib.std import testing
    except ImportError:
      print("Error: Could not import std.testing module.", file=sys.stderr)
      return 0, 1, ["Failed to load std.testing module"]

  # Dynamically import transpiled Python module
  module_name = "sapphire_test_" + os.path.basename(out_py).replace(".", "_")
  spec = importlib.util.spec_from_file_location(module_name, out_py)
  mod = importlib.util.module_from_spec(spec)
  sys.modules[module_name] = mod
  try:
    spec.loader.exec_module(mod)
  except Exception as e:
    return 0, 1, [f"Failed to execute transpiled test module: {e}"]

  passed = 0
  failed = 0
  logs = []

  # Run standalone @test functions
  for fn_name in standalone_tests:
    if filter_pattern and filter_pattern not in fn_name:
      continue
    if not hasattr(mod, fn_name):
      continue
    test_func = getattr(mod, fn_name)
    ctx = testing.TestContext(fn_name)
    testing.set_active_context(ctx)

    err = None
    try:
      test_func()
    except testing.TestFailure as tf:
      err = str(tf)
    except Exception as ex:
      err = f"Unhandled Exception: {ex}"

    if not ctx.failures and err is None:
      passed += 1
      print(f"[ PASS ] {fn_name} ({os.path.basename(sp_file)})")
    else:
      failed += 1
      print(f"[ FAIL ] {fn_name} ({os.path.basename(sp_file)})")
      all_fails = ctx.failures.copy()
      if err and not any(f["fatal"] for f in all_fails):
        all_fails.append({"message": err, "lineno": 0, "filename": sp_file})
      for f in all_fails:
        msg = f["message"]
        lineno = f.get("lineno", 0)
        src_line = get_source_line(sp_file, lineno) if lineno > 0 else None
        print(f"  {msg}")
        if src_line:
          print(f"  Line {lineno}: {src_line}")
          print(f"         {'^' * len(src_line)}")

  # Run struct-based test suites
  for struct_name, methods in suite_tests.items():
    if not hasattr(mod, struct_name):
      continue
    struct_cls = getattr(mod, struct_name)

    for m_name in methods:
      full_name = f"{struct_name}.{m_name}"
      if filter_pattern and filter_pattern not in full_name and filter_pattern not in m_name:
        continue

      instance = struct_cls()
      ctx = testing.TestContext(full_name)
      testing.set_active_context(ctx)

      # Run set_up
      if hasattr(instance, "set_up"):
        try:
          instance.set_up()
        except Exception as ex:
          failed += 1
          print(f"[ FAIL ] {full_name} (set_up failed: {ex})")
          continue
      elif hasattr(instance, "func_set_up"):
        try:
          instance.func_set_up()
        except Exception as ex:
          failed += 1
          print(f"[ FAIL ] {full_name} (set_up failed: {ex})")
          continue

      err = None
      if hasattr(instance, m_name):
        test_m = getattr(instance, m_name)
        try:
          test_m()
        except testing.TestFailure as tf:
          err = str(tf)
        except Exception as ex:
          err = f"Unhandled Exception: {ex}"

      # Run tear_down
      if hasattr(instance, "tear_down"):
        try:
          instance.tear_down()
        except Exception:
          pass
      elif hasattr(instance, "func_tear_down"):
        try:
          instance.func_tear_down()
        except Exception:
          pass

      if not ctx.failures and err is None:
        passed += 1
        print(f"[ PASS ] {full_name} ({os.path.basename(sp_file)})")
      else:
        failed += 1
        print(f"[ FAIL ] {full_name} ({os.path.basename(sp_file)})")
        all_fails = ctx.failures.copy()
        if err and not any(f["fatal"] for f in all_fails):
          all_fails.append({"message": err, "lineno": 0, "filename": sp_file})
        for f in all_fails:
          msg = f["message"]
          lineno = f.get("lineno", 0)
          src_line = get_source_line(sp_file, lineno) if lineno > 0 else None
          print(f"  {msg}")
          if src_line:
            print(f"  Line {lineno}: {src_line}")
            print(f"         {'^' * len(src_line)}")

  return passed, failed, logs


def run_tests_lua(
    sp_file: str,
    standalone_tests: List[str],
    suite_tests: Dict[str, List[str]],
    filter_pattern: Optional[str] = None,
    sourcemap: bool = True,
) -> Tuple[int, int, List[str]]:
  """Executes discovered tests in Lua 5.1 target backend."""
  out_lua = transpile_file(sp_file, target="lua", test_mode=True, sourcemap=sourcemap)
  lua_bin = shutil.which("lua") or shutil.which("luajit") or shutil.which("lua5.1")
  if not lua_bin:
    print("Error: Lua interpreter ('lua', 'luajit', or 'lua5.1') not found in PATH.", file=sys.stderr)
    return 0, 1, ["Lua interpreter not found"]

  workspace_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

  # Construct Lua runner script
  lua_script_lines = [
      f'package.path = "{workspace_root}/lib/?.lua;{workspace_root}/lib/?/init.lua;" .. package.path',
      f'local testing = require("std.testing")',
      f'local target_mod = dofile("{out_lua}")',
      'local total_passed = 0',
      'local total_failed = 0',
  ]

  # Run standalone @test functions
  for fn_name in standalone_tests:
    if filter_pattern and filter_pattern not in fn_name:
      continue
    lua_script_lines.append(f'''
do
  local ctx = testing.TestContext.new("{fn_name}")
  testing.set_active_context(ctx)
  local ok, err = pcall(function()
    if target_mod and target_mod["{fn_name}"] then
      target_mod["{fn_name}"]()
    elseif _G["{fn_name}"] then
      _G["{fn_name}"]()
    end
  end)
  if ok and #ctx.failures == 0 then
    total_passed = total_passed + 1
    print("[ PASS ] " .. "{fn_name} (" .. "{os.path.basename(sp_file)}" .. ")")
  else
    total_failed = total_failed + 1
    print("[ FAIL ] " .. "{fn_name} (" .. "{os.path.basename(sp_file)}" .. ")")
    for _, f in ipairs(ctx.failures) do
      print("  " .. f.message)
    end
    if not ok then
      print("  " .. tostring(err))
    end
  end
end
''')

  # Run struct test suites
  for struct_name, methods in suite_tests.items():
    for m_name in methods:
      full_name = f"{struct_name}.{m_name}"
      if filter_pattern and filter_pattern not in full_name and filter_pattern not in m_name:
        continue
      lua_script_lines.append(f'''
do
  local ctx = testing.TestContext.new("{full_name}")
  testing.set_active_context(ctx)
  local struct_cls = (target_mod and target_mod["{struct_name}"]) or _G["{struct_name}"]
  local inst = nil
  if struct_cls then
    setmetatable(struct_cls, {{ __index = testing.TestCase }})
    if struct_cls.init then
      inst = struct_cls.init()
    elseif struct_cls.new then
      inst = struct_cls.new()
    else
      inst = setmetatable({{}}, struct_cls)
    end
  end

  if inst then
    if inst.set_up then pcall(function() inst:set_up() end) end
    local ok, err = pcall(function()
      if inst["{m_name}"] then inst["{m_name}"](inst) end
    end)
    if inst.tear_down then pcall(function() inst:tear_down() end) end

    if ok and #ctx.failures == 0 then
      total_passed = total_passed + 1
      print("[ PASS ] " .. "{full_name} (" .. "{os.path.basename(sp_file)}" .. ")")
    else
      total_failed = total_failed + 1
      print("[ FAIL ] " .. "{full_name} (" .. "{os.path.basename(sp_file)}" .. ")")
      for _, f in ipairs(ctx.failures) do
        print("  " .. f.message)
      end
      if not ok then
        print("  " .. tostring(err))
      end
    end
  end
end
''')

  lua_script_lines.append('os.exit((total_failed > 0) and 1 or 0)')

  runner_tmp = out_lua + ".runner.lua"
  with open(runner_tmp, "w", encoding="utf-8") as f:
    f.write("\n".join(lua_script_lines))

  cmd = [lua_bin, runner_tmp]
  res = subprocess.run(cmd, capture_output=True, text=True)

  if os.path.exists(runner_tmp):
    os.remove(runner_tmp)

  if res.stdout:
    print(res.stdout.strip())
  if res.stderr:
    print(res.stderr.strip(), file=sys.stderr)

  return (1 if res.returncode != 0 else 0), (0 if res.returncode != 0 else 1), []


def run_tests(
    path: str,
    target: str = "python",
    filter_pattern: Optional[str] = None,
    sourcemap: bool = True,
) -> int:
  """Main entry point for `sapphire test` command.

  Returns:
    Exit code (0 for success, 1 for failure).
  """
  sp_files = find_sp_files(path)
  if not sp_files:
    print(f"No Sapphire (.sp) source files found in '{path}'.", file=sys.stderr)
    return 1

  total_passed = 0
  total_failed = 0
  start_time = time.time()

  print(f"Running Sapphire tests in target '{target}'...\n")

  for sp_file in sp_files:
    try:
      ast = parse_ast(sp_file)
      standalone_tests, suite_tests = discover_tests(ast)
    except Exception as e:
      print(f"Failed to parse test file '{sp_file}': {e}", file=sys.stderr)
      total_failed += 1
      continue

    if not standalone_tests and not suite_tests:
      continue

    if target.lower() in ("lua", "lua5.1"):
      p_fail, p_pass, _ = run_tests_lua(sp_file, standalone_tests, suite_tests, filter_pattern, sourcemap)
      if p_fail > 0:
        total_failed += 1
      else:
        total_passed += 1
    else:
      passed, failed, _ = run_tests_python(sp_file, standalone_tests, suite_tests, filter_pattern)
      total_passed += passed
      total_failed += failed

  duration = time.time() - start_time
  print(f"\nTest Result: {total_passed} passed, {total_failed} failed in {duration:.2f}s")
  return 1 if total_failed > 0 else 0
