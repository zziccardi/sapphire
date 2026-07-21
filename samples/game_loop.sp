/*
 * Sample Sapphire program illustrating a love2d-style game engine loop (load,
 * update, draw).
 *
 * This sample demonstrates:
 * - Enums for game state-machine management (Menu, Playing, GameOver)
 * - Trait contracts for component behavior (Updatable, Renderable)
 * - Prototypal inheritance (`proto` and `clone`) for entity spawning from
 *   blueprints
 * - Swift-style safe optional unwrapping (`if let`) for entity target tracking
 * - Mutable parameter modes (`var game: GameEngine`) for state-modifying
 *   callbacks
 * - Array iteration over frame delta times in a simulated engine main loop
 */

// 1. Game state and math types
enum GameState {
  Menu,
  Playing,
  GameOver,
}

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

  // Calculates the Manhattan distance to another Vector2D point.
  const func get_distance_to(other: Vector2D): float {
    let dx = self.x - other.x;
    let dy = self.y - other.y;
    var abs_dx = dx;

    if abs_dx < 0.0 {
      abs_dx = -abs_dx;
    }

    var abs_dy = dy;

    if abs_dy < 0.0 {
      abs_dy = -abs_dy;
    }

    return abs_dx + abs_dy;
  }
}

// 2. Behavioral traits (love2d engine contracts)
trait Updatable {
  func update(dt: float);
}

trait Renderable {
  func draw();
}

// 3. Prototypal layout and entity types
proto GameObject {
  var id: int;
  var position: Vector2D;
  var active: bool;
}

proto Entity: GameObject {
  var health: int;
  var speed: float;
  let name: String;
}

impl Entity {
  func __init__(id: int, name: String, x: float, y: float, hp: int = 100,
                spd: float = 5.0) {
    self.id = id;
    self.position = Vector2D(x = x, y = y);
    self.active = true;
    self.health = hp;
    self.speed = spd;
    self.name = name;
  }
}

impl Updatable for Entity {
  func update(dt: float) {
    if self.health <= 0 {
      self.active = false;
      return;
    }
    // Update entity position by applying horizontal velocity.
    self.position.translate(dx = self.speed * dt, dy = 0.0);
  }
}

impl Renderable for Entity {
  func draw() {
    if self.active {
      // Frame rendering step for active entity
    }
  }
}

// 4. Main game engine state container
struct GameEngine {
  var state: GameState;
  var score: int;
  var frame_count: int;
  var player: Entity;
  var base_enemy: Entity;
  var active_enemy: Entity?;
  var game_over_timer: float;
}

impl GameEngine {
  func __init__() {
    self.state = GameState.Menu;
    self.score = 0;
    self.frame_count = 0;
    self.player = Entity(id = 1, name = "Hero", x = 10.0, y = 20.0, hp = 100,
                         spd = 12.0);
    self.base_enemy = Entity(id = 0, name = "Slime", x = 100.0, y = 20.0,
                             hp = 30, spd = -4.0);
    self.active_enemy = none;
    self.game_over_timer = 0.0;
  }
}

// 5. Core love2d-style engine callbacks

// `love.load()` -- Initializes game state, entities, and parameters.
func load(var game: GameEngine) {
  game.state = GameState.Playing;
  game.score = 0;
  game.frame_count = 0;
  game.game_over_timer = 0.0;

  // Use prototypal cloning (`clone`) to spawn an enemy instance from template.
  let spawned_slime = clone game.base_enemy {
    self.id = 101;
    self.position = Vector2D(x = 80.0, y = 20.0);
  };

  game.active_enemy = spawned_slime;
}

// `love.update(dt)` -- Process physics, inputs, AI updates, & state
// transitions.
func update(var game: GameEngine, dt: float) {
  game.frame_count += 1;

  // TODO: Add switch/match expressions.
  if game.state == GameState.Playing {
    game.player.update(dt);

    // Swift-style safe optional unwrapping for active enemy
    if let enemy = game.active_enemy {
      enemy.update(dt);

      // Check collision distance between player and enemy
      let dist = game.player.position.get_distance_to(other = enemy.position);

      if dist < 15.0 {
        enemy.health -= 30;
        game.score += 50;

        if enemy.health <= 0 {
          game.active_enemy = none;
          game.state = GameState.GameOver;
        }
      }
    } else {
      // Spawn next enemy wave when active enemy is defeated
      let wave_enemy = clone game.base_enemy {
        self.id = 102;
        self.position = Vector2D(x = 120.0, y = 20.0);
        self.health = 50;
      };

      game.active_enemy = wave_enemy;
    }
  } else if game.state == GameState.GameOver {
    game.game_over_timer += dt;

    if game.game_over_timer >= 3.0 {
      load(game = game);
    }
  }
}

// `love.draw()` -- Perform rendering calls for graphics and HUD UI.
func draw(game: GameEngine) {
  if game.state == GameState.Menu {
    // Draw main menu screen
  } else if game.state == GameState.Playing {
    // Render game objects
    game.player.draw();

    if let enemy = game.active_enemy {
      enemy.draw();
    }
  } else if game.state == GameState.GameOver {
    // Draw game over screen
  }
}

// 6. Engine driver (simulating love2d's main `love.run` loop)
func run_game_loop() {
  var engine = GameEngine();

  // 1. Initialize game engine state and spawn entities.
  load(game = engine);

  // Run game loop across simulated frames with 60FPS delta time (0.016s)
  let frame_deltas = [0.016, 0.016, 0.016, 0.016, 0.016];

  for dt in frame_deltas {
    // 2. Update engine world state.
    update(game = engine, dt = dt);

    // 3. Render frame graphics.
    draw(game = engine);
  }
}

func main(): int {
  run_game_loop();
  return 0;
}
