-- Standard library UTF-8 module for Sapphire (Lua target)

local utf8_mod = {}

local function _is_utf8_cont(b)
  return b >= 0x80 and b <= 0xBF
end

local _pure_utf8 = {}

function _pure_utf8.len(s)
  if s == nil then
    return nil
  end
  local count = 0
  local i = 1
  local n = #s
  while i <= n do
    local b = s:byte(i)
    local seq_len
    if b <= 0x7F then
      seq_len = 1
    elseif b >= 0xC2 and b <= 0xDF then
      seq_len = 2
    elseif b >= 0xE0 and b <= 0xEF then
      seq_len = 3
    elseif b >= 0xF0 and b <= 0xF4 then
      seq_len = 4
    else
      return nil, i
    end
    if i + seq_len - 1 > n then
      return nil, i
    end
    if seq_len == 2 then
      if not _is_utf8_cont(s:byte(i + 1)) then
        return nil, i
      end
    elseif seq_len == 3 then
      local b2 = s:byte(i + 1)
      local b3 = s:byte(i + 2)
      if not _is_utf8_cont(b2) or not _is_utf8_cont(b3) then
        return nil, i
      end
      if (b == 0xE0 and b2 < 0xA0) or (b == 0xED and b2 > 0x9F) then
        return nil, i
      end
    elseif seq_len == 4 then
      local b2 = s:byte(i + 1)
      local b3 = s:byte(i + 2)
      local b4 = s:byte(i + 3)
      if not _is_utf8_cont(b2) or not _is_utf8_cont(b3) or not _is_utf8_cont(b4) then
        return nil, i
      end
      if (b == 0xF0 and b2 < 0x90) or (b == 0xF4 and b2 > 0x8F) then
        return nil, i
      end
    end
    count = count + 1
    i = i + seq_len
  end
  return count
end

function _pure_utf8.offset(s, n, i)
  local slen = #s
  if i == nil then
    i = (n >= 0) and 1 or (slen + 1)
  elseif i < 0 then
    i = slen + 1 + i
  end
  if i < 1 or i > slen + 1 then
    return nil
  end
  if n == 0 then
    while i > 1 and i <= slen and _is_utf8_cont(s:byte(i)) do
      i = i - 1
    end
    return i
  end
  if i <= slen and _is_utf8_cont(s:byte(i)) then
    return nil
  end
  local pos = i
  if n > 0 then
    local rem = n - 1
    while rem > 0 do
      if pos > slen then
        return nil
      end
      pos = pos + 1
      while pos <= slen and _is_utf8_cont(s:byte(pos)) do
        pos = pos + 1
      end
      rem = rem - 1
    end
    return pos
  else
    local rem = -n
    while rem > 0 do
      if pos <= 1 then
        return nil
      end
      pos = pos - 1
      while pos > 1 and _is_utf8_cont(s:byte(pos)) do
        pos = pos - 1
      end
      rem = rem - 1
    end
    return pos
  end
end

local function _is_valid_utf8_lib(mod)
  return mod ~= nil
    and mod ~= utf8_mod
    and type(mod) == "table"
    and type(mod.len) == "function"
    and type(mod.offset) == "function"
end

local function _resolve_utf8()
  if _is_valid_utf8_lib(_G.utf8) then
    return _G.utf8
  end
  for _, name in ipairs({"utf8", "lua-utf8"}) do
    local ok, mod = pcall(require, name)
    if ok and _is_valid_utf8_lib(mod) then
      return mod
    end
  end
  return _pure_utf8
end

local _utf8_impl = _resolve_utf8()
local _is_pure_utf8 = (_utf8_impl == _pure_utf8)
local _utf8_len = _utf8_impl.len
local _utf8_offset = _utf8_impl.offset
local _str_sub = string.sub

local function _safe_offset(s, n, i)
  if _is_pure_utf8 then
    return _utf8_offset(s, n, i)
  end
  local ok, res
  if i == nil then
    ok, res = pcall(_utf8_offset, s, n)
  else
    ok, res = pcall(_utf8_offset, s, n, i)
  end
  if not ok then
    return nil
  end
  return res
end

function utf8_mod.size(s)
  local len = _utf8_len(s)
  return len
end

function utf8_mod.offset(s, n, i)
  return _safe_offset(s, n, i)
end

function utf8_mod.sub(s, start_char, end_char)
  if s == nil or s == "" then
    return ""
  end
  local len = _utf8_len(s)
  if not len then
    return ""
  end
  local i = start_char or 0
  if i < 0 then i = len + i end
  if i < 0 then i = 0 end
  if i >= len then return "" end
  local j = end_char
  if j == nil then
    j = len
  else
    if j < 0 then j = len + j end
    if j > len then j = len end
  end
  if j <= i then return "" end
  if len == #s then
    return _str_sub(s, i + 1, j)
  end
  local byte_start = _safe_offset(s, i + 1)
  if not byte_start then return "" end
  local byte_end_next = _safe_offset(s, j + 1)
  local byte_end = byte_end_next and (byte_end_next - 1) or #s
  return _str_sub(s, byte_start, byte_end)
end

utf8_mod._pure_utf8 = _pure_utf8

return utf8_mod
