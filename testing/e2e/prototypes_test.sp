/*
 * E2E Test: prototypes_test.sp
 * Tests proto declaration, clone expressions, shadowing, and live prototype delegation.
 */

proto Monster {
  var hp: int = 100;
  var attack: int = 10;
}

@test
func test_proto_delegation(): int {
  let arena = Arena();
  let base_m = Monster {} in arena;
  let c1 = clone base_m {};
  return c1.hp;
}

@test
func test_proto_shadowing(): int {
  let arena = Arena();
  let base_m = Monster {} in arena;
  let c1 = clone base_m {
    self.hp = 250;
  };
  return c1.hp;
}

@test
func test_live_proto_mutation(): int {
  let arena = Arena();
  var base_m = Monster {} in arena;
  let c1 = clone base_m {};
  base_m.attack = 30;
  return c1.attack;
}

struct NestedStats {
  var hp: int = 20;
}

impl NestedStats {
  var func take_damage(dmg: int) {
    self.hp -= dmg;
  }
}

struct NestedUnit {
  var stats: NestedStats;
}

proto CombatArchetype {
  var unit: NestedUnit;
}

@test
func test_nested_struct_cow_isolation(): int {
  let arena = Arena();
  let base = CombatArchetype {
    unit = NestedUnit { stats = NestedStats { hp = 20 } }
  } in arena;
  var c1 = clone base {};
  var c2 = clone c1 {};
  c1.unit.stats.hp = 50;
  c1.unit.stats.take_damage(10);
  c2.unit.stats.hp = 99;
  return c1.unit.stats.hp * 10000 + c2.unit.stats.hp * 100 + base.unit.stats.hp;
}
