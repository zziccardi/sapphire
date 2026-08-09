"""Standard library math module for Sapphire (Python target)."""

import math as _math

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

def safe_div(a, b):
  if b == 0 or b == 0.0:
    return None
  if isinstance(a, int) and isinstance(b, int):
    return a // b
  return a / b

def log(x, base=None):
  if x <= 0:
    return None
  if base is not None:
    if base <= 0 or base == 1:
      return None
    return _math.log(x, base)
  return _math.log(x)

def pow(base, exp):
  if isinstance(base, int) and isinstance(exp, int) and exp >= 0:
    return base ** exp
  return _math.pow(base, exp)

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
safe_div__int = safe_div
safe_div__float = safe_div
log__int = log
log__float = log
pow__int = pow
pow__float = pow
ceil__int = ceil
ceil__float = ceil
floor__int = floor
floor__float = floor
