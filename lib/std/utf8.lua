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
    local seq_len = 1
    if b >= 0xF0 and b <= 0xF4 then
      seq_len = 4
    elseif b >= 0xE0 then
      seq_len = 3
    elseif b >= 0xC2 then
      seq_len = 2
    elseif b >= 0x80 then
      return nil, i
    end
    if i + seq_len - 1 > n then
      return nil, i
    end
    for k = 1, seq_len - 1 do
      if not _is_utf8_cont(s:byte(i + k)) then
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

local function _get_utf8()
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

function utf8_mod.size(s)
  local u = _get_utf8()
  if not u then
    return #s
  end
  local len = u.len(s)
  return len
end

function utf8_mod.offset(s, n, i)
  local u = _get_utf8()
  if not u then
    return nil
  end
  if i == nil then
    return u.offset(s, n)
  end
  return u.offset(s, n, i)
end

function utf8_mod.sub(s, start_char, end_char)
  if s == nil or s == "" then
    return ""
  end
  local u = _get_utf8()
  if not u then
    local len = #s
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
    return s:sub(i + 1, j)
  end
  local len = u.len(s)
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
  local byte_start = u.offset(s, i + 1)
  if not byte_start then return "" end
  local byte_end_next = u.offset(s, j + 1)
  local byte_end = byte_end_next and (byte_end_next - 1) or #s
  return s:sub(byte_start, byte_end)
end

return utf8_mod
