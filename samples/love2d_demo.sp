/*
 * Sample Sapphire program demonstrating Love2D game-engine interoperation.
 *
 * Demonstrates:
 * - Opaque resource handles (`struct Image {}`)
 * - Trait contracts for external API interfaces (`trait Graphics`,
     `trait Keyboard`)
 * - Engine container struct (`struct LoveEngine`)
 * - External host variable binding (`@extern("love") var love: LoveEngine;`)
 * - Exported global callbacks (`@export("love.update")`,
     `@export("love.draw")`)
 */

// 1. Opaque resource handle
struct Image {}

// 2. Trait contracts (interface method signatures without implementations)
trait Graphics {
  func setColor(r: float, g: float, b: float);
  func rectangle(mode: String, x: float, y: float, w: float, h: float);
  func clear(r: float, g: float, b: float);
  func newImage(path: String): Image;
}

trait Keyboard {
  func isDown(key: String): bool;
}

// 3. Engine container struct satisfying normal Sapphire rules
struct LoveEngine {
  var graphics: Graphics;
  var keyboard: Keyboard;
}

// 4. Global external host variable binding
@extern("love")
var love: LoveEngine;

// 5. Sapphire game entity
struct Player {
  var x: float;
  var y: float;
  var speed: float;
}

impl Player {
  func update(dt: float) {
    if love.keyboard.isDown(key = "right") {
      self.x += self.speed * dt;
    }
    if love.keyboard.isDown(key = "left") {
      self.x -= self.speed * dt;
    }
  }

  func draw() {
    love.graphics.setColor(r = 0.2, g = 0.8, b = 0.4);
    love.graphics.rectangle(mode = "fill", x = self.x, y = self.y,
                            w = 40.0, h = 40.0);
  }
}

var player = Player { x = 100.0, y = 100.0, speed = 200.0 };

// 6. Exported Love2D callbacks
@export("love.update")
func update(dt: float) {
  player.update(dt);
}

@export("love.draw")
func draw() {
  love.graphics.clear(r = 0.1, g = 0.1, b = 0.1);
  player.draw();
}
