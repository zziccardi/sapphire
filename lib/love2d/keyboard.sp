// Sapphire Love2D bindings -- keyboard subsystem

trait Keyboard {
  func isDown(key: String): bool;
  func setKeyRepeat(enable: bool);
  func hasKeyRepeat(): bool;
}
