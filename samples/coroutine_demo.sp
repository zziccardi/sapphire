// Demonstration of first-class Coroutines in Sapphire

func fibonacci(count: int): Coroutine<int> {
  var a = 0;
  var b = 1;
  for i in range(count) {
    yield a;
    let next = a + b;
    a = b;
    b = next;
  }
}

func cutscene(): Coroutine<void> {
  print("Step 1: NPC waves");
  yield;
  print("Step 2: NPC walks across the room");
  yield;
  print("Step 3: NPC speaks to the hero");
}

func main() {
  print("=== Value Generator Coroutine ===");
  var fib = fibonacci(6);
  while !fib.is_done() {
    if let val ?= fib.step() {
      print(f"Fibonacci: {val}");
    }
  }

  print("\n=== Frame Flow Coroutine ===");
  var scene = cutscene();
  while !scene.is_done() {
    scene.step();
  }

  print("\n=== Coroutine Reset ===");
  fib.reset();
  if let first ?= fib.step() {
    print(f"First fib after reset: {first}");
  }
}
