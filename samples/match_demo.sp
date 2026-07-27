// Demonstration of match expressions

enum Direction {
  North,
  East,
  South,
  West,
}

func get_direction_name(dir: Direction): String {
  return match dir {
    Direction.North -> "North",
    Direction.East -> "East",
    Direction.South -> {
      // Contrived to demonstrate `yield` requirement in blocks.
      yield "South";
    },
    // Default case to handle any other directions. The compiler will enforce
    // exhaustiveness.
    ... -> "West",
  };
}

func handle_action(code: int): String {
  return match code {
    200 -> "OK",
    404 -> "Not Found",
    ... -> {
      let log_msg = "Unknown status code";
      yield log_msg;
    },
  };
}

func run_side_effects(dir: Direction) {
  // Demonstrates that match expressions can be used for side-effect-only use
  // cases, not just returning values.
  // The result of the match expression is unused.
  match dir {
    Direction.North -> {
      let step = 1;
    },
    ... -> {
      let step = 0;
    },
  };
}

func main(): int {
  let dir_name = get_direction_name(Direction.South);
  let status_str = handle_action(code = 404);

  run_side_effects(Direction.East);

  if dir_name == "South" && status_str == "Not Found" {
    return 0;
  }

  return 1;
}

main();
