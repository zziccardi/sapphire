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
  func draw(x: float, y: float);

  @export("draw")
  func drawTransformed(x: float, y: float, r: float = 0.0,
                       sx: float = 1.0, sy: float = 1.0);

  func getWidth(): float;
  func getHeight(): float;
  func getDimensions(): float, float;
  func setFilter(min: enums.FilterMode, mag: enums.FilterMode);
}

trait Canvas {
  func getWidth(): float;
  func getHeight(): float;
  func getDimensions(): float, float;
}

trait Font {
  func getHeight(): float;
  func getWidth(text: String): float;
}

trait Quad {
  func getViewport(): float, float, float, float;
  func setViewport(x: float, y: float, w: float, h: float);
}

trait Graphics {
  static func clear(r: float = 0.0, g: float = 0.0, b: float = 0.0, a: float = 1.0);
  static func setBackgroundColor(r: float, g: float, b: float, a: float = 1.0);
  static func present();

  @export("draw")
  static func drawImage(image: Image, quad: Quad? = none,
                        x: float = 0.0, y: float = 0.0, r: float = 0.0,
                        sx: float = 1.0, sy: float = 1.0);

  @export("draw")
  static func drawImageAt(image: Image,
                          x: float = 0.0, y: float = 0.0, r: float = 0.0,
                          sx: float = 1.0, sy: float = 1.0);

  @export("draw")
  static func drawCanvas(canvas: Canvas, quad: Quad? = none,
                         x: float = 0.0, y: float = 0.0, r: float = 0.0,
                         sx: float = 1.0, sy: float = 1.0);

  @export("draw")
  static func drawCanvasAt(canvas: Canvas,
                           x: float = 0.0, y: float = 0.0, r: float = 0.0,
                           sx: float = 1.0, sy: float = 1.0);

  static func getColor(): float, float, float, float;

  @export("setColor")
  static func setColorRgba(r: float, g: float, b: float, a: float = 1.0);

  static func rectangle(mode: enums.DrawMode, x: float, y: float,
                        width: float, height: float);

  @export("rectangle")
  static func rectangleRounded(mode: enums.DrawMode, x: float, y: float,
                               width: float, height: float,
                               rx: float, ry: float);

  static func circle(mode: enums.DrawMode, x: float, y: float, radius: float);
  static func line(x1: float, y1: float, x2: float, y2: float);
  static func print(text: String, x: float, y: float);
  static func printf(text: String, x: float, y: float, limit: float,
                     align: String = "left");

  static func newImage(path: String): Image;
  static func newCanvas(width: float = 0.0, height: float = 0.0): Canvas;
  static func newFont(path: String, size: int = 12): Font;
  static func newQuad(x: float, y: float, w: float, h: float,
                      sw: float, sh: float): Quad;

  static func setCanvas(canvas: Canvas? = none);
  static func setDefaultFilter(min_filter: enums.FilterMode,
                               mag_filter: enums.FilterMode);
  static func getFont(): Font;
  static func setFont(font: Font);

  static func getDimensions(): float, float;
  static func getWidth(): float;
  static func getHeight(): float;
}
