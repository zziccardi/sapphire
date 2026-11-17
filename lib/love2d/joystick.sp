// Sapphire Love2D bindings -- joystick & gamepad subsystem

export {
  Joystick,
}

trait Joystick {
  func getName(): String;
  func isGamepad(): bool;
}
