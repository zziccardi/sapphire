/*
 * Sample Sapphire program demonstrating Love2D game-engine interoperation.
 *
 * Demonstrates:
 * - Trait contracts for external API interfaces (`trait Graphics`,
     `trait Keyboard`)
 * - Engine container struct (`struct LoveEngine`)
 * - External host variable binding (`@extern var love: LoveEngine;`)
 * - Exported global callbacks (`@export("love.update")`,
     `@export("love.draw")`)
 */

// ==========================================
// 1. Enums
// ==========================================

enum DrawMode {
  Fill = "fill",
  Line = "line",
}

enum FilterMode {
  Linear = "linear",
  Nearest = "nearest",
}

// ==========================================
// 2. Resource handles & subsystem traits
// ==========================================

// TODO: Rename to just `Image`?
trait ImageHandle {
  func draw(self, x: float, y: float);

  @export("draw")
  func drawTransformed(self, x: float, y: float, r: float = 0.0,
                       sx: float = 1.0, sy: float = 1.0);

  func getWidth(self): float;
  func getHeight(self): float;
  func getDimensions(self): float, float;
}

trait Graphics {
  func clear(r: float = 0.0, g: float = 0.0, b: float = 0.0, a: float = 1.0);
  func setBackgroundColor(r: float, g: float, b: float, a: float = 1.0);

  @export("setColor")
  func setColorRGBA(r: float, g: float, b: float, a: float = 1.0);

  @export("rectangle")
  func rectangle(mode: DrawMode, x: float, y: float,
                 width: float, height: float);

  func newImage(path: String): ImageHandle;
  func print(text: String, x: float, y: float);
}

trait Keyboard {
  func isDown(key: String): bool;
}

trait Timer {
  func getFPS(): int;
}

// ===========================================
// 3. Engine container & global binding
// ===========================================

struct LoveEngine {
  var graphics: Graphics;
  var keyboard: Keyboard;
  var timer: Timer;
}

@extern
var love: LoveEngine;

// ==========================================
// 4. Game logic & callbacks
// ==========================================

var hero_img: ImageHandle?;
var hero_x: float = 100.0;
var hero_y: float = 100.0;
let speed:  float = 250.0;

@export("love.load")
func load() {
  love.graphics.setBackgroundColor(r = 0.1, g = 0.1, b = 0.15);
  hero_img = love.graphics.newImage("assets/hero.png");
}

@export("love.update")
func update(dt: float) {
  if love.keyboard.isDown("left") || love.keyboard.isDown("a") {
    hero_x -= speed * dt;
  }
  if love.keyboard.isDown("right") || love.keyboard.isDown("d") {
    hero_x += speed * dt;
  }
  if love.keyboard.isDown("up") || love.keyboard.isDown("w") {
    hero_y -= speed * dt;
  }
  if love.keyboard.isDown("down") || love.keyboard.isDown("s") {
    hero_y += speed * dt;
  }
}

@export("love.draw")
func draw() {
  love.graphics.clear(r = 0.1, g = 0.15, b = 0.2);

  // Draw background shape
  love.graphics.setColorRGBA(0.2, 0.7, 0.5);
  love.graphics.rectangle(mode = DrawMode.Fill, x = 50.0, y = 50.0,
                          width = 300.0, height = 150.0);

  // Draw hero handle
  if let img = hero_img {
    love.graphics.setColorRGBA(1.0, 1.0, 1.0);
    img.draw(x = hero_x, y = hero_y);
  }

  // Draw HUD information
  love.graphics.setColorRGBA(1.0, 1.0, 1.0);
  let fps_str = "FPS: " + love.timer.getFPS();
  love.graphics.print(text = fps_str, x = 10.0, y = 10.0);
}
