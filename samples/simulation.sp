/*
 * Sample Sapphire program illustrating a realistic game entity simulation.
 * It demonstrates:
 * - Math component structs and implementation blocks
 * - Traits for component behavior (Updatable, Combatant)
 * - Static inheritance (syntactic delegation) for structure reuse
 * - Dynamic prototypal inheritance (clone) for entity archetypes
 * - Safe optional chaining and unwrapping (Swift-style if let)
 * - First-class functions and single-expression / block lambdas
 * - Scope-bound aliasing checks (borrow checker constraints)
 */

// 1. Math components
struct Vector2D {
  var x: float;
  var y: float;
}

impl Vector2D {
  func __init__(x: float, y: float) {
    self.x = x;
    self.y = y;
  }

  func translate(dx: float, dy: float) {
    self.x += dx;
    self.y += dy;
  }
}

// 2. Behavioral contracts (Traits)
trait Updatable {
  func update(dt: float);
}

trait Combatant {
  func take_damage(amount: int);
  func get_health(): int;
}

// 3. Game entity base layout
proto GameObject {
  var id: int;
  var position: Vector2D;
  var active: bool;
}

// 4. Dynamically inherited proto: reuse GameObject layout via delegation
proto Character: GameObject {
  var health: int;
  var max_health: int;
  var speed: float;
  let name: String;
}

impl Character {
  func __init__(id: int, name: String, x: float, y: float,
                hp: int = 50, spd: float = 2.0) {
    self.id = id;
    self.position = Vector2D(x = x, y = y);
    self.active = true;
    self.health = hp;
    self.max_health = hp;
    self.speed = spd;
    self.name = name;
  }
}

// Implement traits on Character
impl Updatable for Character {
  func update(dt: float) {
    if self.health <= 0 {
      self.active = false;
      return;
    }
    // Update position: move rightwards based on speed and delta time
    self.position.translate(dx = self.speed * dt, dy = 0.0);
  }
}

impl Combatant for Character {
  func take_damage(amount: int) {
    self.health -= amount;
    if self.health <= 0 {
      self.health = 0;
      self.active = false;
    }
  }

  func get_health(): int {
    return self.health;
  }
}

// 5. Combat function with parameter modes
// - attacker: constant reference (read-only)
// - defender: mutable reference (var)
// - bonus: primitive value-passed parameter with default value
func execute_strike(attacker: Character, var defender: Character,
                    bonus: int = 5): int {
  var damage = 10;
  if attacker.health > 25 {
    damage += bonus;
  }
  defender.take_damage(damage);
  return damage;
}

// 6. Main simulation entry point
func run_demo() {
  // A. Create a prototype archetype (Template)
  // This base_goblin represents a general archetype blueprint.
  var base_goblin = Character(id = 0, name = "Goblin Archer", x = 0.0,
                              y = 0.0, hp = 30, spd = 1.5);

  // B. Clone active characters from the archetype and shadow individual traits
  var goblin_1 = clone base_goblin {
    self.id = 101;
    self.position = Vector2D(x = 10.0, y = 5.0);
  };

  var goblin_2 = clone base_goblin {
    self.id = 102;
    self.position = Vector2D(x = 12.0, y = 6.0);
  };

  // Create a Hero instance from scratch
  var hero = Character(id = 1, name = "Arthur", x = 8.0, y = 5.0, hp = 80,
                       spd = 2.5);

  // C. Show dynamic prototypal inheritance live updates!
  // Mutating the base archetype's stats updates all clones dynamically,
  // unless those properties are shadowed locally.
  base_goblin.speed = 3.5;  // Global haste buff on all Goblins!

  // D. Optionals and Swift-style optional unwrapping (`if let`)
  var target: Character? = none;
  target = goblin_1;

  if let active_target ?= target {
    // Unwrapped active_target is guaranteed non-optional inside this block
    let damage_dealt = execute_strike(attacker = hero,
                                      defender = active_target,
                                      bonus = 10);
  } else {
    // Fallback block if target is none
  }

  // E. Optional Chaining: checking speed on a potential target
  let target_speed = target?.speed;

  // F. Scope-bound aliasing rules (borrow checker)
  // The following call is safe since hero (attacker) and goblin_2 (defender)
  // do not overlap:
  let damage = execute_strike(attacker = hero, defender = goblin_2);

  // Note: The Sapphire compiler would statically reject the following call
  // because goblin_2 cannot be passed as both a constant reference and a
  // mutable reference in the same invocation:
  // execute_strike(attacker = goblin_2, defender = goblin_2);

  // G. Higher-order function / Lambda operations
  // Define lambdas for processing character list
  let is_alive = (c: Character) -> c.health > 0;

  let get_threat_level = (c: Character) -> c.health;

  // Compile local array of entities
  let entities = [hero, goblin_1, goblin_2];

  // Iterate and update all entities
  for entity in entities {
    entity.update(dt = 0.1);
  }

  // Process array of characters using local lambdas
  var total_health = 0;
  for entity in entities {
    if is_alive(entity) {
      total_health += get_threat_level(entity);
    }
  }
}
