/*
 * E2E Test: inheritance_test.sp
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
  let d = Dog(name = "Rex");
  return d.legs;
}

@test
func test_overridden_field(): int {
  let a = Ant();
  return a.legs;
}

@test
func test_own_field(): int {
  let a = Ant();
  return a.colony;
}

struct EntityBase {
  var hp: int = 10;
}

impl EntityBase {
  var func step(dt: int, bonus: int = 5, mult: int = 2) {
    self.hp = self.hp + dt * mult + bonus;
  }
}

struct FlyerMixin {
  var altitude: int = 1;
}

impl FlyerMixin {
  var func lift(delta: int) {
    self.altitude = self.altitude + delta;
  }
}

struct WingedUnit: EntityBase, FlyerMixin {
  var armor: int = 2;
}

impl WingedUnit {
  var func step(dt: int, bonus: int = 5, mult: int = 2) {
    EntityBase.step(self, mult = mult, dt = dt);
    FlyerMixin.lift(self, self.armor + 1);
  }
}

@test
func test_qualified_ancestor_static_dispatch(): int {
  var u = WingedUnit {};
  u.step(4, mult = 3);
  return u.hp * 10 + u.altitude;
}

trait Renderable {
  func render_score(): int;
}

struct BaseNode {
  var x: int = 1;
}

impl BaseNode {
  var func move_by(dx: int) {
    self.x += dx;
  }
}

struct MidNode: BaseNode {
  var y: int = 2;
}

impl MidNode {
  var func step(dt: int) {
    BaseNode.move_by(self, dt);
    self.y += dt * 2;
  }
}

impl Renderable for MidNode {
  func render_score(): int {
    return self.x + self.y;
  }
}

struct LeafNode: MidNode {
  var z: int = 5;
}

impl LeafNode {
  var func step(dt: int) {
    MidNode.step(self, dt);
    self.z += 1;
  }
}

impl Renderable for LeafNode {
  func render_score(): int {
    return self.x + self.y + self.z;
  }
}

@test
func test_multilevel_inheritance_and_trait_dispatch(): int {
  var mid = MidNode {};
  mid.step(3);
  var leaf = LeafNode {};
  leaf.step(3);
  let items: [Renderable] = [mid, leaf];
  return items[0].render_score() * 100 + items[1].render_score();
}
