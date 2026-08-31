/*
 * Sample Sapphire program demonstrating arena-based memory management as
 * defined in docs/SPEC.md (Section 10.B).
 *
 * Key features demonstrated:
 * 1. Explicit Arenas & RAII Destruction: Creating custom Arena instances whose
 *    lexical lifecycle automatically manages allocated objects.
 * 2. Opt-in Struct Allocation: Allocating standard structs in a targeted arena
 *    using the `in` operator.
 * 3. Proto Arena Allocation: Allocating prototypal objects in explicit arenas
 *    via the `in` operator (required for all proto allocations).
 * 4. Clone Arena Propagation: Clones inheriting their prototype's arena by
 *    default, or overriding it via `clone ... in arena`.
 * 5. Scoped RAII Teardown: Instantiating temporary arenas in local scopes for
 *    transient allocations that are automatically freed upon scope exit.
 */

// 1. Standard struct (opt-in arena allocation with 'in')
struct Point {
  var x: float;
  var y: float;
}

impl Point {
  func __init__(x: float = 0.0, y: float = 0.0) {
    self.x = x;
    self.y = y;
  }

  func translate(dx: float, dy: float) {
    self.x += dx;
    self.y += dy;
  }
}

struct Particle {
  var pos: Point;
  var lifetime: float;
}

impl Particle {
  func __init__(pos: Point, lifetime: float = 1.0) {
    self.pos = pos;
    self.lifetime = lifetime;
  }
}

// 2. Proto structures (always arena-allocated)
proto Entity {
  var name: String;
  var hp: int;
  var pos: Point;
}

proto Enemy: Entity {
  var damage: int;
}

impl Enemy {
  func __init__(name: String, hp: int, pos: Point, damage: int = 10) {
    self.name = name;
    self.hp = hp;
    self.pos = pos;
    self.damage = damage;
  }

  func take_damage(amount: int) {
    self.hp -= amount;
    if self.hp < 0 {
      self.hp = 0;
    }
  }
}

// Proto structure inheriting layout from Entity
proto Boss: Entity {
  var phase: int;
}

impl Boss {
  func __init__(name: String, hp: int, pos: Point, phase: int = 1) {
    self.name = name;
    self.hp = hp;
    self.pos = pos;
    self.phase = phase;
  }
}

// Demonstration 1: Explicit Arenas, Struct Allocation, & Clone Propagation
func demo_explicit_arenas(): int {
  // Instantiate explicit arenas with lexical lifecycles
  let level_arena = Arena();
  let combat_arena = Arena();

  // Allocate a standard struct in level_arena using 'in'
  let spawn_point = Point { x = 100.0, y = 200.0 } in level_arena;

  // Allocate a proto instance in level_arena via struct initializer syntax
  let base_goblin = Enemy {
    name = "Goblin Archer",
    hp = 50,
    pos = spawn_point,
    damage = 12,
  } in level_arena;

  // Implicit clone arena propagation: minion inherits level_arena from base
  let minion = clone base_goblin {
    self.hp = 30;
  };

  // Explicit clone arena override: combat_goblin is targeted to combat_arena
  let combat_goblin = clone base_goblin {
    self.hp = 75;
  } in combat_arena;

  minion.take_damage(10);
  combat_goblin.take_damage(25);

  // Return combined remaining health
  return minion.hp + combat_goblin.hp;
}

// Demonstration 2: Scoped Temporary Arenas and RAII Cleanup
func demo_scoped_raii_cleanup(): float {
  var total_lifetime = 0.0;

  {
    // Local arena created within a nested block
    let temp_arena = Arena();

    let origin = Point { x = 5.0, y = 10.0 } in temp_arena;
    let p1 = Particle { pos = origin, lifetime = 1.5 } in temp_arena;
    let p2 = Particle { pos = origin, lifetime = 2.5 } in temp_arena;

    let temp_boss = Boss {
      name = "Dungeon Boss",
      hp = 500,
      pos = origin,
      phase = 1,
    } in temp_arena;

    total_lifetime = p1.lifetime + p2.lifetime;

    // Leaving this scope tears down temp_arena and frees all allocated
    // instances (origin, p1, p2, temp_boss) automatically.
  }

  return total_lifetime;
}

// Demonstration 3: Constructor Proto Allocation with Explicit Arena
func demo_constructor_arena_allocation(): int {
  let dungeon_arena = Arena();
  let default_pos = Point(x = 0.0, y = 0.0);

  // Protos instantiated via constructor require explicit arena via 'in'
  let default_enemy = Enemy(name = "Default Skeleton", hp = 100,
                            pos = default_pos) in dungeon_arena;

  // Clones of default_enemy propagate into dungeon_arena automatically
  let cloned_skeleton = clone default_enemy {
    self.hp = 60;
  };

  cloned_skeleton.take_damage(15);

  return default_enemy.hp + cloned_skeleton.hp;
}

// Main demo orchestrator
func run_demo(): int {
  let score1 = demo_explicit_arenas();
  let score2 = demo_constructor_arena_allocation();
  let duration = demo_scoped_raii_cleanup();
  var result = score1 + score2;

  if duration > 3.0 {
    result += 10;
  }

  return result;
}

// Top-level script execution entry point
run_demo();
