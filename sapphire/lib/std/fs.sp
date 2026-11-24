/*
 * Standard library filesystem module for Sapphire.
 * Provides basic file read, write, and path existence query operations.
 */

export {
  read_file,
  write_file,
  remove_file,
  exists,
}

func read_file(path: String): String? {
  return none;
}

func write_file(path: String, content: String): bool {
  return false;
}

func remove_file(path: String): bool {
  return false;
}

func exists(path: String): bool {
  return false;
}
