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


class GameState(IntEnum):
  Menu = 0
  Playing = 1
  GameOver = 2


class Vector2D(object):
  def __init__(self, *args, **kwargs):
    for k, v in kwargs.items():
      setattr(self, k, v)
    self._init_sapphire(*args, **kwargs)
  def _init_sapphire(self, x, y):
    self.x = x
    self.y = y
  def translate(self, dx, dy):
    self.x += dx
    self.y += dy
  def get_distance_to(self, other):
    dx = (self.x - other.x)
    dy = (self.y - other.y)
    abs_dx = dx
    if (abs_dx < 0.0):
      abs_dx = (-abs_dx)
    abs_dy = dy
    if (abs_dy < 0.0):
      abs_dy = (-abs_dy)
    return (abs_dx + abs_dy)




class GameObject(SapphireObject):
  def __init__(self, *args, proto=None, **kwargs):
    super().__init__(proto=proto)
    if proto is None:
      for k, v in kwargs.items():
        setattr(self, k, v)
  pass


class Entity(GameObject):
  def __init__(self, *args, proto=None, **kwargs):
    super().__init__(proto=proto)
    if proto is None:
      for k, v in kwargs.items():
        setattr(self, k, v)
      self._init_sapphire(*args, **kwargs)
  def _init_sapphire(self, id, name, x, y, hp=100, spd=5.0):
    self.id = id
    self.position = Vector2D(x=x, y=y)
    self.active = True
    self.health = hp
    self.speed = spd
    self.name = name
  def update(self, dt):
    if (self.health <= 0):
      self.active = False
      return
    self.position.translate(dx=(self.speed * dt), dy=0.0)
  def draw(self):
    if self.active:
      pass


class GameEngine(object):
  def __init__(self, *args, **kwargs):
    for k, v in kwargs.items():
      setattr(self, k, v)
    self._init_sapphire(*args, **kwargs)
  def _init_sapphire(self):
    self.state = GameState.Menu
    self.score = 0
    self.frame_count = 0
    self.player = Entity(id=1, name="Hero", x=10.0, y=20.0, hp=100, spd=12.0)
    self.base_enemy = Entity(id=0, name="Slime", x=100.0, y=20.0, hp=30, spd=(-4.0))
    self.active_enemy = None
    self.game_over_timer = 0.0


def load(game):
  game.state = GameState.Playing
  game.score = 0
  game.frame_count = 0
  game.game_over_timer = 0.0
  spawned_slime = _clone_helper(game.base_enemy, lambda self: [setattr(self, 'id', 101), setattr(self, 'position', Vector2D(x=80.0, y=20.0))])
  game.active_enemy = spawned_slime

def update(game, dt):
  game.frame_count += 1
  if (game.state == GameState.Playing):
    game.player.update(dt)
    _val_enemy = game.active_enemy
    if _val_enemy is not None:
      enemy = _val_enemy
      enemy.update(dt)
      dist = game.player.position.get_distance_to(other=enemy.position)
      if (dist < 15.0):
        enemy.health -= 30
        game.score += 50
        if (enemy.health <= 0):
          game.active_enemy = None
          game.state = GameState.GameOver
    else:
      wave_enemy = _clone_helper(game.base_enemy, lambda self: [setattr(self, 'id', 102), setattr(self, 'position', Vector2D(x=120.0, y=20.0)), setattr(self, 'health', 50)])
      game.active_enemy = wave_enemy
  else:
    if (game.state == GameState.GameOver):
      game.game_over_timer += dt
      if (game.game_over_timer >= 3.0):
        load(game=game)

def draw(game):
  if (game.state == GameState.Menu):
    pass
  else:
    if (game.state == GameState.Playing):
      game.player.draw()
      _val_enemy = game.active_enemy
      if _val_enemy is not None:
        enemy = _val_enemy
        enemy.draw()
    else:
      if (game.state == GameState.GameOver):
        pass

def run_game_loop():
  engine = GameEngine()
  load(game=engine)
  frame_deltas = [0.016, 0.016, 0.016, 0.016, 0.016]
  for dt in frame_deltas:
    update(game=engine, dt=dt)
    draw(game=engine)

if __name__ == "__main__":
  
  run_game_loop()
