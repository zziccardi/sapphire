// Sapphire Love2D bindings -- mouse subsystem

export {
  Cursor,
  Mouse,
}

trait Cursor {
  func getType(self): String;
}

trait Mouse {
  static func getPosition(): float, float;
  static func getX(): float;
  static func getY(): float;
  static func isDown(button: int): bool;
  static func setVisible(visible: bool);
  static func isVisible(): bool;
  static func newCursor(filename: String, hotx: int = 0, hoty: int = 0): Cursor;
  static func setCursor(cursor: Cursor);
}
