-- Standard library math module for Sapphire (Lua target)

local math_mod = {}

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
  return math.sqrt(x)
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

function math_mod.safe_div(a, b)
  if b == 0 then
    return nil
  end
  -- TODO: Validate against Lua 5.1 / LuaJIT.
  if math.type and math.type(a) == "integer" and math.type(b) == "integer" then
    return math.floor(a / b)
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
    return math.log(x) / math.log(base)
  end
  return math.log(x)
end

function math_mod.pow(base, exp)
  return base ^ exp
end

function math_mod.ceil(x)
  return math.ceil(x)
end

function math_mod.floor(x)
  return math.floor(x)
end

-- Generic monomorphization aliases
math_mod.abs__int = math_mod.abs
math_mod.abs__float = math_mod.abs
math_mod.sqrt__int = math_mod.sqrt
math_mod.sqrt__float = math_mod.sqrt
math_mod.min__int = math_mod.min
math_mod.min__float = math_mod.min
math_mod.max__int = math_mod.max
math_mod.max__float = math_mod.max
math_mod.safe_div__int = math_mod.safe_div
math_mod.safe_div__float = math_mod.safe_div
math_mod.log__int = math_mod.log
math_mod.log__float = math_mod.log
math_mod.pow__int = math_mod.pow
math_mod.pow__float = math_mod.pow
math_mod.ceil__int = math_mod.ceil
math_mod.ceil__float = math_mod.ceil
math_mod.floor__int = math_mod.floor
math_mod.floor__float = math_mod.floor

return math_mod
