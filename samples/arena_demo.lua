-- Sapphire Lua 5.1 Runtime Header

local Arena = {}
Arena.__index = Arena

function Arena.init()
  local self = setmetatable({}, Arena)
  self.objects = {}
  return self
end

function Arena:register(obj)
  if type(obj) == "table" then
    local meta = getmetatable(obj)
    if meta and meta.__arena and meta.__arena ~= self then
      for i, o in ipairs(meta.__arena.objects) do
        if o == obj then
          table.remove(meta.__arena.objects, i)
          break
        end
      end
    end
    table.insert(self.objects, obj)
    if meta then
      meta.__arena = self
    end
  end
  return obj
end

function Arena:destroy()
  for _, obj in ipairs(self.objects) do
    local meta = getmetatable(obj)
    if meta and meta.__shadow then
      for k in pairs(meta.__shadow) do
        meta.__shadow[k] = nil
      end
    end
  end
  self.objects = {}
end

local _DEFAULT_ARENA = Arena.init()

local _clone_helper

local function _create_proto_object(proto, class_tbl)
  local shadow = {}
  local meta = {}
  meta.__shadow = shadow
  meta.__proto = proto
  meta.__class = class_tbl
  meta.__index = function(tbl, key)
    if key == "__proto__" then return meta.__proto end
    if key == "__shadow__" then return meta.__shadow end
    if shadow[key] ~= nil then return shadow[key] end
    if proto ~= nil then
      local val = proto[key]
      if val ~= nil then
        if type(val) == "table" then
          local cow = _clone_helper(val, nil, nil)
          shadow[key] = cow
          return cow
        end
        return val
      end
    end
    if class_tbl and class_tbl[key] ~= nil then
      return class_tbl[key]
    end
    return nil
  end
  meta.__newindex = function(tbl, key, val)
    if key == "__proto__" or key == "__shadow__" then return end
    if proto ~= nil then
      shadow[key] = val
    else
      rawset(tbl, key, val)
    end
  end
  local obj = setmetatable({}, meta)
  if proto == nil then
    _DEFAULT_ARENA:register(obj)
  end
  return obj
end

_clone_helper = function(obj, init_fn, arena)
  if obj == nil then return nil end
  local clone_obj
  if type(obj) == "table" then
    local meta = getmetatable(obj)
    if obj.clone and type(obj.clone) == "function" then
      clone_obj = obj:clone()
    elseif meta and meta.__class then
      clone_obj = _create_proto_object(obj, meta.__class)
    else
      clone_obj = _create_proto_object(obj, nil)
    end
  else
    clone_obj = obj
  end
  if arena ~= nil and type(clone_obj) == "table" then
    arena:register(clone_obj)
  end
  if init_fn then
    init_fn(clone_obj)
  end
  return clone_obj
end


local Point = {}
Point.__index = Point
function Point.init(kwargs, proto)
  kwargs = kwargs or {}
  local self
  self = setmetatable({}, Point)
  if proto == nil then
  end
  for k, v in pairs(kwargs) do
    self[k] = v
  end
  if Point._init_sapphire then
    Point._init_sapphire(self, (kwargs['x'] ~= nil and kwargs['x'] or kwargs[1]), (kwargs['y'] ~= nil and kwargs['y'] or kwargs[2]))
  end
  return self
end

function Point:_init_sapphire(x, y)
  if x == nil then x = 0.0 end
  if y == nil then y = 0.0 end
  self.x = x
  self.y = y
end

function Point:translate(dx, dy)
  self.x = self.x + dx
  self.y = self.y + dy
end


local Particle = {}
Particle.__index = Particle
function Particle.init(kwargs, proto)
  kwargs = kwargs or {}
  local self
  self = setmetatable({}, Particle)
  if proto == nil then
  end
  for k, v in pairs(kwargs) do
    self[k] = v
  end
  if Particle._init_sapphire then
    Particle._init_sapphire(self, (kwargs['pos'] ~= nil and kwargs['pos'] or kwargs[1]), (kwargs['lifetime'] ~= nil and kwargs['lifetime'] or kwargs[2]))
  end
  return self
end

function Particle:_init_sapphire(pos, lifetime)
  if lifetime == nil then lifetime = 1.0 end
  self.pos = pos
  self.lifetime = lifetime
end


