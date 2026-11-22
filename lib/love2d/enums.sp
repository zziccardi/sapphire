// Sapphire Love2D bindings -- string enums

export {
  DrawMode,
  FilterMode,
  WrapMode,
  AlignMode,
  ArcMode,
  HintingMode,
  KeyCode,
  GamepadButton,
  GamepadAxis,
}

enum DrawMode {
  Fill = "fill",
  Line = "line",
}

enum FilterMode {
  Linear = "linear",
  Nearest = "nearest",
}

enum WrapMode {
  Clamp = "clamp",
  Repeat = "repeat",
  MirroredRepeat = "mirroredrepeat",
}

enum AlignMode {
  Left = "left",
  Center = "center",
  Right = "right",
  Justify = "justify",
}

enum ArcMode {
  Pie = "pie",
  Open = "open",
  Closed = "closed",
}

enum HintingMode {
  Normal = "normal",
  Light = "light",
  Mono = "mono",
  None = "none",
}

enum KeyCode {
  Space = "space",
  Escape = "escape",
  Return = "return",
  Tab = "tab",
  LShift = "lshift",
  RShift = "rshift",
  Up = "up",
  Down = "down",
  Left = "left",
  Right = "right",
  W = "w",
  A = "a",
  S = "s",
  D = "d",
}

enum GamepadButton {
  A = "a",
  B = "b",
  X = "x",
  Y = "y",
  Back = "back",
  Guide = "guide",
  Start = "start",
  LeftStick = "leftstick",
  RightStick = "rightstick",
  LeftShoulder = "leftshoulder",
  RightShoulder = "rightshoulder",
  DPadUp = "dpup",
  DPadDown = "dpdown",
  DPadLeft = "dpleft",
  DPadRight = "dpright",
}

enum GamepadAxis {
  LeftX = "leftx",
  LeftY = "lefty",
  RightX = "rightx",
  RightY = "righty",
  TriggerLeft = "triggerleft",
  TriggerRight = "triggerright",
}
