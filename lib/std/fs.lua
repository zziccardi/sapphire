-- Standard library filesystem module for Sapphire (Lua target)

local fs_mod = {}
local _io = io
local _os = os

function fs_mod.read_file(path)
  local f = _io.open(path, "r")
  if not f then
    return nil
  end
  local content = f:read("*a")
  f:close()
  return content
end

function fs_mod.write_file(path, content)
  local f = _io.open(path, "w")
  if not f then
    return false
  end
  local ok = f:write(content)
  f:close()
  return ok ~= nil
end

function fs_mod.remove_file(path)
  if _os and _os.remove then
    local ok = _os.remove(path)
    return ok ~= nil and ok ~= false
  end
  return false
end

function fs_mod.exists(path)
  local f, err, code = _io.open(path, "r")
  if f ~= nil then
    f:close()
    return true
  end
  if err and (string.find(err, "Permission denied") or
              string.find(err, "Is a directory") or
              code == 13 or code == 21) then
    return true
  end
  return false
end

return fs_mod
