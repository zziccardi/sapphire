-- Standard library time module for Sapphire (Lua target)

local time_mod = {}
local _os = os
local _os_time = _os and _os.time or nil
local _has_socket, _socket = pcall(require, "socket")
local _socket_gettime = (_has_socket and _socket and _socket.gettime) or nil
local _love_epoch_offset = nil

if _socket_gettime then
  time_mod.now = _socket_gettime
else
  function time_mod.now()
    local love = _G.love
    if love and love.timer and love.timer.getTime and _os_time then
      local get_time = love.timer.getTime
      if _love_epoch_offset == nil then
        _love_epoch_offset = (_os_time() * 1.0) - get_time()
      end
      local offset = _love_epoch_offset
      time_mod.now = function()
        return offset + get_time()
      end
      return offset + get_time()
    end
    if _os_time then
      return _os_time() * 1.0
    end
    return 0.0
  end
end

function time_mod.sleep(seconds)
  if not (type(seconds) == "number" and seconds > 0) then
    return
  end
  if _G.love and _G.love.timer and _G.love.timer.sleep then
    _G.love.timer.sleep(seconds)
    return
  end
  if _has_socket and _socket and _socket.sleep then
    _socket.sleep(seconds)
    return
  end
  if _os and _os.execute then
    _os.execute("sleep " .. tostring(seconds))
  end
end

return time_mod
