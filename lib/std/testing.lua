-- Standard library testing module for Sapphire (Lua target)

local testing = {}

local active_context = nil

testing.TestContext = {}
testing.TestContext.__index = testing.TestContext

function testing.TestContext.new(name)
  local self = setmetatable({}, testing.TestContext)
  self.name = name or ""
  self.passed_assertions = 0
  self.failures = {}
  return self
end

function testing.TestContext:record_failure(message, fatal)
  local info = debug.getinfo(3, "Sl")
  local filename = info and info.short_src or "unknown"
  local lineno = info and info.currentline or 0
  table.insert(self.failures, {
    message = message,
    filename = filename,
    lineno = lineno,
    fatal = fatal
  })
  if fatal then
    error(message, 0)
  end
end

function testing.set_active_context(ctx)
  active_context = ctx
end

function testing.get_active_context()
  if not active_context then
    active_context = TestContext.new("standalone")
  end
  return active_context
end

local function format_msg(default_msg, user_msg)
  if user_msg and user_msg ~= "" then
    return default_msg .. " (" .. tostring(user_msg) .. ")"
  end
  return default_msg
end

-- TestCase table
testing.TestCase = {}
testing.TestCase.__index = testing.TestCase

function testing.TestCase.new()
  return setmetatable({}, testing.TestCase)
end

function testing.TestCase:set_up() end
function testing.TestCase:tear_down() end

function testing.TestCase:assert_true(cond, msg) testing.assert_true(cond, msg) end
function testing.TestCase:assert_false(cond, msg) testing.assert_false(cond, msg) end
function testing.TestCase:assert_eq(actual, expected, msg) testing.assert_eq(actual, expected, msg) end
function testing.TestCase:assert_ne(actual, expected, msg) testing.assert_ne(actual, expected, msg) end
function testing.TestCase:assert_almost_eq(a, b, eps, msg) testing.assert_almost_eq(a, b, eps, msg) end
function testing.TestCase:assert_none(opt, msg) testing.assert_none(opt, msg) end
function testing.TestCase:assert_not_none(opt, msg) testing.assert_not_none(opt, msg) end

function testing.TestCase:expect_true(cond, msg) testing.expect_true(cond, msg) end
function testing.TestCase:expect_false(cond, msg) testing.expect_false(cond, msg) end
function testing.TestCase:expect_eq(actual, expected, msg) testing.expect_eq(actual, expected, msg) end
function testing.TestCase:expect_ne(actual, expected, msg) testing.expect_ne(actual, expected, msg) end
function testing.TestCase:expect_almost_eq(a, b, eps, msg) testing.expect_almost_eq(a, b, eps, msg) end
function testing.TestCase:expect_none(opt, msg) testing.expect_none(opt, msg) end
function testing.TestCase:expect_not_none(opt, msg) testing.expect_not_none(opt, msg) end

-- Free-function assertions
local function unwrap(val)
  if type(val) == "table" and val.__opt_val ~= nil then
    return val.__opt_val
  end
  return val
end

local function is_none(val)
  return val == nil or (type(val) == "table" and val.__opt_val == nil)
end

local function normalize_args(a, b, c)
  if a == testing then
    return b, c
  end
  return a, b
end

function testing.assert_true(cond, msg)
  cond, msg = normalize_args(cond, msg)
  local ctx = testing.get_active_context()
  cond = unwrap(cond)
  if not cond then
    ctx:record_failure(format_msg("Expected condition to be true", msg), true)
  else
    ctx.passed_assertions = ctx.passed_assertions + 1
  end
end

function testing.assert_false(cond, msg)
  cond, msg = normalize_args(cond, msg)
  local ctx = testing.get_active_context()
  cond = unwrap(cond)
  if cond then
    ctx:record_failure(format_msg("Expected condition to be false", msg), true)
  else
    ctx.passed_assertions = ctx.passed_assertions + 1
  end
end

function testing.assert_eq(actual, expected, msg)
  if actual == testing then actual = expected; expected = msg; msg = nil end
  local ctx = testing.get_active_context()
  actual = unwrap(actual)
  expected = unwrap(expected)
  if actual ~= expected then
    ctx:record_failure(format_msg("Expected " .. tostring(expected) .. ", got " .. tostring(actual), msg), true)
  else
    ctx.passed_assertions = ctx.passed_assertions + 1
  end
end

