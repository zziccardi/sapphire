// Sapphire Love2D bindings -- keyboard subsystem

export {
  Keyboard,
};

trait Keyboard {
  func isDown(key: String): bool;
  func setKeyRepeat(enable: bool);
  func hasKeyRepeat(): bool;
}
