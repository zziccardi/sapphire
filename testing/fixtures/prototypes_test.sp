/*
 * Fixture: prototypes_test.sp
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
