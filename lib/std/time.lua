-- Standard library time module for Sapphire (Lua target)

local time_mod = {}
local _os = os
local _has_socket, _socket = pcall(require, "socket")

function time_mod.now()
  if _G.love and _G.love.timer and _G.love.timer.getTime then
    return _G.love.timer.getTime()
  end
  if _has_socket and _socket and _socket.gettime then
    return _socket.gettime()
  end
  if _os and _os.time then
    return _os.time() * 1.0
  end
  return 0.0
end

function time_mod.sleep(seconds)
  if seconds == nil or seconds <= 0 then
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
