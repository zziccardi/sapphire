/*
 * Sample Sapphire program demonstrating Love2D game-engine interoperation.
 *
 * Demonstrates:
 * - `@extern struct` and `@extern trait` for type-safe external API
     declarations
 * - `@export("love.update")` and `@export("love.draw")` for registering global
     engine callbacks
 * - Object update and rendering logic targeting Love2D
 */

// 1. External Love2D API declarations
@extern
struct LoveGraphics;

@extern
struct LoveKeyboard;

@extern
trait LoveGraphics {
  static func setColor(r: float, g: float, b: float);
  static func rectangle(mode: String, x: float, y: float, w: float, h: float);
  static func clear(r: float, g: float, b: float);
}

@extern
trait LoveKeyboard {
  static func isDown(key: String): bool;
}

// 2. Sapphire game entity
struct Player {
  var x: float;
  var y: float;
  var speed: float;
}

impl Player {
  func update(dt: float) {
    if LoveKeyboard.isDown(key = "right") {
      self.x += self.speed * dt;
    }
    if LoveKeyboard.isDown(key = "left") {
      self.x -= self.speed * dt;
    }
  }

  func draw() {
    LoveGraphics.setColor(r = 0.2, g = 0.8, b = 0.4);
    LoveGraphics.rectangle(mode = "fill", x = self.x, y = self.y, w = 40.0,
                           h = 40.0);
  }
}

var player = Player { x = 100.0, y = 100.0, speed = 200.0 };

// 3. Exported Love2D callbacks
@export("love.update")
func game_update(dt: float) {
  player.update(dt);
}

@export("love.draw")
func game_draw() {
  LoveGraphics.clear(r = 0.1, g = 0.1, b = 0.1);
  player.draw();
}
