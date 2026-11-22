"""Test discovery and execution engine for Sapphire (`sapphire test`)."""

import contextlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any, Dict, List, Tuple, Optional

from antlr4 import FileStream, CommonTokenStream

from src.parser.gen.SapphireLexer import SapphireLexer
from src.parser.gen.SapphireParser import SapphireParser
from src.parser.ast_builder import ASTBuilder
from src.parser.ast import FuncDeclNode, ImplBlockNode
from src.code_gen.transpiler import transpile_file
from src.cli.diagnostics import get_source_line


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


def discover_tests(
    ast, warnings: Optional[List[str]] = None
) -> Tuple[List[str], Dict[str, List[str]]]:
  """Discovers standalone @test functions and struct-based TestCase methods.

  Args:
    ast: The parsed AST node.
    warnings: Optional list to collect discovery warnings (e.g. methods named
      with 'test_' prefix but missing '@test' annotation).

  Returns:
    (standalone_test_funcs, {struct_name: [test_methods]})
  """
  standalone_tests = []
  suite_tests = {}

  # Check imports to ensure std.testing is referenced
  for imp in getattr(ast, "imports", []):
    if imp.path == "std.testing" or imp.path.startswith("std.testing"):
      break

  # Discover standalone @test functions
  for stmt in getattr(ast, "declarations", []):
    if isinstance(stmt, FuncDeclNode):
      has_test_ann = any(
          getattr(ann, "name", "") == "test"
          for ann in getattr(stmt, "annotations", [])
      )
      if has_test_ann:
        standalone_tests.append(stmt.name)
      elif stmt.name.startswith("test_") and warnings is not None:
        warnings.append(
            f"Function '{stmt.name}' begins with 'test_' but is missing "
            "'@test' annotation; it will not be executed as a test."
        )

    # Discover impl blocks for structs implementing TestCase
    elif isinstance(stmt, ImplBlockNode):
      trait_name = stmt.trait_name
      if trait_name and (
          trait_name == "TestCase" or trait_name.endswith(".TestCase")
      ):
        struct_name = stmt.struct_name
        test_methods = []
        for member in stmt.members:
          func_decl = getattr(member, "func_decl", member)
          if isinstance(func_decl, FuncDeclNode):
            has_test_ann = any(
                getattr(a, "name", "") == "test"
                for a in getattr(func_decl, "annotations", [])
            )
            if has_test_ann:
              test_methods.append(func_decl.name)
            elif func_decl.name.startswith("test_") and warnings is not None:
              warnings.append(
                  f"Method '{struct_name}.{func_decl.name}' begins with "
                  "'test_' but is missing '@test' annotation; it will not be "
                  "executed as a test."
              )
        if test_methods:
          suite_tests.setdefault(struct_name, []).extend(test_methods)

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


def _resolve_sp_lineno(sp_line_map: dict, py_line: int) -> int:
  """Translates a Python output line number to the nearest Sapphire source line."""
  if py_line in sp_line_map:
    return sp_line_map[py_line]
  for offset in range(1, 50):
    if (py_line - offset) in sp_line_map:  # pragma: no cover
      return sp_line_map[py_line - offset]
  return 0


def _format_python_failure(
    f: dict, sp_file: str, sp_line_map: dict
) -> str:
  """Formats a single Python test failure dict into human-readable lines."""
  import re

  lines_out = []
  kind = f.get("kind", "generic")
  expected = f.get("expected")
  actual = f.get("actual")
  user_msg = f.get("message", "")

  if kind in ("eq", "ne", "almost_eq", "bool", "none", "not_none"):
    lines_out.append(f"  Expected: {expected!r}")
    lines_out.append(f"  Actual:   {actual!r}")
    if user_msg:
      user_only = re.sub(r"^[^(]+ \((.+)\)$", r"\1", user_msg)
      if user_only != user_msg:
        lines_out.append(f"  Message:  {user_only}")
  else:  # pragma: no cover
    lines_out.append(f"  {user_msg}")

  sp_line = _resolve_sp_lineno(sp_line_map, f.get("lineno", 0))
  if sp_line > 0:
    src = get_source_line(sp_file, sp_line)
    if src:
      stripped = src.strip()
      lines_out.append(f"  Line {sp_line}:  {stripped}")
      pad = " " * (len(str(sp_line)) + 8)
      lines_out.append(f"  {pad}{'^' * len(stripped)}")

  return "\n".join(lines_out)


