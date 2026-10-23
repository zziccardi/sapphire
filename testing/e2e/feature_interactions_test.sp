/*
 * E2E Test: feature_interactions_test.sp
 * Tests complex interactions across multiple language features.
 */

enum ItemKind {
  Potion = 1,
  Scroll = 2,
  Gem = 3,
}

struct Item {
  var kind: ItemKind;
  var value: int;
}

struct Bag {
  var items: [Item];
  var capacity: int;
}

impl Bag {
  func total_value(): int {
    var sum = 0;
    for item in self.items {
      let multiplier = match item.kind {
        ItemKind.Potion -> 1,
        ItemKind.Scroll -> 2,
        ItemKind.Gem -> 5,
        ... -> 0,
      };
      sum += item.value * multiplier;
    }
    return sum;
  }
}

struct Player {
  var bag: Bag?;
}

func find_positive_square(nums: [int]): int? {
  for n in nums {
    if n > 0 {
      return n * n;
    }
  }
  return none;
}

@test
func test_struct_with_enum_matching_in_loop(): int {
  let p = Item { kind = ItemKind.Potion, value = 10 };
  let s = Item { kind = ItemKind.Scroll, value = 20 };
  let g = Item { kind = ItemKind.Gem, value = 30 };
  let bag = Bag { items = [p, s, g], capacity = 100 };
  return bag.total_value();
}

@test
func test_deep_optional_chaining_on_structs(): int {
  let p1 = Player { bag = none };
  let c1 = p1.bag?.capacity ?? -1;

  let item = Item { kind = ItemKind.Potion, value = 42 };
  let bag = Bag { items = [item], capacity = 50 };
  let p2 = Player { bag = bag };
  let c2 = p2.bag?.capacity ?? -1;

  return c1 + c2;
}

@test
func test_guard_unwrapping_with_block_closure(): int {
  let nums = [-2, -1, 4, 5];
  let res = find_positive_square(nums);

  guard let sq ?= res;
        sq > 10
  else {
    return 0;
  }

  let compute = (base: int, factor: int) -> int {
    let scaled = base * factor;
    return scaled + sq;
  };
  return compute(5, 2);
}
