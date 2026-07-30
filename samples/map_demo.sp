// Demonstration of map literal syntax and map indexing in Sapphire

enum Direction {
  North,
  South,
  East,
  West,
}

func main(): int {
  // 1. String-keyed map with trailing commas
  let scores = {
    "alice": 100,
    "bob": 95,
    "charlie": 90,
  };

  // 2. Int-keyed map
  let status_codes = {
    200: "OK",
    404: "Not Found",
    500: "Internal Error",
  };

  // 3. Enum-keyed map
  let direction_speeds = {
    Direction.North: 10,
    Direction.South: 5,
    Direction.East: 8,
    Direction.West: 8,
  };

  // Map access via indexing
  let alice_score: int = scores["alice"];
  let speed: int = direction_speeds[Direction.North];

  return alice_score + speed;
}