def _print_python_test_failures(
    label: str,
    sp_file: str,
    ctx_failures: list,
    err: Optional[str],
    sp_line_map: dict,
) -> None:
  """Prints the failure header and formatted assertion details for one test."""
  all_fails = ctx_failures.copy()
  if err and not any(f["fatal"] for f in all_fails):  # pragma: no cover
    all_fails.append({
        "message": err,
        "lineno": 0,
        "filename": sp_file,
        "kind": "generic",
    })
  header_line = 0
  for f in all_fails:
    ln = _resolve_sp_lineno(sp_line_map, f.get("lineno", 0))
    if ln > 0:
      header_line = ln
      break
  base_name = os.path.basename(sp_file)
  if header_line > 0:
    print(f"[ FAIL ] {label} ({base_name}:{header_line})")
  else:
    print(f"[ FAIL ] {label} ({base_name})")
  for f in all_fails:
    print(_format_python_failure(f, sp_file, sp_line_map))


def _mangle_python_name(name: str) -> str:
  """Mirrors PythonTranspiler._mangle_name for looking up generated symbols."""
  from src.code_gen.python_runtime import PYTHON_RESERVED_WORDS

  if not name or name in ("self", "__init__", "__del__", "main"):
    return name
  if name in PYTHON_RESERVED_WORDS:
    return f"{name}_"
  return name


def _mangle_lua_name(name: str) -> str:
  """Mirrors LuaTranspiler._mangle_name for looking up generated symbols."""
  from src.code_gen.lua_transpiler import LUA_RESERVED_WORDS

  if not name or name in ("self", "__init__", "__del__", "_init_sapphire"):
    return name
  if name in LUA_RESERVED_WORDS:
    return f"{name}_"
  return name


def _is_path_under(path: str, parent_dir: str) -> bool:
  """Returns True if *path* is equal to or nested inside *parent_dir*."""
  try:
    return os.path.commonpath(
        [os.path.abspath(parent_dir), os.path.abspath(path)]
    ) == os.path.abspath(parent_dir)
  except ValueError:
    return False


def _is_protected_module(
    mod_name: str,
    mod_obj: Any,
    sp_dir: str,
    out_dir: Optional[str],
    compiler_lib_dir: str,
) -> bool:
  """Returns True if *mod_name* belongs to Python stdlib or the compiler."""
  root_pkg = mod_name.split(".", 1)[0]
  if (
      root_pkg in sys.stdlib_module_names
      or root_pkg in sys.builtin_module_names
      or root_pkg in ("src", "antlr4", "std", "unittest", "pytest")
  ):
    return True
  if mod_obj is None:
    return False
  mod_file = getattr(mod_obj, "__file__", None)
  if not mod_file:
    return True
  if _is_path_under(mod_file, compiler_lib_dir) and not _is_path_under(
      compiler_lib_dir, sp_dir
  ):
    return True
  if _is_path_under(mod_file, sp_dir):
    return False
  if out_dir and _is_path_under(mod_file, out_dir):
    return False
  return True


