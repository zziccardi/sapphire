# Sapphire Runtime Header
class SapphireObject:
  def __init__(self, proto=None):
    super().__setattr__('__proto__', proto)
    super().__setattr__('__shadow__', {})

  def clone(self):
    return self.__class__(proto=self)

  def __getattr__(self, name):
    if name == '__proto__':
      return self.__proto__
    if name in self.__shadow__:
      return self.__shadow__[name]
    if self.__proto__ is not None:
      return getattr(self.__proto__, name)
    raise AttributeError(f"Attribute '{name}' not found on {self.__class__.__name__}")

  def __setattr__(self, name, value):
    if name in ('__proto__', '__shadow__'):
      super().__setattr__(name, value)
    elif self.__proto__ is not None:
      self.__shadow__[name] = value
    else:
      super().__setattr__(name, value)

def _clone_helper(obj, init_fn=None):
  clone_obj = obj.clone()
  if init_fn:
    init_fn(clone_obj)
  return clone_obj


class Vector2D(SapphireObject):
  def __init__(self, *args, proto=None, **kwargs):
    super().__init__(proto=proto)
    if proto is None:
      self._init_sapphire(*args, **kwargs)
  def _init_sapphire(self, x, y):
    self.x = x
    self.y = y
  def translate(self, dx, dy):
    self.x += dx
    self.y += dy




class GameObject(SapphireObject):
  def __init__(self, *args, proto=None, **kwargs):
    super().__init__(proto=proto)
    if proto is None:
      pass
  pass


class Character(GameObject):
  def __init__(self, *args, proto=None, **kwargs):
    super().__init__(proto=proto)
    if proto is None:
      self._init_sapphire(*args, **kwargs)
  def _init_sapphire(self, id, name, x, y, hp=50, spd=2.0):
    self.id = id
    self.position = Vector2D(x=x, y=y)
    self.active = True
    self.health = hp
    self.max_health = hp
    self.speed = spd
    self.name = name
  def update(self, dt):
    if (self.health <= 0):
      self.active = False
      return
    self.position.translate(dx=(self.speed * dt), dy=0.0)
  def take_damage(self, amount):
    self.health -= amount
    if (self.health <= 0):
      self.health = 0
      self.active = False
  def get_health(self):
    return self.health


def execute_strike(attacker, defender, bonus=5):
  damage = 10
  if (attacker.health > 25):
    damage += bonus
  defender.take_damage(damage)
  return damage

def run_demo():
  base_goblin = Character(id=0, name="Goblin Archer", x=0.0, y=0.0, hp=30, spd=1.5)
  goblin_1 = _clone_helper(base_goblin, lambda self: [setattr(self, 'id', 101), setattr(self, 'position', Vector2D(x=10.0, y=5.0))])
  goblin_2 = _clone_helper(base_goblin, lambda self: [setattr(self, 'id', 102), setattr(self, 'position', Vector2D(x=12.0, y=6.0))])
  hero = Character(id=1, name="Arthur", x=8.0, y=5.0, hp=80, spd=2.5)
  base_goblin.speed = 3.5
  target = None
  target = goblin_1
  _val_active_target = target
  if _val_active_target is not None:
    active_target = _val_active_target
    damage_dealt = execute_strike(attacker=hero, defender=active_target, bonus=10)
  else:
    pass
  target_speed = (target.speed if target is not None else None)
  damage = execute_strike(attacker=hero, defender=goblin_2)
  is_alive = (lambda c: (c.health > 0))
  get_threat_level = (lambda c: c.health)
  entities = [hero, goblin_1, goblin_2]
  for entity in entities:
    entity.update(dt=0.1)
  total_health = 0
  for entity in entities:
    if is_alive(entity):
      total_health += get_threat_level(entity)
