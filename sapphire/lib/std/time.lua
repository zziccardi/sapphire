-- Standard library time module for Sapphire (Lua target)

local time_mod = {}
local _os = os
local _has_socket, _socket = pcall(require, "socket")
local _love_epoch_offset = nil

function time_mod.now()
  if _has_socket and _socket and _socket.gettime then
    return _socket.gettime()
  end
  if _G.love and _G.love.timer and _G.love.timer.getTime and _os and _os.time then
    if _love_epoch_offset == nil then
      _love_epoch_offset = (_os.time() * 1.0) - _G.love.timer.getTime()
    end
    return _love_epoch_offset + _G.love.timer.getTime()
  end
  if _os and _os.time then
    return _os.time() * 1.0
  end
  return 0.0
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
