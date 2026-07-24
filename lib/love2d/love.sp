// Sapphire Love2D master binding header

// TODO: Add proper module support to Sapphire.
import "lib/love2d/enums.sp";
import "lib/love2d/graphics.sp";
import "lib/love2d/keyboard.sp";
import "lib/love2d/mouse.sp";
import "lib/love2d/timer.sp";

struct LoveEngine {
  var graphics: Graphics;
  var keyboard: Keyboard;
  var mouse: Mouse;
  var timer: Timer;
}

@extern("love")
var love: LoveEngine;
