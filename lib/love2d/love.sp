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
  var graphics: Graphics;
  var keyboard: Keyboard;
  var mouse: Mouse;
  var timer: Timer;
}

@extern("love")
var love: LoveEngine;
