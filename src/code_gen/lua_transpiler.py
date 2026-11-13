"""Code generator to transpile Sapphire AST into executable Lua 5.1 code.

This module implements an AST visitor that formats and outputs Lua 5.1 code
corresponding to the semantic behavior of Sapphire, including a runtime header
for prototypal inheritance delegation and Arena memory management.
"""

from typing import Any, Dict, List, Optional, Set

from src.parser.ast import *
from src.semantics.symbol_table import ArrayType, MapType, RangeType
from src.code_gen.source_map import SourceMapBuilder
from src.code_gen.base_transpiler import BaseTranspiler, extract_type_name, get_default_value_for_type_node, is_coroutine_func
from src.code_gen.transpiler_registry import TranspilerRegistry
from src.code_gen.intrinsics import IntrinsicRegistry


# ==========================================
# Sapphire Lua 5.1 Runtime Preamble
# ==========================================

LUA_RUNTIME_PREAMBLE = """-- Sapphire Lua 5.1 Runtime Header

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

local _sapphire_del
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
  if rawget(self, "_sapphire_disposed_") then
    return
  end
  rawset(self, "_sapphire_disposed_", true)
  for i = #self.objects, 1, -1 do
    local obj = self.objects[i]
    _sapphire_del(obj)
    local meta = getmetatable(obj)
    if meta and meta.__shadow then
      for k in pairs(meta.__shadow) do
        meta.__shadow[k] = nil
      end
    end
  end
  self.objects = {}
end

function Arena:__del__()
  self:destroy()
end

local _clone_helper

local _create_cow_proxy
_create_cow_proxy = function(parent_obj, key, target_tbl)
  if type(target_tbl) == "table" then
    local t_meta = getmetatable(target_tbl)
    if t_meta and t_meta.__get_active then
      target_tbl = t_meta.__get_active()
    end
  end
  local proxy_meta = {}

  local function get_active()
    local p_meta = type(parent_obj) == "table" and getmetatable(parent_obj) or nil
    local parent_active
    if p_meta and p_meta.__get_active then
      parent_active = p_meta.__get_active()
    else
      parent_active = parent_obj
    end
    if type(parent_active) == "table" then
      local pa_meta = getmetatable(parent_active)
      if pa_meta and pa_meta.__shadow then
        if pa_meta.__shadow[key] ~= nil then
          return pa_meta.__shadow[key]
        end
      else
        local v = rawget(parent_active, key)
        if v ~= nil then
          return v
        end
      end
    end
    return target_tbl
  end

  local function ensure_cow()
    local p_meta = type(parent_obj) == "table" and getmetatable(parent_obj) or nil
    local parent_mat
    if p_meta and p_meta.__ensure_cow then
      parent_mat = p_meta.__ensure_cow()
    else
      parent_mat = parent_obj
    end
    local pm_meta = type(parent_mat) == "table" and getmetatable(parent_mat) or nil
    if pm_meta and pm_meta.__shadow then
      if pm_meta.__shadow[key] == nil then
        pm_meta.__shadow[key] = _clone_helper(target_tbl, nil, nil)
      end
      return pm_meta.__shadow[key]
    else
      local curr = rawget(parent_mat, key)
      if curr == nil or curr == target_tbl then
        local cloned = _clone_helper(target_tbl, nil, nil)
        rawset(parent_mat, key, cloned)
        return cloned
      end
      return curr
    end
  end

  proxy_meta.__get_active = get_active
  proxy_meta.__ensure_cow = ensure_cow
  proxy_meta.__index = function(tbl, sub_key)
    local active = get_active()
    if active ~= nil then
      local val = active[sub_key]
      if type(val) == "table" then
        return _create_cow_proxy(tbl, sub_key, val)
      end
      return val
    end
    return nil
  end
  proxy_meta.__newindex = function(tbl, sub_key, value)
    local mat = ensure_cow()
    mat[sub_key] = value
  end
  return setmetatable({}, proxy_meta)
end

local function _create_proto_object(proto, class_tbl)
  local shadow = {}
  local meta = {}
  local obj = {}
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
          return _create_cow_proxy(obj, key, val)
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
  return setmetatable(obj, meta)
end

local function _copy_plain_table(obj, seen)
  if type(obj) ~= "table" then return obj end
  local meta = getmetatable(obj)
  if meta and meta.__get_active then
    obj = meta.__get_active()
    meta = getmetatable(obj)
  end
  if seen and seen[obj] then return seen[obj] end
  if obj.clone and type(obj.clone) == "function" then
    return obj:clone()
  elseif meta and meta.__class then
    return _create_proto_object(obj, meta.__class)
  elseif meta and meta.__proto ~= nil then
    return _create_proto_object(obj, nil)
  end
  seen = seen or {}
  local copy = {}
  seen[obj] = copy
  for k, v in pairs(obj) do
    if type(v) == "table" then
      copy[k] = _copy_plain_table(v, seen)
    else
      copy[k] = v
    end
  end
  if meta then
    setmetatable(copy, meta)
  end
  return copy
end

_clone_helper = function(obj, init_fn, arena)
  if obj == nil then return nil end
  local clone_obj
  if type(obj) == "table" then
    local meta = getmetatable(obj)
    if meta and meta.__get_active then
      obj = meta.__get_active()
      meta = getmetatable(obj)
    end
    if obj.clone and type(obj.clone) == "function" then
      clone_obj = obj:clone()
    elseif meta and meta.__class then
      clone_obj = _create_proto_object(obj, meta.__class)
    elseif meta and meta.__proto ~= nil then
      clone_obj = _create_proto_object(obj, nil)
    else
      clone_obj = _copy_plain_table(obj, nil)
    end
  else
    clone_obj = obj
  end
  if arena == nil and type(obj) == "table" then
    local obj_meta = getmetatable(obj)
    if obj_meta and obj_meta.__arena ~= nil then
      arena = obj_meta.__arena
    end
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

local _sapphire_array_swap = function(arr, i, j)
  local len = #arr
  local idx_i = i < 0 and (len + i + 1) or (i + 1)
  local idx_j = j < 0 and (len + j + 1) or (j + 1)
  if idx_i >= 1 and idx_i <= len and idx_j >= 1 and idx_j <= len then
    local tmp = arr[idx_i]
    arr[idx_i] = arr[idx_j]
    arr[idx_j] = tmp
  end
end

local _sapphire_array_get = function(arr, index)
  if arr == nil then return nil end
  local len = #arr
  local idx_1 = index < 0 and (len + index + 1) or (index + 1)
  if idx_1 >= 1 and idx_1 <= len then
    return arr[idx_1]
  end
  return nil
end

local _sapphire_array_idx = function(arr, index)
  if index < 0 then
    return #arr + index + 1
  end
  return index + 1
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

local _sapphire_map_get = function(m, k)
  if m == nil then return nil end
  return m[k]
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


_sapphire_del = function(obj)
  if obj == nil then return end
  if type(obj) == "table" then
    if getmetatable(obj) == Arena then
      obj:destroy()
    elseif type(obj.__del__) == "function" then
      if rawget(obj, "_sapphire_disposed_") then return end
      rawset(obj, "_sapphire_disposed_", true)
      obj:__del__()
    end
  elseif type(obj) == "userdata" then
    local meta = getmetatable(obj)
    if meta and type(meta.__del__) == "function" then
      obj:__del__()
    end
  end
end

local _Ref = {}
function _Ref.create(val)
  local self = { _val = val }
  local mt = {
    __index = function(t, k)
      if type(val) == "table" then
        local v = val[k]
        if type(v) == "function" then
          return function(recv, ...)
            if recv == self then
              return v(val, ...)
            else
              return v(recv, ...)
            end
          end
        end
        return v
      end
      return nil
    end,
    __newindex = function(t, k, v)
      if type(val) == "table" then
        val[k] = v
      end
    end
  }
  return setmetatable(self, mt)
end
local Ref = _Ref.create

local _SharedRef = {}
local _WeakRef = {}

function _WeakRef.create(cb)
  local self = { _cb = cb }
  function self:upgrade()
    if self._cb and self._cb.strong > 0 then
      self._cb.strong = self._cb.strong + 1
      return _SharedRef.create(self._cb)
    end
    return nil
  end
  return self
end

function _SharedRef.create(target)
  local cb
  if type(target) == "table" and target._cb then
    cb = target._cb
  elseif type(target) == "table" and target.strong ~= nil and target.weak ~= nil then
    cb = target
  elseif type(target) == "table" and target._val then
    cb = { val = target._val, strong = 1, weak = 0 }
  else
    cb = { val = target, strong = 1, weak = 0 }
  end
  local self = { _cb = cb }
  function self:share()
    self._cb.strong = self._cb.strong + 1
    return _SharedRef.create(self._cb)
  end
  function self:downgrade()
    self._cb.weak = self._cb.weak + 1
    return _WeakRef.create(self._cb)
  end
  local mt = {
    __index = function(t, k)
      if k == "share" then return function(recv) return self:share() end end
      if k == "downgrade" then return function(recv) return self:downgrade() end end
      local inner = self._cb.val
      if type(inner) == "table" then
        local v = inner[k]
        if type(v) == "function" then
          return function(recv, ...)
            if recv == self then
              return v(inner, ...)
            else
              return v(recv, ...)
            end
          end
        end
        return v
      end
      return nil
    end,
    __newindex = function(t, k, v)
      if type(self._cb.val) == "table" then
        self._cb.val[k] = v
      end
    end
  }
  return setmetatable(self, mt)
end
local SharedRef = _SharedRef.create
local WeakRef = _WeakRef.create
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


LUA_RUNTIME_MODULE_IMPORT = """-- Sapphire Lua 5.1 Runtime Module Import
local function _sp_load_runtime()
  local ok, rt = pcall(require, "_sapphire_runtime")
  if ok and type(rt) == "table" then return rt end
  local info = debug and debug.getinfo and debug.getinfo(2, "S")
  if info and info.source and info.source:sub(1, 1) == "@" then
    local curr_dir = info.source:sub(2):match("^(.*[/\\\\])") or "./"
    local chunk = loadfile(curr_dir .. "_sapphire_runtime.lua")
    if chunk then return chunk() end
  end
  error("Could not load _sapphire_runtime.lua")
