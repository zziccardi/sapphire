// Map Built-in Instance Methods Demo

func main() {
  print("=== Sapphire Map Built-in Methods Demo ===");

  let scores = {
    "alice": 100,
    "bob": 85,
    "charlie": 70,
  };

  let empty_map: [String: int] = {};

  // 1. Query & Inspection
  print("Map size: " + String.from(scores.size()));
  print("Is scores empty: " + String.from(scores.empty()));
  print("Is empty_map empty: " + String.from(empty_map.empty()));
  print("Contains 'alice': " + String.from(scores.contains("alice")));
  print("Contains 'david': " + String.from(scores.contains("david")));

  // 2. Extractions: keys() & values()
  let k_arr: [String] = scores.keys();
  print("Keys size: " + String.from(k_arr.size()));

  let v_arr: [int] = scores.values();
  print("Values size: " + String.from(v_arr.size()));

  // 3. Mutating Methods on var [K: V]
  var mut_map = {
    "alpha": 1,
    "beta": 2,
  };

  let ins_val = mut_map.insert("gamma", 3);
  let ins_named = mut_map.insert(key = "delta", value = 4);
  print("Inserted gamma: " + String.from(ins_val) + ", map size: " +
        String.from(mut_map.size()));

  if let rem_val ?= mut_map.remove("beta") {
    print("Removed beta val: " + String.from(rem_val));
  }

  let missing_rem = mut_map.remove("nonexistent");
  print("Missing remove is none: " + String.from(missing_rem == none));

  mut_map.clear();
  print("After clear, size: " + String.from(mut_map.size()));

  print("=== Demo Complete ===");
}

main();
