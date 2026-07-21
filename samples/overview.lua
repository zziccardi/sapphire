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


local MAX_PLAYERS = 100


local Position = {}
Position.__index = Position
function Position.new(kwargs, proto)
  kwargs = kwargs or {}
  local self
  self = setmetatable({}, Position)
  if proto == nil then
  end
  for k, v in pairs(kwargs) do
    self[k] = v
  end
  if Position._init_sapphire then
    Position._init_sapphire(self, kwargs)
  end
  return self
end

function Position:_init_sapphire(x, y)
  self.x = x
  self.y = y
end


local Entity = {}
Entity.__index = Entity
function Entity.new(kwargs, proto)
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
    Character._init_sapphire(self, kwargs)
  end
  return self
end

function Character:_init_sapphire(id, name, max_hp)
  self.id = id
  self.pos = Position.new({x = 0.0, y = 0.0})
  self.health = max_hp
  self.max_health = max_hp
  self.name = name
end

function Character:get_health_ratio()
  return (self.health / self.max_health)
end

function Character:heal(amount)
  self.health = self.health + amount
  if (self.health > self.max_health) then
    self.health = self.max_health
  end
end

function Character:take_damage(amount)
  self.health = self.health - amount
  if (self.health < 0) then
    self.health = 0
  else
    if (self.health > self.max_health) then
      self.health = self.max_health
    else
      -- pass
    end
  end
end


local function execute_attack(attacker, defender, is_critical)
  if is_critical == nil then is_critical = false end
  local base_damage = 15
  if is_critical then
    base_damage = base_damage * 2
  end
  defender:take_damage(base_damage)
  return base_damage
end


local function run_demo()
  local player_one = Character.new({id = 1, name = "Galahad"})
  local player_two = Character.new({id = 2, name = "Lancelot", max_hp = 120})
  local target_player = nil
  target_player = player_two
  local _val_active_target = target_player
  if _val_active_target ~= nil then
    local active_target = _val_active_target
    local damage_dealt = execute_attack(player_one, active_target, true)
  else
    -- pass
  end
  local prototype_enemy = Character.new({id = 99, name = "Goblin Minion", max_hp = 30})
  local active_clone = _clone_helper(prototype_enemy, function(self)
    self.health = 25
  end)
  local _val_parent = active_clone.__proto__
  if _val_parent ~= nil then
    local parent = _val_parent
    local name_ref = parent.name
  end
  local damage_multiplier = (function(x)
    return (x * 2)
  end)
  local sum_func = (function(x, y)
    return (x + y)
  end)
  local base_score = (-50)
  local positive_adjustment = (+10)
  local coord_x = 10
  local mixed_result = (coord_x + positive_adjustment)
  local scores = {10, 20, 30}
  local first_score = scores[1]
  local timer = 3
  while (timer > 0) do
    timer = timer - 1
  end
  for _, score in ipairs(scores) do
    local final_score = damage_multiplier(score)
  end
  for _, score in ipairs(scores) do
    score = score + 5
  end
end


run_demo()
