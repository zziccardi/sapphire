"""Lua 5.1 runtime preamble for Sapphire."""

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

