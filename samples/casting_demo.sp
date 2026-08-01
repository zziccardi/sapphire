// Samples: Infallible Static Casting & String Conversion Methods in Sapphire

enum Direction {
  North = 1,
  South = 2,
}

enum LogLevel {
  Info = "INFO",
  Warn = "WARN",
  Error = "ERROR",
}

// 1. Guaranteed Static Type Casting (`as` operator)
let raw_int: int = 42;
let as_float: float = raw_int as float;

let pi_float: float = 3.14159;
let as_int: int = pi_float as int;

let is_valid: bool = true;
let bool_as_int: int = is_valid as int;

let dir: Direction = Direction.North;
let dir_code: int = dir as int;

print("--- 1. Guaranteed Static Casts (`as`) ---");
print("int -> float: " + String.from(as_float));
print("float -> int: " + String.from(as_int));
print("bool -> int: " + String.from(bool_as_int));
print("enum -> int: " + String.from(dir_code));


// 2. String Creation Intrinsic (`String.from`)
print("\n--- 2. String Creation (`String.from`) ---");
let str_int = String.from(100);
let str_float = String.from(2.718);
let str_bool = String.from(false);
let str_enum = String.from(Direction.South);

print("String.from(100): " + str_int);
print("String.from(2.718): " + str_float);
print("String.from(false): " + str_bool);
print("String.from(Direction.South): " + str_enum);


// 3. Fallible String Parsing Instance Methods (`.to_int()`, `.to_float()`, `.to_bool()`)
print("\n--- 3. Fallible String Parsing Methods ---");

// Parsing Integer with default (base 10) and custom radix
if let port ?= "8080".to_int() {
  print("Parsed integer: " + String.from(port));
}

if let hex_val ?= "FF".to_int(radix = 16) {
  print("Parsed hex 'FF': " + String.from(hex_val));
}

// Parsing Float
let score_str = "98.5";
let score = score_str.to_float() ?? 0.0;
print("Parsed float score: " + String.from(score));

// Parsing Boolean
if let active ?= "true".to_bool() {
  print("Parsed bool: " + String.from(active));
}

// Invalid String Parsing (returns none)
let invalid_num = "not_a_number".to_int();
if invalid_num == none {
  print("Invalid number string correctly evaluated to none!");
}


// 4. Fallible Enum Conversions (`EnumName.from(val)`)
print("\n--- 4. Fallible Enum Conversions (`EnumName.from`) ---");

if let d1 ?= Direction.from(1) {
  print("Direction.from(1): " + String.from(d1));
}

if let d2 ?= Direction.from("South") {
  print("Direction.from(\"South\"): " + String.from(d2));
}

if let l1 ?= LogLevel.from("INFO") {
  print("LogLevel.from(\"INFO\"): " + l1);
}

if let l2 ?= LogLevel.from("Warn") {
  print("LogLevel.from(\"Warn\"): " + l2);
}

if Direction.from(999) == none {
  print("Direction.from(999) correctly evaluated to none!");
}
