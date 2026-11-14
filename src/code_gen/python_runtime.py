"""Python runtime preamble and reserved word table for Sapphire."""

# ==========================================
# Sapphire Python Runtime Preamble
# ==========================================

PYTHON_RUNTIME_PREAMBLE = """# Sapphire Runtime Header
import os
import sys

_curr_dir = os.path.dirname(os.path.abspath(__file__)) if '__file__' in globals() else os.getcwd()
if _curr_dir not in sys.path:
  sys.path.insert(0, _curr_dir)

# Ensure std and lib packages can be resolved when executed directly
_parent_dir = os.path.dirname(_curr_dir)
for _cand in [os.path.join(_curr_dir, "lib"), os.path.join(_parent_dir, "lib"), _parent_dir]:
  if os.path.isdir(_cand) and _cand not in sys.path:
    sys.path.insert(0, _cand)

import copy
from enum import Enum, IntEnum

class _SapphireCoroutine:
  def __init__(self, fn, *args, **kwargs):
    self._fn = fn
    self._args = args
    self._kwargs = kwargs
    self._gen = None
    self._done = False
    self.reset()

  def step(self):
    if self._done:
      return None
    try:
      return next(self._gen)
    except StopIteration:
      self._done = True
      return None

  def is_done(self):
    return self._done

  def reset(self):
    self._gen = self._fn(*self._args, **self._kwargs)
    self._done = False

class Arena:
  def __init__(self):
    self.objects = []
  def register(self, obj):
    if hasattr(obj, '__arena__') and obj.__arena__ is not None:
      if obj.__arena__ is not self:
        try:
          obj.__arena__.objects.remove(obj)
        except ValueError:
          pass
    if obj not in self.objects:
      self.objects.append(obj)
    if hasattr(obj, '__setattr__'):
      try:
        object.__setattr__(obj, '__arena__', self)
      except AttributeError:
        pass
    return obj
  def destroy(self):
    if getattr(self, '__dict__', {}).get('_sapphire_disposed_', False):
      return
    for obj in reversed(self.objects):
      _sapphire_del(obj)
      if hasattr(obj, '__shadow__'):
        obj.__shadow__.clear()
    self.objects.clear()
    object.__setattr__(self, '_sapphire_disposed_', True)
  def __del__(self):
    self.destroy()
  def __enter__(self):
    return self
  def __exit__(self, exc_type, exc_val, exc_tb):
    self.destroy()

def _sapphire_del(obj):
  if obj is not None and not getattr(obj, '__dict__', {}).get('_sapphire_disposed_', False):
    if hasattr(obj, '__del__') and callable(obj.__del__):
      obj.__del__()

def _sapphire_cow_copy(target, _seen=None):
  if isinstance(target, _LazyCoWProxy):
    target = target._get_active()
  if isinstance(target, (int, float, bool, str, type(None), Enum)):
    return target
  if hasattr(target, 'clone') and callable(target.clone):
    return target.clone()
  if _seen is None:
    _seen = {}
  obj_id = id(target)
  if obj_id in _seen:
    return _seen[obj_id]
  if isinstance(target, list):
    res = []
    _seen[obj_id] = res
    for item in target:
      res.append(_sapphire_cow_copy(item, _seen))
    return res
  if isinstance(target, dict):
    res = {}
    _seen[obj_id] = res
    for k, v in target.items():
      res[k] = _sapphire_cow_copy(v, _seen)
    return res
  if hasattr(target, '__dict__'):
    res = copy.copy(target)
    _seen[obj_id] = res
    for k, v in list(res.__dict__.items()):
      if not k.startswith('__'):
        setattr(res, k, _sapphire_cow_copy(v, _seen))
    return res
  return copy.copy(target)

class _LazyCoWProxy:
  def __init__(self, parent, name, target):
    if isinstance(target, _LazyCoWProxy):
      target = target._get_active()
    super().__setattr__('_parent', parent)
    super().__setattr__('_name', name)
    super().__setattr__('_target', target)

  def _get_parent_obj(self):
    p = super().__getattribute__('_parent')
    if isinstance(p, _LazyCoWProxy):
      return p._get_active()
    return p

  def _get_active(self):
    parent = self._get_parent_obj()
    name = super().__getattribute__('_name')
    if isinstance(parent, dict):
      return parent[name] if name in parent else super().__getattribute__('_target')
    if isinstance(parent, list):
      return parent[name] if 0 <= name < len(parent) else super().__getattribute__('_target')
    if hasattr(parent, '__shadow__'):
      if name in parent.__shadow__:
        return parent.__shadow__[name]
      return super().__getattribute__('_target')
    if isinstance(name, str) and hasattr(parent, name):
      val = getattr(parent, name)
      if val is not None:
        return val
    return super().__getattribute__('_target')

  def _ensure_cow(self):
    p = super().__getattribute__('_parent')
    attr_name = super().__getattribute__('_name')
    target = super().__getattribute__('_target')
    if isinstance(target, _LazyCoWProxy):
      target = target._get_active()

    if isinstance(p, _LazyCoWProxy):
      parent_obj = p._ensure_cow()
    else:
      parent_obj = p

    if isinstance(parent_obj, dict):
      if attr_name not in parent_obj or parent_obj[attr_name] is target:
        cow_val = _sapphire_cow_copy(target)
        parent_obj[attr_name] = cow_val
        return cow_val
      return parent_obj[attr_name]

    if isinstance(parent_obj, list):
      if parent_obj[attr_name] is target:
        cow_val = _sapphire_cow_copy(target)
        parent_obj[attr_name] = cow_val
        return cow_val
      return parent_obj[attr_name]

    if hasattr(parent_obj, '__shadow__'):
      if attr_name not in parent_obj.__shadow__:
        cow_val = _sapphire_cow_copy(target)
        parent_obj.__shadow__[attr_name] = cow_val
        return cow_val
      return parent_obj.__shadow__[attr_name]

    curr = getattr(parent_obj, attr_name, None)
    if curr is None or curr is target:
      cow_val = _sapphire_cow_copy(target)
      setattr(parent_obj, attr_name, cow_val)
      return cow_val
    return curr

  def __getattr__(self, name):
    if name.startswith('_'):
      return super().__getattribute__(name)
    active = self._get_active()
    val = getattr(active, name)
    if hasattr(val, '__self__') and hasattr(val, '__func__') and val.__self__ is active:
      return lambda *args, **kwargs: val.__func__(self, *args, **kwargs)
    if not isinstance(val, (int, float, bool, str, type(None))):
      return _LazyCoWProxy(self, name, val)
    return val

  def __setattr__(self, name, value):
    if name.startswith('_'):
      super().__setattr__(name, value)
      return
    target_obj = self._ensure_cow()
    setattr(target_obj, name, value)

  def __getitem__(self, key):
    active = self._get_active()
    val = active[key]
    if not isinstance(val, (int, float, bool, str, type(None))):
      return _LazyCoWProxy(self, key, val)
    return val

  def __setitem__(self, key, value):
    target_obj = self._ensure_cow()
    target_obj[key] = value

  def __len__(self):
    return len(self._get_active())

  def __iter__(self):
    return iter(self._get_active())

  def __repr__(self):
    return repr(self._get_active())

  def __str__(self):
    return str(self._get_active())

  def __bool__(self):
    return bool(self._get_active())

  def __call__(self, *args, **kwargs):
    return self._get_active()(*args, **kwargs)

  def __contains__(self, item):
    return item in self._get_active()

  def __eq__(self, other):
    return self._get_active() == (other._get_active() if isinstance(other, _LazyCoWProxy) else other)

  def __ne__(self, other):
    return not (self == other)

  def __lt__(self, other):
    return self._get_active() < (other._get_active() if isinstance(other, _LazyCoWProxy) else other)

  def __le__(self, other):
    return self._get_active() <= (other._get_active() if isinstance(other, _LazyCoWProxy) else other)

  def __gt__(self, other):
    return self._get_active() > (other._get_active() if isinstance(other, _LazyCoWProxy) else other)

  def __ge__(self, other):
    return self._get_active() >= (other._get_active() if isinstance(other, _LazyCoWProxy) else other)

  def __add__(self, other):
    return self._get_active() + (other._get_active() if isinstance(other, _LazyCoWProxy) else other)

  def __radd__(self, other):
    return (other._get_active() if isinstance(other, _LazyCoWProxy) else other) + self._get_active()

  def __iadd__(self, other):
    target_obj = self._ensure_cow()
    val = (other._get_active() if isinstance(other, _LazyCoWProxy) else other)
    target_obj += val
    return self

  def __sub__(self, other):
    return self._get_active() - (other._get_active() if isinstance(other, _LazyCoWProxy) else other)

  def __rsub__(self, other):
    return (other._get_active() if isinstance(other, _LazyCoWProxy) else other) - self._get_active()

  def __isub__(self, other):
    target_obj = self._ensure_cow()
    val = (other._get_active() if isinstance(other, _LazyCoWProxy) else other)
    target_obj -= val
    return self

  def __mul__(self, other):
    return self._get_active() * (other._get_active() if isinstance(other, _LazyCoWProxy) else other)

  def __rmul__(self, other):
    return (other._get_active() if isinstance(other, _LazyCoWProxy) else other) * self._get_active()

  def __imul__(self, other):
    target_obj = self._ensure_cow()
    val = (other._get_active() if isinstance(other, _LazyCoWProxy) else other)
    target_obj *= val
    return self

  def __truediv__(self, other):
    return self._get_active() / (other._get_active() if isinstance(other, _LazyCoWProxy) else other)

  def __itruediv__(self, other):
    target_obj = self._ensure_cow()
    val = (other._get_active() if isinstance(other, _LazyCoWProxy) else other)
    target_obj /= val
    return self

  def __floordiv__(self, other):
    return self._get_active() // (other._get_active() if isinstance(other, _LazyCoWProxy) else other)

  def __mod__(self, other):
    return self._get_active() % (other._get_active() if isinstance(other, _LazyCoWProxy) else other)

  def __imod__(self, other):
    target_obj = self._ensure_cow()
    val = (other._get_active() if isinstance(other, _LazyCoWProxy) else other)
    target_obj %= val
    return self

class SapphireObject:
  def __init__(self, proto=None):
    super().__setattr__('__proto__', proto)
    super().__setattr__('__shadow__', {})

  def clone(self):
    clone_obj = self.__class__(proto=self)
    if hasattr(self, '__arena__') and self.__arena__ is not None:
      self.__arena__.register(clone_obj)
    return clone_obj

  def __getattr__(self, name):
    if name.startswith('__') and name.endswith('__'):
      if name == '__proto__':
        return self.__proto__
      raise AttributeError(f"Attribute '{name}' not found on {self.__class__.__name__}")
    if name in self.__shadow__:
      return self.__shadow__[name]
    if self.__proto__ is not None:
      val = getattr(self.__proto__, name)
      if not isinstance(val, (int, float, bool, str, type(None))):
        return _LazyCoWProxy(self, name, val)
      return val
    raise AttributeError(f"Attribute '{name}' not found on {self.__class__.__name__}")

  def __setattr__(self, name, value):
    if name in ('__proto__', '__shadow__'):
      super().__setattr__(name, value)
    elif self.__proto__ is not None:
      self.__shadow__[name] = value
    else:
      super().__setattr__(name, value)

def _clone_helper(obj, init_fn=None, arena=None):
  if arena is None and hasattr(obj, '__arena__'):
    arena = getattr(obj, '__arena__', None)
  clone_obj = obj.clone()
  if arena is not None:
    arena.register(clone_obj)
  if init_fn:
    init_fn(clone_obj)
  return clone_obj

def _sapphire_string_split(s, sep=None):
  if s is None:
    return []
  if sep == "":
    return list(s)
  return s.split(sep)

def _sapphire_string_find(s, sub, start=0, reverse=False):
  if s is None or sub is None:
    return None
  if reverse:
    res = s.rfind(sub, start)
  else:
    res = s.find(sub, start)
  return None if res == -1 else res

def _sapphire_string_to_int(s, radix=10):
  if s is None:
    return None
  try:
    return int(s, radix)
  except (ValueError, TypeError):
    return None

def _sapphire_string_to_float(s):
  if s is None:
    return None
  try:
    return float(s)
  except (ValueError, TypeError):
    return None

def _sapphire_string_to_bool(s):
  if not isinstance(s, str):
    return None
  val = s.strip().lower()
  if val == "true":
    return True
  if val == "false":
    return False
  return None

def _sapphire_string_from(val):
  if val is True:
    return "true"
  if val is False:
    return "false"
  if isinstance(val, Enum):
    return str(val.value)
  return str(val)

def _sapphire_enum_from(enum_cls, val):
  if val is None:
    return None
  try:
    return enum_cls(val)
  except ValueError:
    if isinstance(val, str):
      try:
        return enum_cls[val]
      except KeyError:
        return None
    return None

def _sapphire_array_map(arr, fn, in_place=False):
  if in_place:
    for i in range(len(arr)):
      arr[i] = fn(arr[i])
    return arr
  return [fn(x) for x in arr]

def _sapphire_array_filter(arr, fn, in_place=False):
  if in_place:
    filtered = [x for x in arr if fn(x)]
    arr[:] = filtered
    return arr
  return [x for x in arr if fn(x)]

def _sapphire_array_reduce(arr, initial, fn, reverse=False):
  items = reversed(arr) if reverse else arr
  acc = initial
  for x in items:
    acc = fn(acc, x)
  return acc

def _sapphire_array_contains(arr, element):
  return element in arr

def _sapphire_array_reverse(arr, in_place=False):
  if in_place:
    arr.reverse()
    return arr
  return list(reversed(arr))

def _sapphire_array_sort(arr, by=None, reverse=False, in_place=False):
  if in_place:
    if by is None:
      arr.sort(reverse=reverse)
    else:
      import functools
      arr.sort(key=functools.cmp_to_key(by), reverse=reverse)
    return arr
  if by is None:
    return sorted(arr, reverse=reverse)
  import functools
  return sorted(arr, key=functools.cmp_to_key(by), reverse=reverse)

def _sapphire_array_join(arr, sep=", "):
  return sep.join(str(x) for x in arr)

def _sapphire_array_push(arr, element):
  arr.append(element)
  return element

def _sapphire_array_pop(arr):
  if not arr:
    return None
  return arr.pop()

def _sapphire_array_insert(arr, index, element):
  idx = len(arr) + index if index < 0 else index
  if idx < 0:
    idx = 0
  elif idx > len(arr):
    idx = len(arr)
  arr.insert(idx, element)
  return element

def _sapphire_array_remove(arr, index):
  idx = len(arr) + index if index < 0 else index
  if 0 <= idx < len(arr):
    return arr.pop(idx)
  return None

def _sapphire_array_clear(arr):
  arr.clear()

def _sapphire_array_swap(arr, i, j):
  n = len(arr)
  idx_i = n + i if i < 0 else i
  idx_j = n + j if j < 0 else j
  if 0 <= idx_i < n and 0 <= idx_j < n:
    arr[idx_i], arr[idx_j] = arr[idx_j], arr[idx_i]

def _sapphire_map_size(m):
  return len(m)

def _sapphire_map_empty(m):
  return len(m) == 0

def _sapphire_map_contains(m, k):
  return k in m

def _sapphire_map_keys(m):
  return list(m.keys())

def _sapphire_map_values(m):
  return list(m.values())

def _sapphire_map_insert(m, k, v):
  m[k] = v
  return v

def _sapphire_map_remove(m, k):
  return m.pop(k, None)

def _sapphire_array_get(arr, index):
  if arr is None:
    return None
  idx = len(arr) + index if index < 0 else index
  if 0 <= idx < len(arr):
    return arr[idx]
  return None

def _sapphire_map_get(m, key):
  if m is None or not isinstance(m, dict):
    return None
  return m.get(key, None)

def _sapphire_map_clear(m):
  m.clear()

class _SapphireRef:
  def __init__(self, value):
    super().__setattr__('_value', value)
  def __getattr__(self, name):
    return getattr(self._value, name)
  def __setattr__(self, name, val):
    if name == '_value':
      super().__setattr__(name, val)
    else:
      setattr(self._value, name, val)
  def __repr__(self):
    return f"Ref({self._value!r})"

class _SapphireSharedControlBlock:
  def __init__(self, value):
    self.value = value
    self.strong_count = 1
    self.weak_count = 0

class _SapphireSharedRef:
  def __init__(self, target):
    if isinstance(target, _SapphireRef):
      super().__setattr__('_cb', _SapphireSharedControlBlock(target._value))
    elif isinstance(target, _SapphireSharedControlBlock):
      super().__setattr__('_cb', target)
    else:
      super().__setattr__('_cb', _SapphireSharedControlBlock(target))

  def share(self):
    self._cb.strong_count += 1
    return _SapphireSharedRef(self._cb)

  def downgrade(self):
    self._cb.weak_count += 1
    return _SapphireWeakRef(self._cb)

  def __getattr__(self, name):
    if name in ('_cb', 'share', 'downgrade'):
      return super().__getattribute__(name)
    return getattr(self._cb.value, name)

  def __setattr__(self, name, val):
    if name == '_cb':
      super().__setattr__(name, val)
    else:
      setattr(self._cb.value, name, val)

  def __repr__(self):
    return f"SharedRef({self._cb.value!r})"

class _SapphireWeakRef:
  def __init__(self, cb):
    self._cb = cb

  def upgrade(self):
    if self._cb is not None and self._cb.strong_count > 0:
      self._cb.strong_count += 1
      return _SapphireSharedRef(self._cb)
    return None

  def __repr__(self):
    return f"WeakRef({self._cb.value!r})" if (self._cb and self._cb.strong_count > 0) else "WeakRef(expired)"

def Ref(val):
  return _SapphireRef(val)

def SharedRef(val):
  return _SapphireSharedRef(val)
"""

RUNTIME_PREAMBLE = PYTHON_RUNTIME_PREAMBLE

PYTHON_RUNTIME_MODULE_IMPORT = """# Sapphire Runtime Module Import
import os
import sys

_curr_dir = os.path.dirname(os.path.abspath(__file__)) if '__file__' in globals() else os.getcwd()
if _curr_dir not in sys.path:
  sys.path.insert(0, _curr_dir)

_parent_dir = os.path.dirname(_curr_dir)
for _cand in [os.path.join(_curr_dir, "lib"), os.path.join(_parent_dir, "lib"), _parent_dir]:
  if os.path.isdir(_cand) and _cand not in sys.path:
    sys.path.insert(0, _cand)

from _sapphire_runtime import *
"""


PYTHON_RESERVED_WORDS = {
    "False", "None", "True", "and", "as", "assert", "async", "await",
    "break", "class", "continue", "def", "del", "elif", "else", "except",
    "finally", "for", "from", "global", "if", "import", "in", "is",
    "lambda", "nonlocal", "not", "or", "pass", "raise", "return", "try",
    "while", "with", "yield",
}

