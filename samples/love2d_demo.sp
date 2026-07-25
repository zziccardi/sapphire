/*
 * Sample Sapphire program demonstrating Love2D game-engine interoperation.
 *
 * Uses Sapphire's modular Love2D library (`lib.love2d.*`).
 */

import lib.love2d.enums;
import lib.love2d.graphics;
import lib.love2d.love2d;

let love = love2d.love;

var hero_img: graphics.ImageHandle?;
var hero_x: float = 100.0;
var hero_y: float = 100.0;
let speed: float = 250.0;

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
  love.graphics.rectangle(mode = enums.DrawMode.Fill, x = 50.0, y = 50.0,
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
