// Demonstration of integer-backed enums in Sapphire

enum Direction {
  North,
  East,
  South,
  West,
}

enum HttpStatus {
  Ok = 200,
  Created = 201,
  BadRequest = 400,
  NotFound = 404,
  InternalError = 500,
}

func get_direction_code(dir: Direction): int {
  let raw_val: int = dir as int;
  return raw_val;
}

func main(): int {
  // Implicit type inference
  let current_dir = Direction.East;

  // Explicit type annotation
  let status: HttpStatus = HttpStatus.Ok;

  // Integer conversion / comparison
  let dir_code = get_direction_code(current_dir);
  let status_code: int = status as int;

  return dir_code + status_code;
}
