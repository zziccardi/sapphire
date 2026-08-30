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

from src.parser.gen.SapphireLexer import SapphireLexer
from src.parser.gen.SapphireParser import SapphireParser
from src.parser.ast_builder import ASTBuilder
from src.parser.ast import FuncDeclNode, ImplBlockNode, IdentifierNode
from src.code_gen.transpiler import transpile_file
from src.code_gen.source_map import SourceMapBuilder
from src.cli.diagnostics import get_source_line, format_diagnostic



from src.common.errors import SapphireError, SapphireSyntaxError
from src.parser.error_listener import CustomErrorListener


class TestDiscoveryError(SapphireError):
  """Raised when test discovery or test suite parsing encounters invalid states."""

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
  error_listener = CustomErrorListener(file_path=sp_file, source_content=input_stream, quiet=True)
  lexer = SapphireLexer(input_stream)
  lexer.removeErrorListeners()
  lexer.addErrorListener(error_listener)
  stream = CommonTokenStream(lexer)
  parser = SapphireParser(stream)
  parser.removeErrorListeners()
  parser.addErrorListener(error_listener)
  tree = parser.program()
  if error_listener.errors > 0:
    err_text = "\n".join(error_listener.error_messages) if error_listener.error_messages else f"Parsing failed with {error_listener.errors} syntax error(s)."
    raise SapphireSyntaxError(err_text, file_path=sp_file)
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


def find_lua_binary() -> Optional[str]:
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