end
local _SP_RT = _sp_load_runtime()
local _Coroutine, Arena, _clone_helper, _create_cow_proxy, _create_proto_object = _SP_RT._Coroutine, _SP_RT.Arena, _SP_RT._clone_helper, _SP_RT._create_cow_proxy, _SP_RT._create_proto_object
local _sapphire_string_strip, _sapphire_string_split, _sapphire_string_find, _sapphire_string_to_int, _sapphire_string_to_float, _sapphire_string_to_bool, _sapphire_cast_int, _sapphire_enum_from = _SP_RT._sapphire_string_strip, _SP_RT._sapphire_string_split, _SP_RT._sapphire_string_find, _SP_RT._sapphire_string_to_int, _SP_RT._sapphire_string_to_float, _SP_RT._sapphire_string_to_bool, _SP_RT._sapphire_cast_int, _SP_RT._sapphire_enum_from
local _sapphire_array_map, _sapphire_array_filter, _sapphire_array_reduce, _sapphire_array_contains, _sapphire_array_reverse, _sapphire_array_sort, _sapphire_array_join, _sapphire_array_push, _sapphire_array_pop, _sapphire_array_insert, _sapphire_array_remove, _sapphire_array_clear, _sapphire_array_swap, _sapphire_array_get, _sapphire_array_idx = _SP_RT._sapphire_array_map, _SP_RT._sapphire_array_filter, _SP_RT._sapphire_array_reduce, _SP_RT._sapphire_array_contains, _SP_RT._sapphire_array_reverse, _SP_RT._sapphire_array_sort, _SP_RT._sapphire_array_join, _SP_RT._sapphire_array_push, _SP_RT._sapphire_array_pop, _SP_RT._sapphire_array_insert, _SP_RT._sapphire_array_remove, _SP_RT._sapphire_array_clear, _SP_RT._sapphire_array_swap, _SP_RT._sapphire_array_get, _SP_RT._sapphire_array_idx
local _sapphire_map_size, _sapphire_map_empty, _sapphire_map_contains, _sapphire_map_get, _sapphire_map_keys, _sapphire_map_values, _sapphire_map_insert, _sapphire_map_remove, _sapphire_map_clear = _SP_RT._sapphire_map_size, _SP_RT._sapphire_map_empty, _SP_RT._sapphire_map_contains, _SP_RT._sapphire_map_get, _SP_RT._sapphire_map_keys, _SP_RT._sapphire_map_values, _SP_RT._sapphire_map_insert, _SP_RT._sapphire_map_remove, _SP_RT._sapphire_map_clear
local _sapphire_iter_array, _sapphire_range, _sapphire_del, _Ref, Ref, _SharedRef, _WeakRef, SharedRef, WeakRef = _SP_RT._sapphire_iter_array, _SP_RT._sapphire_range, _SP_RT._sapphire_del, _SP_RT._Ref, _SP_RT.Ref, _SP_RT._SharedRef, _SP_RT._WeakRef, _SP_RT.SharedRef, _SP_RT.WeakRef
"""

LUA_RUNTIME_MODULE_EXPORTS = """
return {
  _Coroutine = _Coroutine,
  Arena = Arena,
  _clone_helper = _clone_helper,
  _create_cow_proxy = _create_cow_proxy,
  _create_proto_object = _create_proto_object,
  _sapphire_string_strip = _sapphire_string_strip,
  _sapphire_string_split = _sapphire_string_split,
  _sapphire_string_find = _sapphire_string_find,
  _sapphire_string_to_int = _sapphire_string_to_int,
  _sapphire_string_to_float = _sapphire_string_to_float,
  _sapphire_string_to_bool = _sapphire_string_to_bool,
  _sapphire_cast_int = _sapphire_cast_int,
  _sapphire_enum_from = _sapphire_enum_from,
  _sapphire_array_map = _sapphire_array_map,
  _sapphire_array_filter = _sapphire_array_filter,
  _sapphire_array_reduce = _sapphire_array_reduce,
  _sapphire_array_contains = _sapphire_array_contains,
  _sapphire_array_reverse = _sapphire_array_reverse,
  _sapphire_array_sort = _sapphire_array_sort,
  _sapphire_array_join = _sapphire_array_join,
  _sapphire_array_push = _sapphire_array_push,
  _sapphire_array_pop = _sapphire_array_pop,
  _sapphire_array_insert = _sapphire_array_insert,
  _sapphire_array_remove = _sapphire_array_remove,
  _sapphire_array_clear = _sapphire_array_clear,
  _sapphire_array_swap = _sapphire_array_swap,
  _sapphire_array_get = _sapphire_array_get,
  _sapphire_array_idx = _sapphire_array_idx,
  _sapphire_map_size = _sapphire_map_size,
  _sapphire_map_empty = _sapphire_map_empty,
  _sapphire_map_contains = _sapphire_map_contains,
  _sapphire_map_get = _sapphire_map_get,
  _sapphire_map_keys = _sapphire_map_keys,
  _sapphire_map_values = _sapphire_map_values,
  _sapphire_map_insert = _sapphire_map_insert,
  _sapphire_map_remove = _sapphire_map_remove,
  _sapphire_map_clear = _sapphire_map_clear,
  _sapphire_iter_array = _sapphire_iter_array,
  _sapphire_range = _sapphire_range,
  _sapphire_del = _sapphire_del,
  _Ref = _Ref,
  Ref = Ref,
  _SharedRef = _SharedRef,
  _WeakRef = _WeakRef,
  SharedRef = SharedRef,
  WeakRef = WeakRef,
}
"""


LUA_RESERVED_WORDS = {
    "and", "break", "do", "else", "elseif", "end", "false", "for",
    "function", "goto", "if", "in", "local", "nil", "not", "or",
    "repeat", "return", "then", "true", "until", "while",
}


@TranspilerRegistry.register(aliases=["lua", "lua5.1", "love2d", "love"], display_name="Lua 5.1", default_extension=".lua")
class LuaTranspiler(BaseTranspiler):

  """AST visitor to transpile Sapphire code to Lua 5.1."""

  def _mangle_name(self, name: str) -> str:
    """Mangles Sapphire identifiers that collide with Lua reserved keywords."""
    if not name:
      return name
    if name in ("self", "__init__", "__del__", "_init_sapphire"):
      return name
    if name in LUA_RESERVED_WORDS:
      return f"{name}_"
    return name

  def __init__(
      self,
      source_file: Optional[str] = None,
      source_map_builder: Optional[SourceMapBuilder] = None,
      test_mode: bool = False,
      dev_mode: bool = False,
      use_runtime_module: bool = False,
  ):
    self.code: List[str] = []
    self.indent_level = 0
    self.current_line = 1
    self.current_column = 0
    self.source_file = source_file
    self.source_map_builder = source_map_builder
    self.test_mode = test_mode
    self.dev_mode = dev_mode
    self.use_runtime_module = use_runtime_module
    self.on_reload_callbacks: List[str] = []
    self.declared_symbols: List[str] = []
    # Map struct names to their collected method AST nodes from impl blocks
    self.struct_methods: Dict[str, List[Any]] = {}
    self.known_structs: Set[str] = set()
    self.imported_modules: Set[str] = set()
    self.destructor_stack: List[List[str]] = []
    self.loop_destructor_depth: List[int] = []
    self.structs_with_destructor: Set[str] = {"Arena"}
    self.proto_structs: Set[str] = set()
    self.struct_destructible_fields: Dict[str, List[str]] = {}
    self.struct_parent_names: Dict[str, List[str]] = {}
    self.moved_vars: Set[str] = set()
    self._branch_depth: int = 0
    self._var_branch_depth: Dict[str, int] = {}
    self._pending_null_vars: List[str] = []
    self.func_return_types: Dict[str, str] = {}
    self.method_return_types: Dict[str, str] = {}
    self.variable_types: Dict[str, str] = {}
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

    # 1. Output runtime preamble or shared runtime module import
    preamble = LUA_RUNTIME_MODULE_IMPORT if self.use_runtime_module else LUA_RUNTIME_PREAMBLE
    self.emit(preamble)
    self.newline()

    if self.dev_mode:
      self.emit(LUA_DEV_RELOAD_WATCHER)
      self.newline()

    # 1b. Transpile module imports
    for imp in getattr(program, "imports", []):
      self.visit(imp)

    # 2. Collect known struct names and impl block methods
    self._collect_struct_metadata(program, track_known_structs=True)

    struct_decls = []
    func_decls = []
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

    # 4. Transpile main invocation if present
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
    raw_alias = node.alias if node.alias else node.path.split(".")[-1]
    alias_name = self._mangle_name(raw_alias)
    self.imported_modules.add(alias_name)
    self.emit(f"local {alias_name} = require(\"{node.path}\")")
    if self.dev_mode:
      file_path = node.path.replace(".", "/") + ".lua"
      self.newline()
      self.emit(f"if _SP_DEV_WATCHER and _SP_DEV_WATCHER.register_file then _SP_DEV_WATCHER.register_file(\"{file_path}\") end")
    self.newline()

  def visit_ExportStmtNode(self, node: ExportStmtNode) -> None:
    self.newline()
    default_spec = next(
        (
            s
            for s in node.specifiers
            if (s.alias == "default" or s.exported_name == "default")
            and not s.module_prefix
        ),
        None,
    )
    if default_spec is None and len(node.specifiers) == 1 and not node.specifiers[0].module_prefix:
      if node.specifiers[0].symbol in self.known_structs:
        default_spec = node.specifiers[0]

    if default_spec is not None:
      primary_sym = default_spec.symbol
      self.emit(f"{primary_sym}.{primary_sym} = {primary_sym}")
      self.newline()
      self.emit(f"{primary_sym}.default = {primary_sym}")
      self.newline()
      for spec in node.specifiers:
        if spec is default_spec and (spec.alias == "default" or spec.exported_name == "default"):
          continue
        exp_name = spec.exported_name
        sym = self._mangle_name(spec.symbol)
        if exp_name == primary_sym and not spec.module_prefix:
          continue
        prop_access = f'["{exp_name}"]' if exp_name in LUA_RESERVED_WORDS else f".{exp_name}"
        if spec.module_prefix:
          self.emit(f"{primary_sym}{prop_access} = {spec.module_prefix}.{sym}")
        else:
          self.emit(f"{primary_sym}{prop_access} = {sym}")
        self.newline()
      self.emit(f"return {primary_sym}")
      self.newline()
    else:
      self.emit("local _M = {}")
      self.newline()
      for spec in node.specifiers:
        exp_name = spec.exported_name
        sym = self._mangle_name(spec.symbol)
        prop_access = f'["{exp_name}"]' if exp_name in LUA_RESERVED_WORDS else f".{exp_name}"
        if spec.module_prefix:
          self.emit(f"_M{prop_access} = {spec.module_prefix}.{sym}")
        else:
          self.emit(f"_M{prop_access} = {sym}")
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
        self.emit(f"self.{self._mangle_name(f.name)} = {temp.get_output()}")
    self.dedent()
    self.newline()
    self.emit("end")
    self.newline()

    # Define constructor `.init(...)`
    self.emit(f"function {struct_name}.init(...)")
    self.indent()
    self.newline()
    self.emit("local _n_args = select(\"#\", ...)")
    self.newline()
    self.emit("local self")
    self.newline()
    if is_proto:
      self.emit(f"local proto = (_n_args == 2 and type(select(2, ...)) == \"table\") and select(2, ...) or nil")
      self.newline()
      self.emit(f"self = _create_proto_object(proto, {struct_name})")
      self.newline()
      self.emit("if proto == nil then")
      self.indent()
      self.newline()
      self.emit(f"{struct_name}._init_fields(self)")
      self.dedent()
      self.newline()
      self.emit("end")
    else:
      self.emit(f"self = setmetatable({{}}, {struct_name})")
      self.newline()
      self.emit(f"{struct_name}._init_fields(self)")

    init_member = next((m for m in methods if m.func_decl.name == "__init__"), None)
    if init_member:
      self.newline()
      self.emit(f"if {struct_name}._init_sapphire then")
      self.indent()
      self.newline()
      self.emit("if _n_args > 1 then")
      self.indent()
      self.newline()
      self.emit(f"{struct_name}._init_sapphire(self, ...)")
      self.dedent()
      self.newline()
      self.emit("elseif _n_args == 1 then")
      self.indent()
      self.newline()
      self.emit("local _arg1 = ...")
      self.newline()
      init_params = init_member.func_decl.parameters
      if len(init_params) == 0:
        self.emit(f"{struct_name}._init_sapphire(self)")
      else:
        init_args = []
        for idx, p in enumerate(init_params):
          init_args.append(f"(_arg1['{p.name}'] ~= nil and _arg1['{p.name}'] or _arg1[{idx + 1}])")
        call_args = ["self"] + init_args

        param_checks = " or ".join(f"_arg1['{p.name}'] ~= nil" for p in init_params)
        self.emit(f"if type(_arg1) == \"table\" and ({param_checks} or _arg1[1] ~= nil) then")
        self.indent()
        self.newline()
        self.emit(f"{struct_name}._init_sapphire({', '.join(call_args)})")
        self.dedent()
        self.newline()
        self.emit("else")
        self.indent()
        self.newline()
        self.emit(f"{struct_name}._init_sapphire(self, _arg1)")
        self.dedent()
        self.newline()
        self.emit("end")
      self.dedent()
      self.newline()
      self.emit("else")
      self.indent()
      self.newline()
      self.emit(f"{struct_name}._init_sapphire(self)")
      self.dedent()
      self.newline()
      self.emit("end")
      self.dedent()
      self.newline()
      self.emit("end")
    else:
      self.newline()
      self.emit("if _n_args > 1 then")
      self.indent()
      self.newline()
      self.emit("local _args = { ... }")
      for idx, f in enumerate(node.fields):
        self.newline()
        self.emit(f"if _args[{idx + 1}] ~= nil then self.{self._mangle_name(f.name)} = _args[{idx + 1}] end")
      self.dedent()
      self.newline()
      self.emit("elseif _n_args == 1 then")
      self.indent()
      self.newline()
      self.emit("local _arg1 = ...")
      self.newline()
      self.emit("if type(_arg1) == \"table\" then")
      self.indent()
      self.newline()
      self.emit("for k, v in pairs(_arg1) do")
      self.indent()
      self.newline()
      self.emit("if type(k) == \"string\" then self[k] = v end")
      self.dedent()
      self.newline()
      self.emit("end")
      for idx, f in enumerate(node.fields):
        self.newline()
        self.emit(f"if _arg1[{idx + 1}] ~= nil and self.{self._mangle_name(f.name)} == nil then self.{self._mangle_name(f.name)} = _arg1[{idx + 1}] end")
      self.dedent()
      self.newline()
      self.emit("else")
      self.indent()
      if node.fields:
        self.newline()
        self.emit(f"self.{self._mangle_name(node.fields[0].name)} = _arg1")
      self.dedent()
      self.newline()
      self.emit("end")
      self.dedent()
      self.newline()
      self.emit("end")

    self.newline()
    self.emit("return self")
    self.dedent()
    self.newline()
    self.emit("end")
    self.newline()

    has_explicit_del = any(
        getattr(m, "func_decl", None) and m.func_decl.name == "__del__"
        for m in methods
    )
    destructible_parents = [
        p for p in (node.parent_names or []) if p in self.structs_with_destructor
    ]
    needs_synth_del = (
        not is_proto
        and not has_explicit_del
        and struct_name in self.structs_with_destructor
        and bool(
            self.struct_destructible_fields.get(struct_name)
            or len(destructible_parents) > 1
        )
    )

    # Emit methods from impl block
    for m in methods:
      self._visit_ImplMemberNode_for_struct(m, struct_name)

    if needs_synth_del:
      self.newline()
      self.emit(f"function {struct_name}:__del__()")
      self.indent()
      self._emit_struct_auto_teardown(struct_name, call_parents=True)
      self.dedent()
      self.newline()
      self.emit("end")
      self.newline()

  def _emit_destructor_call(self, var_name: str) -> None:
    """Emits Lua destructor teardown (`destroy()` for Arena, `_sapphire_del` otherwise)."""
    if self.variable_types.get(var_name) == "Arena":
      self.emit(f"if {var_name} ~= nil then {var_name}:destroy() end")
    else:
      self.emit(f"_sapphire_del({var_name})")

  def _emit_struct_auto_teardown(
      self, struct_name: str, call_parents: bool = True
  ) -> None:
    """Emits LIFO `_sapphire_del` calls for destructible fields and parents in Lua."""
    for f_name in reversed(self.struct_destructible_fields.get(struct_name, [])):
      self.newline()
      self.emit(f"_sapphire_del(self.{self._mangle_name(f_name)})")
    if call_parents:
      for p_name in reversed(self.struct_parent_names.get(struct_name, [])):
        if p_name in self.structs_with_destructor:
          self.newline()
          self.emit(f"if {p_name}.__del__ then {p_name}.__del__(self) end")

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
    is_test_func = any(
        getattr(a, "name", "") == "test"
        for a in getattr(func, "annotations", [])
    )
    if is_test_func and not self.test_mode:
      return

    func_name = "_init_sapphire" if func.name == "__init__" else self._mangle_name(func.name)
    self.newline()

    if node.modifier == "static":
      params = [self._mangle_name(p.name) for p in func.parameters if p.name != "self"]
      self.emit(f"function {struct_name}.{func_name}({', '.join(params)})")
    else:
      other_params = [self._mangle_name(p.name) for p in func.parameters if p.name != "self"]
      self.emit(f"function {struct_name}:{func_name}({', '.join(other_params)})")

    self.indent()
    for p in func.parameters:
      if p.default_expr:
        self.newline()
        temp = LuaTranspiler()
        temp.known_structs = self.known_structs
        temp.visit(p.default_expr)
        pname = self._mangle_name(p.name)
        self.emit(f"if {pname} == nil then {pname} = {temp.get_output()} end")
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
      if func.name == "__init__" and getattr(func, "base_initializers", None):
        for base_init in func.base_initializers:
          parent_name = base_init.callee.name
          p_members = self.struct_methods.get(parent_name, [])
          p_init = next((m for m in p_members if getattr(m, "func_decl", None) and m.func_decl.name == "__init__"), None)
          param_names = [p.name for p in p_init.func_decl.parameters if p.name != "self"] if p_init else []

          args_strs = ["self"]
          if param_names:
            args_by_name = {}
            for idx, arg in enumerate(base_init.arguments):
              temp = LuaTranspiler()
              temp.known_structs = self.known_structs
              temp.visit(arg.expr)
              val = temp.get_output()
              if arg.name:
                args_by_name[arg.name] = val
              elif idx < len(param_names):
                args_by_name[param_names[idx]] = val
            args_strs.extend(args_by_name.get(p_name, "nil") for p_name in param_names)
          else:
            for arg in base_init.arguments:
              temp = LuaTranspiler()
              temp.known_structs = self.known_structs
              temp.visit(arg.expr)
              args_strs.append(temp.get_output())

          self.newline()
          self.emit(f"{parent_name}._init_sapphire({', '.join(args_strs)})")
      has_auto_teardown = (
          func.name == "__del__"
          and struct_name not in self.proto_structs
          and bool(
              self.struct_destructible_fields.get(struct_name)
              or any(
                  p in self.structs_with_destructor
                  for p in self.struct_parent_names.get(struct_name, [])
              )
          )
      )
      if has_auto_teardown:
        self.newline()
        self.emit("(function()")
        self.indent()
        self.visit(func.body)
        self.dedent()
        self.newline()
        self.emit("end)()")
        self._emit_struct_auto_teardown(struct_name, call_parents=True)
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
    fn_name = self._mangle_name(node.name)
    params = [self._mangle_name(p.name) for p in node.parameters]

    self.newline()
    if export_ann:
      target_path = export_ann.arg if export_ann.arg else fn_name
      self.emit(f"function {target_path}({', '.join(params)})")
    else:
      self.emit(f"function {fn_name}({', '.join(params)})")

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
        pname = self._mangle_name(p.name)
        self.emit(f"if {pname} == nil then {pname} = {temp.get_output()} end")
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
    self.destructor_stack.append([])
    if getattr(node, "_block_destructibles", None):
      for d_var in node._block_destructibles:
        self.destructor_stack[-1].append(d_var)
        self._var_branch_depth[d_var] = self._branch_depth
    if not node.statements:
      self.newline()
      self.emit("-- pass")
    else:
      for stmt in node.statements:
        self.visit(stmt)
        if not isinstance(stmt, ReturnNode):
          self._drain_pending_null_vars("nil")

    current_destructors = self.destructor_stack.pop()
    has_returned = bool(node.statements and isinstance(node.statements[-1], ReturnNode))
    if not has_returned:
      for var_name in reversed(current_destructors):
        if var_name not in self.moved_vars:
          self.newline()
          self._emit_destructor_call(var_name)
    for var_name in current_destructors:
      self.moved_vars.discard(var_name)
      self._var_branch_depth.pop(var_name, None)

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

    for idx, name in enumerate(node.names):
      val_type = node.val_types[idx] if idx < len(node.val_types) else None
      type_name = extract_type_name(val_type) if val_type else None
      st_name = None
      if type_name and type_name in self.structs_with_destructor:
        st_name = type_name
      elif node.exprs and idx < len(node.exprs):
        st_name = self._expr_destructible_struct(node.exprs[idx])
      elif node.exprs and len(node.exprs) == 1:
        st_name = self._expr_destructible_struct(node.exprs[0], return_index=idx)
      elif node.expr:
        st_name = self._expr_destructible_struct(node.expr, return_index=idx)

      if st_name:
        m_name = self._mangle_name(name)
        self.variable_types[m_name] = st_name
        if self.destructor_stack:
          self.destructor_stack[-1].append(m_name)
          self._var_branch_depth[m_name] = self._branch_depth

    self._lift_match_expressions(node.exprs)

    self.newline()
    names_str = ", ".join([self._mangle_name(n) for n in node.names])
    if self.dev_mode and self.indent_level == 0 and len(node.names) == 1 and node.exprs:
      name = self._mangle_name(node.names[0])
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

    if node.op == "=":
      live_destructible_targets = [
          self._mangle_name(t.name)
          for t in node.targets
          if isinstance(t, IdentifierNode)
          and self._is_active_destructible_var(self._mangle_name(t.name))
          and self._mangle_name(t.name) not in self.moved_vars
      ]
      if live_destructible_targets:
        self._temp_reassign_count = getattr(self, "_temp_reassign_count", 0) + 1
        tmp_names = [
            f"_reassign_{self._temp_reassign_count}_{i + 1}"
            for i in range(len(node.targets))
        ]
        self.newline()
        self.emit("local " + ", ".join(tmp_names) + " = ")
        for idx, expr in enumerate(node.exprs):
          if idx > 0:
            self.emit(", ")
          self.visit(expr)
        for m_t in live_destructible_targets:
          if m_t not in self.moved_vars and m_t not in self._pending_null_vars:
            self.newline()
            self._emit_destructor_call(m_t)
        assigned_id_names = {
            self._mangle_name(t.name)
            for t in node.targets
            if isinstance(t, IdentifierNode)
        }
        self._drain_pending_null_vars("nil", exclude=assigned_id_names)
        self.newline()
        for idx, target in enumerate(node.targets):
          if isinstance(target, IdentifierNode):
            self.moved_vars.discard(self._mangle_name(target.name))
          if idx > 0:
            self.emit(", ")
          self.visit(target)
        self.emit(" = " + ", ".join(tmp_names))
        return

    self.newline()
    if node.op == "=":
      for idx, target in enumerate(node.targets):
        if isinstance(target, IdentifierNode):
          self.moved_vars.discard(self._mangle_name(target.name))
        if idx > 0:
          self.emit(", ")
        self.visit(target)
      self.emit(" = ")
      for idx, expr in enumerate(node.exprs):
        if idx > 0:
          self.emit(", ")
        self.visit(expr)
    else:
      if isinstance(node.target, IdentifierNode):
        self.moved_vars.discard(self._mangle_name(node.target.name))
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
    all_active_destructors = [
        d for frame in reversed(self.destructor_stack) for d in reversed(frame)
    ]
    self._lift_match_expressions(node.expressions)

    # RVO: Identifiers returned directly are transferred to caller, so elide local destructor
    returned_ids = {
        self._mangle_name(expr.name)
        for expr in node.expressions
        if isinstance(expr, (IdentifierNode, MoveNode))
    }
    destructors_to_run = [
        d for d in all_active_destructors
        if d not in returned_ids and d not in self.moved_vars
    ]

    # If return expressions exist alongside destructors, evaluate expressions first
    should_evaluate_first = bool(
        node.expressions
        and destructors_to_run
        and not all(isinstance(e, (LiteralNode, IdentifierNode)) for e in node.expressions)
    )

    if should_evaluate_first:
      ret_tmps = []
      for idx, expr in enumerate(node.expressions):
        tmp_name = f"_ret_val_{idx + 1}"
        ret_tmps.append(tmp_name)
        self.newline()
        self.emit(f"local {tmp_name} = ")
        self.visit(expr)

      for var_name in destructors_to_run:
        if var_name not in self.moved_vars:
          self.newline()
          self._emit_destructor_call(var_name)

      self.newline()
      self.emit("return " + ", ".join(ret_tmps))
      self._pending_null_vars.clear()
      return

    for var_name in destructors_to_run:
      if var_name not in self.moved_vars:
        self.newline()
        self._emit_destructor_call(var_name)

    self.newline()
    if node.expressions:
      self.emit("return ")
      for idx, expr in enumerate(node.expressions):
        if idx > 0:
          self.emit(", ")
        self.visit(expr)
    else:
      self.emit("return")
    self._pending_null_vars.clear()

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
      self._branch_depth += 1
      try:
        if isinstance(case.body, BlockNode):
          self.visit(case.body)
        else:
          self.newline()
          if target_var:
            self.emit(f"{target_var} = ")
            self.visit(case.body)
          else:
            self.visit(case.body)  # pragma: no cover
        self._drain_pending_null_vars("nil")
      finally:
        self._branch_depth -= 1
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
    bindings = getattr(node, "bindings", [node.init_binding] if getattr(node, "init_binding", None) else [])

    if not bindings:
      if node.condition:
        self._lift_match_expressions(node.condition)
      self.newline()
      self.emit("if ")
      self.visit(node.condition)
      self.emit(" then")
      self.indent()
      self._visit_in_branch(node.then_block)
      self.dedent()
      if node.else_block:
        self.newline()
        self.emit("else")
        self.indent()
        self._visit_in_branch(node.else_block)
        self.dedent()
      self.newline()
      self.emit("end")
      return

    if len(bindings) == 1:
      binding = bindings[0]
      self._lift_match_expressions(binding.expr)
      if node.condition:
        self._lift_match_expressions(node.condition)
      let_names = getattr(binding, "let_names", [binding.let_name])
      let_name = binding.let_name

      self.newline()
      if binding.is_unwrap:
        val_var = f"_val_{let_name}"
        self.emit(f"local {val_var} = ")
        self.visit(binding.expr)
        self.newline()

        old_map = self._identifier_map.copy()
        if len(let_names) == 1:
          self._identifier_map[let_name] = val_var
        else:
          for idx, name in enumerate(let_names):
            self._identifier_map[name] = f"{val_var}[{idx + 1}]"

        self.emit(f"if {val_var} ~= nil")
        if node.condition:
          self.emit(" and ")
          self.visit(node.condition)
        self.emit(" then")

        self._identifier_map = old_map

        self.indent()
        self.newline()
        if len(let_names) > 1:
          for idx, name in enumerate(let_names):
            self.emit(f"local {self._mangle_name(name)} = {val_var}[{idx + 1}]")
            if idx < len(let_names) - 1:
              self.newline()
        else:
          self.emit(f"local {self._mangle_name(let_name)} = {val_var}")

        st_name = self._expr_destructible_struct(binding.expr)
        if st_name and self._is_owned_unwrap_expr(binding.expr):
          for name in let_names:
            self.variable_types[name] = st_name
            if not hasattr(node.then_block, "_block_destructibles"):
              node.then_block._block_destructibles = []
            node.then_block._block_destructibles.append(name)
        self._visit_in_branch(node.then_block)
        self.dedent()
      else:
        # Standard bind + condition
        self.emit(f"local {let_name} = ")
        self.visit(binding.expr)
        self.newline()
        st_name = self._expr_destructible_struct(binding.expr)
        if st_name:
          for name in let_names:
            self.variable_types[name] = st_name
            if not hasattr(node.then_block, "_block_destructibles"):
              node.then_block._block_destructibles = []
            node.then_block._block_destructibles.append(name)
        self.emit("if ")
        self.visit(node.condition)
        self.emit(" then")
        self.indent()
        self._visit_in_branch(node.then_block)
        self.dedent()

      if node.else_block:
        self.newline()
        self.emit("else")
        self.indent()
        self._visit_in_branch(node.else_block)
        self.dedent()

      self.newline()
      self.emit("end")
      return

    # Multi-binding (len(bindings) > 1) with sequential short-circuiting and LIFO destructors
    self._temp_if_count = getattr(self, "_temp_if_count", 0) + 1
    cond_flag = f"_if_ok_{self._temp_if_count}"

    for b in bindings:
      self._lift_match_expressions(b.expr)
    if node.condition:
      self._lift_match_expressions(node.condition)

    self.newline()
    self.emit(f"local {cond_flag} = false")

    def emit_binding_level(idx: int, prior_destructibles: List[str]):
      if idx < len(bindings):
        b = bindings[idx]
        let_names = getattr(b, "let_names", [b.let_name])
        let_name = b.let_name
        st_name = self._expr_destructible_struct(b.expr)
        current_destructibles = list(prior_destructibles)
        if st_name and (not b.is_unwrap or self._is_owned_unwrap_expr(b.expr)):
          for name in let_names:
            self.variable_types[name] = st_name
            if not hasattr(node.then_block, "_block_destructibles"):
              node.then_block._block_destructibles = []
            node.then_block._block_destructibles.append(name)
          current_destructibles.extend(let_names)

        if b.is_unwrap:
          val_var = f"_val_{let_name}_{idx + 1}"
          self.newline()
          self.emit(f"local {val_var} = ")
          self.visit(b.expr)
          self.newline()
          self.emit(f"if {val_var} ~= nil then")
          self.indent()
          self.newline()
          if len(let_names) > 1:
            for n_idx, name in enumerate(let_names):
              self.emit(f"local {name} = {val_var}[{n_idx + 1}]")
              if n_idx < len(let_names) - 1:
                self.newline()
          else:
            self.emit(f"local {let_name} = {val_var}")

          emit_binding_level(idx + 1, current_destructibles)
          self.dedent()
          if prior_destructibles:
            self.newline()
            self.emit("else")
            self.indent()
            for d_var in reversed(prior_destructibles):
              self.newline()
              self.emit(f"_sapphire_del({d_var})")
            self.dedent()
          self.newline()
          self.emit("end")
        else:
          self.newline()
          self.emit(f"local {let_name} = ")
          self.visit(b.expr)
          emit_binding_level(idx + 1, current_destructibles)
      else:
        # All bindings acquired; check condition if present
        if node.condition:
          self.newline()
          self.emit("if ")
          self.visit(node.condition)
          self.emit(" then")
          self.indent()
          self.newline()
          self.emit(f"{cond_flag} = true")
          self._visit_in_branch(node.then_block)
          self.dedent()
          if prior_destructibles:
            self.newline()
            self.emit("else")
            self.indent()
            for d_var in reversed(prior_destructibles):
              self.newline()
              self.emit(f"_sapphire_del({d_var})")
            self.dedent()
          self.newline()
          self.emit("end")
        else:
          self.newline()
          self.emit(f"{cond_flag} = true")
          self._visit_in_branch(node.then_block)

    emit_binding_level(0, [])

    if node.else_block:
      self.newline()
      self.emit(f"if not {cond_flag} then")
      self.indent()
      self._visit_in_branch(node.else_block)
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
    self.loop_destructor_depth.append(len(self.destructor_stack))
    try:
      if node.condition:
        self._lift_match_expressions(node.condition)

      self.newline()
      self.emit("while ")
      self.visit(node.condition)
      self.emit(" do")
      self.indent()
      self._visit_loop_body(node.block, has_continue)
      self.dedent()
      self.newline()
      self.emit("end")
    finally:
      self.loop_destructor_depth.pop()
      self._loop_stack.pop()

  def visit_ForNode(self, node: ForNode) -> None:
    has_continue = _has_continue_node(node.block)
    self._loop_stack.append(has_continue)
    self.loop_destructor_depth.append(len(self.destructor_stack))
    try:
      self._lift_match_expressions(node.iterable)
      self.newline()
      val_var = self._mangle_name(node.val_var)
      key_var = self._mangle_name(node.key_var) if node.key_var is not None else None
      if node.key_var is not None:
        self.emit(f"for {key_var}, {val_var} in pairs(")
        self.visit(node.iterable)
        self.emit(") do")
      elif (
          isinstance(getattr(node.iterable, "inferred_type", None), RangeType)
          or (isinstance(node.iterable, CallNode) and isinstance(node.iterable.callee, IdentifierNode) and node.iterable.callee.name == "range")
      ):
        self.emit(f"for {val_var} in ")
        self.visit(node.iterable)
        self.emit(" do")
      else:
        self.emit(f"for _, {val_var} in _sapphire_iter_array(")
        self.visit(node.iterable)
        self.emit(") do")
      self.indent()
      self._visit_loop_body(node.block, has_continue)
      self.dedent()
      self.newline()
      self.emit("end")
    finally:
      self.loop_destructor_depth.pop()
      self._loop_stack.pop()

  def visit_BreakNode(self, node: BreakNode) -> None:
    self._emit_loop_destructors()
    self.newline()
    if self._loop_stack and self._loop_stack[-1]:
      self.emit("_break_outer = true")
      self.newline()
    self.emit("break")

  def visit_ContinueNode(self, node: ContinueNode) -> None:
    self._emit_loop_destructors()
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
      val = str(node.value).replace("\r", "\\r").replace("\n", "\\n")
      self.emit(f'"{val}"')
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
      name = self._identifier_map.get(node.name, self._mangle_name(node.name))
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
    if IntrinsicRegistry.try_emit("lua", self, node):
      return

    # Check if this call is calling a struct constructor, e.g. Weapon(...)
    if (isinstance(node.callee, IdentifierNode) and
        node.callee.name in self.known_structs):
      struct_name = node.callee.name
      if node.arena_expr:
        self.visit(node.arena_expr)
        self.emit(":register(")
      self.emit(f"{struct_name}.init({{")
      for idx, arg in enumerate(node.arguments):
        if idx > 0:
          self.emit(", ")
        if arg.name:
          self.emit(f"{self._mangle_name(arg.name)} = ")
        else:
          self.emit(f"[{idx + 1}] = ")
        self.visit(arg.expr)
      self.emit("})")
      if node.arena_expr:
        self.emit(")")
      return

    if node.arena_expr:
      self.visit(node.arena_expr)
      self.emit(":register(")

    if isinstance(node.callee, MemberAccessNode):
      member_name = getattr(node.callee, "target_name", None) or self._mangle_name(node.callee.member)
      receiver_name = getattr(node.callee.receiver, "name", None)
      if node.callee.is_optional:
        sep = ":" if getattr(node.callee, "is_instance_method", False) else "."
        self.emit("((function(_r) if _r ~= nil then return _r")
        self.emit(f"{sep}{member_name}(")
        for idx, arg in enumerate(node.arguments):
          if idx > 0:
            self.emit(", ")
          self.visit(arg.expr)
        self.emit(") else return nil end end)(")
        self.visit(node.callee.receiver)
        self.emit("))")
        return
      if getattr(node.callee, "is_instance_method", False):
        self.visit(node.callee.receiver)
        self.emit(f":{member_name}(")
      elif getattr(node.callee, "is_static_method", False) or (receiver_name and (receiver_name in self.known_structs or receiver_name in self.imported_modules)):
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
    if node.arena_expr:
      self.emit(")")

  def visit_MemberAccessNode(self, node: MemberAccessNode) -> None:
    member_name = getattr(node, "target_name", None) or self._mangle_name(node.member)
    if node.is_optional:
      self.emit("((function(_r) if _r ~= nil then return _r.")
      self.emit(member_name)
      self.emit(" else return nil end end)(")
      self.visit(node.receiver)
      self.emit("))")
    else:
      self.visit(node.receiver)
      self.emit(f".{member_name}")

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

  def visit_MoveNode(self, node: MoveNode) -> None:
    m_name = self._mangle_name(node.name)
    name = self._identifier_map.get(m_name, m_name)
    self._record_move(m_name)
    self.emit(name)

  def visit_LambdaNode(self, node: LambdaNode) -> None:
    params = [self._mangle_name(p.name) for p in node.parameters]
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
    is_map = isinstance(getattr(node.array, 'inferred_type', None), MapType)
    if is_map:
      self.visit(node.array)
      self.emit("[")
      self.visit(node.index)
      self.emit("]")
      return

    if isinstance(node.index, LiteralNode) and node.index.lit_type == "int" and int(node.index.value) >= 0:
      self.visit(node.array)
      self.emit("[")
      self.emit(str(int(node.index.value) + 1))
      self.emit("]")
      return

    const_val = None
    if isinstance(node.index, LiteralNode) and node.index.lit_type == "int":
      const_val = int(node.index.value)
    elif (
        isinstance(node.index, UnaryOpNode)
        and node.index.op == "-"
        and isinstance(node.index.expr, LiteralNode)
        and node.index.expr.lit_type == "int"
    ):
      const_val = -int(node.index.expr.value)

    arr_type = getattr(node.array, 'inferred_type', None)
    if const_val is not None and const_val < 0 and isinstance(arr_type, ArrayType) and arr_type.size is not None:
      self.visit(node.array)
      self.emit("[")
      self.emit(str(arr_type.size + const_val + 1))
      self.emit("]")
      return

    self.visit(node.array)
    self.emit("[_sapphire_array_idx(")
    self.visit(node.array)
    self.emit(", ")
    self.visit(node.index)
    self.emit(")]")

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
            self.emit(f"local {self._mangle_name(name)} = {tmp_var}[{idx + 1}]")
            if idx < len(let_names) - 1:
              self.newline()
        else:
          self.emit(f"local {self._mangle_name(binding.let_name)} = {tmp_var}")
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

  def visit_StructInitializerNode(self, node: StructInitializerNode) -> None:
    if node.arena_expr:
      self.visit(node.arena_expr)
      self.emit(":register(")
    self.emit(f"{node.struct_name}.init({{")
    for idx, arg in enumerate(node.fields):
      if idx > 0:
        self.emit(", ")
      if arg.name:
        self.emit(f"{self._mangle_name(arg.name)} = ")
      else:
        self.emit(f"[{idx + 1}] = ")
      self.visit(arg.expr)
    self.emit("})")
    if node.arena_expr:
      self.emit(")")
