// Sapphire Love2D bindings -- keyboard subsystem

import lib.love2d.enums;

export {
  Keyboard,
}

trait Keyboard {
  static func isDown(key: enums.KeyCode): bool;
  static func setKeyRepeat(enable: bool);
  static func hasKeyRepeat(): bool;
}
