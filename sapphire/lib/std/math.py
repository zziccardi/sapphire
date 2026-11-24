"""Standard library math module for Sapphire (Python target)."""

import math as _math

_builtins_abs = abs


def abs(x):
  return -x if x < 0 else x


def sqrt(x):
  if x < 0:
    return None
  return _math.sqrt(x)


def min(a, b):
  return a if a < b else b


def max(a, b):
  return a if a > b else b


def safe_div__int(a, b):
  if b == 0:
    return None
  q = _builtins_abs(a) // _builtins_abs(b)
  return -q if (a < 0) ^ (b < 0) else q


def safe_div__float(a, b):
  if b == 0 or b == 0.0:
    return None
  return float(a) / float(b)


def safe_div(a, b):
  if b == 0 or b == 0.0:
    return None
  if isinstance(a, int) and isinstance(b, int):
    return safe_div__int(a, b)
  return float(a) / float(b)


def log(x, base=None):
  if x <= 0:
    return None
  if base is not None:
    if base <= 0 or base == 1:
      return None
    return _math.log(x, base)
  return _math.log(x)


def pow(base, exp):
  bf = float(base)
  ef = float(exp)
  if _math.isnan(bf) or _math.isnan(ef):
    return float("nan")
  if bf == 0.0 and ef < 0.0:
    return float("inf")
  if bf < 0.0 and not ef.is_integer():
    return float("nan")
  try:
    return float(_math.pow(bf, ef))
  except OverflowError:
    if bf < 0.0 and ef.is_integer() and int(ef) % 2 != 0:
      return float("-inf")
    return float("inf")
  except ValueError:
    return float("nan")


def ceil(x):
  return _math.ceil(x)


def floor(x):
  return _math.floor(x)


# Generic monomorphization aliases
abs__int = abs
abs__float = abs
sqrt__int = sqrt
sqrt__float = sqrt
min__int = min
min__float = min
max__int = max
max__float = max
log__int = log
log__float = log
pow__int = pow
pow__float = pow
ceil__int = ceil
ceil__float = ceil
floor__int = floor
floor__float = floor