def run_tests_python(
    sp_file: str,
    standalone_tests: List[str],
    suite_tests: Dict[str, List[str]],
    filter_pattern: Optional[str] = None,
) -> Tuple[int, int, List[str]]:
  """Executes discovered tests in Python target backend."""
  try:
    out_py = transpile_file(sp_file, target="python", test_mode=True, quiet=True, raise_on_error=True)
  except BaseException as e:  # pragma: no cover
    print(f"[ FAIL ] {os.path.basename(sp_file)} (transpilation failed)")
    for line in str(e).splitlines():
      print(f"  {line}")
    return 0, 1, [f"Transpilation failed: {e}"]

  # Ensure workspace root, lib directory, and test source directory are in sys.path
  workspace_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
  lib_dir = os.path.join(workspace_root, "lib")
  sp_dir = os.path.dirname(os.path.abspath(sp_file))
  cwd = os.getcwd()
  for path_entry in (workspace_root, lib_dir, cwd, sp_dir):
    if path_entry:
      if path_entry in sys.path:
        sys.path.remove(path_entry)
      sys.path.insert(0, path_entry)

  try:
    import std.testing as testing
  except ImportError:  # pragma: no cover
    try:
      from lib.std import testing
    except ImportError:  # pragma: no cover
      print(f"[ FAIL ] {os.path.basename(sp_file)} (could not import std.testing module)", file=sys.stderr)
      return 0, 1, ["Failed to load std.testing module"]

  # If a 'lib' directory exists in sp_dir, clear stale repo 'lib' modules from sys.modules
  sp_lib = os.path.join(sp_dir, "lib")
  if os.path.isdir(sp_lib):
    to_del = [k for k in list(sys.modules.keys()) if k == "lib" or k.startswith("lib.")]
    for k in to_del:
      del sys.modules[k]

  # Invalidate cached modules in sys.modules that match files within sp_dir
  for root, _, files in os.walk(sp_dir):
    rel_root = os.path.relpath(root, sp_dir).replace(os.sep, ".")
    for f in files:
      if f.endswith(".py"):
        base_f = os.path.splitext(f)[0]
        mod_candidates = [base_f]
        if rel_root != ".":
          mod_candidates.append(f"{rel_root}.{base_f}")
        for mc in mod_candidates:
          if mc in sys.modules and mc != "std.testing":
            del sys.modules[mc]

  # Dynamically import transpiled Python module
  module_name = "sapphire_test_" + os.path.basename(out_py).replace(".", "_")
  spec = importlib.util.spec_from_file_location(module_name, out_py)
  mod = importlib.util.module_from_spec(spec)
  sys.modules[module_name] = mod
  try:
    spec.loader.exec_module(mod)
  except BaseException as e:  # pragma: no cover
    print(f"[ FAIL ] {os.path.basename(sp_file)} (failed to load module)")
    for line in str(e).splitlines():
      print(f"  {line}")
    return 0, 1, [f"Failed to execute transpiled test module: {e}"]

  passed = 0
  failed = 0
  logs = []

  # Load source line map from transpiled module (Python line -> Sapphire line)
  sp_line_map = getattr(mod, "_SP_LINE_MAP", {})

  def sp_lineno(py_line: int) -> int:
    """Translate a Python output line number to the nearest Sapphire source line."""
    if py_line in sp_line_map:
      return sp_line_map[py_line]
    # Walk backwards to find the nearest mapped line
    for offset in range(1, 50):
      if (py_line - offset) in sp_line_map:  # pragma: no cover
        return sp_line_map[py_line - offset]
    return 0

  def format_failure(f: dict, sp_file: str) -> str:
    """Format a single failure dict into the documented output lines."""
    lines_out = []
    kind = f.get("kind", "generic")
    expected = f.get("expected")
    actual = f.get("actual")
    user_msg = f.get("message", "")

    if kind in ("eq", "ne", "almost_eq"):
      lines_out.append(f"  Expected: {expected!r}")
      lines_out.append(f"  Actual:   {actual!r}")
      if user_msg:
        # Strip the auto-generated prefix to show only the user message
        import re
        user_only = re.sub(r"^[^(]+ \((.+)\)$", r"\1", user_msg)
        if user_only != user_msg:
          lines_out.append(f"  Message:  {user_only}")
    elif kind in ("bool",):
      lines_out.append(f"  Expected: {expected!r}")
      lines_out.append(f"  Actual:   {actual!r}")
      if user_msg:
        import re
        user_only = re.sub(r"^[^(]+ \((.+)\)$", r"\1", user_msg)
        if user_only != user_msg:
          lines_out.append(f"  Message:  {user_only}")
    elif kind in ("none", "not_none"):
      lines_out.append(f"  Expected: {expected!r}")
      lines_out.append(f"  Actual:   {actual!r}")
    else:  # pragma: no cover
      lines_out.append(f"  {user_msg}")

    # Source line display
    sp_line = sp_lineno(f.get("lineno", 0))
    if sp_line > 0:
      src = get_source_line(sp_file, sp_line)
      if src:
        stripped = src.strip()
        indent_len = len(src) - len(src.lstrip())
        lines_out.append(f"  Line {sp_line}:  {stripped}")
        lines_out.append(f"  {' ' * (len(str(sp_line)) + 8)}{'^' * len(stripped)}")

    return "\n".join(lines_out)

  def first_sp_line(failures: list) -> int:
    """Return the Sapphire source line of the first failure, for the header."""
    for f in failures:
      line = sp_lineno(f.get("lineno", 0))
      if line > 0:
        return line
    return 0

  # Run standalone @test functions
  for fn_name in standalone_tests:
    if filter_pattern and filter_pattern not in fn_name:
      continue
    if not hasattr(mod, fn_name):  # pragma: no cover
      continue
    test_func = getattr(mod, fn_name)
    ctx = testing.TestContext(fn_name)
    testing.set_active_context(ctx)

    err = None
    try:
      test_func()
    except testing.TestFailure as tf:
      err = str(tf)
    except Exception as ex:  # pragma: no cover
      err = f"Unhandled Exception: {ex}"

    if not ctx.failures and err is None:
      passed += 1
      print(f"[ PASS ] {fn_name} ({os.path.basename(sp_file)})")
    else:
      failed += 1
      all_fails = ctx.failures.copy()
      if err and not any(f["fatal"] for f in all_fails):  # pragma: no cover
        all_fails.append({"message": err, "lineno": 0, "filename": sp_file, "kind": "generic"})
      header_line = first_sp_line(all_fails)
      if header_line > 0:
        print(f"[ FAIL ] {fn_name} ({os.path.basename(sp_file)}:{header_line})")
      else:
        print(f"[ FAIL ] {fn_name} ({os.path.basename(sp_file)})")
      for f in all_fails:
        print(format_failure(f, sp_file))

  # Run struct-based test suites
  for struct_name, methods in suite_tests.items():
    if not hasattr(mod, struct_name):  # pragma: no cover
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
      elif hasattr(instance, "func_set_up"):  # pragma: no cover
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
        except Exception as ex:  # pragma: no cover
          err = f"Unhandled Exception: {ex}"

      # Run tear_down
      if hasattr(instance, "tear_down"):
        try:
          instance.tear_down()
        except Exception:  # pragma: no cover
          pass
      elif hasattr(instance, "func_tear_down"):  # pragma: no cover
        try:
          instance.func_tear_down()
        except Exception:
          pass

      if not ctx.failures and err is None:
        passed += 1
        print(f"[ PASS ] {full_name} ({os.path.basename(sp_file)})")
      else:
        failed += 1
        all_fails = ctx.failures.copy()
        if err and not any(f["fatal"] for f in all_fails):  # pragma: no cover
          all_fails.append({"message": err, "lineno": 0, "filename": sp_file, "kind": "generic"})
        header_line = first_sp_line(all_fails)
        if header_line > 0:
          print(f"[ FAIL ] {full_name} ({os.path.basename(sp_file)}:{header_line})")
        else:
          print(f"[ FAIL ] {full_name} ({os.path.basename(sp_file)})")
        for f in all_fails:
          print(format_failure(f, sp_file))

  return passed, failed, logs


