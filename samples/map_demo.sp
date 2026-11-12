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
  print(f"Map size: {scores.size()}");
  print(f"Is scores empty: {scores.empty()}");
  print(f"Is empty_map empty: {empty_map.empty()}");
  let has_alice = scores.contains("alice");
  let has_david = scores.contains("david");
  print(f"Contains 'alice': {has_alice}");
  print(f"Contains 'david': {has_david}");

  // 2. Extractions: keys() & values()
  let k_arr = scores.keys();
  print(f"Keys size: {k_arr.size()}");

  let v_arr = scores.values();
  print(f"Values size: {v_arr.size()}");

  // 3. Mutating Methods on var [K: V]
  var mut_map = {
    "alpha": 1,
    "beta": 2,
  };

  let ins_val = mut_map.insert("gamma", 3);
  let ins_named = mut_map.insert(key = "delta", value = 4);
  print(f"Inserted gamma: {ins_val}, map size: {mut_map.size()}");

  if let rem_val ?= mut_map.remove("beta") {
    print(f"Removed beta val: {rem_val}");
  }

  let missing_rem = mut_map.remove("nonexistent");
  print(f"Missing remove is none: {missing_rem == none}");

  mut_map.clear();
  print(f"After clear, size: {mut_map.size()}");

  print("=== Demo Complete ===");
}
