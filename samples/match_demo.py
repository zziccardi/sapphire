# Sapphire Runtime Header
import copy
from enum import Enum, IntEnum

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
    for obj in self.objects:
      if hasattr(obj, '__shadow__'):
        obj.__shadow__.clear()
    self.objects.clear()
  def __enter__(self):
    return self
  def __exit__(self, exc_type, exc_val, exc_tb):
    self.destroy()

_DEFAULT_ARENA = Arena()

class SapphireObject:
  def __init__(self, proto=None):
    super().__setattr__('__proto__', proto)
    super().__setattr__('__shadow__', {})
    if proto is None:
      _DEFAULT_ARENA.register(self)

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
        if hasattr(val, 'clone'):
          cow_val = val.clone()
        else:
          cow_val = copy.deepcopy(val)
        self.__shadow__[name] = cow_val
        return cow_val
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


class Direction(IntEnum):
  North = 0
  East = 1
  South = 2
  West = 3


def get_direction_name(dir):
  _match_res_1 = None
  match dir:
    case Direction.North:
      _match_res_1 = "North"
    case Direction.East:
      _match_res_1 = "East"
    case Direction.South:
      _match_res_1 = "South"
    case _:
      _match_res_1 = "West"
  name = _match_res_1
  return name

def handle_action(code):
  _match_res_2 = None
  match code:
    case 200:
      _match_res_2 = "OK"
    case 404:
      _match_res_2 = "Not Found"
    case _:
      log_msg = "Unknown status code"
      _match_res_2 = log_msg
  result = _match_res_2
  return result

def run_side_effects(dir):
  match dir:
    case Direction.North:
      step = 1
    case _:
      step = 0

def main():
  dir_name = get_direction_name(Direction.South)
  status_str = handle_action(404)
  run_side_effects(Direction.East)
  if ((dir_name == "South") and (status_str == "Not Found")):
    return 0
  return 1

if __name__ == "__main__":
  
  main()
  main()
