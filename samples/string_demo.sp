// Demonstration of built-in String methods in Sapphire

func main() {
  let greeting = "  Hello Sapphire!  ";
  
  // 1. size() & empty()
  print("Size: " + greeting.size());
  print("Is empty: " + greeting.empty());
  
  // 2. strip(), lower(), upper()
  let clean = greeting.strip();
  print("Cleaned: '" + clean + "'");
  print("Lower: " + clean.lower());
  print("Upper: " + clean.upper());
  
  // 3. contains()
  let has_sapphire = clean.contains("Sapphire");
  print("Contains 'Sapphire': " + has_sapphire);
  
  // 4. find() with forward and reverse options
  if let pos ?= clean.find("p") {
    print("First 'p' index: " + pos);
  }
  
  let last_p = clean.find("p", reverse = true);
  if let rev_pos ?= last_p {
    print("Last 'p' index: " + rev_pos);
  }
  
  let missing = clean.find("xyz");
  if missing == none {
    print("Missing substring returned none as expected");
  }

  // 5. split()
  let fruits_csv = "apple,banana,cherry";
  let parts = fruits_csv.split(",");
  for item in parts {
    print("Fruit: " + item);
  }

  let words = "one two three".split();
  for word in words {
    print("Word: " + word);
  }
}

main();
