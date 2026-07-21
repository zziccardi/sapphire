/*
 * Sample Sapphire program demonstrating top-level script execution
 * without requiring a main() function entry point.
 */

var count: int = 0;
let items = [10, 20, 30];

for item in items {
  count += item;
}

if count > 50 {
  // Script logic executed directly
}
