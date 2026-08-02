// Demonstration of break and continue loop control statements in Sapphire

// 1. While loop demonstration
print("--- While Loop Demo ---");
var i = 0;
while i < 10 {
  i += 1;
  if i % 2 != 0 {
    continue;  // Skip odd numbers
  }
  if i > 8 {
    break;  // Exit loop when i exceeds 8
  }
  print(f"Even number: {i}");
}

// 2. For-in array iteration demonstration
print("--- Array Iteration Demo ---");
let numbers = [10, 15, 20, 25, 30, 35, 40];
for num in numbers {
  if num == 15 {
    continue;  // Skip 15
  }
  if num == 35 {
    break;  // Stop at 35
  }
  print(f"Number: {num}");
}

// 3. For-in map iteration demonstration
print("--- Map Iteration Demo ---");
let items = {"apple": 1, "banana": 2, "cherry": 3, "durian": 4};
for key, val in items {
  if val % 2 == 0 {
    continue;  // Skip even quantities
  }
  print(f"Item: {key} -> {val}");
}
