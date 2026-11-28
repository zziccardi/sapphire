-- Standard library math module for Sapphire (Lua target)

local math_mod = {}
local _math_sqrt = math.sqrt
local _math_floor = math.floor
local _math_ceil = math.ceil
local _math_log = math.log
local _math_type = math.type

function math_mod.abs(x)
  if x < 0 then
    return -x
  end
  return x
end

function math_mod.sqrt(x)
  if x < 0 then
    return nil
  end
  return _math_sqrt(x)
end

function math_mod.min(a, b)
  if a < b then
    return a
  end
  return b
end

function math_mod.max(a, b)
  if a > b then
    return a
  end
  return b
end

function math_mod.safe_div__int(a, b)
  if b == 0 then
    return nil
  end
  local q = a / b
  if q >= 0 then
    return _math_floor(q)
  end
  return _math_ceil(q)
end

function math_mod.safe_div__float(a, b)
  if b == 0 then
    return nil
  end
  return a / b
end

function math_mod.safe_div(a, b)
  if b == 0 then
    return nil
  end
  if _math_type and _math_type(a) == "integer" and _math_type(b) == "integer" then
    return math_mod.safe_div__int(a, b)
  end
  return a / b
end

function math_mod.log(x, base)
  if x <= 0 then
    return nil
  end
  if base ~= nil then
    if base <= 0 or base == 1 then
      return nil
    end
    return _math_log(x) / _math_log(base)
  end
  return _math_log(x)
end

function math_mod.pow(base, exp)
  return base ^ exp
end

math_mod.ceil = _math_ceil
math_mod.floor = _math_floor

-- Generic monomorphization aliases
math_mod.abs__int = math_mod.abs
math_mod.abs__float = math_mod.abs
math_mod.sqrt__int = math_mod.sqrt
math_mod.sqrt__float = math_mod.sqrt
math_mod.min__int = math_mod.min
math_mod.min__float = math_mod.min
math_mod.max__int = math_mod.max
math_mod.max__float = math_mod.max
math_mod.log__int = math_mod.log
math_mod.log__float = math_mod.log
math_mod.pow__int = math_mod.pow
math_mod.pow__float = math_mod.pow
math_mod.ceil__int = math_mod.ceil
math_mod.ceil__float = math_mod.ceil
math_mod.floor__int = math_mod.floor
math_mod.floor__float = math_mod.floor

return math_mod