function testing.assert_ne(actual, expected, msg)
  if actual == testing then actual = expected; expected = msg; msg = nil end
  local ctx = testing.get_active_context()
  actual = unwrap(actual)
  expected = unwrap(expected)
  if actual == expected then
    ctx:record_failure(format_msg("Expected value to not equal " .. tostring(expected), msg), true)
  else
    ctx.passed_assertions = ctx.passed_assertions + 1
  end
end

function testing.assert_almost_eq(a, b, eps, msg)
  if a == testing then a = b; b = eps; eps = msg; msg = nil end
  eps = eps or 1e-5
  a = unwrap(a)
  b = unwrap(b)
  local ctx = testing.get_active_context()
  if math.abs(a - b) > eps then
    ctx:record_failure(format_msg("Expected " .. tostring(a) .. " to almost equal " .. tostring(b), msg), true)
  else
    ctx.passed_assertions = ctx.passed_assertions + 1
  end
end

function testing.assert_none(opt, msg)
  opt, msg = normalize_args(opt, msg)
  local ctx = testing.get_active_context()
  if not is_none(opt) then
    ctx:record_failure(format_msg("Expected nil/None, got " .. tostring(unwrap(opt)), msg), true)
  else
    ctx.passed_assertions = ctx.passed_assertions + 1
  end
end

function testing.assert_not_none(opt, msg)
  opt, msg = normalize_args(opt, msg)
  local ctx = testing.get_active_context()
  if is_none(opt) then
    ctx:record_failure(format_msg("Expected non-nil value, got nil", msg), true)
  else
    ctx.passed_assertions = ctx.passed_assertions + 1
  end
end

function testing.expect_true(cond, msg)
  cond, msg = normalize_args(cond, msg)
  local ctx = testing.get_active_context()
  cond = unwrap(cond)
  if not cond then
    ctx:record_failure(format_msg("Expected condition to be true", msg), false)
  else
    ctx.passed_assertions = ctx.passed_assertions + 1
  end
end

function testing.expect_false(cond, msg)
  cond, msg = normalize_args(cond, msg)
  local ctx = testing.get_active_context()
  cond = unwrap(cond)
  if cond then
    ctx:record_failure(format_msg("Expected condition to be false", msg), false)
  else
    ctx.passed_assertions = ctx.passed_assertions + 1
  end
end

function testing.expect_eq(actual, expected, msg)
  if actual == testing then actual = expected; expected = msg; msg = nil end
  local ctx = testing.get_active_context()
  actual = unwrap(actual)
  expected = unwrap(expected)
  if actual ~= expected then
    ctx:record_failure(format_msg("Expected " .. tostring(expected) .. ", got " .. tostring(actual), msg), false)
  else
    ctx.passed_assertions = ctx.passed_assertions + 1
  end
end

function testing.expect_ne(actual, expected, msg)
  if actual == testing then actual = expected; expected = msg; msg = nil end
  local ctx = testing.get_active_context()
  actual = unwrap(actual)
  expected = unwrap(expected)
  if actual == expected then
    ctx:record_failure(format_msg("Expected value to not equal " .. tostring(expected), msg), false)
  else
    ctx.passed_assertions = ctx.passed_assertions + 1
  end
end

function testing.expect_almost_eq(a, b, eps, msg)
  if a == testing then a = b; b = eps; eps = msg; msg = nil end
  eps = eps or 1e-5
  a = unwrap(a)
  b = unwrap(b)
  local ctx = testing.get_active_context()
  if math.abs(a - b) > eps then
    ctx:record_failure(format_msg("Expected " .. tostring(a) .. " to almost equal " .. tostring(b), msg), false)
  else
    ctx.passed_assertions = ctx.passed_assertions + 1
  end
end

function testing.expect_none(opt, msg)
  opt, msg = normalize_args(opt, msg)
  local ctx = testing.get_active_context()
  if not is_none(opt) then
    ctx:record_failure(format_msg("Expected nil/None, got " .. tostring(unwrap(opt)), msg), false)
  else
    ctx.passed_assertions = ctx.passed_assertions + 1
  end
end

function testing.expect_not_none(opt, msg)
  opt, msg = normalize_args(opt, msg)
  local ctx = testing.get_active_context()
  if is_none(opt) then
    ctx:record_failure(format_msg("Expected non-nil value, got nil", msg), false)
  else
    ctx.passed_assertions = ctx.passed_assertions + 1
  end
end

return testing
