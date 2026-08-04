// Multi-Parent Struct Syntactic Delegation Demo in Sapphire

struct Position {
  var x: float = 0.0;
  var y: float = 0.0;
}

struct Health {
  var hp: int = 100;
  var max_hp: int = 100;
}

// Player inlines field layout from both Position and Health
struct Player: Position, Health {
  var name: String;
}

impl Position {
  func move_by(dx: float, dy: float) {
    self.x += dx;
    self.y += dy;
  }
}

impl Health {
  func take_damage(amount: int) {
    self.hp -= amount;
    if self.hp < 0 {
      self.hp = 0;
    }
  }
}

func main() {
  var hero = Player {
    name = "Arthur",
    x = 10.0,
    y = 20.0
  };

  print(f"Player Name: {hero.name}");
  print(f"Initial Position: ({hero.x}, {hero.y})");
  print(f"Initial HP: {hero.hp}/{hero.max_hp}");

  hero.move_by(5.5, -2.5);
  hero.take_damage(35);

  print(f"Updated Position: ({hero.x}, {hero.y})");
  print(f"Updated HP: {hero.hp}/{hero.max_hp}");
}