def _prepare_python_test_paths(
    sp_file: str, out_dir: Optional[str] = None
) -> str:
  """Configures sys.path and clears stale local test modules for *sp_file*."""
  workspace_root = os.path.abspath(
      os.path.join(os.path.dirname(__file__), "..", "..")
  )
  from src.semantics.module_resolver import find_sapphire_lib_dir

  discovered_lib = find_sapphire_lib_dir()
  lib_dir = os.path.abspath(discovered_lib or os.path.join(workspace_root, "lib"))
  lib_parent = os.path.dirname(lib_dir)
  sp_dir = os.path.dirname(os.path.abspath(sp_file))
  cwd = os.getcwd()
  for path_entry in (workspace_root, lib_parent, lib_dir, cwd, sp_dir, out_dir):
    if path_entry:
      if path_entry in sys.path:
        sys.path.remove(path_entry)
      sys.path.insert(0, path_entry)

  # Clear stale local `lib` or test-dir modules so each test file loads fresh,
  # while never evicting Python stdlib or Sapphire compiler modules.
  sp_lib = os.path.abspath(os.path.join(sp_dir, "lib"))
  if os.path.isdir(sp_lib) and sp_lib != lib_dir:
    for k in [
        k for k in list(sys.modules.keys()) if k == "lib" or k.startswith("lib.")
    ]:
      mod_obj = sys.modules.get(k)
      if mod_obj is None or (
          getattr(mod_obj, "__file__", None)
          and _is_path_under(mod_obj.__file__, sp_lib)
      ):
        del sys.modules[k]

  # Avoid walking the compiler source tree if a test resides at workspace root.
  skip_dirs = {
      os.path.abspath(os.path.join(workspace_root, "src")),
      lib_dir,
      os.path.abspath(os.path.join(workspace_root, "testing")),
  }
  for root, dirs, files in os.walk(sp_dir):
    abs_root = os.path.abspath(root)
    dirs[:] = [
        d
        for d in dirs
        if d not in ("__pycache__", ".git", "node_modules")
        and os.path.abspath(os.path.join(abs_root, d)) not in skip_dirs
    ]
    if abs_root in skip_dirs:
      continue
    rel_root = os.path.relpath(root, sp_dir).replace(os.sep, ".")
    for f in files:
      if f.endswith(".py"):
        base_f = os.path.splitext(f)[0]
        mod_candidates = [base_f]
        if rel_root != ".":
          mod_candidates.append(f"{rel_root}.{base_f}")
        for mc in mod_candidates:
          if mc in sys.modules and not _is_protected_module(
              mc, sys.modules.get(mc), sp_dir, out_dir, lib_dir
          ):
            del sys.modules[mc]
  return sp_dir


