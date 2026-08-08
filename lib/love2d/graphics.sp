// Sapphire Love2D bindings -- graphics subsystem

import lib.love2d.enums;

export {
  Canvas,
  Color,
  Font,
  Graphics,
  Image,
  Quad,
}

struct Color {
  var r: float;
  var g: float;
  var b: float;
  var a: float = 1.0;
}

trait Image {
  func draw(self, x: float, y: float);

  @export("draw")
  func drawTransformed(self, x: float, y: float, r: float = 0.0,
                       sx: float = 1.0, sy: float = 1.0);

  func getWidth(self): float;
  func getHeight(self): float;
  func getDimensions(self): float, float;
  func setFilter(self, min: enums.FilterMode, mag: enums.FilterMode);
}

trait Canvas {
  func getWidth(self): float;
  func getHeight(self): float;
  func getDimensions(self): float, float;
}

trait Font {
  func getHeight(self): float;
  func getWidth(self, text: String): float;
}

trait Quad {
  func getViewport(self): float, float, float, float;
  func setViewport(self, x: float, y: float, w: float, h: float);
}

trait Graphics {
  func clear(r: float = 0.0, g: float = 0.0, b: float = 0.0, a: float = 1.0);
  func setBackgroundColor(r: float, g: float, b: float, a: float = 1.0);
  func present();

  @export("setColor")
  func setColorRgba(r: float, g: float, b: float, a: float = 1.0);

  func rectangle(mode: enums.DrawMode, x: float, y: float,
                 width: float, height: float);

  @export("rectangle")
  func rectangleRounded(mode: enums.DrawMode, x: float, y: float,
                        width: float, height: float,
                        rx: float, ry: float);

  func circle(mode: enums.DrawMode, x: float, y: float, radius: float);
  func line(x1: float, y1: float, x2: float, y2: float);
  func print(text: String, x: float, y: float);

  func newImage(path: String): Image;
  func newCanvas(width: float = 0.0, height: float = 0.0): Canvas;
  func newFont(path: String, size: int = 12): Font;
  func newQuad(x: float, y: float, w: float, h: float,
               sw: float, sh: float): Quad;

  func setCanvas(canvas: Canvas? = none);
  func setFont(font: Font);
}
