// Sapphire Love2D bindings -- timer subsystem

trait Timer {
  func getDelta(): float;
  func getFPS(): int;
  func getTime(): float;
  func sleep(seconds: float);
  func step(): float;
}
