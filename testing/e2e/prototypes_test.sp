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
  var arena = Arena();
  let base_m = Monster {} in arena;
  let c1 = clone base_m {};
  return c1.hp;
}

@test
func test_proto_shadowing(): int {
  var arena = Arena();
  let base_m = Monster {} in arena;
  let c1 = clone base_m {
    self.hp = 250;
  };
  return c1.hp;
}

@test
func test_live_proto_mutation(): int {
  var arena = Arena();
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
  var arena = Arena();
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

trait Combatant {
  func get_hp(): int;
  var func set_hp(hp: int);
}

proto UnitArchetype {
  var name: String = "Skeleton";
  var hp: int = 20;
  var atk: int = 6;
}

impl Combatant for UnitArchetype {
  func get_hp(): int {
    return self.hp;
  }

  var func set_hp(hp: int) {
    self.hp = hp;
  }
}

struct BattleContext {
  var unit_arena: Arena;
  var archetypes: [String: UnitArchetype] = {};
  var units: [int: UnitArchetype] = {};
}

impl BattleContext {
  var func init_archetypes() {
    self.archetypes["SWORD"] = UnitArchetype {
      name = "Sword Skeleton",
      hp = 20,
      atk = 7,
    } in self.unit_arena;
  }

  var func spawn_unit(unit_id: int, key: String, name: String) {
    if let base ?= self.archetypes.get(key) {
      self.units[unit_id] = clone base {
        self.name = name;
      };
    }
  }
}

func create_battle_context(): BattleContext {
  var ctx = BattleContext {
    unit_arena = Arena(),
  };
  ctx.init_archetypes();
  ctx.spawn_unit(10, "SWORD", "Skeleton A");
  ctx.spawn_unit(11, "SWORD", "Skeleton B");
  return move ctx;
}

func apply_hit(var target: Combatant, dmg: int) {
  target.set_hp(target.get_hp() - dmg);
}

@test
func test_proto_trait_impl_in_struct_arena_map_with_if_var_dispatch(): int {
  var ctx = create_battle_context();
  if var u10 ?= ctx.units.get(10) {
    apply_hit(u10, 7);
  }
  let hp10 = ctx.units.get(10)?.get_hp() ?? 0;
  let hp11 = ctx.units.get(11)?.get_hp() ?? 0;
  let base_hp = ctx.archetypes.get("SWORD")?.get_hp() ?? 0;
  // 13 * 10000 + 20 * 100 + 20 = 132020
  return hp10 * 10000 + hp11 * 100 + base_hp;
}
