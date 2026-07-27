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


local Direction = {
  North = 0,
  East = 1,
  South = 2,
  West = 3
}


local function get_direction_name(dir)
  local _match_res_1 = nil
  local _subj_1 = dir
  if _subj_1 == Direction.North then
    _match_res_1 = "North"
  elseif _subj_1 == Direction.East then
    _match_res_1 = "East"
  elseif _subj_1 == Direction.South then
    _match_res_1 = "South"
  else
    _match_res_1 = "West"
  end
  local name = _match_res_1
  return name
end


local function handle_action(code)
  local _match_res_2 = nil
  local _subj_2 = code
  if _subj_2 == 200 then
    _match_res_2 = "OK"
  elseif _subj_2 == 404 then
    _match_res_2 = "Not Found"
  else
    local log_msg = "Unknown status code"
    _match_res_2 = log_msg
  end
  local result = _match_res_2
  return result
end


local function run_side_effects(dir)
  local _subj_3 = dir
  if _subj_3 == Direction.North then
    local step = 1
  else
    local step = 0
  end
end


local function main()
  local dir_name = get_direction_name(Direction.South)
  local status_str = handle_action(404)
  run_side_effects(Direction.East)
  if ((dir_name == "South") and (status_str == "Not Found")) then
    return 0
  end
  return 1
end


main()
main()
