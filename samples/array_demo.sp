// Sample Sapphire program demonstrating Array instance built-in methods:
// size(), empty(), contains(), map(), filter(), reduce(), reverse(), sort(), join(),
// push(), pop(), insert(), remove(), and clear().

func main() {
  print("=== Sapphire Array Built-in Methods Demo ===");

  let numbers = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10];

  // 1. Array inspection & querying
  let total_count = numbers.size();
  let is_blank = numbers.empty();
  let empty_arr: [int] = [];
  let is_empty_true = empty_arr.empty();
  let has_five = numbers.contains(5);

  print("Array size: " + total_count);
  print("Is numbers empty: " + String.from(is_blank));
  print("Is empty_arr empty: " + String.from(is_empty_true));
  print("Contains 5: " + String.from(has_five));

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
  let sum = numbers.reduce(0, (acc, x) -> acc + x);
  print("Sum of elements: " + sum);

  let words = ["world!", "beautiful", "Hello,"];
  let sentence = words.reduce("", (acc, w) -> acc + " " + w, reverse = true);
  print("Reversed sentence:" + sentence);

  // 5. Query & Transformation: reverse, sort, join
  let rev_nums = numbers.reverse();
  print("Reversed numbers size: " + rev_nums.size());

  let unsorted = [3, 1, 4, 1, 5, 9, 2, 6];
  let sorted_asc = unsorted.sort();
  let sorted_desc = unsorted.sort(reverse = true);

  let joined_str = words.join(" ");
  print("Joined words: " + joined_str);

  // 6. Dynamic Array Mutation (var [T])
  var mut_arr = [10, 20];
  let pushed_val = mut_arr.push(30);
  print("Pushed val: " + pushed_val + ", array size: " + mut_arr.size());

  let inserted_val = mut_arr.insert(1, 15);
  print("Inserted val: " + inserted_val);

  if let popped ?= mut_arr.pop() {
    print("Popped val: " + popped);
  }

  if let removed ?= mut_arr.remove(1) {
    print("Removed val at index 1: " + removed);
  }

  mut_arr.clear();
  print("After clear, size: " + mut_arr.size());

  // 7. Method Chaining
  let sum_of_even_squares = numbers
      .filter(x -> x % 2 == 0)
      .map(x -> x * x)
      .reduce(0, (acc, x) -> acc + x);

  print("Sum of even squares: " + sum_of_even_squares);
  print("=== Demo Complete ===");
}

main();
