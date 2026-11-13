-- Standard library OS module for Sapphire (Lua target)

local os_mod = {}
local _os = os
local _arg = arg
local _env_overrides = {}

local _has_ffi, _ffi = pcall(require, "ffi")
if _has_ffi and _ffi then
  pcall(function()
    _ffi.cdef([[
      int setenv(const char *name, const char *value, int overwrite);
    ]])
  end)
end

function os_mod.args()
  local res = {}
  if _arg ~= nil then
    table.insert(res, _arg[0] or "")
    local i = 1
    while _arg[i] ~= nil do
      table.insert(res, _arg[i])
      i = i + 1
    end
  end
  return res
end

function os_mod.get_env(name)
  if _env_overrides[name] ~= nil then
    return _env_overrides[name]
  end
  if _os and _os.getenv then
    local val = _os.getenv(name)
    if val ~= nil then
      return val
    end
  end
  return nil
end

function os_mod.set_env(name, value)
  local str_val = tostring(value)
  _env_overrides[name] = str_val
  if _os and _os.setenv then
    pcall(_os.setenv, name, str_val)
  end
  if _has_ffi and _ffi and _ffi.C and _ffi.C.setenv then
    pcall(_ffi.C.setenv, name, str_val, 1)
  end
end

function os_mod.exit(code)
  if code == nil then
    code = 0
  end
  if _os and _os.exit then
    _os.exit(code)
  end
end

return os_mod