def run_tests_lua(
    sp_file: str,
    standalone_tests: List[str],
    suite_tests: Dict[str, List[str]],
    filter_pattern: Optional[str] = None,
    sourcemap: bool = True,
) -> Tuple[int, int, List[str]]:
  """Executes discovered tests in Lua 5.1 target backend."""
  try:
    out_lua = transpile_file(sp_file, target="lua", test_mode=True, sourcemap=sourcemap, quiet=True, raise_on_error=True)
  except BaseException as e:  # pragma: no cover
    print(f"[ FAIL ] {os.path.basename(sp_file)} (transpilation failed)")
    for line in str(e).splitlines():
      print(f"  {line}")
    return 0, 1, [f"Transpilation failed: {e}"]

  lua_bin = find_lua_binary()
  if not lua_bin:  # pragma: no cover
    print("Error: Lua interpreter ('lua', 'luajit', or 'lua5.1') not found in PATH.", file=sys.stderr)
    print(f"[ FAIL ] {os.path.basename(sp_file)} (Lua interpreter not found in PATH)")
    return 0, 1, ["Lua interpreter not found"]

  workspace_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
  sp_dir = os.path.dirname(os.path.abspath(sp_file))

  # Construct Lua runner script
  lua_script_lines = [
      f'package.path = "{workspace_root}/lib/?.lua;{workspace_root}/lib/?/init.lua;{sp_dir}/?.lua;{sp_dir}/?/init.lua;" .. package.path',
      '''
local function _sp_install_loader()
  if _G._SP_RELATIVE_LOADER_INSTALLED then return end
  _G._SP_RELATIVE_LOADER_INSTALLED = true
  local loaders = package.searchers or package.loaders
  if not loaders then return end

  local function relative_loader(modname)
    local rel_path = modname:gsub("%.", "/")
    for level = 2, 20 do
      local info = debug.getinfo(level, "S")
      if info and info.source and info.source:sub(1, 1) == "@" then
        local caller_file = info.source:sub(2)
        local curr_dir = caller_file:match("^(.*[/\\\\])") or "./"
        while curr_dir and curr_dir ~= "" do
          local cand1 = curr_dir .. rel_path .. ".lua"
          local cand2 = curr_dir .. rel_path .. "/init.lua"
          local f = io.open(cand1, "r")
          if f then
            f:close()
            local chunk, err = loadfile(cand1)
            if chunk then return chunk, cand1 else error("error loading module '" .. modname .. "' from file '" .. cand1 .. "':\\n\\t" .. tostring(err), 3) end
          end
          f = io.open(cand2, "r")
          if f then
            f:close()
            local chunk, err = loadfile(cand2)
            if chunk then return chunk, cand2 else error("error loading module '" .. modname .. "' from file '" .. cand2 .. "':\\n\\t" .. tostring(err), 3) end
          end
          local parent = curr_dir:match("^(.*[/\\\\])[^/\\\\]+[/\\\\]$")
          if not parent or parent == curr_dir then
            if curr_dir ~= "./" and curr_dir ~= "/" and not curr_dir:match("^[A-Za-z]:[\\\\/]$") then
              local f_dot1 = io.open("./" .. rel_path .. ".lua", "r")
              if f_dot1 then
                f_dot1:close()
                local chunk, err = loadfile("./" .. rel_path .. ".lua")
                if chunk then return chunk, "./" .. rel_path .. ".lua" else error("error loading module '" .. modname .. "' from file './" .. rel_path .. ".lua':\\n\\t" .. tostring(err), 3) end
              end
              local f_dot2 = io.open("./" .. rel_path .. "/init.lua", "r")
              if f_dot2 then
                f_dot2:close()
                local chunk, err = loadfile("./" .. rel_path .. "/init.lua")
                if chunk then return chunk, "./" .. rel_path .. "/init.lua" else error("error loading module '" .. modname .. "' from file './" .. rel_path .. "/init.lua':\\n\\t" .. tostring(err), 3) end
              end
            end
            break
          end
          curr_dir = parent
        end
      end
    end
    return "\\n\\tno relative sapphire module found for '" .. modname .. "'"
  end

  table.insert(loaders, 2, relative_loader)
end
_sp_install_loader()
''',
      f'local testing = require("std.testing")',
      f'local target_mod_ok, target_mod = pcall(function() return dofile("{out_lua}") end)',
      'if not target_mod_ok then',
      f'  print("[ FAIL ] {os.path.basename(sp_file)} (module load error)")',
      '  print("  " .. tostring(target_mod))',
      '  os.exit(1)',
      'end',
      'local total_passed = 0',
      'local total_failed = 0',
      '''
local function get_sp_info(line_num)
  local map = (type(target_mod) == "table" and target_mod._SP_LINE_MAP) or _G._SP_LINE_MAP or _SP_LINE_MAP
  if map and line_num then
    local entry = map[line_num]
    if entry then return entry.line, entry.file, entry.text end
    for offset = 1, 50 do
      entry = map[line_num - offset]
      if entry then return entry.line, entry.file, entry.text end
    end
  end
  return 0, nil, nil
end

local function format_val(v)
  if type(v) == "string" then
    return '"' .. v .. '"'
  end
  return tostring(v)
end

local function print_failure(f)
  local kind = f.kind or "generic"
  local user_msg = f.message or ""
  if kind == "eq" or kind == "ne" or kind == "almost_eq" or kind == "bool" or kind == "none" or kind == "not_none" then
    print("  Expected: " .. format_val(f.expected))
    print("  Actual:   " .. format_val(f.actual))
    if user_msg ~= "" then
      local user_only = user_msg:match("%((.+)%)$")
      if user_only and user_only ~= user_msg then
        print("  Message:  " .. tostring(user_only))
      end
    end
  else
    print("  " .. user_msg)
  end

  local sp_line, _, sp_text = get_sp_info(f.lineno)
  if sp_line and sp_line > 0 and sp_text then
    local stripped = sp_text:match("^%s*(.-)%s*$")
    local line_str = tostring(sp_line)
    print("  Line " .. line_str .. ":  " .. stripped)
    local indent = string.rep(" ", #line_str + 8)
    print("  " .. indent .. string.rep("^", #stripped))
  end
end

local function get_first_sp_line(failures)
  for _, f in ipairs(failures) do
    local sp_line = get_sp_info(f.lineno)
    if sp_line and sp_line > 0 then return sp_line end
  end
  return 0
end
''',
  ]

  # Run standalone @test functions
  for fn_name in standalone_tests:
    if filter_pattern and filter_pattern not in fn_name:
      continue
    lua_script_lines.append(f'''
do
  local ctx = testing.TestContext.new("{fn_name}")
  testing.set_active_context(ctx)
  local fn = (target_mod and target_mod["{fn_name}"]) or _G["{fn_name}"]
  if type(fn) ~= "function" then
    total_failed = total_failed + 1
    print("[ FAIL ] {fn_name} ({os.path.basename(sp_file)})")
    print("  Test function '{fn_name}' not found or not callable")
  else
    local ok, err = pcall(fn)
    if ok and #ctx.failures == 0 then
      total_passed = total_passed + 1
      print("[ PASS ] {fn_name} ({os.path.basename(sp_file)})")
    else
      total_failed = total_failed + 1
      local header_line = get_first_sp_line(ctx.failures)
      if header_line > 0 then
        print("[ FAIL ] {fn_name} ({os.path.basename(sp_file)}:" .. header_line .. ")")
      else
        print("[ FAIL ] {fn_name} ({os.path.basename(sp_file)})")
      end
      for _, f in ipairs(ctx.failures) do
        print_failure(f)
      end
      if not ok then
        local has_fatal = false
        for _, f in ipairs(ctx.failures) do
          if f.fatal then has_fatal = true break end
        end
        if not has_fatal then
          print("  Unhandled Error: " .. tostring(err))
        end
      end
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

  if not inst then
    total_failed = total_failed + 1
    print("[ FAIL ] {full_name} ({os.path.basename(sp_file)})")
    print("  Test suite struct '{struct_name}' could not be instantiated")
  else
    local setup_ok, setup_err = true, nil
    if inst.set_up then setup_ok, setup_err = pcall(function() inst:set_up() end) end
    if not setup_ok then
      total_failed = total_failed + 1
      print("[ FAIL ] {full_name} (set_up failed: " .. tostring(setup_err) .. ")")
    else
      local test_fn = inst["{m_name}"]
      if type(test_fn) ~= "function" then
        total_failed = total_failed + 1
        print("[ FAIL ] {full_name} ({os.path.basename(sp_file)})")
        print("  Test method '{m_name}' not found on struct '{struct_name}'")
      else
        local ok, err = pcall(function() test_fn(inst) end)
        if inst.tear_down then pcall(function() inst:tear_down() end) end

        if ok and #ctx.failures == 0 then
          total_passed = total_passed + 1
          print("[ PASS ] {full_name} ({os.path.basename(sp_file)})")
        else
          total_failed = total_failed + 1
          local header_line = get_first_sp_line(ctx.failures)
          if header_line > 0 then
            print("[ FAIL ] {full_name} ({os.path.basename(sp_file)}:" .. header_line .. ")")
          else
            print("[ FAIL ] {full_name} ({os.path.basename(sp_file)})")
          end
          for _, f in ipairs(ctx.failures) do
            print_failure(f)
          end
          if not ok then
            local has_fatal = false
            for _, f in ipairs(ctx.failures) do
              if f.fatal then has_fatal = true break end
            end
            if not has_fatal then
              print("  Unhandled Error: " .. tostring(err))
            end
          end
        end
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
  if res.stderr:  # pragma: no cover
    print(res.stderr.strip(), file=sys.stderr)

  stdout_lines = [l.strip() for l in res.stdout.splitlines() if l.strip()]
  passed = sum(1 for l in stdout_lines if l.startswith("[ PASS ]"))
  failed = sum(1 for l in stdout_lines if l.startswith("[ FAIL ]"))
  if res.returncode != 0 and passed == 0 and failed == 0:
    failed = 1

  return passed, failed, []


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
  if not sp_files:  # pragma: no cover
    print(f"No Sapphire (.sp) source files found in '{path}'.", file=sys.stderr)
    return 1

  total_passed = 0
  total_failed = 0
  tests_found = 0
  start_time = time.time()

  print(f"Running Sapphire tests in target '{target}'...\n")

  for sp_file in sp_files:
    try:
      ast = parse_ast(sp_file)
      standalone_tests, suite_tests = discover_tests(ast)
    except BaseException as e:  # pragma: no cover
      print(f"[ FAIL ] {os.path.basename(sp_file)} (parsing failed)")
      for line in str(e).splitlines():
        print(f"  {line}")
      total_failed += 1
      continue

    if not standalone_tests and not suite_tests:
      if len(sp_files) == 1:
        print(f"No tests found in '{sp_file}'.")
      continue

    tests_found += len(standalone_tests) + sum(len(m) for m in suite_tests.values())

    if target.lower() in ("lua", "lua5.1"):
      passed, failed, _ = run_tests_lua(sp_file, standalone_tests, suite_tests, filter_pattern, sourcemap)
      total_passed += passed
      total_failed += failed
    else:
      passed, failed, _ = run_tests_python(sp_file, standalone_tests, suite_tests, filter_pattern)
      total_passed += passed
      total_failed += failed

  if len(sp_files) > 1 and tests_found == 0 and total_failed == 0:
    print(f"No tests found in '{path}'.")

  duration = time.time() - start_time
  print(f"\nTest Result: {total_passed} passed, {total_failed} failed in {duration:.2f}s")
  return 1 if total_failed > 0 else 0
