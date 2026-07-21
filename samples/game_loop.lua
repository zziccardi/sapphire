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


local GameState = {
  Menu = 0,
  Playing = 1,
  GameOver = 2
}


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
  return self
end

function Vector2D:translate(dx, dy)
  self.x = self.x + dx
  self.y = self.y + dy
end

function Vector2D:get_distance_to(other)
  local dx = (self.x - other.x)
  local dy = (self.y - other.y)
  local abs_dx = dx
  local abs_dy = dy
  if (abs_dx < 0.0) then
    abs_dx = (-abs_dx)
  end
  if (abs_dy < 0.0) then
    abs_dy = (-abs_dy)
  end
  return (abs_dx + abs_dy)
end




local GameObject = {}
GameObject.__index = GameObject
function GameObject.new(kwargs, proto)
  kwargs = kwargs or {}
  local self
  self = _create_proto_object(proto, GameObject)
  if proto == nil then
    self.active = true
  end
  for k, v in pairs(kwargs) do
    self[k] = v
  end
  return self
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
  if Entity._init_sapphire then
    Entity._init_sapphire(self, (kwargs['id'] ~= nil and kwargs['id'] or kwargs[1]), (kwargs['name'] ~= nil and kwargs['name'] or kwargs[2]), (kwargs['x'] ~= nil and kwargs['x'] or kwargs[3]), (kwargs['y'] ~= nil and kwargs['y'] or kwargs[4]), (kwargs['hp'] ~= nil and kwargs['hp'] or kwargs[5]), (kwargs['spd'] ~= nil and kwargs['spd'] or kwargs[6]))
  end
  return self
end

function Entity:_init_sapphire(id, name, x, y, hp, spd)
  if hp == nil then hp = 100 end
  if spd == nil then spd = 5.0 end
  self.id = id
  self.position = Vector2D.new({x = x, y = y})
  self.health = hp
  self.speed = spd
  self.name = name
end

function Entity:update(dt)
  if (self.health <= 0) then
    self.active = false
    return
  end
  self.position:translate((self.speed * dt), 0.0)
end

function Entity:draw()
  if self.active then
    -- pass
  end
end


local GameEngine = {}
GameEngine.__index = GameEngine
function GameEngine.new(kwargs, proto)
  kwargs = kwargs or {}
  local self
  self = setmetatable({}, GameEngine)
  if proto == nil then
  end
  for k, v in pairs(kwargs) do
    self[k] = v
  end
  if GameEngine._init_sapphire then
    GameEngine._init_sapphire(self)
  end
  return self
end

function GameEngine:_init_sapphire()
  self.state = GameState.Menu
  self.score = 0
  self.frame_count = 0
  self.player = Entity.new({id = 1, name = "Hero", x = 10.0, y = 20.0, hp = 100, spd = 12.0})
  self.base_enemy = Entity.new({id = 0, name = "Slime", x = 100.0, y = 20.0, hp = 30, spd = (-4.0)})
  self.active_enemy = nil
  self.game_over_timer = 0.0
end

function GameEngine:load()
  self.state = GameState.Playing
  self.score = 0
  self.frame_count = 0
  self.game_over_timer = 0.0
  self.active_enemy = _clone_helper(self.base_enemy, function(self)
    self.id = 101
    self.position = Vector2D.new({x = 80.0, y = 20.0})
  end)
end

function GameEngine:update(dt)
  self.frame_count = self.frame_count + 1
  if (self.state == GameState.Playing) then
    self.player:update(dt)
    local _val_enemy = self.active_enemy
    if _val_enemy ~= nil then
      local enemy = _val_enemy
      enemy:update(dt)
      local dist = self.player.position:get_distance_to(enemy.position)
      if (dist < 15.0) then
        enemy.health = enemy.health - 30
        self.score = self.score + 50
        if (enemy.health <= 0) then
          self.active_enemy = nil
          self.state = GameState.GameOver
        end
      end
    else
      self.active_enemy = _clone_helper(self.base_enemy, function(self)
        self.id = 102
        self.position = Vector2D.new({x = 120.0, y = 20.0})
        self.health = 50
      end)
    end
  else
    if (self.state == GameState.GameOver) then
      self.game_over_timer = self.game_over_timer + dt
      if (self.game_over_timer >= 3.0) then
        self:load()
      end
    end
  end
end

function GameEngine:draw()
  if (self.state == GameState.Menu) then
    -- pass
  else
    if (self.state == GameState.Playing) then
      self.player:draw()
      local _val_enemy = self.active_enemy
      if _val_enemy ~= nil then
        local enemy = _val_enemy
        enemy:draw()
      end
    else
      if (self.state == GameState.GameOver) then
        -- pass
      end
    end
  end
end



local function run_game_loop()
  local engine = GameEngine.new({})
  engine:load()
  local frame_deltas = {0.016, 0.016, 0.016, 0.016, 0.016}
  for _, dt in ipairs(frame_deltas) do
    engine:update(dt)
    engine:draw()
  end
end


run_game_loop()
