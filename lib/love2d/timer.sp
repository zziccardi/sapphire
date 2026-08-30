// Sapphire Love2D bindings -- timer subsystem

export {
  Timer,
}

trait Timer {
  static func getDelta(): float;
  static func getFPS(): int;
  static func getTime(): float;
  static func sleep(seconds: float);
  static func step(): float;
}
