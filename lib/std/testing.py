"""Standard library testing module for Sapphire (Python target)."""

import inspect

class TestFailure(Exception):
  """Exception raised by fatal assertions (assert_*)."""
  def __init__(self, message: str):
    super().__init__(message)
    self.message = message


class TestContext:
  """Active test execution context tracking soft/hard failures."""
  def __init__(self, name: str = ""):
    self.name = name
    self.passed_assertions = 0
    self.failures = []

  def record_failure(self, message: str, fatal: bool = False,
                     caller_frame=None, kind: str = "generic",
                     expected=None, actual=None):
    if caller_frame is None:
      caller_frame = inspect.currentframe().f_back.f_back
    filename = caller_frame.f_code.co_filename
    lineno = caller_frame.f_lineno
    failure_info = {
        "message": message,
        "filename": filename,
        "lineno": lineno,
        "fatal": fatal,
        "kind": kind,
        "expected": expected,
        "actual": actual,
    }
    self.failures.append(failure_info)
    if fatal:
      raise TestFailure(message)


_active_context = None

def set_active_context(ctx: TestContext):
  global _active_context
  _active_context = ctx

def get_active_context() -> TestContext:
  global _active_context
  if _active_context is None:
    _active_context = TestContext("standalone")
  return _active_context


def _format_msg(default_msg: str, user_msg: str) -> str:
  if user_msg:
    return f"{default_msg} ({user_msg})"
  return default_msg


class TestCase:
  """Base class for test suites implementing std.testing.TestCase."""
  def set_up(self):
    pass

  func_set_up = set_up  # Alias for Sapphire convention

  def tear_down(self):
    pass

  func_tear_down = tear_down  # Alias for Sapphire convention

  def assert_true(self, cond: bool, msg: str = ""):
    _caller = inspect.currentframe().f_back
    assert_true(cond, msg, _caller=_caller)

  def assert_false(self, cond: bool, msg: str = ""):
    _caller = inspect.currentframe().f_back
    assert_false(cond, msg, _caller=_caller)

  def assert_eq(self, actual, expected, msg: str = ""):
    _caller = inspect.currentframe().f_back
    assert_eq(actual, expected, msg, _caller=_caller)

  def assert_ne(self, actual, expected, msg: str = ""):
    _caller = inspect.currentframe().f_back
    assert_ne(actual, expected, msg, _caller=_caller)

  def assert_almost_eq(self, a: float, b: float, eps: float = 1e-5,
                       msg: str = ""):
    _caller = inspect.currentframe().f_back
    assert_almost_eq(a, b, eps, msg, _caller=_caller)

  def assert_none(self, opt, msg: str = ""):
    _caller = inspect.currentframe().f_back
    assert_none(opt, msg, _caller=_caller)

  def assert_not_none(self, opt, msg: str = ""):
    _caller = inspect.currentframe().f_back
    assert_not_none(opt, msg, _caller=_caller)

  def expect_true(self, cond: bool, msg: str = ""):
    _caller = inspect.currentframe().f_back
    expect_true(cond, msg, _caller=_caller)

  def expect_false(self, cond: bool, msg: str = ""):
    _caller = inspect.currentframe().f_back
    expect_false(cond, msg, _caller=_caller)

  def expect_eq(self, actual, expected, msg: str = ""):
    _caller = inspect.currentframe().f_back
    expect_eq(actual, expected, msg, _caller=_caller)

  def expect_ne(self, actual, expected, msg: str = ""):
    _caller = inspect.currentframe().f_back
    expect_ne(actual, expected, msg, _caller=_caller)

  def expect_almost_eq(self, a: float, b: float, eps: float = 1e-5,
                       msg: str = ""):
    _caller = inspect.currentframe().f_back
    expect_almost_eq(a, b, eps, msg, _caller=_caller)

  def expect_none(self, opt, msg: str = ""):
    _caller = inspect.currentframe().f_back
    expect_none(opt, msg, _caller=_caller)

  def expect_not_none(self, opt, msg: str = ""):
    _caller = inspect.currentframe().f_back
    expect_not_none(opt, msg, _caller=_caller)


# --- Standalone / Global Assertion Functions ---

def assert_true(cond: bool, msg: str = "", _caller=None):
  ctx = get_active_context()
  if not cond:
    ctx.record_failure(_format_msg("Expected condition to be true", msg),
                       fatal=True,
                       caller_frame=_caller or inspect.currentframe().f_back,
                       kind="bool", expected=True, actual=cond)
  else:
    ctx.passed_assertions += 1

def assert_false(cond: bool, msg: str = "", _caller=None):
  ctx = get_active_context()
  if cond:
    ctx.record_failure(_format_msg("Expected condition to be false", msg),
                       fatal=True,
                       caller_frame=_caller or inspect.currentframe().f_back,
                       kind="bool", expected=False, actual=cond)
  else:
    ctx.passed_assertions += 1

