// Demonstration of built-in String methods in Sapphire

func main() {
  let greeting = "  Hello Sapphire!  ";

  // 1. size() & empty()
  print(f"Size: {greeting.size()}");
  print(f"Is empty: {greeting.empty()}");

  // 2. strip(), lower(), upper()
  let clean = greeting.strip();
  print(f"Cleaned: '{clean}'");
  print(f"Lower: {clean.lower()}");
  print(f"Upper: {clean.upper()}");

  // 3. contains()
  let has_sapphire = clean.contains("Sapphire");
  print(f"Contains 'Sapphire': {has_sapphire}");

  // 4. find() with forward and reverse options
  if let pos ?= clean.find("p") {
    print(f"First 'p' index: {pos}");
  }

  let last_p = clean.find("p", reverse = true);
  if let rev_pos ?= last_p {
    print(f"Last 'p' index: {rev_pos}");
  }

  let missing = clean.find("xyz");
  if missing == none {
    print("Missing substring returned none as expected");
  }

  // 5. split()
  let fruits_csv = "apple,banana,cherry";
  let parts = fruits_csv.split(",");
  for item in parts {
    print(f"Fruit: {item}");
  }

  let words = "one two three".split();
  for word in words {
    print(f"Word: {word}");
  }
}
