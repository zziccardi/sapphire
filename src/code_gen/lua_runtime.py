"""Lua 5.1 runtime preamble for Sapphire.

Provides the embedded runtime header emitted into transpiled Lua modules:
- Relative module loader (`_sp_install_loader`) for nested `.sapphire` imports.
- Coroutine wrapper (`_SapphireCoroutine`), `Arena`, and RAII `_sapphire_del`.
- `SapphireObject` prototype delegation (`__proto__`) using `rawget`/`rawset`
  for per-instance lifecycle flags (`_sapphire_disposed_`) and CoW isolation.
- 1-based array/string/map helpers (`_sapphire_array_*`, `_sapphire_map_*`).
"""

# ==========================================
# Sapphire Lua 5.1 Runtime Preamble
# ==========================================

LUA_RUNTIME_PREAMBLE = """-- Sapphire Lua 5.1 Runtime Header
local _SP_RT = {}
do
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

  local _SP_NONE = {}
  local _SP_UNSET = {}
  _SP_RT._SP_NONE = _SP_NONE
  _SP_RT._SP_UNSET = _SP_UNSET

  local function _wrap_opt(v)
    if v == nil then return _SP_NONE end
    return v
  end
  local function _unwrap_opt(v)
    if v == _SP_NONE then return nil end
    return v
  end
  _SP_RT._wrap_opt = _wrap_opt
  _SP_RT._unwrap_opt = _unwrap_opt

  local function _unwrap_read(obj)
    while type(obj) == "table" do
      local mt = getmetatable(obj)
      if mt and mt.__get_active then
        obj = mt.__get_active()
      elseif mt and mt.__is_ref then
        obj = rawget(obj, "_val")
      elseif mt and mt.__is_shared_ref then
        local cb = rawget(obj, "_cb")
        obj = cb and cb.val or nil
      else
        return obj
      end
    end
    return obj
  end

  local function _unwrap_write(obj)
    while type(obj) == "table" do
      local mt = getmetatable(obj)
      if mt and mt.__ensure_cow then
        obj = mt.__ensure_cow()
      elseif mt and mt.__is_ref then
        obj = rawget(obj, "_val")
      elseif mt and mt.__is_shared_ref then
        local cb = rawget(obj, "_cb")
        obj = cb and cb.val or nil
      else
        return obj
      end
    end
    return obj
  end
  _SP_RT._unwrap_read = _unwrap_read
  _SP_RT._unwrap_write = _unwrap_write

  local _Coroutine = { __is_coroutine = true }
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
  _SP_RT._Coroutine = _Coroutine

  local _sapphire_del
  local _arena_owners = setmetatable({}, { __mode = "k" })
  local Arena = { __is_arena = true }
  Arena.__index = Arena

  function Arena.init()
    local self = setmetatable({}, Arena)
    self.objects = {}
    return self
  end

  function Arena:register(obj)
    if type(obj) == "table" then
      local prev = _arena_owners[obj]
      if prev and prev ~= self then
        for i, o in ipairs(prev.objects) do
          if o == obj then
            table.remove(prev.objects, i)
            break
          end
        end
      end
      if prev ~= self then
        table.insert(self.objects, obj)
        _arena_owners[obj] = self
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
      _arena_owners[obj] = nil
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
  _SP_RT.Arena = Arena

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
          local sv = pa_meta.__shadow[key]
          if sv ~= nil then
            return _unwrap_opt(sv)
          end
        else
          local v = rawget(parent_active, key)
          if v ~= nil then
            return _unwrap_opt(v)
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
        return _unwrap_opt(pm_meta.__shadow[key])
      else
        local curr = rawget(parent_mat, key)
        if curr == nil or curr == target_tbl then
          local cloned = _clone_helper(target_tbl, nil, nil)
          rawset(parent_mat, key, cloned)
          return cloned
        end
        return _unwrap_opt(curr)
      end
    end

    proxy_meta.__get_active = get_active
    proxy_meta.__ensure_cow = ensure_cow
    proxy_meta.__index = function(tbl, sub_key)
      local active = get_active()
      if active ~= nil then
        local val = active[sub_key]
        if val == _SP_NONE then return nil end
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
  _SP_RT._create_cow_proxy = _create_cow_proxy

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
      local sv = shadow[key]
      if sv ~= nil then
        if sv == _SP_NONE then return nil end
        return sv
      end
      if proto ~= nil then
        local val = proto[key]
        if val ~= nil then
          if val == _SP_NONE then return nil end
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
        shadow[key] = (val == nil) and _SP_NONE or val
      else
        rawset(tbl, key, val)
      end
    end
    return setmetatable(obj, meta)
  end
  _SP_RT._create_proto_object = _create_proto_object

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
      if type(v) == "table" and v ~= _SP_NONE then
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
      arena = _arena_owners[obj]
    end
    if arena ~= nil and type(clone_obj) == "table" then
      arena:register(clone_obj)
    end
    if init_fn then
      init_fn(clone_obj)
    end
    return clone_obj
  end
  _SP_RT._clone_helper = _clone_helper

  _SP_RT._sapphire_copy = function(val)
    if type(val) ~= "table" then return val end
    if val == _SP_NONE or val == _SP_UNSET then return val end
    local mt = getmetatable(val)
    if mt and mt.__get_active then
      val = mt.__get_active()
      if type(val) ~= "table" then return val end
      mt = getmetatable(val)
    end
    if mt and (mt.__shadow or mt.__proto ~= nil or mt.__class or mt.__is_arena or mt.__is_ref or mt.__is_shared_ref or mt.__is_weak_ref or mt.__is_coroutine) then
      return val
    end
    if type(val.__del__) == "function" then
      return val
    end
    local copy = {}
    for k, v in pairs(val) do
      copy[k] = v
    end
    if mt then
      setmetatable(copy, mt)
    end
    return copy
  end

  local function _sapphire_eq(a, b)
    if type(a) == "table" then
      local mta = getmetatable(a)
      if mta and mta.__get_active then a = mta.__get_active() end
    end
    if type(b) == "table" then
      local mtb = getmetatable(b)
      if mtb and mtb.__get_active then b = mtb.__get_active() end
    end
    if a == _SP_NONE then a = nil end
    if b == _SP_NONE then b = nil end
    if a == b then return true end
    if type(a) ~= "table" or type(b) ~= "table" then return false end
    if getmetatable(a) ~= nil or getmetatable(b) ~= nil then return false end
    local count_a = 0
    for k, va in pairs(a) do
      count_a = count_a + 1
      local vb = b[k]
      if vb == nil then return false end
      if not _sapphire_eq(va, vb) then return false end
    end
    local count_b = 0
    for _ in pairs(b) do
      count_b = count_b + 1
    end
    return count_a == count_b
  end
  _SP_RT._sapphire_eq = _sapphire_eq

  -- UTF-8 code-point utilities (Lua 5.1/LuaJIT safe)
  local function _utf8_offsets(s)
    local offsets = {}
    local i = 1
    local len = #s
    while i <= len do
      offsets[#offsets + 1] = i
      local b = string.byte(s, i)
      if b < 128 then
        i = i + 1
      elseif b >= 240 then
        i = i + 4
      elseif b >= 224 then
        i = i + 3
      elseif b >= 192 then
        i = i + 2
      else
        i = i + 1
      end
    end
    offsets[#offsets + 1] = len + 1
    return offsets
  end

  _SP_RT._sapphire_string_size = function(s)
    if s == nil then return 0 end
    local _, count = string.gsub(s, "[^\\128-\\191]", "")
    return count
  end

  _SP_RT._sapphire_string_strip = function(s, chars)
    if s == nil then return "" end
    if chars == nil then
      return s:match("^%s*(.-)%s*$") or ""
    end
    if chars == "" then
      return s
    end
    local escaped = chars:gsub("(%W)", "%%%1")
    local pattern = "^[" .. escaped .. "]*(.-)[" .. escaped .. "]*$"
    return s:match(pattern) or ""
  end

  _SP_RT._sapphire_string_slice = function(s, start_idx, end_idx)
    if s == nil then return "" end
    local offsets = _utf8_offsets(s)
    local len = #offsets - 1
    local i = start_idx or 0
    if i < 0 then i = len + i end
    if i < 0 then i = 0 end
    if i > len then return "" end
    local j = end_idx
    if j == nil then
      j = len
    else
      if j < 0 then j = len + j end
      if j < 0 then j = 0 end
      if j > len then j = len end
    end
    if j <= i then return "" end
    return s:sub(offsets[i + 1], offsets[j + 1] - 1)
  end

  _SP_RT._sapphire_string_split = function(s, sep)
    if s == nil then return {} end
    local res = {}
    if sep == "" then
      local offsets = _utf8_offsets(s)
      for i = 1, #offsets - 1 do
        res[i] = s:sub(offsets[i], offsets[i + 1] - 1)
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

  _SP_RT._sapphire_string_find = function(s, sub, start_idx, reverse)
    if s == nil or sub == nil then return nil end
    local offsets = _utf8_offsets(s)
    local cp_len = #offsets - 1
    local start_0 = start_idx or 0
    if start_0 < 0 then start_0 = cp_len + start_0 end
    if start_0 < 0 then start_0 = 0 end
    if sub == "" then
      if start_0 > cp_len then return nil end
      if reverse then return cp_len end
      return start_0
    end
    if start_0 >= cp_len then return nil end
    local start_byte = offsets[start_0 + 1]
    local function byte_to_cp(b_idx)
      local lo, hi = 1, cp_len
      while lo <= hi do
        local mid = math.floor((lo + hi) / 2)
        if offsets[mid] == b_idx then return mid - 1 end
        if offsets[mid] < b_idx then lo = mid + 1 else hi = mid - 1 end
      end
      return lo - 2
    end
    if reverse then
      local last_byte = nil
      local curr = start_byte
      local s_len = #s
      while curr <= s_len do
        local p_start = s:find(sub, curr, true)
        if not p_start then break end
        last_byte = p_start
        curr = p_start + 1
      end
      if last_byte == nil then return nil end
      return byte_to_cp(last_byte)
    else
      local p_start = s:find(sub, start_byte, true)
      if p_start then
        return byte_to_cp(p_start)
      end
      return nil
    end
  end

  _SP_RT._sapphire_string_to_int = function(s, radix)
    if type(s) ~= "string" then return nil end
    local r = radix or 10
    if r < 2 or r > 36 then return nil end
    local clean = s:match("^%s*(.-)%s*$")
    if clean == "" then return nil end
    local sign = 1
    local body = clean
    local first = body:sub(1, 1)
    if first == "-" then
      sign = -1
      body = body:sub(2)
    elseif first == "+" then
      body = body:sub(2)
    end
    if r == 16 and body:match("^0[xX]") then
      body = body:sub(3)
    elseif r == 2 and body:match("^0[bB]") then
      body = body:sub(3)
    elseif r == 8 and body:match("^0[oO]") then
      body = body:sub(3)
    end
    if body == "" or not body:match("^[0-9a-zA-Z]+$") then return nil end
    for i = 1, #body do
      local c = string.byte(body, i)
      local d
      if c >= 48 and c <= 57 then d = c - 48
      elseif c >= 65 and c <= 90 then d = c - 55
      elseif c >= 97 and c <= 122 then d = c - 87
      else return nil end
      if d >= r then return nil end
    end
    local num = tonumber(body, r)
    if num == nil then return nil end
    return sign * num
  end

  _SP_RT._sapphire_string_to_float = function(s)
    if type(s) ~= "string" then return nil end
    local clean = s:match("^%s*(.-)%s*$")
    if clean == "" then return nil end
    if clean:match("^[+-]?0[xX]") then return nil end
    return tonumber(clean)
  end

  _SP_RT._sapphire_string_to_bool = function(s)
    if type(s) ~= "string" then return nil end
    local clean = s:match("^%s*(.-)%s*$"):lower()
    if clean == "true" then return true end
    if clean == "false" then return false end
    return nil
  end

  _SP_RT._sapphire_cast_int = function(v)
    if type(v) == "boolean" then return v and 1 or 0 end
    local n = tonumber(v)
    if not n then return 0 end
    if n >= 0 then return math.floor(n) else return math.ceil(n) end
  end

  _SP_RT._sapphire_cast_float = function(v)
    if type(v) == "boolean" then return v and 1.0 or 0.0 end
    return tonumber(v) or 0.0
  end

  _SP_RT._sapphire_cast_bool = function(v)
    return v ~= false and v ~= nil and v ~= 0
  end

  _SP_RT._sapphire_div = function(a, b)
    if b == 0 then error("division by zero") end
    local q = a / b
    if q >= 0 then return math.floor(q) else return math.ceil(q) end
  end

  _SP_RT._sapphire_enum_from = function(enum_tbl, val)
    if val == nil or enum_tbl == nil then return nil end
    for _, value in pairs(enum_tbl) do
      if value == val then
        return value
      end
    end
    if type(val) == "string" and enum_tbl[val] ~= nil then
      return enum_tbl[val]
    end
    return nil
  end

  _SP_RT._sapphire_array_size = function(arr)
    arr = _unwrap_read(arr)
    if arr == nil then return 0 end
    return #arr
  end

  _SP_RT._sapphire_array_empty = function(arr)
    arr = _unwrap_read(arr)
    if arr == nil then return true end
    return #arr == 0
  end

  _SP_RT._sapphire_array_at = function(arr, index)
    arr = _unwrap_read(arr)
    local len = #arr
    local idx_1 = index < 0 and (len + index + 1) or (index + 1)
    if idx_1 < 1 or idx_1 > len then
      error("Array index out of bounds: " .. tostring(index) .. " (size " .. tostring(len) .. ")")
    end
    return _unwrap_opt(arr[idx_1])
  end

  _SP_RT._sapphire_array_set = function(arr, index, val)
    arr = _unwrap_write(arr)
    local len = #arr
    local idx_1 = index < 0 and (len + index + 1) or (index + 1)
    if idx_1 < 1 or idx_1 > len then
      error("Array index out of bounds: " .. tostring(index) .. " (size " .. tostring(len) .. ")")
    end
    arr[idx_1] = _wrap_opt(val)
    return val
  end

  _SP_RT._sapphire_array_map = function(arr, fn, in_place)
    arr = in_place and _unwrap_write(arr) or _unwrap_read(arr)
    if in_place then
      for i = 1, #arr do
        arr[i] = _wrap_opt(fn(_unwrap_opt(arr[i])))
      end
      return arr
    end
    local res = {}
    for i = 1, #arr do
      res[i] = _wrap_opt(fn(_unwrap_opt(arr[i])))
    end
    return res
  end

  _SP_RT._sapphire_array_filter = function(arr, fn, in_place)
    arr = in_place and _unwrap_write(arr) or _unwrap_read(arr)
    if in_place then
      local res = {}
      for i = 1, #arr do
        if fn(_unwrap_opt(arr[i])) then
          res[#res + 1] = arr[i]
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
      if fn(_unwrap_opt(arr[i])) then
        res[#res + 1] = arr[i]
      end
    end
    return res
  end

  _SP_RT._sapphire_array_reduce = function(arr, initial, fn, reverse)
    arr = _unwrap_read(arr)
    local acc = initial
    local len = #arr
    if reverse then
      for i = len, 1, -1 do
        acc = fn(acc, _unwrap_opt(arr[i]))
      end
    else
      for i = 1, len do
        acc = fn(acc, _unwrap_opt(arr[i]))
      end
    end
    return acc
  end

  _SP_RT._sapphire_array_contains = function(arr, element)
    arr = _unwrap_read(arr)
    for i = 1, #arr do
      if _sapphire_eq(_unwrap_opt(arr[i]), element) then
        return true
      end
    end
    return false
  end

  _SP_RT._sapphire_array_reverse = function(arr, in_place)
    arr = in_place and _unwrap_write(arr) or _unwrap_read(arr)
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

  _SP_RT._sapphire_array_sort = function(arr, by, reverse, in_place)
    arr = in_place and _unwrap_write(arr) or _unwrap_read(arr)
    local target = arr
    if not in_place then
      target = {}
      for i = 1, #arr do
        target[i] = arr[i]
      end
    end
    table.sort(target, function(a, b)
      local ua, ub = _unwrap_opt(a), _unwrap_opt(b)
      if by then
        local cmp = by(ua, ub)
        if reverse then
          return cmp > 0
        else
          return cmp < 0
        end
      else
        if reverse then
          return ua > ub
        else
          return ua < ub
        end
      end
    end)
    return target
  end

  _SP_RT._sapphire_array_join = function(arr, sep)
    arr = _unwrap_read(arr)
    local delimiter = sep
    if delimiter == nil then delimiter = ", " end
    local str_arr = {}
    for i = 1, #arr do
      str_arr[i] = tostring(_unwrap_opt(arr[i]))
    end
    return table.concat(str_arr, delimiter)
  end

  _SP_RT._sapphire_array_push = function(arr, element)
    arr = _unwrap_write(arr)
    arr[#arr + 1] = _wrap_opt(element)
    return element
  end

  _SP_RT._sapphire_array_pop = function(arr)
    arr = _unwrap_write(arr)
    if #arr == 0 then return nil end
    return _unwrap_opt(table.remove(arr))
  end

  _SP_RT._sapphire_array_insert = function(arr, index, element)
    arr = _unwrap_write(arr)
    local len = #arr
    local idx_1 = index < 0 and (len + index + 1) or (index + 1)
    if idx_1 < 1 then idx_1 = 1 end
    if idx_1 > len + 1 then idx_1 = len + 1 end
    table.insert(arr, idx_1, _wrap_opt(element))
    return element
  end

  _SP_RT._sapphire_array_remove = function(arr, index)
    arr = _unwrap_write(arr)
    local len = #arr
    local idx_1 = index < 0 and (len + index + 1) or (index + 1)
    if idx_1 >= 1 and idx_1 <= len then
      return _unwrap_opt(table.remove(arr, idx_1))
    end
    return nil
  end

  _SP_RT._sapphire_array_clear = function(arr)
    arr = _unwrap_write(arr)
    for i = #arr, 1, -1 do
      arr[i] = nil
    end
  end

  _SP_RT._sapphire_array_swap = function(arr, i, j)
    arr = _unwrap_write(arr)
    local len = #arr
    local idx_i = i < 0 and (len + i + 1) or (i + 1)
    local idx_j = j < 0 and (len + j + 1) or (j + 1)
    if idx_i >= 1 and idx_i <= len and idx_j >= 1 and idx_j <= len then
      local tmp = arr[idx_i]
      arr[idx_i] = arr[idx_j]
      arr[idx_j] = tmp
    end
  end

  _SP_RT._sapphire_array_get = function(arr, index)
    arr = _unwrap_read(arr)
    if arr == nil then return nil end
    local len = #arr
    local idx_1 = index < 0 and (len + index + 1) or (index + 1)
    if idx_1 >= 1 and idx_1 <= len then
      return _unwrap_opt(arr[idx_1])
    end
    return nil
  end

  _SP_RT._sapphire_array_idx = function(arr, index)
    arr = _unwrap_read(arr)
    if index < 0 then
      return #arr + index + 1
    end
    return index + 1
  end

  _SP_RT._sapphire_map_size = function(m)
    m = _unwrap_read(m)
    local count = 0
    for _ in pairs(m) do
      count = count + 1
    end
    return count
  end

  _SP_RT._sapphire_map_empty = function(m)
    m = _unwrap_read(m)
    return next(m) == nil
  end

  _SP_RT._sapphire_map_contains = function(m, k)
    m = _unwrap_read(m)
    return m[k] ~= nil
  end

  _SP_RT._sapphire_map_at = function(m, k)
    m = _unwrap_read(m)
    local v = m[k]
    if v == nil then
      error("KeyError: key '" .. tostring(k) .. "' not found in map")
    end
    return _unwrap_opt(v)
  end

  _SP_RT._sapphire_map_set = function(m, k, v)
    m = _unwrap_write(m)
    m[k] = _wrap_opt(v)
    return v
  end

  _SP_RT._sapphire_map_get = function(m, k)
    m = _unwrap_read(m)
    if m == nil then return nil end
    return _unwrap_opt(m[k])
  end

  _SP_RT._sapphire_map_keys = function(m)
    m = _unwrap_read(m)
    local res = {}
    for k in pairs(m) do
      res[#res + 1] = k
    end
    return res
  end

  _SP_RT._sapphire_map_values = function(m)
    m = _unwrap_read(m)
    local res = {}
    for _, v in pairs(m) do
      res[#res + 1] = v
    end
    return res
  end

  _SP_RT._sapphire_map_insert = function(m, k, v)
    m = _unwrap_write(m)
    m[k] = _wrap_opt(v)
    return v
  end

  _SP_RT._sapphire_map_remove = function(m, k)
    m = _unwrap_write(m)
    local val = m[k]
    m[k] = nil
    return _unwrap_opt(val)
  end

  _SP_RT._sapphire_map_clear = function(m)
    m = _unwrap_write(m)
    for k in pairs(m) do
      m[k] = nil
    end
  end

  _SP_RT._sapphire_iter_array = function(arr)
    arr = _unwrap_read(arr)
    if type(arr) ~= "table" then return ipairs({}) end
    local len = #arr
    local i = 0
    return function()
      i = i + 1
      if i <= len then
        return i, _unwrap_opt(arr[i])
      end
      return nil
    end
  end

  _SP_RT._sapphire_iter_map = function(m)
    m = _unwrap_read(m)
    if type(m) ~= "table" then return pairs({}) end
    local k = nil
    return function()
      local v
      k, v = next(m, k)
      if k == nil then return nil end
      return k, _unwrap_opt(v)
    end
  end

  _SP_RT._sapphire_range = function(a, b, c)
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
      local mt = getmetatable(obj)
      if mt == Arena then
        obj:destroy()
      elseif mt and mt.__is_ref then
        if rawget(obj, "_sapphire_disposed_") then return end
        rawset(obj, "_sapphire_disposed_", true)
        local val = rawget(obj, "_val")
        rawset(obj, "_val", nil)
        _sapphire_del(val)
      elseif mt and mt.__is_shared_ref then
        if rawget(obj, "_sapphire_disposed_") then return end
        rawset(obj, "_sapphire_disposed_", true)
        local cb = rawget(obj, "_cb")
        if cb ~= nil then
          cb.strong = cb.strong - 1
          if cb.strong == 0 then
            local val = cb.val
            cb.val = nil
            _sapphire_del(val)
          end
        end
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
  _SP_RT._sapphire_del = _sapphire_del

  local _Ref = {}
  function _Ref.create(val)
    local self = { _val = val }
    local mt = {
      __is_ref = true,
      __index = function(t, k)
        local inner = rawget(self, "_val")
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
        local inner = rawget(self, "_val")
        if type(inner) == "table" then
          inner[k] = v
        end
      end
    }
    return setmetatable(self, mt)
  end
  _SP_RT._Ref = _Ref
  _SP_RT.Ref = _Ref.create

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
    return setmetatable(self, { __is_weak_ref = true })
  end

  function _SharedRef.create(target)
    local cb
    local t_mt = type(target) == "table" and getmetatable(target) or nil
    if t_mt and t_mt.__is_shared_ref then
      cb = rawget(target, "_cb")
    elseif type(target) == "table" and rawget(target, "strong") ~= nil and rawget(target, "weak") ~= nil then
      cb = target
    elseif t_mt and t_mt.__is_ref then
      local val = rawget(target, "_val")
      rawset(target, "_sapphire_disposed_", true)
      rawset(target, "_val", nil)
      cb = { val = val, strong = 1, weak = 0 }
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
      __is_shared_ref = true,
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
  _SP_RT._SharedRef = _SharedRef
  _SP_RT._WeakRef = _WeakRef
  _SP_RT.SharedRef = _SharedRef.create
  _SP_RT.WeakRef = _WeakRef.create
end
local Arena, Ref, SharedRef, WeakRef = _SP_RT.Arena, _SP_RT.Ref, _SP_RT.SharedRef, _SP_RT.WeakRef
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
        local safe_sp_info = sp_info:gsub("%%", "%%%%")
        cur_line = cur_line:gsub("([^:%s]+%.?l?u?a?):" .. line_num .. ":", safe_sp_info)
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

