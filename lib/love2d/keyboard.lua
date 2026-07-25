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



local _M = {}
_M.Keyboard = Keyboard
return _M
