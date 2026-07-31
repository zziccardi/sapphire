// Sample demonstrating map iteration in Sapphire

func main() {
  let inventory = {
    "potions": "5 units",
    "elixirs": "2 units",
    "scrolls": "10 units",
  };

  print("--- Inventory Contents ---");
  for item, count in inventory {
    print(item + ": " + count);
  }
}