def assert_eq(actual, expected, msg: str = "", _caller=None):
  ctx = get_active_context()
  if actual != expected:
    ctx.record_failure(
        _format_msg(f"Expected {expected!r}, got {actual!r}", msg), fatal=True,
        caller_frame=_caller or inspect.currentframe().f_back,
        kind="eq", expected=expected, actual=actual)
  else:
    ctx.passed_assertions += 1

def assert_ne(actual, expected, msg: str = "", _caller=None):
  ctx = get_active_context()
  if actual == expected:
    ctx.record_failure(
        _format_msg(f"Expected value to not equal {expected!r}", msg),
        fatal=True,
        caller_frame=_caller or inspect.currentframe().f_back,
        kind="ne", expected=f"anything != {expected!r}", actual=actual)
  else:
    ctx.passed_assertions += 1

def assert_almost_eq(a: float, b: float, eps: float = 1e-5, msg: str = "",
                     _caller=None):
  ctx = get_active_context()
  if abs(a - b) > eps:
    ctx.record_failure(
        _format_msg(f"Expected {a} to almost equal {b} (eps={eps})", msg),
        fatal=True,
        caller_frame=_caller or inspect.currentframe().f_back,
        kind="almost_eq", expected=b, actual=a)
  else:
    ctx.passed_assertions += 1

def assert_none(opt, msg: str = "", _caller=None):
  ctx = get_active_context()
  if opt is not None:
    ctx.record_failure(
        _format_msg(f"Expected None, got {opt!r}", msg),
        fatal=True,
        caller_frame=_caller or inspect.currentframe().f_back,
        kind="none", expected=None, actual=opt)
  else:
    ctx.passed_assertions += 1

def assert_not_none(opt, msg: str = "", _caller=None):
  ctx = get_active_context()
  if opt is None:
    ctx.record_failure(
        _format_msg("Expected non-None value, got None", msg),
        fatal=True,
        caller_frame=_caller or inspect.currentframe().f_back,
        kind="not_none", expected="<non-None>", actual=None)
  else:
    ctx.passed_assertions += 1

def expect_true(cond: bool, msg: str = "", _caller=None):
  ctx = get_active_context()
  if not cond:
    ctx.record_failure(_format_msg("Expected condition to be true", msg),
                       fatal=False,
                       caller_frame=_caller or inspect.currentframe().f_back,
                       kind="bool", expected=True, actual=cond)
  else:
    ctx.passed_assertions += 1

def expect_false(cond: bool, msg: str = "", _caller=None):
  ctx = get_active_context()
  if cond:
    ctx.record_failure(_format_msg("Expected condition to be false", msg),
                       fatal=False,
                       caller_frame=_caller or inspect.currentframe().f_back,
                       kind="bool", expected=False, actual=cond)
  else:
    ctx.passed_assertions += 1

def expect_eq(actual, expected, msg: str = "", _caller=None):
  ctx = get_active_context()
  if actual != expected:
    ctx.record_failure(
        _format_msg(f"Expected {expected!r}, got {actual!r}", msg),
        fatal=False,
        caller_frame=_caller or inspect.currentframe().f_back,
        kind="eq", expected=expected, actual=actual)
  else:
    ctx.passed_assertions += 1

def expect_ne(actual, expected, msg: str = "", _caller=None):
  ctx = get_active_context()
  if actual == expected:
    ctx.record_failure(
        _format_msg(f"Expected value to not equal {expected!r}", msg),
        fatal=False,
        caller_frame=_caller or inspect.currentframe().f_back,
        kind="ne", expected=f"anything != {expected!r}", actual=actual)
  else:
    ctx.passed_assertions += 1

def expect_almost_eq(a: float, b: float, eps: float = 1e-5, msg: str = "",
                     _caller=None):
  ctx = get_active_context()
  if abs(a - b) > eps:
    ctx.record_failure(
        _format_msg(f"Expected {a} to almost equal {b} (eps={eps})", msg),
        fatal=False,
        caller_frame=_caller or inspect.currentframe().f_back,
        kind="almost_eq", expected=b, actual=a)
  else:
    ctx.passed_assertions += 1

def expect_none(opt, msg: str = "", _caller=None):
  ctx = get_active_context()
  if opt is not None:
    ctx.record_failure(
        _format_msg(f"Expected None, got {opt!r}", msg),
        fatal=False,
        caller_frame=_caller or inspect.currentframe().f_back,
        kind="none", expected=None, actual=opt)
  else:
    ctx.passed_assertions += 1

def expect_not_none(opt, msg: str = "", _caller=None):
  ctx = get_active_context()
  if opt is None:
    ctx.record_failure(
        _format_msg("Expected non-None value, got None", msg),
        fatal=False,
        caller_frame=_caller or inspect.currentframe().f_back,
        kind="not_none", expected="<non-None>", actual=None)
  else:
    ctx.passed_assertions += 1
