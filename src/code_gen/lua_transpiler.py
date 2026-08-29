"""Code generator to transpile Sapphire AST into executable Lua 5.1 code.

This module implements an AST visitor that formats and outputs Lua 5.1 code
corresponding to the semantic behavior of Sapphire, including a runtime header
for prototypal inheritance delegation and Arena memory management.
"""

import os
import sys
from typing import Any, Dict, List, Optional, Set

from antlr4 import FileStream, CommonTokenStream
from antlr4.error.ErrorListener import ErrorListener

from src.parser.ast import *
from src.parser.gen.SapphireLexer import SapphireLexer
from src.parser.gen.SapphireParser import SapphireParser
from src.parser.ast_builder import ASTBuilder
from src.semantics.type_checker import TypeChecker, SemanticError
from src.semantics.symbol_table import MapType, RangeType
from src.code_gen.source_map import SourceMapBuilder
from src.code_gen.base_transpiler import BaseTranspiler, get_default_value_for_type_node, is_coroutine_func
from src.code_gen.transpiler_registry import TranspilerRegistry



# ==========================================
# Sapphire Lua 5.1 Runtime Preamble
# ==========================================

LUA_RUNTIME_PREAMBLE = """-- Sapphire Lua 5.1 Runtime Header

local _Coroutine = {}
_Coroutine.__index = _Coroutine

function _Coroutine.create(fn, ...)
  local args = { ... }
  local n = select("#", ...)
  local self = setmetatable({}, _Coroutine)
  self._fn = fn
  self._args = args
  self._n = n
  self._done = false
  self:reset()
  return self
end

function _Coroutine:step(...)
  if self._done or (self._co and coroutine.status(self._co) == "dead") then
    self._done = true
    return nil
  end
  local ok, val = coroutine.resume(self._co, ...)
  if not ok then
    error(val)
  end
  if coroutine.status(self._co) == "dead" then
    self._done = true
    return val
  end
  return val
end

function _Coroutine:is_done()
  if self._done or (self._co and coroutine.status(self._co) == "dead") then
    self._done = true
    return true
  end
  return false
end

function _Coroutine:reset()
  local fn = self._fn
  local args = self._args
  local n = self._n or #args
  self._co = coroutine.create(function()
    if table.unpack then
      return fn(table.unpack(args, 1, n))
    else
      return fn(unpack(args, 1, n))
    end
  end)
  self._done = false
end

local Arena = {}
Arena.__index = Arena

function Arena.init()
  local self = setmetatable({}, Arena)
  self.objects = {}
  return self
end

function Arena:register(obj)
  if type(obj) == "table" then
    local meta = getmetatable(obj)
    if meta and meta.__arena and meta.__arena ~= self then
      for i, o in ipairs(meta.__arena.objects) do
        if o == obj then
          table.remove(meta.__arena.objects, i)
          break
        end
      end
    end
    table.insert(self.objects, obj)
    if meta then
      meta.__arena = self
    end
  end
  return obj
end

function Arena:destroy()
  for _, obj in ipairs(self.objects) do
    local meta = getmetatable(obj)
    if meta and meta.__shadow then
      for k in pairs(meta.__shadow) do
        meta.__shadow[k] = nil
      end
    end
  end
  self.objects = {}
end

function Arena:dispose()
  self:destroy()
end

local _DEFAULT_ARENA = Arena.init()

local _clone_helper

local _create_cow_proxy
_create_cow_proxy = function(parent_shadow, parent_proto, key)
  local proxy_meta = {}
  proxy_meta.__index = function(tbl, sub_key)
    if parent_shadow[key] ~= nil then
      return parent_shadow[key][sub_key]
    end
    if parent_proto and parent_proto[key] ~= nil then
      local val = parent_proto[key][sub_key]
      if type(val) == "table" then
        return _create_cow_proxy(parent_shadow, parent_proto[key], sub_key)
      end
      return val
    end
    return nil
  end
  proxy_meta.__newindex = function(tbl, sub_key, value)
    if parent_shadow[key] == nil then
      local target = parent_proto[key]
      parent_shadow[key] = _clone_helper(target, nil, nil)
    end
    parent_shadow[key][sub_key] = value
  end
  return setmetatable({}, proxy_meta)
end

local function _create_proto_object(proto, class_tbl)
  local shadow = {}
  local meta = {}
  meta.__shadow = shadow
  meta.__proto = proto
  meta.__class = class_tbl
  meta.__index = function(tbl, key)
    if key == "__proto__" then return meta.__proto end
    if key == "__shadow__" then return meta.__shadow end
    if shadow[key] ~= nil then return shadow[key] end
    if proto ~= nil then
      local val = proto[key]
      if val ~= nil then
        if type(val) == "table" then
          return _create_cow_proxy(shadow, proto, key)
        end
        return val
      end
    end
    if class_tbl and class_tbl[key] ~= nil then
      return class_tbl[key]
    end
    return nil
  end
  meta.__newindex = function(tbl, key, val)
    if key == "__proto__" or key == "__shadow__" then return end
    if proto ~= nil then
      shadow[key] = val
    else
      rawset(tbl, key, val)
    end
  end
  local obj = setmetatable({}, meta)
  if proto == nil then
    _DEFAULT_ARENA:register(obj)
  end
  return obj
end

_clone_helper = function(obj, init_fn, arena)
  if obj == nil then return nil end
  local clone_obj
  if type(obj) == "table" then
    local meta = getmetatable(obj)
    if obj.clone and type(obj.clone) == "function" then
      clone_obj = obj:clone()
    elseif meta and meta.__class then
      clone_obj = _create_proto_object(obj, meta.__class)
    else
      clone_obj = _create_proto_object(obj, nil)
    end
  else
    clone_obj = obj
  end
  if arena ~= nil and type(clone_obj) == "table" then
    arena:register(clone_obj)
  end
  if init_fn then
    init_fn(clone_obj)
  end
  return clone_obj
end

local _sapphire_string_strip = function(s, chars)
  if s == nil then return "" end
  if chars == nil or chars == "" then
    return s:match("^%s*(.-)%s*$") or ""
  end
  local escaped = chars:gsub("(%W)", "%%%1")
  local pattern = "^[" .. escaped .. "]*(.-)[" .. escaped .. "]*$"
  return s:match(pattern) or ""
end

local _sapphire_string_split = function(s, sep)
  if s == nil then return {} end
  local res = {}
  if sep == "" then
    for i = 1, #s do
      table.insert(res, s:sub(i, i))
    end
    return res
  end
  if sep == nil then
    for w in s:gmatch("%S+") do
      table.insert(res, w)
    end
    return res
  end
  local start = 1
  while true do
    local p_start, p_end = s:find(sep, start, true)
    if not p_start then
      table.insert(res, s:sub(start))
      break
    end
    table.insert(res, s:sub(start, p_start - 1))
    start = p_end + 1
  end
  return res
end

local _sapphire_string_find = function(s, sub, start_idx, reverse)
  if s == nil or sub == nil then return nil end
  local s_len = #s
  local start_0 = start_idx or 0
  if reverse then
    local last_pos = nil
    local curr = 1
    while curr <= s_len do
      local p_start = s:find(sub, curr, true)
      if not p_start then break end
      local idx_0 = p_start - 1
      if idx_0 >= start_0 then
        last_pos = idx_0
      end
      curr = p_start + 1
    end
    return last_pos
  else
    local start_1 = start_0 + 1
    local p_start = s:find(sub, start_1, true)
    if p_start then
      return p_start - 1
    end
    return nil
  end
end

local _sapphire_string_to_int = function(s, radix)
  if s == nil then return nil end
  local r = radix or 10
  local num = tonumber(s, r)
  if num then
    return math.floor(num)
  end
  return nil
end

local _sapphire_string_to_float = function(s)
  if s == nil then return nil end
  return tonumber(s)
end

local _sapphire_string_to_bool = function(s)
  if type(s) ~= "string" then return nil end
  local clean = s:match("^%s*(.-)%s*$"):lower()
  if clean == "true" then return true end
  if clean == "false" then return false end
  return nil
end

local _sapphire_cast_int = function(v)
  if type(v) == "boolean" then return v and 1 or 0 end
  local n = tonumber(v)
  return n and math.floor(n) or 0
end

local _sapphire_enum_from = function(enum_tbl, val)
  if val == nil or enum_tbl == nil then return nil end
  for name, value in pairs(enum_tbl) do
    if value == val or name == val then
      return value
    end
  end
  return nil
end

local _sapphire_array_map = function(arr, fn, in_place)
  if in_place then
    for i = 1, #arr do
      arr[i] = fn(arr[i])
    end
    return arr
  end
  local res = {}
  for i = 1, #arr do
    res[i] = fn(arr[i])
  end
  return res
end

local _sapphire_array_filter = function(arr, fn, in_place)
  if in_place then
    local res = {}
    for i = 1, #arr do
      if fn(arr[i]) then
        table.insert(res, arr[i])
      end
    end
    for i = #arr, 1, -1 do
      arr[i] = nil
    end
    for i = 1, #res do
      arr[i] = res[i]
    end
    return arr
  end
  local res = {}
  for i = 1, #arr do
    if fn(arr[i]) then
      table.insert(res, arr[i])
    end
  end
  return res
end

local _sapphire_array_reduce = function(arr, initial, fn, reverse)
  local acc = initial
  local len = #arr
  if reverse then
    for i = len, 1, -1 do
      acc = fn(acc, arr[i])
    end
  else
    for i = 1, len do
      acc = fn(acc, arr[i])
    end
  end
  return acc
end

local _sapphire_array_contains = function(arr, element)
  for i = 1, #arr do
    if arr[i] == element then
      return true
    end
  end
  return false
end

local _sapphire_array_reverse = function(arr, in_place)
  local len = #arr
  if in_place then
    for i = 1, math.floor(len / 2) do
      local tmp = arr[i]
      arr[i] = arr[len - i + 1]
      arr[len - i + 1] = tmp
    end
    return arr
  end
  local res = {}
  for i = 1, len do
    res[i] = arr[len - i + 1]
  end
  return res
end

local _sapphire_array_sort = function(arr, by, reverse, in_place)
  local target = arr
  if not in_place then
    target = {}
    for i = 1, #arr do
      target[i] = arr[i]
    end
  end
  table.sort(target, function(a, b)
    if by then
      local cmp = by(a, b)
      if reverse then
        return cmp > 0
      else
        return cmp < 0
      end
    else
      if reverse then
        return a > b
      else
        return a < b
      end
    end
  end)
  return target
end

local _sapphire_array_join = function(arr, sep)
  local delimiter = sep
  if delimiter == nil then delimiter = ", " end
  local str_arr = {}
  for i = 1, #arr do
    str_arr[i] = tostring(arr[i])
  end
  return table.concat(str_arr, delimiter)
end

local _sapphire_array_push = function(arr, element)
  table.insert(arr, element)
  return element
end

local _sapphire_array_pop = function(arr)
  if #arr == 0 then return nil end
  return table.remove(arr)
end

local _sapphire_array_insert = function(arr, index, element)
  local len = #arr
  local idx_1 = index < 0 and (len + index + 1) or (index + 1)
  if idx_1 < 1 then idx_1 = 1 end
  if idx_1 > len + 1 then idx_1 = len + 1 end
  table.insert(arr, idx_1, element)
  return element
end

local _sapphire_array_remove = function(arr, index)
  local len = #arr
  local idx_1 = index < 0 and (len + index + 1) or (index + 1)
  if idx_1 >= 1 and idx_1 <= len then
    return table.remove(arr, idx_1)
  end
  return nil
end

local _sapphire_array_clear = function(arr)
  for i = #arr, 1, -1 do
    arr[i] = nil
  end
end

local _sapphire_map_size = function(m)
  local count = 0
  for _ in pairs(m) do
    count = count + 1
  end
  return count
end

local _sapphire_map_empty = function(m)
  return next(m) == nil
end

local _sapphire_map_contains = function(m, k)
  return m[k] ~= nil
end

local _sapphire_map_keys = function(m)
  local res = {}
  for k in pairs(m) do
    table.insert(res, k)
  end
  return res
end

local _sapphire_map_values = function(m)
  local res = {}
  for _, v in pairs(m) do
    table.insert(res, v)
  end
  return res
end

local _sapphire_map_insert = function(m, k, v)
  m[k] = v
  return v
end

local _sapphire_map_remove = function(m, k)
  local val = m[k]
  m[k] = nil
  return val
end

local _sapphire_map_clear = function(m)
  for k in pairs(m) do
    m[k] = nil
  end
end

local _sapphire_iter_array = function(arr)
  if type(arr) ~= "table" then return ipairs({}) end
  local meta = getmetatable(arr)
  if meta and meta.__index then
    local i = 0
    return function()
      i = i + 1
      local val = arr[i]
      if val ~= nil then
        return i, val
      end
      return nil
    end
  end
  return ipairs(arr)
end

local _sapphire_range = function(a, b, c)
  local start, stop, step
  if b == nil then
    start = 0
    stop = a
    step = 1
  elseif c == nil then
    start = a
    stop = b
    step = 1
  else
    start = a
    stop = b
    step = c
  end
  local iter = function(state, curr)
    local next_val = curr + state.step
    if (state.step > 0 and next_val < state.stop) or (state.step < 0 and next_val > state.stop) then
      return next_val
    end
    return nil
  end
  return iter, {stop = stop, step = step}, start - step
end

local _sapphire_dispose = function(obj)
  if obj == nil then return end
  if type(obj) == "table" and type(obj.dispose) == "function" then
    obj:dispose()
  elseif type(obj) == "userdata" then
    local meta = getmetatable(obj)
    if meta and type(meta.dispose) == "function" then
      obj:dispose()
    end
  end
end
"""