def run_tests_python(
    sp_file: str,
    standalone_tests: List[str],
    suite_tests: Dict[str, List[str]],
    filter_pattern: Optional[str] = None,
) -> Tuple[int, int, List[str]]:
  """Executes discovered tests in Python target backend."""
  orig_sys_path = list(sys.path)
  orig_modules = set(sys.modules.keys())
  stem = os.path.splitext(os.path.basename(sp_file))[0]
  try:
    with tempfile.TemporaryDirectory(prefix="sapphire_test_py_") as tmp_dir:
      target_out_py = os.path.join(tmp_dir, f"{stem}.py")
      try:
        out_py = transpile_file(
            sp_file,
            output_file=target_out_py,
            target="python",
            test_mode=True,
            quiet=True,
            raise_on_error=True,
        )
      except Exception as e:  # pragma: no cover
        print(f"[ FAIL ] {os.path.basename(sp_file)} (transpilation failed)")
        for line in str(e).splitlines():
          print(f"  {line}")
        return 0, 1, [f"Transpilation failed: {e}"]

      out_dir = os.path.dirname(os.path.abspath(out_py))
      _prepare_python_test_paths(sp_file, out_dir=out_dir)

      try:
        import std.testing as testing
      except ImportError:  # pragma: no cover
        try:
          from lib.std import testing
        except ImportError:  # pragma: no cover
          print(
              f"[ FAIL ] {os.path.basename(sp_file)} (could not import"
              f" std.testing module)",
              file=sys.stderr,
          )
          return 0, 1, ["Failed to load std.testing module"]

      module_name = "sapphire_test_" + os.path.basename(out_py).replace(".", "_")
      spec = importlib.util.spec_from_file_location(module_name, out_py)
      mod = importlib.util.module_from_spec(spec)
      sys.modules[module_name] = mod
      try:
        spec.loader.exec_module(mod)
      except Exception as e:  # pragma: no cover
        print(f"[ FAIL ] {os.path.basename(sp_file)} (failed to load module)")
        for line in str(e).splitlines():
          print(f"  {line}")
        return 0, 1, [f"Failed to execute transpiled test module: {e}"]

      passed = 0
      failed = 0
      logs: List[str] = []
      sp_line_map = getattr(mod, "_SP_LINE_MAP", {})

      for fn_name in standalone_tests:
        if filter_pattern and filter_pattern not in fn_name:
          continue
        py_fn_name = _mangle_python_name(fn_name)
        test_func = getattr(mod, py_fn_name, None)
        if test_func is None and py_fn_name != fn_name:
          test_func = getattr(mod, fn_name, None)
        if not callable(test_func):
          failed += 1
          msg = f"Test function '{fn_name}' not found or not callable"
          print(f"[ FAIL ] {fn_name} ({os.path.basename(sp_file)})")
          print(f"  {msg}")
          logs.append(msg)
          continue

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
          _print_python_test_failures(
              fn_name, sp_file, ctx.failures, err, sp_line_map
          )

      for struct_name, methods in suite_tests.items():
        py_struct_name = _mangle_python_name(struct_name)
        struct_cls = getattr(mod, py_struct_name, None)
        if struct_cls is None and py_struct_name != struct_name:
          struct_cls = getattr(mod, struct_name, None)

        for m_name in methods:
          full_name = f"{struct_name}.{m_name}"
          if (
              filter_pattern
              and filter_pattern not in full_name
              and filter_pattern not in m_name
          ):
            continue

          if struct_cls is None:
            failed += 1
            msg = f"Test suite struct '{struct_name}' not found"
            print(f"[ FAIL ] {full_name} ({os.path.basename(sp_file)})")
            print(f"  {msg}")
            logs.append(msg)
            continue

          try:
            instance = struct_cls()
          except Exception as ex:
            failed += 1
            msg = f"instantiation failed: {ex}"
            print(f"[ FAIL ] {full_name} ({msg})")
            logs.append(f"{full_name}: {msg}")
            continue

          ctx = testing.TestContext(full_name)
          testing.set_active_context(ctx)

          setup_fn = getattr(instance, "set_up", None) or getattr(
              instance, "func_set_up", None
          )
          if setup_fn:
            try:
              setup_fn()
            except Exception as ex:
              failed += 1
              print(f"[ FAIL ] {full_name} (set_up failed: {ex})")
              continue

          err = None
          py_m_name = _mangle_python_name(m_name)
          test_method = getattr(instance, py_m_name, None)
          if test_method is None and py_m_name != m_name:
            test_method = getattr(instance, m_name, None)

          if not callable(test_method):
            err = f"Test method '{m_name}' not found on struct '{struct_name}'"
          else:
            try:
              test_method()
            except testing.TestFailure as tf:
              err = str(tf)
            except Exception as ex:  # pragma: no cover
              err = f"Unhandled Exception: {ex}"

          teardown_fn = getattr(instance, "tear_down", None) or getattr(
              instance, "func_tear_down", None
          )
          if teardown_fn:
            try:
              teardown_fn()
            except Exception as ex:
              td_msg = f"tear_down failed: {ex}"
              if err is None:
                err = td_msg
              else:
                ctx.failures.append({
                    "message": td_msg,
                    "lineno": 0,
                    "filename": sp_file,
                    "fatal": False,
                    "kind": "generic",
                })

          if not ctx.failures and err is None:
            passed += 1
            print(f"[ PASS ] {full_name} ({os.path.basename(sp_file)})")
          else:
            failed += 1
            _print_python_test_failures(
                full_name, sp_file, ctx.failures, err, sp_line_map
            )

      return passed, failed, logs
  finally:
    for k in list(sys.modules.keys()):
      if k not in orig_modules or k.startswith("sapphire_test_"):
        del sys.modules[k]
    sys.path[:] = orig_sys_path


