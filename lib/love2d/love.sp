// Sapphire Love2D master binding header

import lib.love2d.enums;
import lib.love2d.graphics;
import lib.love2d.keyboard;
import lib.love2d.mouse;
import lib.love2d.timer;

export {
  LoveEngine,
  love,
};

struct LoveEngine {
  var graphics: graphics.Graphics;
  var keyboard: keyboard.Keyboard;
  var mouse: mouse.Mouse;
  var timer: timer.Timer;
}

@extern
var love: LoveEngine;
