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

import lib.love2d.enums
import lib.love2d.graphics
import lib.love2d.love2d

love = love2d.love

hero_img

hero_x = 100.0

hero_y = 100.0

speed = 250.0

def load():
  love.graphics.setBackgroundColor(r=0.1, g=0.1, b=0.15)
  hero_img = love.graphics.newImage("assets/hero.png")

def update(dt):
  if (love.keyboard.isDown("left") or love.keyboard.isDown("a")):
    hero_x -= (speed * dt)
  if (love.keyboard.isDown("right") or love.keyboard.isDown("d")):
    hero_x += (speed * dt)
  if (love.keyboard.isDown("up") or love.keyboard.isDown("w")):
    hero_y -= (speed * dt)
  if (love.keyboard.isDown("down") or love.keyboard.isDown("s")):
    hero_y += (speed * dt)

def draw():
  love.graphics.clear(r=0.1, g=0.15, b=0.2)
  love.graphics.setColor(0.2, 0.7, 0.5)
  love.graphics.rectangle(mode=enums.DrawMode.Fill, x=50.0, y=50.0, width=300.0, height=150.0)
  _val_img = hero_img
  if _val_img is not None:
    img = _val_img
    love.graphics.setColor(1.0, 1.0, 1.0)
    img.draw(x=hero_x, y=hero_y)
  love.graphics.setColor(1.0, 1.0, 1.0)
  fps_str = ("FPS: " + love.timer.getFPS())
  love.graphics.print(text=fps_str, x=10.0, y=10.0)
