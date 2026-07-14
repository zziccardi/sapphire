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


MAX_PLAYERS = 100


class Position(SapphireObject):
  def __init__(self, *args, proto=None, **kwargs):
    super().__init__(proto)
    if proto is None:
      self._init_sapphire(*args, **kwargs)
  def _init_sapphire(self, x, y):
    self.x = x
    self.y = y


class Entity(SapphireObject):
  def __init__(self, *args, proto=None, **kwargs):
    super().__init__(proto)
    if proto is None:
      pass
  pass


class Character(Entity):
  def __init__(self, *args, proto=None, **kwargs):
    super().__init__(proto)
    if proto is None:
      self._init_sapphire(*args, **kwargs)
  def _init_sapphire(self, id, name, max_hp=100):
    self.id = id
    self.pos = Position(x=0.0, y=0.0)
    self.health = max_hp
    self.max_health = max_hp
    self.name = name
  def get_health_ratio(self):
    return (self.health / self.max_health)
  def heal(self, amount):
    self.health += amount
    if (self.health > self.max_health):
      self.health = self.max_health
  def take_damage(self, amount):
    self.health -= amount
    if (self.health < 0):
      self.health = 0
    else:
      if (self.health > self.max_health):
        self.health = self.max_health
      else:
        pass


def execute_attack(attacker, defender, is_critical=False):
  base_damage = 15
  if is_critical:
    base_damage *= 2
  defender.take_damage(base_damage)
  return base_damage

def run_demo():
  player_one = Character(id=1, name="Galahad")
  player_two = Character(id=2, name="Lancelot", max_hp=120)
  target_player = None
  target_player = player_two
  _val_active_target = target_player
  if _val_active_target is not None:
    active_target = _val_active_target
    damage_dealt = execute_attack(attacker=player_one, defender=active_target, is_critical=True)
  else:
    pass
  prototype_enemy = Character(id=99, name="Goblin Minion", max_hp=30)
  active_clone = _clone_helper(prototype_enemy, lambda self: [setattr(self, 'health', 25)])
  _val_parent = active_clone.__proto__
  if _val_parent is not None:
    parent = _val_parent
    name_ref = parent.name
  damage_multiplier = (lambda x: (x * 2))
  sum_func = (lambda x, y: (x + y))
  base_score = (-50)
  positive_adjustment = (+10)
  coord_x = 10
  mixed_result = (coord_x + positive_adjustment)
  scores = [10, 20, 30]
  first_score = scores[0]
  timer = 3
  while (timer > 0):
    timer -= 1
  for score in scores:
    final_score = damage_multiplier(score)
  for score in scores:
    score += 5