LUA_SOURCEMAP_DEMANGLER = """-- Sapphire Lua Runtime Source Map Demangler & Love2D Error Handler Hook
local function _sapphire_demangle_traceback(msg)
  local err_msg = tostring(msg or "Runtime Error")
  local traceback = debug.traceback("", 2)
  local demangled_lines = {}
  local full_text = err_msg .. "\\n" .. traceback

  for line in full_text:gmatch("[^\\r\\n]+") do
    local cur_line = line
    local lua_file, line_num = cur_line:match("([^:%s]+%.lua):(%d+):")
    if not line_num then
      lua_file, line_num = cur_line:match("([^:%s]+):(%d+):")
    end
    if line_num then
      local n = tonumber(line_num)
      if _SP_LINE_MAP and _SP_LINE_MAP[n] then
        local info = _SP_LINE_MAP[n]
        local sp_info = string.format("%s:%d: (at %s:%d)", info.file, info.line, lua_file or "lua", n)
        if info.text and info.text ~= "" then
          sp_info = sp_info .. " -> `" .. info.text .. "`"
        end
        cur_line = cur_line:gsub("([^:%s]+%.?l?u?a?):" .. line_num .. ":", sp_info)
      end
    end
    table.insert(demangled_lines, cur_line)
  end
  return table.concat(demangled_lines, "\\n")
end

if love and love.errorhandler then
  local original_errorhandler = love.errorhandler
  love.errorhandler = function(msg)
    local demangled = _sapphire_demangle_traceback(msg)
    print("========================================")
    print("SAPPHIRE RUNTIME ERROR (Love2D)")
    print(demangled)
    print("========================================")
    return original_errorhandler(demangled)
  end
end
"""

LUA_DEV_RELOAD_WATCHER = """-- Sapphire Dev Mode: High-Performance Live Hot-Reloading Hook
local _SP_DEV_WATCHER = {
  last_modified = {},
  tracked_files = { "main.lua", ".sapphire_reload" },
  poll_interval = 0.1,
  elapsed = 0
}

function _SP_DEV_WATCHER.register_file(path)
  if not path then return end
  for _, f in ipairs(_SP_DEV_WATCHER.tracked_files) do
    if f == path then return end
  end
  table.insert(_SP_DEV_WATCHER.tracked_files, path)
end

local function _sp_reload_file(file)
  local modname = file:gsub("%.lua$", ""):gsub("/", ".")
  package.loaded[modname] = nil
  local chunk, err = love.filesystem.load(file)
  if chunk then
    local ok, runtime_err = pcall(chunk)
    if not ok then
      print("[Sapphire Hot-Reload Error] " .. tostring(runtime_err))
    else
      print("[Sapphire Hot-Reload] Successfully reloaded " .. file)
    end
  else
    print("[Sapphire Hot-Reload Compile Error] " .. tostring(err))
  end
end

function _SP_DEV_WATCHER.check(dt)
  if not love or not love.filesystem then return end
  _SP_DEV_WATCHER.elapsed = _SP_DEV_WATCHER.elapsed + (dt or 0)
  if _SP_DEV_WATCHER.elapsed < _SP_DEV_WATCHER.poll_interval then return end
  _SP_DEV_WATCHER.elapsed = 0

  -- 1. Check direct signal trigger file (.sapphire_reload)
  local sig_info = love.filesystem.getInfo(".sapphire_reload")
  if sig_info and sig_info.modtime then
    if _SP_DEV_WATCHER.last_modified[".sapphire_reload"] and _SP_DEV_WATCHER.last_modified[".sapphire_reload"] ~= sig_info.modtime then
      _SP_DEV_WATCHER.last_modified[".sapphire_reload"] = sig_info.modtime
      local content, _ = love.filesystem.read(".sapphire_reload")
      if content then
        for target_file in content:gmatch("[^\\r\\n]+") do
          local clean_file = target_file:match("^%s*(.-)%s*$")
          if clean_file and clean_file ~= "" then
            _sp_reload_file(clean_file)
          end
        end
      end
    else
      _SP_DEV_WATCHER.last_modified[".sapphire_reload"] = sig_info.modtime
    end
  end

  -- 2. Check tracked game files directly without directory traversal
  for _, file in ipairs(_SP_DEV_WATCHER.tracked_files) do
    if file ~= ".sapphire_reload" then
      local info = love.filesystem.getInfo(file)
      if info and info.modtime then
        if _SP_DEV_WATCHER.last_modified[file] and _SP_DEV_WATCHER.last_modified[file] ~= info.modtime then
          _SP_DEV_WATCHER.last_modified[file] = info.modtime
          _sp_reload_file(file)
        else
          _SP_DEV_WATCHER.last_modified[file] = info.modtime
        end
      end
    end
  end
end
"""


