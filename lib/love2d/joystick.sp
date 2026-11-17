// Sapphire Love2D bindings -- joystick & gamepad subsystem

export {
  Joystick,
}

trait Joystick {
  func getName(self): String;
  func isGamepad(self): bool;
}
