// Sapphire Love2D bindings -- keyboard subsystem

import lib.love2d.enums;

export {
  Keyboard,
}

trait Keyboard {
  func isDown(key: enums.KeyCode): bool;
  func setKeyRepeat(enable: bool);
  func hasKeyRepeat(): bool;
}
