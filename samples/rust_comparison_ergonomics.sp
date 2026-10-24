/*
 * rust_comparison_ergonomics.sp
 *
 * Demonstrates how Sapphire solves Rust's friction and ergonomics pain points:
 * 1. Structural code reuse: Syntactic delegation vs manual forwarding.
 * 2. Scope-bound reference safety: No lifetime annotations ('a).
 * 3. Swift-style guard unwrapping: Eliminating rightward drift.
 * 4. Zero-vtable trait polymorphism: Monomorphized heterogeneous collections.
 *
 * Reference: docs/rust_comparison.md Sections 2.1, 2.3, 2.4, 2.6
 */

// ============================================================================
// 1. Structural Code Reuse (Syntactic Delegation)
// Rust avoids inheritance, requiring manual composition and tedious forwarding
// methods for every nested method, or complex third-party macros.
// Sapphire allows multi-parent delegation (`struct Player: Transform2D, ...`).
// The compiler automatically forwards methods with zero vtables and zero
// runtime penalty. Struct up-casting (`Player as Transform2D`) is prohibited.
// ============================================================================

struct Transform2D {
  var x: float;
  var y: float;
}

impl Transform2D {
  var func translate(dx: float, dy: float) {
    self.x += dx;
    self.y += dy;
  }
}

struct RigidBody {
  var vx: float;
  var vy: float;
  var mass: float;
}

impl RigidBody {
  var func apply_force(fx: float, fy: float) {
    self.vx += fx / self.mass;
    self.vy += fy / self.mass;
  }
}

// Player transparently delegates to Transform2D and RigidBody
struct Player: Transform2D, RigidBody {
  var name: String;
  var score: int;
}

// ============================================================================
// 2. Zero-Vtable Trait Polymorphism
// Rust dynamic dispatch (`dyn Trait`) incurs 2-word fat pointer overhead,
// vtable lookups, and strict object-safety constraints (no generics, no Self).
// Sapphire heterogeneous trait collections (`[Renderable]`) synthesize closed
// tagged unions at compile time, eliminating vtables and enabling inlining.
// ============================================================================

trait Renderable {
  func render(): String;
}

impl Renderable for Player {
  func render(): String {
    return f"Player {self.name} at ({self.x}, {self.y})";
  }
}

struct Obstacle {
  var label: String;
}

impl Renderable for Obstacle {
  func render(): String {
    return f"Obstacle [{self.label}])";
  }
}

// ============================================================================
// 3. Guard Statements & Swift-Style Optionals
// Rust pattern matching with `if let` and `match` often leads to nested
// rightward drift. Unwrapping Option often requires .as_ref() gymnastics.
// Sapphire `guard` unwraps optionals, validates conditions, and promotes the
// unwrapped binding into the enclosing scope, keeping the happy path flat.
// ============================================================================

struct UserAccount {
  var username: String;
  var active: bool;
  var email: String?;
}

func get_verified_email(account: UserAccount?): String {
  // `user` is automatically promoted to non-optional UserAccount in this scope
  guard let user ?= account; user.active else {
    return "inactive_or_missing";
  }

  // Nil-coalescing (??) provides clean default fallback
  return user.email ?? "no_email_provided";
}

// ============================================================================
// Demonstrations
// ============================================================================

func demo_syntactic_delegation() {
  print("=== 1. Syntactic Delegation (Structural Code Reuse) ===");
  var hero = Player {
    name = "Aria",
    score = 1500,
    x = 10.0,
    y = 20.0,
    vx = 0.0,
    vy = 0.0,
    mass = 2.0,
  };

  // Directly invoke methods inherited from Transform2D and RigidBody
  hero.translate(5.0, 10.0);
  hero.apply_force(10.0, 4.0);

  print(f"Player pos: ({hero.x}, {hero.y})");
  print(f"Player velocity: ({hero.vx}, {hero.vy})");
}

func demo_guard_and_optionals() {
  print("=== 2. Guard Statements & Swift-Style Optionals ===");
  let active_user = UserAccount {
    username = "sapphire_dev",
    active = true,
    email = "dev@sapphire-lang.org",
  };

  let unverified_user = UserAccount {
    username = "guest",
    active = false,
    email = none,
  };

  // TODO: Update LSP implementation to handle format strings correctly.
  print(f"Active email: {get_verified_email(active_user)}");
  print(f"Guest email: {get_verified_email(unverified_user)}");
}

func demo_zero_vtable_traits() {
  print("=== 3. Zero-Vtable Trait Polymorphism ===");
  let player = Player {
    name = "Hero",
    score = 100,
    x = 0.0,
    y = 0.0,
    vx = 0.0,
    vy = 0.0,
    mass = 1.0,
  };
  let obstacle = Obstacle { label = "Stone Wall" };

  // Heterogeneous trait collection [Renderable]
  let scene: [Renderable] = [player, obstacle];
  for item in scene {
    print(f"Render: {item.render()}");
  }
}

func main() {
  demo_syntactic_delegation();
  demo_guard_and_optionals();
  demo_zero_vtable_traits();
}
