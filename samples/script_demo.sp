/*
 * Sample Sapphire program demonstrating module entry with func main()
 * and module-level compile-time constant expressions.
 */

let ITEMS = [10, 20, 30];

func main() {
  var count = 0;
  for item in ITEMS {
    count += item;
  }

  if count > 50 {
    print("Items processed successfully");
  }
}