def _escape_lua_string(s: str) -> str:
  """Normalizes backslashes to forward slashes and escapes quotes for Lua."""
  return s.replace("\\", "/").replace('"', '\\"')


def _build_lua_test_harness(
    sp_file: str,
    out_lua: str,
    standalone_tests: List[str],
    suite_tests: Dict[str, List[str]],
    filter_pattern: Optional[str],
) -> str:
  """Constructs a self-contained Lua 5.1 script that executes discovered tests."""
  workspace_root = os.path.abspath(
      os.path.join(os.path.dirname(__file__), "..", "..")
  )
  sp_dir = os.path.dirname(os.path.abspath(sp_file))
  out_dir = os.path.dirname(os.path.abspath(out_lua))
  esc_workspace_root = _escape_lua_string(workspace_root)
  esc_sp_dir = _escape_lua_string(sp_dir)
  esc_out_dir = _escape_lua_string(out_dir)
  esc_out_lua = _escape_lua_string(out_lua)
  esc_sp_basename = _escape_lua_string(os.path.basename(sp_file))

  pkg_path = (
      f'package.path = "{esc_out_dir}/?.lua;{esc_out_dir}/?/init.lua;'
      f'{esc_workspace_root}/?.lua;'
      f'{esc_workspace_root}/?/init.lua;'
      f'{esc_workspace_root}/lib/?.lua;'
      f'{esc_workspace_root}/lib/?/init.lua;'
      f'{esc_sp_dir}/?.lua;{esc_sp_dir}/?/init.lua;" .. package.path'
  )
  dofile_stmt = (
      f'local target_mod_ok, target_mod = pcall(function() '
      f'return dofile("{esc_out_lua}") end)'
  )
  lua_script_lines = [
      pkg_path,
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
      'local testing = require("std.testing")',
      dofile_stmt,
      'if not target_mod_ok then',
      f'  print("[ FAIL ] {esc_sp_basename} (module load error)")',
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

  for fn_name in standalone_tests:
    if filter_pattern and filter_pattern not in fn_name:
      continue
    esc_fn = _escape_lua_string(fn_name)
    esc_lua_fn = _escape_lua_string(_mangle_lua_name(fn_name))
    lua_script_lines.append(f'''
  do
    local ctx = testing.TestContext.init("{esc_fn}")
    testing.set_active_context(ctx)
    local fn = (target_mod and (target_mod["{esc_lua_fn}"] or target_mod["{esc_fn}"]))
        or _G["{esc_lua_fn}"] or _G["{esc_fn}"]
    if type(fn) ~= "function" then
      total_failed = total_failed + 1
      print("[ FAIL ] {esc_fn} ({esc_sp_basename})")
      print("  Test function '{esc_fn}' not found or not callable")
    else
      local ok, err = pcall(fn)
      if ok and #ctx.failures == 0 then
        total_passed = total_passed + 1
        print("[ PASS ] {esc_fn} ({esc_sp_basename})")
      else
        total_failed = total_failed + 1
        local header_line = get_first_sp_line(ctx.failures)
        if header_line > 0 then
          print("[ FAIL ] {esc_fn} ({esc_sp_basename}:" .. header_line .. ")")
        else
          print("[ FAIL ] {esc_fn} ({esc_sp_basename})")
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

  for struct_name, methods in suite_tests.items():
    for m_name in methods:
      full_name = f"{struct_name}.{m_name}"
      if (
          filter_pattern
          and filter_pattern not in full_name
          and filter_pattern not in m_name
      ):
        continue
      esc_struct = _escape_lua_string(struct_name)
      esc_lua_struct = _escape_lua_string(_mangle_lua_name(struct_name))
      esc_m = _escape_lua_string(m_name)
      esc_lua_m = _escape_lua_string(_mangle_lua_name(m_name))
      esc_full = _escape_lua_string(full_name)
      lua_script_lines.append(f'''
  do
    local ctx = testing.TestContext.init("{esc_full}")
    testing.set_active_context(ctx)
    local struct_cls = (target_mod and (target_mod["{esc_lua_struct}"] or target_mod["{esc_struct}"]))
        or _G["{esc_lua_struct}"] or _G["{esc_struct}"]
    local inst = nil
    local init_ok, init_err = true, nil
    if struct_cls then
      for k, v in pairs(testing.TestCase) do
        if k ~= "__index" and struct_cls[k] == nil then
          struct_cls[k] = v
        end
      end
      if struct_cls.init then
        init_ok, inst = pcall(function() return struct_cls.init() end)
        if not init_ok then
          init_err = inst
          inst = nil
        end
      else
        inst = setmetatable({{}}, struct_cls)
      end
    end

    if not init_ok then
      total_failed = total_failed + 1
      print("[ FAIL ] {esc_full} (instantiation failed: " .. tostring(init_err) .. ")")
    elseif not inst then
      total_failed = total_failed + 1
      print("[ FAIL ] {esc_full} ({esc_sp_basename})")
      print("  Test suite struct '{esc_struct}' could not be instantiated")
    else
      local setup_ok, setup_err = true, nil
      if inst.set_up then
        setup_ok, setup_err = pcall(function() inst:set_up() end)
      end
      if not setup_ok then
        total_failed = total_failed + 1
        print("[ FAIL ] {esc_full} (set_up failed: "
            .. tostring(setup_err) .. ")")
      else
        local test_fn = inst["{esc_lua_m}"] or inst["{esc_m}"]
        if type(test_fn) ~= "function" then
          total_failed = total_failed + 1
          print("[ FAIL ] {esc_full} ({esc_sp_basename})")
          print("  Test method '{esc_m}' not found on struct '{esc_struct}'")
        else
          local ok, err = pcall(function() test_fn(inst) end)
          local td_ok, td_err = true, nil
          if inst.tear_down then
            td_ok, td_err = pcall(function() inst:tear_down() end)
          end
          if not td_ok then
            if ok then
              ok = false
              err = "tear_down failed: " .. tostring(td_err)
            else
              table.insert(ctx.failures, {{
                message = "tear_down failed: " .. tostring(td_err),
                lineno = 0,
                fatal = false,
                kind = "generic",
              }})
            end
          end

          if ok and #ctx.failures == 0 then
            total_passed = total_passed + 1
            print("[ PASS ] {esc_full} ({esc_sp_basename})")
          else
            total_failed = total_failed + 1
            local header_line = get_first_sp_line(ctx.failures)
            if header_line > 0 then
              print("[ FAIL ] {esc_full} ({esc_sp_basename}:"
                  .. header_line .. ")")
            else
              print("[ FAIL ] {esc_full} ({esc_sp_basename})")
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

  lua_script_lines.append("os.exit((total_failed > 0) and 1 or 0)")
  return "\n".join(lua_script_lines)


def run_tests_lua(
    sp_file: str,
    standalone_tests: List[str],
    suite_tests: Dict[str, List[str]],
    filter_pattern: Optional[str] = None,
    sourcemap: bool = True,
) -> Tuple[int, int, List[str]]:
  """Executes discovered tests in Lua 5.1 target backend."""
  stem = os.path.splitext(os.path.basename(sp_file))[0]
  with tempfile.TemporaryDirectory(prefix="sapphire_test_lua_") as tmp_dir:
    target_out_lua = os.path.join(tmp_dir, f"{stem}.lua")
    try:
      out_lua = transpile_file(
          sp_file,
          output_file=target_out_lua,
          target="lua",
          test_mode=True,
          sourcemap=sourcemap,
          quiet=True,
          raise_on_error=True,
      )
    except Exception as e:  # pragma: no cover
      print(f"[ FAIL ] {os.path.basename(sp_file)} (transpilation failed)")
      for line in str(e).splitlines():
        print(f"  {line}")
      return 0, 1, [f"Transpilation failed: {e}"]

    lua_bin = find_lua_binary()
    if not lua_bin:  # pragma: no cover
      print(
          "Error: Lua interpreter ('lua', 'luajit', or 'lua5.1') not found in"
          " PATH.",
          file=sys.stderr,
      )
      print(
          f"[ FAIL ] {os.path.basename(sp_file)} (Lua interpreter not found in"
          f" PATH)"
      )
      return 0, 1, ["Lua interpreter not found"]

    harness_src = _build_lua_test_harness(
        sp_file, out_lua, standalone_tests, suite_tests, filter_pattern
    )
    runner_tmp = os.path.join(tmp_dir, f"{stem}.runner.lua")
    with open(runner_tmp, "w", encoding="utf-8") as f:
      f.write(harness_src)

    res = subprocess.run([lua_bin, runner_tmp], capture_output=True, text=True)
    if res.stdout:
      print(res.stdout.strip())
    stderr_text = res.stderr.strip() if res.stderr else ""
    if stderr_text:  # pragma: no cover
      print(stderr_text, file=sys.stderr)

    stdout_lines = [l.strip() for l in res.stdout.splitlines() if l.strip()]
    passed = sum(1 for l in stdout_lines if l.startswith("[ PASS ]"))
    failed = sum(1 for l in stdout_lines if l.startswith("[ FAIL ]"))
    errs: List[str] = []
    if stderr_text:
      errs.append(stderr_text)
    if res.returncode != 0 and failed == 0:
      failed = 1
      crash_msg = (
          f"Lua test runner exited unexpectedly with code {res.returncode}"
          + (f": {stderr_text}" if stderr_text else "")
      )
      print(f"[ FAIL ] {os.path.basename(sp_file)} ({crash_msg})")
      if not errs:
        errs.append(crash_msg)

    return passed, failed, errs



def _parse_test_output_lines(
    output: str, sp_file: str
) -> List[Dict[str, Any]]:
  """Parses [ PASS ] / [ FAIL ] lines from captured test runner output."""
  records: List[Dict[str, Any]] = []
  current: Optional[Dict[str, Any]] = None
  for raw_line in output.splitlines():
    stripped = raw_line.strip()
    if stripped.startswith("[ PASS ] "):
      name = stripped[len("[ PASS ] "):]
      current = {"status": "pass", "name": name, "file": sp_file}
      records.append(current)
    elif stripped.startswith("[ FAIL ] "):
      name = stripped[len("[ FAIL ] "):]
      current = {
          "status": "fail",
          "name": name,
          "file": sp_file,
          "details": [],
      }
      records.append(current)
    elif current is not None and current["status"] == "fail" and stripped:
      current["details"].append(stripped)
  return records


def run_tests(
    path: Any,
    target: str = "python",
    filter_pattern: Optional[str] = None,
    sourcemap: bool = True,
    json_output: bool = False,
) -> int:
  """Main entry point for `sapphire test` command.

  Returns:
    Exit code (0 for success, 1 for failure).
  """
  paths = [path] if isinstance(path, str) else list(path or ["."])
  sp_files: List[str] = []
  seen_files = set()
  for p in paths:
    if json_output and not os.path.exists(p):
      print(
          json.dumps(
              {
                  "ok": False,
                  "target": target,
                  "passed": 0,
                  "failed": 1,
                  "duration_sec": 0.0,
                  "tests": [],
                  "errors": [{"file": p, "message": f"Path '{p}' not found."}],
              },
              indent=2,
          )
      )
      return 1
    for f in find_sp_files(p):
      norm = os.path.abspath(f)
      if norm not in seen_files:
        seen_files.add(norm)
        sp_files.append(f)
  if not sp_files:  # pragma: no cover
    joined = ", ".join(paths)
    if json_output:
      print(
          json.dumps(
              {
                  "ok": False,
                  "target": target,
                  "passed": 0,
                  "failed": 1,
                  "duration_sec": 0.0,
                  "tests": [],
                  "errors": [
                      {
                          "file": joined,
                          "message": f"No Sapphire (.sp) source files found in '{joined}'.",
                      }
                  ],
              },
              indent=2,
          )
      )
    else:
      print(f"No Sapphire (.sp) source files found in '{joined}'.", file=sys.stderr)
    return 1

  total_passed = 0
  total_failed = 0
  tests_found = 0
  test_records: List[Dict[str, Any]] = []
  file_errors: List[Dict[str, Any]] = []
  start_time = time.time()
  use_lua_backend = target.lower() in ("lua", "lua5.1", "love2d", "love")

  if not json_output:
    print(f"Running Sapphire tests in target '{target}'...\n")

  for sp_file in sp_files:
    try:
      ast = parse_ast(sp_file)
      disc_warnings: List[str] = []
      standalone_tests, suite_tests = discover_tests(ast, warnings=disc_warnings)
      if not json_output:
        for w in disc_warnings:
          print(f"[ WARNING ] {os.path.basename(sp_file)}: {w}")
    except Exception as e:  # pragma: no cover
      if json_output:
        file_errors.append({"file": sp_file, "message": str(e)})
      else:
        print(f"[ FAIL ] {os.path.basename(sp_file)} (parsing failed)")
        for line in str(e).splitlines():
          print(f"  {line}")
      total_failed += 1
      continue

    if not standalone_tests and not suite_tests:
      if len(sp_files) == 1 and not json_output:
        print(f"No tests found in '{sp_file}'.")
      continue

    tests_found += len(standalone_tests) + sum(len(m) for m in suite_tests.values())

    if json_output:
      out_buf = io.StringIO()
      err_buf = io.StringIO()
      with contextlib.redirect_stdout(out_buf), contextlib.redirect_stderr(err_buf):
        if use_lua_backend:
          passed, failed, errs = run_tests_lua(
              sp_file, standalone_tests, suite_tests, filter_pattern, sourcemap
          )
        else:
          passed, failed, errs = run_tests_python(
              sp_file, standalone_tests, suite_tests, filter_pattern
          )
      total_passed += passed
      total_failed += failed
      test_records.extend(_parse_test_output_lines(out_buf.getvalue(), sp_file))
      for err_msg in errs:
        file_errors.append({"file": sp_file, "message": err_msg})
      extra_err = err_buf.getvalue().strip()
      if extra_err and extra_err not in errs:
        file_errors.append({"file": sp_file, "message": extra_err})
    else:
      if use_lua_backend:
        passed, failed, _ = run_tests_lua(
            sp_file, standalone_tests, suite_tests, filter_pattern, sourcemap
        )
        total_passed += passed
        total_failed += failed
      else:
        passed, failed, _ = run_tests_python(
            sp_file, standalone_tests, suite_tests, filter_pattern
        )
        total_passed += passed
        total_failed += failed

  if len(sp_files) > 1 and tests_found == 0 and total_failed == 0 and not json_output:
    joined = ", ".join(paths)
    print(f"No tests found in '{joined}'.")

  duration = time.time() - start_time
  if json_output:
    print(
        json.dumps(
            {
                "ok": total_failed == 0,
                "target": target,
                "passed": total_passed,
                "failed": total_failed,
                "duration_sec": round(duration, 3),
                "tests": test_records,
                "errors": file_errors,
            },
            indent=2,
        )
    )
  else:
    print(f"\nTest Result: {total_passed} passed, {total_failed} failed in {duration:.2f}s")
  return 1 if total_failed > 0 else 0
