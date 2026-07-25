// Sapphire Love2D bindings -- graphics subsystem

import lib.love2d.enums;

export {
  Color,
  ImageHandle,
  CanvasHandle,
  FontHandle,
  QuadHandle,
};

struct Color {
  var r: float;
  var g: float;
  var b: float;
  var a: float = 1.0;
}

trait ImageHandle {
  func draw(self, x: float, y: float);

  @export("draw")
  func drawTransformed(self, x: float, y: float, r: float = 0.0,
                       sx: float = 1.0, sy: float = 1.0);

  func getWidth(self): float;
  func getHeight(self): float;
  func getDimensions(self): float, float;
  func setFilter(self, min: enums.FilterMode, mag: enums.FilterMode);
}

trait CanvasHandle {
  func getWidth(self): float;
  func getHeight(self): float;
  func getDimensions(self): float, float;
}

trait FontHandle {
  func getHeight(self): float;
  func getWidth(self, text: String): float;
}

trait QuadHandle {
  func getViewport(self): float, float, float, float;
  func setViewport(self, x: float, y: float, w: float, h: float);
}

trait Graphics {
  func clear(r: float = 0.0, g: float = 0.0, b: float = 0.0, a: float = 1.0);
  func setBackgroundColor(r: float, g: float, b: float, a: float = 1.0);
  func present();

  @export("setColor")
  func setColorRGBA(r: float, g: float, b: float, a: float = 1.0);

  @export("rectangle")
  func rectangle(mode: enums.DrawMode, x: float, y: float,
                 width: float, height: float);

  @export("rectangle")
  func rectangleRounded(mode: enums.DrawMode, x: float, y: float,
                        width: float, height: float,
                        rx: float, ry: float);

  func circle(mode: enums.DrawMode, x: float, y: float, radius: float);
  func line(x1: float, y1: float, x2: float, y2: float);
  func print(text: String, x: float, y: float);

  func newImage(path: String): ImageHandle;
  func newCanvas(width: float = 0.0, height: float = 0.0): CanvasHandle;
  func newFont(path: String, size: int = 12): FontHandle;
  func newQuad(x: float, y: float, w: float, h: float,
               sw: float, sh: float): QuadHandle;

  func setCanvas(canvas: CanvasHandle? = none);
  func setFont(font: FontHandle);
}
