/*
 * Sample Sapphire program illustrating a love2d-style game engine loop (load,
 * update, draw).
 *
 * This sample demonstrates:
 * - Enums for game state-machine management (Menu, Playing, GameOver)
 * - Trait contracts for component behavior (Updatable, Drawable)
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
  func translate(dx: float, dy: float) {
    self.x += dx;
    self.y += dy;
  }

  // Calculates the Manhattan distance to another Vector2D point.
  const func get_distance_to(other: Vector2D): float {
    let dx = self.x - other.x;
    let dy = self.y - other.y;
    var abs_dx = dx;
    var abs_dy = dy;

    if abs_dx < 0.0 {
      abs_dx = -abs_dx;
    }

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

trait Drawable {
  func draw();
}

// 3. Prototypal layout and entity types
proto GameObject {
  var id: int;
  var position: Vector2D;
  var active: bool = true;
}

proto Entity: GameObject {
  var health: int;
  var speed: float;
  let name: String;
}

impl Entity {
  // Python-style constructor for nontrivial initialization of entity fields.
  func __init__(id: int, name: String, x: float, y: float, hp: int = 100,
                spd: float = 5.0) {
    self.id = id;
    self.position = Vector2D { x = x, y = y };
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

impl Drawable for Entity {
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
trait Love2D {
  func load();
  func update(dt: float);
  func draw();
}

impl Love2D for GameEngine {
  // Initializes game state, entities, and parameters.
  // This is called once at the start of the game loop.
  // Simulates `love.load()` in love2d.
  func load() {
    self.state = GameState.Playing;
    self.score = 0;
    self.frame_count = 0;
    self.game_over_timer = 0.0;

    // Use prototypal cloning (`clone`) to spawn an enemy instance from the
    // base enemy template.
    self.active_enemy = clone self.base_enemy {
      self.id = 101;
      self.position = Vector2D { x = 80.0, y = 20.0 };
    };
  }

  // Process physics, inputs, AI updates, & state transitions.
  // This is called once per frame with a delta-time param.
  // Simulates `love.update(dt)` in love2d.
  func update(dt: float) {
    self.frame_count += 1;

    match self.state {
      GameState.Menu -> {
        // Menu state logic (e.g., wait for user input to start game)
      },
      GameState.Playing -> {
        self.player.update(dt);

        // Swift-style safe optional unwrapping for active enemy
        if let enemy ?= self.active_enemy {
          enemy.update(dt);

          // Check collision distance between player and enemy
          let dist = self.player.position.get_distance_to(enemy.position);

          if dist < 15.0 {
            enemy.health -= 30;
            self.score += 50;

            if enemy.health <= 0 {
              self.active_enemy = none;
              self.state = GameState.GameOver;
            }
          }
        } else {
          // Spawn next enemy wave when active enemy is defeated
          self.active_enemy = clone self.base_enemy {
            self.id = 102;
            self.position = Vector2D { x = 120.0, y = 20.0 };
            self.health = 50;
          };
        }
      },
      GameState.GameOver -> {
        self.game_over_timer += dt;

        if self.game_over_timer >= 3.0 {
          self.load();
        }
      },
    };
  }

  // Perform rendering calls for graphics and HUD UI.
  // This is called once per frame after the update step.
  // Simulates `love.draw()` in love2d.
  func draw() {
    match self.state {
      GameState.Playing -> {
        self.player.draw();

        if let enemy ?= self.active_enemy {
          enemy.draw();
        }
      },
      // In practice we'd render the main-menu and game-over screens here.
      ... -> {},
    };
  }
}

// 6. Engine driver (simulating love2d's main `love.run` loop)
func run_game_loop() {
  var engine = GameEngine();

  // 1. Initialize game engine state and spawn entities.
  engine.load();

  // Run game loop across simulated frames with 60FPS delta time (0.016s)
  let frame_deltas = [0.016, 0.016, 0.016, 0.016, 0.016];

  for dt in frame_deltas {
    // 2. Update engine world state.
    engine.update(dt);

    // 3. Render frame graphics.
    engine.draw();
  }
}

// Top-level script execution entry point
run_game_loop();
