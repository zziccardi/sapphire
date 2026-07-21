-- Sapphire Lua 5.1 Runtime Header

local Arena = {}
Arena.__index = Arena

function Arena.new()
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

local _DEFAULT_ARENA = Arena.new()

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


local Vector2D = {}
Vector2D.__index = Vector2D
function Vector2D.new(kwargs, proto)
  kwargs = kwargs or {}
  local self
  self = setmetatable({}, Vector2D)
  if proto == nil then
  end
  for k, v in pairs(kwargs) do
    self[k] = v
  end
  if Vector2D._init_sapphire then
    Vector2D._init_sapphire(self, (kwargs['x'] ~= nil and kwargs['x'] or kwargs[1]), (kwargs['y'] ~= nil and kwargs['y'] or kwargs[2]))
  end
  return self
end

function Vector2D:_init_sapphire(x, y)
  self.x = x
  self.y = y
end

function Vector2D:translate(dx, dy)
  self.x = self.x + dx
  self.y = self.y + dy
end




local GameObject = {}
GameObject.__index = GameObject
function GameObject.new(kwargs, proto)
  kwargs = kwargs or {}
  local self
  self = _create_proto_object(proto, GameObject)
  if proto == nil then
  end
  for k, v in pairs(kwargs) do
    self[k] = v
  end
  return self
end


local Character = {}
Character.__index = Character
function Character.new(kwargs, proto)
  kwargs = kwargs or {}
  local self
  self = _create_proto_object(proto, Character)
  if proto == nil then
  end
  for k, v in pairs(kwargs) do
    self[k] = v
  end
  if Character._init_sapphire then
    Character._init_sapphire(self, (kwargs['id'] ~= nil and kwargs['id'] or kwargs[1]), (kwargs['name'] ~= nil and kwargs['name'] or kwargs[2]), (kwargs['x'] ~= nil and kwargs['x'] or kwargs[3]), (kwargs['y'] ~= nil and kwargs['y'] or kwargs[4]), (kwargs['hp'] ~= nil and kwargs['hp'] or kwargs[5]), (kwargs['spd'] ~= nil and kwargs['spd'] or kwargs[6]))
  end
  return self
end

function Character:_init_sapphire(id, name, x, y, hp, spd)
  if hp == nil then hp = 50 end
  if spd == nil then spd = 2.0 end
  self.id = id
  self.position = Vector2D.new({x = x, y = y})
  self.active = true
  self.health = hp
  self.max_health = hp
  self.speed = spd
  self.name = name
end

function Character:update(dt)
  if (self.health <= 0) then
    self.active = false
    return
  end
  self.position:translate((self.speed * dt), 0.0)
end

function Character:take_damage(amount)
  self.health = self.health - amount
  if (self.health <= 0) then
    self.health = 0
    self.active = false
  end
end

function Character:get_health()
  return self.health
end


local function execute_strike(attacker, defender, bonus)
  if bonus == nil then bonus = 5 end
  local damage = 10
  if (attacker.health > 25) then
    damage = damage + bonus
  end
  defender:take_damage(damage)
  return damage
end


local function run_demo()
  local base_goblin = Character.new({id = 0, name = "Goblin Archer", x = 0.0, y = 0.0, hp = 30, spd = 1.5})
  local goblin_1 = _clone_helper(base_goblin, function(self)
    self.id = 101
    self.position = Vector2D.new({x = 10.0, y = 5.0})
  end)
  local goblin_2 = _clone_helper(base_goblin, function(self)
    self.id = 102
    self.position = Vector2D.new({x = 12.0, y = 6.0})
  end)
  local hero = Character.new({id = 1, name = "Arthur", x = 8.0, y = 5.0, hp = 80, spd = 2.5})
  base_goblin.speed = 3.5
  local target = nil
  target = goblin_1
  local _val_active_target = target
  if _val_active_target ~= nil then
    local active_target = _val_active_target
    local damage_dealt = execute_strike(hero, active_target, 10)
  else
    -- pass
  end
  local target_speed = (target ~= nil and target.speed or nil)
  local damage = execute_strike(hero, goblin_2)
  local is_alive = (function(c)
    return (c.health > 0)
  end)
  local get_threat_level = (function(c)
    return c.health
  end)
  local entities = {hero, goblin_1, goblin_2}
  for _, entity in ipairs(entities) do
    entity:update(0.1)
  end
  local total_health = 0
  for _, entity in ipairs(entities) do
    if is_alive(entity) then
      total_health = total_health + get_threat_level(entity)
    end
  end
end

