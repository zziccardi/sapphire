-- Standard library UTF-8 module for Sapphire (Lua target)

local utf8_mod = {}

local function _get_utf8()
  if _G.utf8 then
    return _G.utf8
  end
  local ok, mod = pcall(require, "utf8")
  if ok then
    return mod
  end
  return nil
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
    return s:sub((start_char or 0) + 1, end_char)
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
