/*
 * Fixture: inheritance_test.sp
 * Tests single-parent struct inheritance and prototypal field delegation.
 */

struct Animal {
  var sound: String = "...";
  var legs: int = 4;
}

struct Dog: Animal {
  var name: String;
}

impl Dog {
  func __init__(name: String) {
    self.name = name;
    self.sound = "woof";
  }
}

struct Ant: Animal {
  var colony: int = 1;
}

impl Ant {
  func __init__() {
    self.legs = 6;
  }
}

@test
func test_inherited_field(): int {
  let d = Dog { name = "Rex" };
  return d.legs;
}

@test
func test_overridden_field(): int {
  let a = Ant {};
  return a.legs;
}

@test
func test_own_field(): int {
  let a = Ant {};
  return a.colony;
}
