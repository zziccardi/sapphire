// Sapphire Love2D bindings -- mouse subsystem

export {
  Cursor,
  Mouse,
}

trait Cursor {
  func getType(self): String;
}

trait Mouse {
  func getPosition(): float, float;
  func getX(): float;
  func getY(): float;
  func isDown(button: int): bool;
  func setVisible(visible: bool);
  func isVisible(): bool;
  func newCursor(filename: String, hotx: int = 0, hoty: int = 0): Cursor;
  func setCursor(cursor: Cursor);
}
