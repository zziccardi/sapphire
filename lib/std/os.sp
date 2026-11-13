/*
 * Standard library OS module for Sapphire.
 * Provides process execution and operating system environment primitives.
 */

export {
  args,
  get_env,
  set_env,
  exit,
}

func args(): [String] {
  return [];
}

func get_env(name: String): String? {
  return none;
}

func set_env(name: String, value: String) {}

func exit(code: int = 0) {}
