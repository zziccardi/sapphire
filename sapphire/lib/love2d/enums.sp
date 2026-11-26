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
  // Navigation & editing
  Space = "space",
  Escape = "escape",
  Return = "return",
  Tab = "tab",
  Backspace = "backspace",
  Delete = "delete",
  Insert = "insert",
  Home = "home",
  End = "end",
  PageUp = "pageup",
  PageDown = "pagedown",
  Up = "up",
  Down = "down",
  Left = "left",
  Right = "right",

  // Modifiers & locks
  LShift = "lshift",
  RShift = "rshift",
  LCtrl = "lctrl",
  RCtrl = "rctrl",
  LAlt = "lalt",
  RAlt = "ralt",
  LGui = "lgui",
  RGui = "rgui",
  CapsLock = "capslock",
  NumLock = "numlock",
  ScrollLock = "scrolllock",

  // Letters
  A = "a",
  B = "b",
  C = "c",
  D = "d",
  E = "e",
  F = "f",
  G = "g",
  H = "h",
  I = "i",
  J = "j",
  K = "k",
  L = "l",
  M = "m",
  N = "n",
  O = "o",
  P = "p",
  Q = "q",
  R = "r",
  S = "s",
  T = "t",
  U = "u",
  V = "v",
  W = "w",
  X = "x",
  Y = "y",
  Z = "z",

  // Number row
  Num0 = "0",
  Num1 = "1",
  Num2 = "2",
  Num3 = "3",
  Num4 = "4",
  Num5 = "5",
  Num6 = "6",
  Num7 = "7",
  Num8 = "8",
  Num9 = "9",

  // Function keys
  F1 = "f1",
  F2 = "f2",
  F3 = "f3",
  F4 = "f4",
  F5 = "f5",
  F6 = "f6",
  F7 = "f7",
  F8 = "f8",
  F9 = "f9",
  F10 = "f10",
  F11 = "f11",
  F12 = "f12",

  // Punctuation & symbols
  Minus = "-",
  Equals = "=",
  LeftBracket = "[",
  RightBracket = "]",
  Backslash = "\\",
  Semicolon = ";",
  Apostrophe = "'",
  Grave = "`",
  Comma = ",",
  Period = ".",
  Slash = "/",

  // Numpad
  Kp0 = "kp0",
  Kp1 = "kp1",
  Kp2 = "kp2",
  Kp3 = "kp3",
  Kp4 = "kp4",
  Kp5 = "kp5",
  Kp6 = "kp6",
  Kp7 = "kp7",
  Kp8 = "kp8",
  Kp9 = "kp9",
  KpDecimal = "kp.",
  KpDivide = "kp/",
  KpMultiply = "kp*",
  KpMinus = "kp-",
  KpPlus = "kp+",
  KpEnter = "kpenter",
  KpEquals = "kp=",

  // Misc
  PrintScreen = "printscreen",
  Pause = "pause",
  Menu = "menu",
  Application = "application",
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