local Entity = {}
Entity.__index = Entity
function Entity.init(kwargs, proto)
  kwargs = kwargs or {}
  local self
  self = _create_proto_object(proto, Entity)
  if proto == nil then
  end
  for k, v in pairs(kwargs) do
    self[k] = v
  end
  return self
end


local Enemy = {}
Enemy.__index = Enemy
function Enemy.init(kwargs, proto)
  kwargs = kwargs or {}
  local self
  self = _create_proto_object(proto, Enemy)
  if proto == nil then
  end
  for k, v in pairs(kwargs) do
    self[k] = v
  end
  if Enemy._init_sapphire then
    Enemy._init_sapphire(self, (kwargs['name'] ~= nil and kwargs['name'] or kwargs[1]), (kwargs['hp'] ~= nil and kwargs['hp'] or kwargs[2]), (kwargs['pos'] ~= nil and kwargs['pos'] or kwargs[3]), (kwargs['damage'] ~= nil and kwargs['damage'] or kwargs[4]))
  end
  return self
end

function Enemy:_init_sapphire(name, hp, pos, damage)
  if damage == nil then damage = 10 end
  self.name = name
  self.hp = hp
  self.pos = pos
  self.damage = damage
end

function Enemy:take_damage(amount)
  self.hp = self.hp - amount
  if (self.hp < 0) then
    self.hp = 0
  end
end


local Boss = {}
Boss.__index = Boss
function Boss.init(kwargs, proto)
  kwargs = kwargs or {}
  local self
  self = _create_proto_object(proto, Boss)
  if proto == nil then
  end
  for k, v in pairs(kwargs) do
    self[k] = v
  end
  if Boss._init_sapphire then
    Boss._init_sapphire(self, (kwargs['name'] ~= nil and kwargs['name'] or kwargs[1]), (kwargs['hp'] ~= nil and kwargs['hp'] or kwargs[2]), (kwargs['pos'] ~= nil and kwargs['pos'] or kwargs[3]), (kwargs['phase'] ~= nil and kwargs['phase'] or kwargs[4]))
  end
  return self
end

function Boss:_init_sapphire(name, hp, pos, phase)
  if phase == nil then phase = 1 end
  self.name = name
  self.hp = hp
  self.pos = pos
  self.phase = phase
end


local function demo_explicit_arenas()
  local level_arena = Arena.init()
  local combat_arena = Arena.init()
  local spawn_point = level_arena:register(Point.init({x = 100.0, y = 200.0}))
  local base_goblin = level_arena:register(Enemy.init({name = "Goblin Archer", hp = 50, pos = spawn_point, damage = 12}))
  local minion = _clone_helper(base_goblin, function(self)
    self.hp = 30
  end)
  local combat_goblin = _clone_helper(base_goblin, function(self)
    self.hp = 75
  end, combat_arena)
  minion:take_damage(10)
  combat_goblin:take_damage(25)
  combat_arena:destroy()
  level_arena:destroy()
  return (minion.hp + combat_goblin.hp)
end


local function demo_scoped_raii_cleanup()
  local total_lifetime = 0.0
  local temp_arena = Arena.init()
  local origin = temp_arena:register(Point.init({x = 5.0, y = 10.0}))
  local p1 = temp_arena:register(Particle.init({pos = origin, lifetime = 1.5}))
  local p2 = temp_arena:register(Particle.init({pos = origin, lifetime = 2.5}))
  local temp_boss = temp_arena:register(Boss.init({name = "Dungeon Boss", hp = 500, pos = origin, phase = 1}))
  total_lifetime = (p1.lifetime + p2.lifetime)
  temp_arena:destroy()
  return total_lifetime
end


local function demo_implicit_default_arena()
  local default_pos = Point.init({x = 0.0, y = 0.0})
  local default_enemy = Enemy.init({name = "Default Skeleton", hp = 100, pos = default_pos})
  local cloned_skeleton = _clone_helper(default_enemy, function(self)
    self.hp = 60
  end)
  cloned_skeleton:take_damage(15)
  return (default_enemy.hp + cloned_skeleton.hp)
end


local function run_demo()
  local score1 = demo_explicit_arenas()
  local score2 = demo_implicit_default_arena()
  local duration = demo_scoped_raii_cleanup()
  local result = (score1 + score2)
  if (duration > 3.0) then
    result = result + 10
  end
  return result
end


run_demo()
