// Sapphire Love2D bindings -- mouse subsystem

export {
  CursorHandle,
  Mouse,
};

trait CursorHandle {
  func getType(self): String;
}

trait Mouse {
  func getPosition(): float, float;
  func getX(): float;
  func getY(): float;
  func isDown(button: int): bool;
  func setVisible(visible: bool);
  func isVisible(): bool;
  func newCursor(filename: String, hotx: int = 0, hoty: int = 0): CursorHandle;
  func setCursor(cursor: CursorHandle);
}