def _has_continue_node(node: ASTNode) -> bool:
  if isinstance(node, ContinueNode):
    return True
  if isinstance(node, (WhileNode, ForNode)):
    return False
  for attr_name, attr_val in getattr(node, "__dict__", {}).items():
    if attr_name.startswith("_"):
      continue
    if isinstance(attr_val, ASTNode):
      if _has_continue_node(attr_val):
        return True
    elif isinstance(attr_val, list):
      for item in attr_val:
        if isinstance(item, ASTNode) and _has_continue_node(item):
          return True
  return False


@TranspilerRegistry.register(aliases=["lua", "lua5.1", "love2d", "love"], display_name="Lua 5.1", default_extension=".lua")
class LuaTranspiler(BaseTranspiler):

  """AST visitor to transpile Sapphire code to Lua 5.1."""

  def __init__(
      self,
      source_file: Optional[str] = None,
      source_map_builder: Optional[SourceMapBuilder] = None,
      test_mode: bool = False,
      dev_mode: bool = False,
  ):
    self.code: List[str] = []
    self.indent_level = 0
    self.current_line = 1
    self.current_column = 0
    self.source_file = source_file
    self.source_map_builder = source_map_builder
    self.test_mode = test_mode
    self.dev_mode = dev_mode
    self.on_reload_callbacks: List[str] = []
    self.declared_symbols: List[str] = []
    # Map struct names to their collected method AST nodes from impl blocks
    self.struct_methods: Dict[str, List[Any]] = {}
    self.known_structs: Set[str] = set()
    self.arena_stack: List[List[str]] = []
    self.disposable_stack: List[List[str]] = []
    self._identifier_map: Dict[str, str] = {}
    self._loop_stack: List[bool] = []

  def emit(self, text: str) -> None:
    """Emits text on the current line and updates line/column numbers."""
    lines = text.split("\n")
    if len(lines) == 1:
      self.current_column += len(text)
    else:
      self.current_line += len(lines) - 1
      self.current_column = len(lines[-1])
    self.code.append(text)

  def newline(self) -> None:
    """Starts a new line with the current level of indentation."""
    indent_str = "  " * self.indent_level
    self.code.append("\n" + indent_str)
    self.current_line += 1
    self.current_column = len(indent_str)

  def indent(self) -> None:
    """Increments the indentation level."""
    self.indent_level += 1

  def dedent(self) -> None:
    """Decrements the indentation level."""
    if self.indent_level > 0:
      self.indent_level -= 1

  def get_output(self) -> str:
    """Returns the final generated Lua 5.1 source code string."""
    return "".join(self.code)

  def transpile(
      self,
      program: ProgramNode,
      source_file: Optional[str] = None,
      source_map_builder: Optional[SourceMapBuilder] = None,
  ) -> str:
    """Main entry point to transpile a Sapphire ProgramNode to Lua 5.1."""
    if source_file:
      self.source_file = source_file
    if source_map_builder:
      self.source_map_builder = source_map_builder

    # 1. Output runtime preamble
    self.emit(LUA_RUNTIME_PREAMBLE)
    self.newline()

    if self.dev_mode:
      self.emit(LUA_DEV_RELOAD_WATCHER)
      self.newline()

    # 1b. Transpile module imports
    for imp in getattr(program, "imports", []):
      self.visit(imp)

    # 2. Collect known struct names and impl block methods
    for decl in program.declarations:
      if getattr(decl, "type_params", None):
        continue
      if isinstance(decl, StructDeclNode):
        self.known_structs.add(decl.name)
      elif isinstance(decl, ImplBlockNode):
        if decl.struct_name not in self.struct_methods:
          self.struct_methods[decl.struct_name] = []
        self.struct_methods[decl.struct_name].extend(decl.members)

    struct_decls = []
    func_decls = []
    executable_stmts = []
    has_main = False

    for decl in program.declarations:
      if getattr(decl, "type_params", None):
        continue
      if isinstance(decl, ImplBlockNode):
        continue
      elif isinstance(decl, FuncDeclNode):
        if decl.name == "main":
          has_main = True
        func_decls.append(decl)
      elif isinstance(decl, (StructDeclNode, EnumDeclNode, TraitDeclNode,
                             VarDeclNode)):
        struct_decls.append(decl)
      else:
        executable_stmts.append(decl)

    forward_names = []
    if not self.dev_mode:
      for decl in struct_decls:
        if isinstance(decl, StructDeclNode):
          forward_names.append(decl.name)
      for decl in func_decls:
        if not any(a.name == "export" for a in getattr(decl, "annotations", [])):
          forward_names.append(decl.name)

    if forward_names:
      self.emit(f"local {', '.join(forward_names)}")
      self.newline()

    top_level_decls = struct_decls + func_decls

    # 3. Transpile all top-level declarations (types, functions, global variables)
    for decl in top_level_decls:
      self.visit(decl)
      self.newline()

    # 4. Transpile executable top-level statements and main invocation
    for stmt in executable_stmts:
      self.visit(stmt)
      self.newline()

    if has_main:
      self.emit("main()")
      self.newline()

    for cb in self.on_reload_callbacks:
      self.newline()
      self.emit(f"if {cb} then {cb}() end")

    # 6. Append inline source map table and Love2D error demangler if sourcemap builder present
    if self.source_map_builder and self.source_map_builder.mappings:
      self.newline()
      self.emit(self.source_map_builder.to_lua_line_map_table())
      self.newline()
      self.emit(LUA_SOURCEMAP_DEMANGLER)
      self.newline()

    if getattr(program, "export_block", None):
      self.visit(program.export_block)
    elif self.test_mode and self.declared_symbols:
      self.newline()
      self.emit("local _M = {}")
      for sym in self.declared_symbols:
        self.newline()
        self.emit(f"_M.{sym} = {sym}")
      self.newline()
      self.emit("return _M")

    return self.get_output()

  # ==========================================
  # Visitor Dispatcher
  # ==========================================

  def visit(self, node: ASTNode) -> None:
    """Visit an AST node and emit its corresponding Lua code."""
    if self.source_map_builder and getattr(node, "start_line", None) is not None:
      src = getattr(node, "source_file", None) or self.source_file
      if src:
        self.source_map_builder.add_mapping(
            gen_line=self.current_line,
            gen_col=self.current_column,
            source_file=src,
            orig_line=node.start_line,
            orig_col=node.start_column or 0,
        )
    method_name = f"visit_{node.__class__.__name__}"
    visitor = getattr(self, method_name, self.generic_visit)
    visitor(node)

  def generic_visit(self, node: ASTNode) -> None:
    raise NotImplementedError(
      f"Lua Transpilation for visitor visit_{node.__class__.__name__}"
      f" is not implemented.")

  # ==========================================
  # Declarations Visitor
  # ==========================================

  def visit_EnumDeclNode(self, node: EnumDeclNode) -> None:
    self.newline()
    self.emit(f"local {node.name} = {{")
    self.indent()
    current_val: Union[int, str] = 0
    is_string_enum = any(isinstance(m.value, str) for m in node.members)
    for idx, member in enumerate(node.members):
      if member.value is not None:
        current_val = member.value
      elif is_string_enum and isinstance(current_val, str):
        current_val = member.name
      self.newline()
      if isinstance(current_val, str):
        self.emit(f'{member.name} = "{current_val}"')
      else:
        self.emit(f"{member.name} = {current_val}")
        current_val += 1
      if idx < len(node.members) - 1:
        self.emit(",")
    self.dedent()
    self.newline()
    self.emit("}")
    self.newline()

  def visit_ImportStmtNode(self, node: ImportStmtNode) -> None:
    alias_name = node.alias if node.alias else node.path.split(".")[-1]
    self.emit(f"local {alias_name} = require(\"{node.path}\")")
    if self.dev_mode:
      file_path = node.path.replace(".", "/") + ".lua"
      self.newline()
      self.emit(f"if _SP_DEV_WATCHER and _SP_DEV_WATCHER.register_file then _SP_DEV_WATCHER.register_file(\"{file_path}\") end")
    self.newline()

  def visit_ExportStmtNode(self, node: ExportStmtNode) -> None:
    self.newline()
    self.emit("local _M = {}")
    self.newline()
    for spec in node.specifiers:
      exp_name = spec.exported_name
      if spec.module_prefix:
        self.emit(f"_M.{exp_name} = {spec.module_prefix}.{spec.symbol}")
      else:
        self.emit(f"_M.{exp_name} = {spec.symbol}")
      self.newline()
    self.emit("return _M")
    self.newline()

  def visit_StructDeclNode(self, node: StructDeclNode) -> None:
    # Header definition for struct
    self.known_structs.add(node.name)
    self.declared_symbols.append(node.name)
    is_proto = node.is_prototype
    struct_name = node.name
    methods = self.struct_methods.get(struct_name, [])

    self.newline()
    if self.dev_mode:
      self.emit(f"{struct_name} = {struct_name} or {{}}")
    else:
      self.emit(f"{struct_name} = {{}}")
    self.newline()
    self.emit(f"{struct_name}.__index = {struct_name}")
    self.newline()

    if node.parent_names:
      if len(node.parent_names) == 1:
        self.emit(f"setmetatable({struct_name}, {{ __index = {node.parent_names[0]} }})")
      else:
        chain = " or ".join(f"{p}[k]" for p in node.parent_names)
        self.emit(f"setmetatable({struct_name}, {{ __index = function(t, k) return {chain} end }})")
      self.newline()

    # Define helper `._init_fields(self)`
    self.emit(f"function {struct_name}._init_fields(self)")
    self.indent()
    if node.parent_names:
      for p in node.parent_names:
        self.newline()
        self.emit(f"if {p}._init_fields then {p}._init_fields(self) end")
    for f in node.fields:
      default_expr = f.default_expr or get_default_value_for_type_node(f.field_type)
      if default_expr:
        self.newline()
        temp = LuaTranspiler()
        temp.known_structs = self.known_structs
        temp.visit(default_expr)
        self.emit(f"self.{f.name} = {temp.get_output()}")
    self.dedent()
    self.newline()
    self.emit("end")
    self.newline()

    # Define constructor `.init(...)`
    self.emit(f"function {struct_name}.init(kwargs, proto)")
    self.indent()
    self.newline()
    self.emit("kwargs = kwargs or {}")
    self.newline()
    self.emit("local self")
    self.newline()
    if is_proto:
      self.emit(f"self = _create_proto_object(proto, {struct_name})")
    else:
      self.emit(f"self = setmetatable({{}}, {struct_name})")

    self.newline()
    self.emit("if proto == nil then")
    self.indent()
    self.newline()
    self.emit(f"{struct_name}._init_fields(self)")
    self.dedent()
    self.newline()
    self.emit("end")
    self.newline()

    self.emit("for k, v in pairs(kwargs) do")
    self.indent()
    self.newline()
    self.emit("self[k] = v")
    self.dedent()
    self.newline()
    self.emit("end")

    init_member = next((m for m in methods if m.func_decl.name == "__init__"), None)
    if init_member:
      init_args = []
      for idx, p in enumerate(init_member.func_decl.parameters):
        init_args.append(f"(kwargs['{p.name}'] ~= nil and kwargs['{p.name}'] or kwargs[{idx + 1}])")
      call_args = ["self"] + init_args
      self.newline()
      self.emit(f"if {struct_name}._init_sapphire then")
      self.indent()
      self.newline()
      self.emit(f"{struct_name}._init_sapphire({', '.join(call_args)})")
      self.dedent()
      self.newline()
      self.emit("end")

    self.newline()
    self.emit("return self")
    self.dedent()
    self.newline()
    self.emit("end")
    self.newline()

    # Emit methods from impl block
    for m in methods:
      self._visit_ImplMemberNode_for_struct(m, struct_name)

  def visit_StructFieldNode(self, node: StructFieldNode) -> None:
    pass

  def visit_ImplMemberNode(self, node: ImplMemberNode) -> None:
    """Public visitor satisfying the BaseTranspiler contract.

    Impl members are not visited standalone in the Lua backend -- they are
    emitted as part of `visit_StructDeclNode` via the private helper. This
    method exists solely to fulfil the abstract-method contract so that the
    class hierarchy remains structurally symmetric with `PythonTranspiler`.
    """
    # Struct name is unavailable at this call site; callers that need to emit
    # a specific impl member should use _visit_ImplMemberNode_for_struct.
    raise NotImplementedError(
        "visit_ImplMemberNode must be called via visit_StructDeclNode in the "
        "Lua backend, not directly on a standalone ImplMemberNode."
    )

  def _visit_ImplMemberNode_for_struct(self, node: ImplMemberNode,
                                       struct_name: str) -> None:
    func = node.func_decl
    func_name = "_init_sapphire" if func.name == "__init__" else func.name
    self.newline()

    if node.modifier == "static":
      params = [p.name for p in func.parameters if p.name != "self"]
      self.emit(f"function {struct_name}.{func_name}({', '.join(params)})")
    else:
      other_params = [p.name for p in func.parameters if p.name != "self"]
      self.emit(f"function {struct_name}:{func_name}({', '.join(other_params)})")

    self.indent()
    for p in func.parameters:
      if p.default_expr:
        self.newline()
        temp = LuaTranspiler()
        temp.known_structs = self.known_structs
        temp.visit(p.default_expr)
        self.emit(f"if {p.name} == nil then {p.name} = {temp.get_output()} end")
    if is_coroutine_func(func):
      self.newline()
      all_params = (["self"] if node.modifier != "static" else []) + [p.name for p in func.parameters if p.name != "self"]
      if all_params:
        self.emit(f"return _Coroutine.create(function({', '.join(all_params)})")
      else:
        self.emit("return _Coroutine.create(function()")
      self.indent()
      self.visit(func.body)
      self.dedent()
      self.newline()
      if all_params:
        self.emit(f"end, {', '.join(all_params)})")
      else:
        self.emit("end)")
    else:
      self.visit(func.body)
    self.dedent()
    self.newline()
    self.emit("end")
    self.newline()

  def visit_TraitDeclNode(self, node: TraitDeclNode) -> None:
    # Traits are compile-time contracts erased at runtime
    pass

  def visit_FuncDeclNode(self, node: FuncDeclNode) -> None:
    is_test_func = any(getattr(a, "name", "") == "test" for a in getattr(node, "annotations", []))
    if is_test_func and not self.test_mode:
      return
    if is_test_func:
      self.declared_symbols.append(node.name)

    if any(getattr(a, "name", "") == "on_reload" for a in getattr(node, "annotations", [])):
      self.on_reload_callbacks.append(node.name)

    export_ann = next((a for a in node.annotations if a.name == "export"), None)
    params = [p.name for p in node.parameters]

    self.newline()
    if export_ann:
      target_path = export_ann.arg if export_ann.arg else node.name
      self.emit(f"function {target_path}({', '.join(params)})")
    else:
      self.emit(f"function {node.name}({', '.join(params)})")

    self.indent()
    if self.dev_mode and export_ann and export_ann.arg == "love.update":
      self.newline()
      self.emit("if _SP_DEV_WATCHER then _SP_DEV_WATCHER.check(dt) end")

    # Check default parameters
    for p in node.parameters:
      if p.default_expr:
        self.newline()
        temp = LuaTranspiler()
        temp.known_structs = self.known_structs
        temp.visit(p.default_expr)
        self.emit(f"if {p.name} == nil then {p.name} = {temp.get_output()} end")
    if is_coroutine_func(node):
      self.newline()
      if params:
        self.emit(f"return _Coroutine.create(function({', '.join(params)})")
      else:
        self.emit("return _Coroutine.create(function()")
      self.indent()
      self.visit(node.body)
      self.dedent()
      self.newline()
      if params:
        self.emit(f"end, {', '.join(params)})")
      else:
        self.emit("end)")
    else:
      self.visit(node.body)
    self.dedent()
    self.newline()
    self.emit("end")
    self.newline()

  # ==========================================
  # Statements Visitor
  # ==========================================

  def visit_BlockNode(self, node: BlockNode) -> None:
    self.arena_stack.append([])
    self.disposable_stack.append([])
    if getattr(node, "_with_disposables", None):
      self.disposable_stack[-1].extend(node._with_disposables)
    if not node.statements:
      self.newline()
      self.emit("-- pass")
    else:
      for stmt in node.statements:
        self.visit(stmt)

    current_arenas = self.arena_stack.pop()
    current_disposables = self.disposable_stack.pop()
    has_returned = bool(node.statements and isinstance(node.statements[-1], ReturnNode))
    if not has_returned:
      for disp_name in reversed(current_disposables):
        self.newline()
        self.emit(f"_sapphire_dispose({disp_name})")
      for arena_name in reversed(current_arenas):
        self.newline()
        self.emit(f"{arena_name}:destroy()")

  def _lift_match_expressions(self, node: Any) -> None:
    """Finds all MatchExprNode in the AST subtree and emits their match statement blocks first."""
    if node is None:
      return
    if isinstance(node, MatchExprNode):
      if not getattr(node, "_is_lifted", False):
        node._is_lifted = True
        for case in node.cases:
          self._lift_match_expressions(case.body)
        node._lifted_var = self._emit_match_statement(node)
      return
    if isinstance(node, list):
      for item in node:
        self._lift_match_expressions(item)
      return
    if isinstance(node, ASTNode):
      for v in node.__dict__.values():
        if isinstance(v, (ASTNode, list)):
          self._lift_match_expressions(v)

  def visit_VarDeclNode(self, node: VarDeclNode) -> None:
    if any(a.name == "extern" for a in node.annotations):
      return

    if len(node.names) == 1 and node.expr:
      is_arena = (
          isinstance(node.expr, CallNode)
          and isinstance(node.expr.callee, IdentifierNode)
          and node.expr.callee.name == "Arena"
      )
      if is_arena and self.arena_stack:
        self.arena_stack[-1].append(node.names[0])

    self._lift_match_expressions(node.exprs)

    self.newline()
    names_str = ", ".join(node.names)
    if self.dev_mode and self.indent_level == 0 and len(node.names) == 1 and node.exprs:
      name = node.names[0]
      self.emit(f"{name} = {name} ~= nil and {name} or ")
      self.visit(node.exprs[0])
      return

    self.emit(f"local {names_str}")
    if node.exprs:
      self.emit(" = ")
      for idx, expr in enumerate(node.exprs):
        if idx > 0:
          self.emit(", ")
        self.visit(expr)
    else:
      defaults = []
      has_non_nil = False
      for idx, name in enumerate(node.names):
        val_type = node.val_types[idx] if idx < len(node.val_types) else None
        default_expr = get_default_value_for_type_node(val_type)
        if default_expr:
          temp = LuaTranspiler()
          temp.known_structs = self.known_structs
          temp.visit(default_expr)
          defaults.append(temp.get_output())
          if default_expr.lit_type != "none":
            has_non_nil = True
        else:
          defaults.append("nil")
      if has_non_nil:
        self.emit(" = " + ", ".join(defaults))

  def visit_AssignmentNode(self, node: AssignmentNode) -> None:
    self._lift_match_expressions(node.targets)
    self._lift_match_expressions(node.exprs)

    self.newline()
    if node.op == "=":
      for idx, target in enumerate(node.targets):
        if idx > 0:
          self.emit(", ")
        self.visit(target)
      self.emit(" = ")
      for idx, expr in enumerate(node.exprs):
        if idx > 0:
          self.emit(", ")
        self.visit(expr)
    else:
      raw_op = node.op[:-1]
      self.visit(node.target)
      self.emit(" = ")
      self.visit(node.target)
      self.emit(f" {raw_op} ")
      self.visit(node.expr)

  def visit_ExprStmtNode(self, node: ExprStmtNode) -> None:
    if isinstance(node.expr, MatchExprNode):
      self._emit_match_statement(node.expr, target_var=None)
      return
    self._lift_match_expressions(node.expr)
    self.newline()
    self.visit(node.expr)

  def visit_ReturnNode(self, node: ReturnNode) -> None:
    all_active_arenas = [
        a for frame in reversed(self.arena_stack) for a in reversed(frame)
    ]
    all_active_disposables = [
        d for frame in reversed(self.disposable_stack) for d in reversed(frame)
    ]
    self._lift_match_expressions(node.expressions)

    for disp_name in all_active_disposables:
      self.newline()
      self.emit(f"_sapphire_dispose({disp_name})")

    for arena_name in all_active_arenas:
      self.newline()
      self.emit(f"{arena_name}:destroy()")

    self.newline()
    if node.expressions:
      self.emit("return ")
      for idx, expr in enumerate(node.expressions):
        if idx > 0:
          self.emit(", ")
        self.visit(expr)
    else:
      self.emit("return")

  def _emit_match_statement(self, node: MatchExprNode, target_var: Optional[str] = "") -> str:
    if target_var == "":
      self._temp_match_count = getattr(self, "_temp_match_count", 0) + 1
      target_var = f"_match_res_{self._temp_match_count}"
      self.newline()
      self.emit(f"local {target_var} = nil")

    self._temp_subj_count = getattr(self, "_temp_subj_count", 0) + 1
    subj_var = f"_subj_{self._temp_subj_count}"
    self.newline()
    self.emit(f"local {subj_var} = ")
    self.visit(node.subject)

    prev_target = getattr(self, "_current_match_target", None)
    prev_match_node = getattr(self, "_current_match_node", None)
    self._current_match_target = target_var
    self._current_match_node = node

    for idx, case in enumerate(node.cases):
      self.newline()
      if isinstance(case.pattern, EllipsisPatternNode):
        if idx == 0:
          self.emit("if true then")
        else:
          self.emit("else")
      else:
        if idx == 0:
          self.emit(f"if {subj_var} == ")
          self.visit(case.pattern)
          self.emit(" then")
        else:
          self.emit(f"elseif {subj_var} == ")
          self.visit(case.pattern)
          self.emit(" then")

      self.indent()
      if isinstance(case.body, BlockNode):
        self.visit(case.body)
      else:
        self.newline()
        if target_var:
          self.emit(f"{target_var} = ")
          self.visit(case.body)
        else:
          self.visit(case.body)  # pragma: no cover
      self.dedent()

    self.newline()
    self.emit("end")
    self._current_match_target = prev_target
    self._current_match_node = prev_match_node
    return target_var or ""

  def visit_YieldNode(self, node: YieldNode) -> None:
    exprs = getattr(node, "expressions", None) or ([node.expr] if node.expr else [])
    self._lift_match_expressions(exprs)
    target = getattr(self, "_current_match_target", None)
    match_node = getattr(self, "_current_match_node", None)
    self.newline()
    if target:
      self.emit(f"{target} = ")
      if not exprs:
        self.emit("nil")
      elif len(exprs) == 1:
        self.visit(exprs[0])
      else:
        if match_node:
          match_node._is_multi_yield = True
        self.emit("{ ")
        for idx, expr in enumerate(exprs):
          if idx > 0:
            self.emit(", ")
          self.visit(expr)
        self.emit(" }")
    else:
      if not exprs:
        self.emit("coroutine.yield()")
      elif len(exprs) == 1:
        self.emit("coroutine.yield(")
        self.visit(exprs[0])
        self.emit(")")
      else:
        self.emit("coroutine.yield(")
        for idx, expr in enumerate(exprs):
          if idx > 0:
            self.emit(", ")
          self.visit(expr)
        self.emit(")")

  def visit_MatchExprNode(self, node: MatchExprNode) -> None:
    if not getattr(node, "_is_lifted", False):
      node._is_lifted = True
      node._lifted_var = self._emit_match_statement(node)
    if getattr(node, "_is_multi_yield", False):
      self.emit(f"(table.unpack or unpack)({node._lifted_var})")
    else:
      self.emit(node._lifted_var)

  def visit_EllipsisPatternNode(self, node: EllipsisPatternNode) -> None:
    pass

  def visit_IfNode(self, node: IfNode) -> None:
    if node.init_binding:
      self._lift_match_expressions(node.init_binding.expr)
    if node.condition:
      self._lift_match_expressions(node.condition)

    self.newline()
    if node.init_binding:
      let_name = node.init_binding.let_name
      if node.init_binding.is_unwrap:
        val_var = f"_val_{let_name}"
        self.emit(f"local {val_var} = ")
        self.visit(node.init_binding.expr)
        self.newline()

        # Map identifier to temporary variable during condition check
        old_map = self._identifier_map.copy()
        self._identifier_map[let_name] = val_var

        self.emit(f"if {val_var} ~= nil")
        if node.condition:
          self.emit(" and ")
          self.visit(node.condition)
        self.emit(" then")

        # Restore identifier map
        self._identifier_map = old_map

        self.indent()
        self.newline()
        self.emit(f"local {let_name} = {val_var}")
        self.visit(node.then_block)
        self.dedent()
      else:
        # Standard bind + condition
        self.emit(f"local {let_name} = ")
        self.visit(node.init_binding.expr)
        self.newline()
        self.emit("if ")
        self.visit(node.condition)
        self.emit(" then")
        self.indent()
        self.visit(node.then_block)
        self.dedent()
    else:
      self.emit("if ")
      self.visit(node.condition)
      self.emit(" then")
      self.indent()
      self.visit(node.then_block)
      self.dedent()

    if node.else_block:
      self.newline()
      self.emit("else")
      self.indent()
      self.visit(node.else_block)
      self.dedent()

    self.newline()
    self.emit("end")

  def _visit_loop_body(self, block: BlockNode, has_continue: bool) -> None:
    if has_continue:
      self.newline()
      self.emit("local _break_outer = false")
      self.newline()
      self.emit("repeat")
      self.indent()
      self.visit(block)
      self.dedent()
      self.newline()
      self.emit("until true")
      self.newline()
      self.emit("if _break_outer then break end")
    else:
      self.visit(block)

  def visit_WhileNode(self, node: WhileNode) -> None:
    has_continue = _has_continue_node(node.block)
    self._loop_stack.append(has_continue)
    try:
      if node.init_binding:
        self._lift_match_expressions(node.init_binding.expr)
      if node.condition:
        self._lift_match_expressions(node.condition)

      self.newline()
      if node.init_binding:
        let_name = node.init_binding.let_name
        if node.init_binding.is_unwrap:
          self.emit("while true do")
          self.indent()
          self.newline()
          val_var = f"_val_{let_name}"
          self.emit(f"local {val_var} = ")
          self.visit(node.init_binding.expr)
          self.newline()

          # Map identifier to temporary variable during condition check
          old_map = self._identifier_map.copy()
          self._identifier_map[let_name] = val_var

          self.emit(f"if not ({val_var} ~= nil")
          if node.condition:
            self.emit(" and ")
            self.visit(node.condition)
          self.emit(") then")

          # Restore map
          self._identifier_map = old_map

          self.indent()
          self.newline()
          self.emit("break")
          self.dedent()
          self.newline()
          self.emit("end")
          self.newline()
          self.emit(f"local {let_name} = {val_var}")
          self._visit_loop_body(node.block, has_continue)
          self.dedent()
          self.newline()
          self.emit("end")
        else:
          # Standard init-statement: execute once before loop begins
          self.emit(f"local {let_name} = ")
          self.visit(node.init_binding.expr)
          self.newline()
          self.emit("while ")
          self.visit(node.condition)
          self.emit(" do")
          self.indent()
          self._visit_loop_body(node.block, has_continue)
          self.dedent()
          self.newline()
          self.emit("end")
      else:
        self.emit("while ")
        self.visit(node.condition)
        self.emit(" do")
        self.indent()
        self._visit_loop_body(node.block, has_continue)
        self.dedent()
        self.newline()
        self.emit("end")
    finally:
      self._loop_stack.pop()

  def visit_ForNode(self, node: ForNode) -> None:
    has_continue = _has_continue_node(node.block)
    self._loop_stack.append(has_continue)
    try:
      self._lift_match_expressions(node.iterable)
      self.newline()
      if node.key_var is not None:
        self.emit(f"for {node.key_var}, {node.val_var} in pairs(")
        self.visit(node.iterable)
        self.emit(") do")
      elif (
          isinstance(getattr(node.iterable, "inferred_type", None), RangeType)
          or (isinstance(node.iterable, CallNode) and isinstance(node.iterable.callee, IdentifierNode) and node.iterable.callee.name == "range")
      ):
        self.emit(f"for {node.val_var} in ")
        self.visit(node.iterable)
        self.emit(" do")
      else:
        self.emit(f"for _, {node.val_var} in _sapphire_iter_array(")
        self.visit(node.iterable)
        self.emit(") do")
      self.indent()
      self._visit_loop_body(node.block, has_continue)
      self.dedent()
      self.newline()
      self.emit("end")
    finally:
      self._loop_stack.pop()

  def visit_BreakNode(self, node: BreakNode) -> None:
    self.newline()
    if self._loop_stack and self._loop_stack[-1]:
      self.emit("_break_outer = true")
      self.newline()
    self.emit("break")

  def visit_ContinueNode(self, node: ContinueNode) -> None:
    self.newline()
    self.emit("break")

  # ==========================================
  # Expressions Visitor
  # ==========================================

  def visit_LiteralNode(self, node: LiteralNode) -> None:
    if node.lit_type == "bool":
      self.emit("true" if node.value else "false")
    elif node.lit_type == "none":
      self.emit("nil")
    elif node.lit_type == "string":
      self.emit(f'"{node.value}"')
    else:
      self.emit(str(node.value))

  def visit_InterpolatedStringNode(self, node: InterpolatedStringNode) -> None:
    if not node.parts:
      self.emit('""')
      return

    if len(node.parts) == 1:
      part = node.parts[0]
      if isinstance(part, LiteralNode) and part.lit_type == "string":
        escaped_val = part.value.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
        self.emit(f'"{escaped_val}"')
      else:
        self.emit("tostring(")
        self.visit(part)
        self.emit(")")
      return

    self.emit("(")
    for idx, part in enumerate(node.parts):
      if idx > 0:
        self.emit(" .. ")
      if isinstance(part, LiteralNode) and part.lit_type == "string":
        escaped_val = part.value.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
        self.emit(f'"{escaped_val}"')
      else:
        self.emit("tostring(")
        self.visit(part)
        self.emit(")")
    self.emit(")")

  def visit_IdentifierNode(self, node: IdentifierNode) -> None:
    if node.name == "Arena":
      self.emit("Arena.init")
    else:
      name = self._identifier_map.get(node.name, node.name)
      self.emit(name)

  def visit_BinaryOpNode(self, node: BinaryOpNode) -> None:
    if node.op == "??":
      self.emit("((function() local _v = ")
      self.visit(node.left)
      self.emit("; if _v ~= nil then return _v else return ")
      self.visit(node.right)
      self.emit(" end end)())")
      return

    op_map = {"&&": "and", "||": "or", "!=": "~="}
    op = op_map.get(node.op, node.op)

    if op == "+":
      if getattr(node, "is_string_concat", False) or (isinstance(node.left, LiteralNode) and node.left.lit_type == "string") or (isinstance(node.right, LiteralNode) and node.right.lit_type == "string"):
        op = ".."

    self.emit("(")
    self._visit_concat_operand(node.left, is_string_concat=(op == ".."))
    self.emit(f" {op} ")
    self._visit_concat_operand(node.right, is_string_concat=(op == ".."))
    self.emit(")")

  def _visit_concat_operand(self, expr: ASTNode, is_string_concat: bool) -> None:
    if not is_string_concat:
      self.visit(expr)
      return
    if isinstance(expr, LiteralNode) and expr.lit_type in ("string", "int", "float"):
      self.visit(expr)
    elif isinstance(expr, (CallNode, IdentifierNode, MemberAccessNode, IndexExprNode)):
      self.emit("tostring(")
      self.visit(expr)
      self.emit(")")
    else:
      self.visit(expr)

  def visit_TernaryExprNode(self, node: TernaryExprNode) -> None:
    self.emit("((function() if ")
    self.visit(node.condition)
    self.emit(" then return ")
    self.visit(node.true_expr)
    self.emit(" else return ")
    self.visit(node.false_expr)
    self.emit(" end end)())")

  def visit_UnaryOpNode(self, node: UnaryOpNode) -> None:
    if node.op == "+":
      self.emit("(")
      self.visit(node.expr)
      self.emit(")")
      return
    op_map = {"!": "not "}
    op = op_map.get(node.op, node.op)
    self.emit(f"({op}")
    self.visit(node.expr)
    self.emit(")")

  def visit_CastExprNode(self, node: CastExprNode) -> None:
    target = node.target_type.name if hasattr(node.target_type, "name") else str(node.target_type)
    if target == "float":
      self.emit("tonumber(")
      self.visit(node.expr)
      self.emit(")")
    elif target == "int":
      self.emit("_sapphire_cast_int(")
      self.visit(node.expr)
      self.emit(")")
    elif target == "bool":
      self.emit("(not not ")
      self.visit(node.expr)
      self.emit(")")
    elif target == "String":
      self.emit("tostring(")
      self.visit(node.expr)
      self.emit(")")
    else:
      self.visit(node.expr)

  def visit_CallNode(self, node: CallNode) -> None:
    if isinstance(node.callee, MemberAccessNode) and getattr(node.callee, "is_string_from", False):
      self.emit("tostring(")
      self.visit(node.arguments[0].expr)
      self.emit(")")
      return

    if isinstance(node.callee, MemberAccessNode) and getattr(node.callee, "is_enum_from", False):
      self.emit("_sapphire_enum_from(")
      self.visit(node.callee.receiver)
      self.emit(", ")
      self.visit(node.arguments[0].expr)
      self.emit(")")
      return

    if isinstance(node.callee, MemberAccessNode) and getattr(node.callee, "is_string_method", False):
      method = node.callee.member
      receiver = node.callee.receiver
      if method == "size":
        self.emit("(#")
        self.visit(receiver)
        self.emit(")")
        return
      elif method == "empty":
        self.emit("(#")
        self.visit(receiver)
        self.emit(" == 0)")
        return
      elif method == "lower":
        self.emit("string.lower(")
        self.visit(receiver)
        self.emit(")")
        return
      elif method == "upper":
        self.emit("string.upper(")
        self.visit(receiver)
        self.emit(")")
        return
      elif method == "strip":
        self.emit("_sapphire_string_strip(")
        self.visit(receiver)
        if node.arguments:
          self.emit(", ")
          self.visit(node.arguments[0].expr)
        self.emit(")")
        return
      elif method == "split":
        self.emit("_sapphire_string_split(")
        self.visit(receiver)
        if node.arguments:
          self.emit(", ")
          self.visit(node.arguments[0].expr)
        self.emit(")")
        return
      elif method == "contains":
        self.emit("(string.find(")
        self.visit(receiver)
        self.emit(", ")
        self.visit(node.arguments[0].expr)
        self.emit(", 1, true) ~= nil)")
        return
      elif method == "find":
        self.emit("_sapphire_string_find(")
        self.visit(receiver)
        args_by_param = [None, None, None]  # sub, start, reverse
        param_names = ["sub", "start", "reverse"]
        for idx, arg in enumerate(node.arguments):
          if arg.name and arg.name in param_names:
            p_idx = param_names.index(arg.name)
            args_by_param[p_idx] = arg.expr
          elif idx < 3:
            args_by_param[idx] = arg.expr

        while args_by_param and args_by_param[-1] is None:
          args_by_param.pop()

        for p_expr in args_by_param:
          self.emit(", ")
          if p_expr is None:
            self.emit("nil")
          else:
            self.visit(p_expr)
        self.emit(")")
        return
      elif method == "to_int":
        self.emit("_sapphire_string_to_int(")
        self.visit(receiver)
        if node.arguments:
          for arg in node.arguments:
            self.emit(", ")
            self.visit(arg.expr)
        self.emit(")")
        return
      elif method == "to_float":
        self.emit("_sapphire_string_to_float(")
        self.visit(receiver)
        self.emit(")")
        return
      elif method == "to_bool":
        self.emit("_sapphire_string_to_bool(")
        self.visit(receiver)
        self.emit(")")
        return

    if isinstance(node.callee, MemberAccessNode) and getattr(node.callee, "is_array_method", False):
      method = node.callee.array_method
      receiver = node.callee.receiver
      if method == "size":
        self.emit("#")
        self.visit(receiver)
        return
      elif method == "empty":
        self.emit("(#")
        self.visit(receiver)
        self.emit(" == 0)")
        return
      elif method == "map":
        self.emit("_sapphire_array_map(")
        self.visit(receiver)
        fn_expr = None
        in_place_expr = None
        for idx, arg in enumerate(node.arguments):
          if arg.name == "fn":
            fn_expr = arg.expr
          elif arg.name == "in_place":
            in_place_expr = arg.expr
          elif idx == 0 and not arg.name:
            fn_expr = arg.expr
          elif idx == 1 and not arg.name:
            in_place_expr = arg.expr
        self.emit(", ")
        self.visit(fn_expr)
        if in_place_expr:
          self.emit(", ")
          self.visit(in_place_expr)
        self.emit(")")
        return
      elif method == "filter":
        self.emit("_sapphire_array_filter(")
        self.visit(receiver)
        fn_expr = None
        in_place_expr = None
        for idx, arg in enumerate(node.arguments):
          if arg.name == "fn":
            fn_expr = arg.expr
          elif arg.name == "in_place":
            in_place_expr = arg.expr
          elif idx == 0 and not arg.name:
            fn_expr = arg.expr
          elif idx == 1 and not arg.name:
            in_place_expr = arg.expr
        self.emit(", ")
        self.visit(fn_expr)
        if in_place_expr:
          self.emit(", ")
          self.visit(in_place_expr)
        self.emit(")")
        return
      elif method == "reduce":
        self.emit("_sapphire_array_reduce(")
        self.visit(receiver)
        initial_expr = None
        fn_expr = None
        reverse_expr = None
        for idx, arg in enumerate(node.arguments):
          if arg.name == "initial":
            initial_expr = arg.expr
          elif arg.name == "fn":
            fn_expr = arg.expr
          elif arg.name == "reverse":
            reverse_expr = arg.expr
          elif idx == 0 and not arg.name:
            initial_expr = arg.expr
          elif idx == 1 and not arg.name:
            fn_expr = arg.expr
          elif idx == 2 and not arg.name:
            reverse_expr = arg.expr

        self.emit(", ")
        self.visit(initial_expr)
        self.emit(", ")
        self.visit(fn_expr)
        if reverse_expr:
          self.emit(", ")
          self.visit(reverse_expr)
        self.emit(")")
        return
      elif method == "contains":
        self.emit("_sapphire_array_contains(")
        self.visit(receiver)
        self.emit(", ")
        self.visit(node.arguments[0].expr)
        self.emit(")")
        return
      elif method == "reverse":
        self.emit("_sapphire_array_reverse(")
        self.visit(receiver)
        if node.arguments:
          self.emit(", ")
          self.visit(node.arguments[0].expr)
        self.emit(")")
        return
      elif method == "sort":
        self.emit("_sapphire_array_sort(")
        self.visit(receiver)
        by_expr = None
        reverse_expr = None
        in_place_expr = None
        for idx, arg in enumerate(node.arguments):
          if arg.name == "by":
            by_expr = arg.expr
          elif arg.name == "reverse":
            reverse_expr = arg.expr
          elif arg.name == "in_place":
            in_place_expr = arg.expr
          elif idx == 0 and not arg.name:
            by_expr = arg.expr
          elif idx == 1 and not arg.name:
            reverse_expr = arg.expr
          elif idx == 2 and not arg.name:
            in_place_expr = arg.expr

        self.emit(", ")
        if by_expr:
          self.visit(by_expr)
        else:
          self.emit("nil")
        if reverse_expr:
          self.emit(", ")
          self.visit(reverse_expr)
        else:
          self.emit(", false")
        if in_place_expr:
          self.emit(", ")
          self.visit(in_place_expr)
        self.emit(")")
        return
      elif method == "join":
        self.emit("_sapphire_array_join(")
        self.visit(receiver)
        if node.arguments:
          self.emit(", ")
          self.visit(node.arguments[0].expr)
        self.emit(")")
        return
      elif method == "push":
        self.emit("_sapphire_array_push(")
        self.visit(receiver)
        self.emit(", ")
        self.visit(node.arguments[0].expr)
        self.emit(")")
        return
      elif method == "pop":
        self.emit("_sapphire_array_pop(")
        self.visit(receiver)
        self.emit(")")
        return
      elif method == "insert":
        self.emit("_sapphire_array_insert(")
        self.visit(receiver)
        index_expr = None
        element_expr = None
        for idx, arg in enumerate(node.arguments):
          if arg.name == "index":
            index_expr = arg.expr
          elif arg.name == "element":
            element_expr = arg.expr
          elif idx == 0 and not arg.name:
            index_expr = arg.expr
          elif idx == 1 and not arg.name:
            element_expr = arg.expr
        self.emit(", ")
        self.visit(index_expr)
        self.emit(", ")
        self.visit(element_expr)
        self.emit(")")
        return
      elif method == "remove":
        self.emit("_sapphire_array_remove(")
        self.visit(receiver)
        self.emit(", ")
        self.visit(node.arguments[0].expr)
        self.emit(")")
        return
      elif method == "clear":
        self.emit("_sapphire_array_clear(")
        self.visit(receiver)
        self.emit(")")
        return

    if isinstance(node.callee, MemberAccessNode) and getattr(node.callee, "is_map_method", False):
      method = node.callee.map_method
      receiver = node.callee.receiver
      if method == "size":
        self.emit("_sapphire_map_size(")
        self.visit(receiver)
        self.emit(")")
        return
      elif method == "empty":
        self.emit("_sapphire_map_empty(")
        self.visit(receiver)
        self.emit(")")
        return
      elif method == "contains":
        self.emit("_sapphire_map_contains(")
        self.visit(receiver)
        self.emit(", ")
        self.visit(node.arguments[0].expr)
        self.emit(")")
        return
      elif method == "keys":
        self.emit("_sapphire_map_keys(")
        self.visit(receiver)
        self.emit(")")
        return
      elif method == "values":
        self.emit("_sapphire_map_values(")
        self.visit(receiver)
        self.emit(")")
        return
      elif method == "insert":
        self.emit("_sapphire_map_insert(")
        self.visit(receiver)
        key_expr = None
        val_expr = None
        for idx, arg in enumerate(node.arguments):
          if arg.name == "key":
            key_expr = arg.expr
          elif arg.name == "value":
            val_expr = arg.expr
          elif idx == 0 and not arg.name:
            key_expr = arg.expr
          elif idx == 1 and not arg.name:
            val_expr = arg.expr
        self.emit(", ")
        self.visit(key_expr)
        self.emit(", ")
        self.visit(val_expr)
        self.emit(")")
        return
      elif method == "remove":
        self.emit("_sapphire_map_remove(")
        self.visit(receiver)
        self.emit(", ")
        self.visit(node.arguments[0].expr)
        self.emit(")")
        return
      elif method == "clear":
        self.emit("_sapphire_map_clear(")
        self.visit(receiver)
        self.emit(")")
        return

    # Check if this call is calling a struct constructor, e.g. Weapon(...)
    if (isinstance(node.callee, IdentifierNode) and
        node.callee.name in self.known_structs):
      struct_name = node.callee.name
      self.emit(f"{struct_name}.init({{")
      for idx, arg in enumerate(node.arguments):
        if idx > 0:
          self.emit(", ")
        if arg.name:
          self.emit(f"{arg.name} = ")
        else:
          self.emit(f"[{idx + 1}] = ")
        self.visit(arg.expr)
      self.emit("})")
      return

    # Method call optimization for instance methods (e.g. obj.method()) vs
    # static calls
    if isinstance(node.callee, IdentifierNode) and node.callee.name == "range":
      self.emit("_sapphire_range(")
      for idx, arg in enumerate(node.arguments):
        if idx > 0:
          self.emit(", ")
        self.visit(arg.expr)
      self.emit(")")
      return

    if isinstance(node.callee, MemberAccessNode):
      member_name = getattr(node.callee, "target_name", None) or node.callee.member
      receiver_name = getattr(node.callee.receiver, "name", None)
      if getattr(node.callee, "is_instance_method", False):
        self.visit(node.callee.receiver)
        self.emit(f":{member_name}(")
      elif getattr(node.callee, "is_static_method", False) or (receiver_name and receiver_name in self.known_structs):
        self.visit(node.callee.receiver)
        self.emit(f".{member_name}(")
      elif isinstance(node.callee.receiver, MemberAccessNode):
        self.visit(node.callee.receiver)
        self.emit(f".{member_name}(")
      else:
        self.visit(node.callee.receiver)
        self.emit(f":{member_name}(")
    else:
      self.visit(node.callee)
      self.emit("(")

    for idx, arg in enumerate(node.arguments):
      if idx > 0:
        self.emit(", ")
      self.visit(arg.expr)
    self.emit(")")

  def visit_MemberAccessNode(self, node: MemberAccessNode) -> None:
    if node.is_optional:
      self.emit("(")
      self.visit(node.receiver)
      self.emit(" ~= nil and ")
      self.visit(node.receiver)
      self.emit(f".{node.member} or nil)")
    else:
      self.visit(node.receiver)
      self.emit(f".{node.member}")

  def visit_CloneNode(self, node: CloneNode) -> None:
    self.emit("_clone_helper(")
    self.visit(node.expr)

    if node.initializer_block:
      self.emit(", function(self)")
      self.indent()
      for stmt in node.initializer_block:
        self.visit(stmt)
      self.dedent()
      self.newline()
      self.emit("end")
    else:
      if node.arena_expr:
        self.emit(", nil")

    if node.arena_expr:
      self.emit(", ")
      self.visit(node.arena_expr)

    self.emit(")")

  def visit_LambdaNode(self, node: LambdaNode) -> None:
    params = [p.name for p in node.parameters]
    self.emit(f"(function({', '.join(params)})")
    self.indent()
    if isinstance(node.body, BlockNode):
      self.visit(node.body)
    else:
      self.newline()
      self.emit("return ")
      self.visit(node.body)
    self.dedent()
    self.newline()
    self.emit("end)")

  def visit_ArrayLiteralNode(self, node: ArrayLiteralNode) -> None:
    self.emit("{")
    for idx, elem in enumerate(node.elements):
      if idx > 0:
        self.emit(", ")
      self.visit(elem)
    self.emit("}")

  def visit_MapLiteralNode(self, node: MapLiteralNode) -> None:
    self.emit("{")
    for idx, entry in enumerate(node.entries):
      if idx > 0:
        self.emit(", ")
      self.emit("[")
      self.visit(entry.key)
      self.emit("] = ")
      self.visit(entry.value)
    self.emit("}")

  def visit_IndexExprNode(self, node: IndexExprNode) -> None:
    self.visit(node.array)
    self.emit("[")
    is_map = isinstance(getattr(node.array, 'inferred_type', None), MapType)
    if is_map:
      self.visit(node.index)
    else:
      if isinstance(node.index, LiteralNode) and node.index.lit_type == "int":
        self.emit(str(node.index.value + 1))
      else:
        self.visit(node.index)
        self.emit(" + 1")
    self.emit("]")

  def visit_GuardStmtNode(self, node: GuardStmtNode) -> None:
    for clause in node.clauses:
      self.newline()
      if clause.binding:
        binding = clause.binding
        let_names = getattr(binding, "let_names", [binding.let_name])
        self._temp_guard_count = getattr(self, "_temp_guard_count", 0) + 1
        tmp_var = f"_guard_val_{self._temp_guard_count}"

        self.emit(f"local {tmp_var} = ")
        self.visit(binding.expr)
        self.newline()

        if binding.is_unwrap:
          self.emit(f"if {tmp_var} == nil then")
          self.indent()
          self.visit(node.else_block)
          self.dedent()
          self.newline()
          self.emit("end")
          self.newline()

        if len(let_names) > 1:
          for idx, name in enumerate(let_names):
            self.emit(f"local {name} = {tmp_var}[{idx + 1}]")
            if idx < len(let_names) - 1:
              self.newline()
        else:
          self.emit(f"local {binding.let_name} = {tmp_var}")
      elif clause.condition:
        self.emit("if not (")
        self.visit(clause.condition)
        self.emit(") then")
        self.indent()
        self.visit(node.else_block)
        self.dedent()
        self.newline()
        self.emit("end")

  def visit_GuardClauseNode(self, node: GuardClauseNode) -> None:
    if node.binding:
      self.visit(node.binding.expr)
    elif node.condition:
      self.visit(node.condition)

  def visit_WithClauseNode(self, node: WithClauseNode) -> None:
    if node.binding:
      self.visit(node.binding.expr)
    elif node.expr:
      self.visit(node.expr)

  def visit_WithStmtNode(self, node: WithStmtNode) -> None:
    self._temp_with_count = getattr(self, "_temp_with_count", 0)

    clause_vars = []  # List of (tmp_var, is_unwrap, binding, expr)
    for clause in node.clauses:
      self._temp_with_count += 1
      tmp_var = f"_with_res_{self._temp_with_count}"
      if clause.binding:
        binding = clause.binding
        self._lift_match_expressions(binding.expr)
        self.newline()
        self.emit(f"local {tmp_var} = ")
        self.visit(binding.expr)
        clause_vars.append((tmp_var, binding.is_unwrap, binding, None))
      elif clause.expr:
        self._lift_match_expressions(clause.expr)
        self.newline()
        self.emit(f"local {tmp_var} = ")
        self.visit(clause.expr)
        clause_vars.append((tmp_var, False, None, clause.expr))

    has_unwrap = any(is_unwrap for _, is_unwrap, _, _ in clause_vars)
    unwrap_vars = [tmp_var for tmp_var, is_unwrap, _, _ in clause_vars if is_unwrap]

    def emit_body_statements():
      for tmp_var, _, binding, _ in clause_vars:
        if binding:
          let_names = getattr(binding, "let_names", [binding.let_name])
          if len(let_names) > 1:
            for idx, name in enumerate(let_names):
              self.newline()
              self.emit(f"local {name} = {tmp_var}[{idx + 1}]")
          else:
            self.newline()
            self.emit(f"local {binding.let_name} = {tmp_var}")

      node.body._with_disposables = [tmp_var for tmp_var, _, _, _ in clause_vars]
      self.visit(node.body)

    if has_unwrap:
      cond = " and ".join(f"{v} ~= nil" for v in unwrap_vars)
      self.newline()
      self.emit(f"if {cond} then")
      self.indent()
      emit_body_statements()
      self.dedent()
      self.newline()
      if node.else_body:
        self.emit("else")
        self.indent()
        for tmp_var, _, _, _ in reversed(clause_vars):
          self.newline()
          self.emit(f"_sapphire_dispose({tmp_var})")
        self.visit(node.else_body)
        self.dedent()
        self.newline()
        self.emit("end")
      else:
        self.emit("else")
        self.indent()
        for tmp_var, _, _, _ in reversed(clause_vars):
          self.newline()
          self.emit(f"_sapphire_dispose({tmp_var})")
        self.dedent()
        self.newline()
        self.emit("end")
    else:
      emit_body_statements()

  def visit_StructInitializerNode(self, node: StructInitializerNode) -> None:
    if node.arena_expr:
      self.visit(node.arena_expr)
      self.emit(":register(")
    self.emit(f"{node.struct_name}.init({{")
    for idx, arg in enumerate(node.fields):
      if idx > 0:
        self.emit(", ")
      if arg.name:
        self.emit(f"{arg.name} = ")
      else:
        self.emit(f"[{idx + 1}] = ")
      self.visit(arg.expr)
    self.emit("})")
    if node.arena_expr:
      self.emit(")")
