// Global compile-time constant
let MAX_PLAYERS: int = 100;

// 1. Traits defining contracts
trait Damageable {
  func take_damage(amount: int);
}

// 2. Struct declarations (static inheritance & fields)
struct Position {
  var x: float;
  var y: float;
}

impl Position {
  func __init__(x: float, y: float) {
    self.x = x;
    self.y = y;
  }
}

struct Entity {
  var pos: Position;
  let id: int;
}

// Inherits Entity physical layout at compile-time
struct Character: Entity {
  var health: int;
  var max_health: int;
  let name: String;
}

// 3. Implementation block for Character
impl Character {
  // Python-style initializer syntax
  func __init__(id: int, name: String, max_hp: int = 100) {
    self.id = id;
    self.pos = Position(x = 0.0, y = 0.0); // Named parameter call
    self.health = max_hp;
    self.max_health = max_hp;
    self.name = name;
  }

  // Const method (cannot modify self)
  const func get_health_ratio(): float {
    return self.health / self.max_health;
  }

  // Mutable method (can modify self)
  func heal(amount: int) {
    self.health += amount;
    if self.health > self.max_health {
      self.health = self.max_health;
    }
  }
}

// Implement trait for Character
impl Damageable for Character {
  func take_damage(amount: int) {
    self.health -= amount;
    if self.health < 0 {
      self.health = 0;
    }
  }
}

// 4. Function showing parameter modes:
// - attacker: passed by constant reference (non-primitive)
// - defender: passed by mutable reference (var)
// - is_critical: passed by value (primitive) with default parameter
func execute_attack(attacker: Character, var defender: Character,
                    is_critical: bool = false): int {
  var base_damage = 15;
  if is_critical {
    base_damage *= 2;
  }

  // Trait method dispatch resolved statically
  defender.take_damage(base_damage);
  return base_damage;
}

// 5. Main entry demonstration function
func run_demo() {
  // Variable declarations and type inference
  // Constant binding
  let player_one = Character(id = 1, name = "Galahad");
  // Mutable binding
  var player_two = Character(id = 2, name = "Lancelot", max_hp = 120);

  // Optionals and swift-style optional unwrapping
  var target_player: Character? = none;
  target_player = player_two;

  if let active_target = target_player {
    // active_target is unwrapped and guaranteed to be non-optional here
    let damage_dealt = execute_attack(attacker = player_one,
                                      defender = active_target,
                                      is_critical = true);
  }

  // Dynamic prototypal inheritance via 'clone'
  let prototype_enemy = Character(id = 99, name = "Goblin Minion", max_hp = 30);

  // Clone creates a live reference delegation back to prototype_enemy
  var active_clone = clone prototype_enemy {
    self.health = 25; // Shadowed locally
  };

  // Inspecting prototype chain (__proto__ is read-only and type T?)
  if let parent = active_clone.__proto__ {
    let name_ref = parent.name;
  }

  // First-class functions and closures
  var damage_multiplier: (int) -> int = x -> x * 2;

  // Array literals with optional trailing commas & collection functions
  let scores = [10, 20, 30,];
  let first_score = scores[0]; // Array indexing

  // Loops: while loop (no parentheses around condition)
  var timer = 3;
  while timer > 0 {
    timer -= 1;
  }

  // Loops: for-in loop (implicitly constant loop variable)
  for score in scores {
    let final_score = damage_multiplier(score);
  }

  // Loops: for-in loop with var keyword (mutable loop variable)
  for var score in scores {
    score += 5;
  }
}
