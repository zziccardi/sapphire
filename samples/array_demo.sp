// Sample Sapphire program demonstrating Array instance built-in methods:
// size(), empty(), map(), filter(), and reduce() (forward & reverse).

func main() {
  print("=== Sapphire Array Built-in Methods Demo ===");

  let numbers = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10];

  // 1. Array inspection methods
  let total_count = numbers.size();
  let is_blank = numbers.empty();
  let empty_arr: [int] = [];
  let is_empty_true = empty_arr.empty();

  print("Array size: " + total_count);
  print("Is numbers empty: " + String.from(is_blank));
  print("Is empty_arr empty: " + String.from(is_empty_true));

  // 2. Functional mapping (map)
  let doubled = numbers.map(x -> x * 2);
  print("Doubled elements:");
  for item in doubled {
    print("  item: " + item);
  }

  // 3. Functional filtering (filter)
  let evens = numbers.filter(x -> x % 2 == 0);
  print("Even elements:");
  for item in evens {
    print("  even: " + item);
  }

  // 4. Functional reduction (reduce)
  // Left-to-right forward reduction
  let sum = numbers.reduce(0, (acc, x) -> acc + x);
  print("Sum of elements: " + sum);

  // Right-to-left reverse reduction
  let words = ["world!", "beautiful", "Hello,"];
  let sentence = words.reduce("", (acc, w) -> acc + " " + w, reverse = true);
  print("Reversed sentence:" + sentence);

  // Named parameter reduction
  let product = numbers.reduce(initial = 1, fn = (acc, x) -> acc * x,
                               reverse = false);
  print("Product of elements: " + product);

  // 5. Method Chaining
  let sum_of_even_squares = numbers
      .filter(x -> x % 2 == 0)
      .map(x -> x * x)
      .reduce(0, (acc, x) -> acc + x);

  print("Sum of even squares (2^2 + 4^2 + 6^2 + 8^2 + 10^2): " +
        sum_of_even_squares);
  print("=== Demo Complete ===");
}

main();
