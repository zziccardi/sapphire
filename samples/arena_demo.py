# Sapphire Runtime Header
import copy
from enum import IntEnum

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


class Point(object):
  def __init__(self, *args, **kwargs):
    for k, v in kwargs.items():
      setattr(self, k, v)
    self._init_sapphire(*args, **kwargs)
  def _init_sapphire(self, x=0.0, y=0.0):
    self.x = x
    self.y = y
  def translate(self, dx, dy):
    self.x += dx
    self.y += dy


class Particle(object):
  def __init__(self, *args, **kwargs):
    for k, v in kwargs.items():
      setattr(self, k, v)
    self._init_sapphire(*args, **kwargs)
  def _init_sapphire(self, pos, lifetime=1.0):
    self.pos = pos
    self.lifetime = lifetime


class Entity(SapphireObject):
  def __init__(self, *args, proto=None, **kwargs):
    super().__init__(proto=proto)
    if proto is None:
      for k, v in kwargs.items():
        setattr(self, k, v)
  pass


class Enemy(Entity):
  def __init__(self, *args, proto=None, **kwargs):
    super().__init__(proto=proto)
    if proto is None:
      for k, v in kwargs.items():
        setattr(self, k, v)
      self._init_sapphire(*args, **kwargs)
  def _init_sapphire(self, name, hp, pos, damage=10):
    self.name = name
    self.hp = hp
    self.pos = pos
    self.damage = damage
  def take_damage(self, amount):
    self.hp -= amount
    if (self.hp < 0):
      self.hp = 0


class Boss(Entity):
  def __init__(self, *args, proto=None, **kwargs):
    super().__init__(proto=proto)
    if proto is None:
      for k, v in kwargs.items():
        setattr(self, k, v)
      self._init_sapphire(*args, **kwargs)
  def _init_sapphire(self, name, hp, pos, phase=1):
    self.name = name
    self.hp = hp
    self.pos = pos
    self.phase = phase


def demo_explicit_arenas():
  level_arena = Arena()
  try:
    combat_arena = Arena()
    try:
      spawn_point = level_arena.register(Point(x=100.0, y=200.0))
      base_goblin = level_arena.register(Enemy(name="Goblin Archer", hp=50, pos=spawn_point, damage=12))
      minion = _clone_helper(base_goblin, lambda self: [setattr(self, 'hp', 30)])
      combat_goblin = _clone_helper(base_goblin, lambda self: [setattr(self, 'hp', 75)], arena=combat_arena)
      minion.take_damage(10)
      combat_goblin.take_damage(25)
      return (minion.hp + combat_goblin.hp)
    finally:
      combat_arena.destroy()
  finally:
    level_arena.destroy()

def demo_scoped_raii_cleanup():
  total_lifetime = 0.0
  temp_arena = Arena()
  try:
    origin = temp_arena.register(Point(x=5.0, y=10.0))
    p1 = temp_arena.register(Particle(pos=origin, lifetime=1.5))
    p2 = temp_arena.register(Particle(pos=origin, lifetime=2.5))
    temp_boss = temp_arena.register(Boss(name="Dungeon Boss", hp=500, pos=origin, phase=1))
    total_lifetime = (p1.lifetime + p2.lifetime)
  finally:
    temp_arena.destroy()
  return total_lifetime

def demo_implicit_default_arena():
  default_pos = Point(x=0.0, y=0.0)
  default_enemy = Enemy(name="Default Skeleton", hp=100, pos=default_pos)
  cloned_skeleton = _clone_helper(default_enemy, lambda self: [setattr(self, 'hp', 60)])
  cloned_skeleton.take_damage(15)
  return (default_enemy.hp + cloned_skeleton.hp)

def run_demo():
  score1 = demo_explicit_arenas()
  score2 = demo_implicit_default_arena()
  duration = demo_scoped_raii_cleanup()
  result = (score1 + score2)
  if (duration > 3.0):
    result += 10
  return result

if __name__ == "__main__":
  
  run_demo()
