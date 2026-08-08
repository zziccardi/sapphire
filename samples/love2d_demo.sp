/*
 * Sample Sapphire program demonstrating Love2D game-engine interoperation.
 *
 * Uses Sapphire's modular Love2D library (`lib.love2d.*`).
 */

import lib.love2d.enums;
import lib.love2d.graphics;
import lib.love2d.love2d;

let love = love2d.love;

var hero_x: float = 200.0;
var hero_y: float = 200.0;
let speed: float = 250.0;

@export("love.load")
func load() {
  love.graphics.setBackgroundColor(r = 0.1, g = 0.1, b = 0.15);
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

  // Draw background playing arena
  love.graphics.setColorRgba(0.2, 0.7, 0.5);
  love.graphics.rectangle(mode = enums.DrawMode.Fill, x = 50.0, y = 50.0,
                          width = 700.0, height = 500.0);

  // Draw mock hero character procedurally (in practice use image asset)
  love.graphics.setColorRgba(0.9, 0.3, 0.4);
  love.graphics.circle(mode = enums.DrawMode.Fill, x = hero_x, y = hero_y,
                       radius = 24.0);

  // Draw hero outline
  love.graphics.setColorRgba(1.0, 1.0, 1.0);
  love.graphics.circle(mode = enums.DrawMode.Line, x = hero_x, y = hero_y,
                       radius = 24.0);

  // Draw HUD information & Controls
  love.graphics.setColorRgba(1.0, 1.0, 1.0);
  let fps_str = "FPS: " + love.timer.getFPS();
  love.graphics.print(text = fps_str, x = 10.0, y = 10.0);
  love.graphics.print(text = "Move with WASD or Arrow Keys",
                      x = 10.0, y = 30.0);
}
