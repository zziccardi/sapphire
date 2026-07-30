// Sapphire Love2D bindings -- string enums

export {
  DrawMode,
  FilterMode,
  WrapMode,
  AlignMode,
  ArcMode,
  KeyCode,
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

enum KeyCode {
  Space = "space",
  Escape = "escape",
  Return = "return",
  Up = "up",
  Down = "down",
  Left = "left",
  Right = "right",
  W = "w",
  A = "a",
  S = "s",
  D = "d",
}
