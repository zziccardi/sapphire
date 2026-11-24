/*
 * E2E Test: traits_polymorphism_test.sp
 * Tests trait implementation, heterogeneous dispatch, and trait arguments.
 */

trait Greeter {
  func greet(): int;
}

struct FriendlyBot {
  var code: int = 100;
}

impl Greeter for FriendlyBot {
  func greet(): int {
    return self.code + 1;
  }
}

struct FormalBot {
  var code: int = 200;
}

impl Greeter for FormalBot {
  func greet(): int {
    return self.code + 2;
  }
}

func execute_greeting(g: Greeter): int {
  return g.greet();
}

@test
func test_polymorphic_trait_call(): int {
  let f = FriendlyBot {};
  let b = FormalBot {};
  return execute_greeting(f) + execute_greeting(b);
}

trait Counter {
  var func bump(delta: int);
  func value(): int;
}

struct StepCounter {
  var count: int = 0;
}

impl Counter for StepCounter {
  var func bump(delta: int) {
    self.count += delta;
  }
  func value(): int {
    return self.count;
  }
}

struct DoubleCounter {
  var count: int = 10;
}

impl Counter for DoubleCounter {
  var func bump(delta: int) {
    self.count += delta * 2;
  }
  func value(): int {
    return self.count;
  }
}

struct Squad {
  var leader: Greeter?;
}

@test
func test_heterogeneous_trait_array(): int {
  let bots: [Greeter] = [FriendlyBot { code = 10 }, FormalBot { code = 20 }];
  var sum = 0;
  for bot in bots {
    sum += bot.greet();
  }
  return sum;
}

@test
func test_trait_array_mutating_method(): int {
  var counters: [Counter] = [StepCounter {}, DoubleCounter {}];
  counters[0].bump(5);
  counters[1].bump(3);
  return counters[0].value() + counters[1].value();
}

@test
func test_trait_in_nested_map(): int {
  var grid: [int: [int: Greeter]] = {};
  var r1: [int: Greeter] = {};
  r1[2] = FriendlyBot { code = 30 };
  var r2: [int: Greeter] = {};
  r2[4] = FormalBot { code = 40 };
  grid[1] = r1;
  grid[3] = r2;
  let g1 = grid.get(1)?.get(2);
  let g2 = grid.get(3)?.get(4);
  let a = g1?.greet() ?? 0;
  let b = g2?.greet() ?? 0;
  return a + b;
}

@test
func test_optional_trait_field(): int {
  let empty = Squad { leader = none };
  let active = Squad { leader = FriendlyBot { code = 50 } };
  let v1 = empty.leader?.greet() ?? -1;
  let v2 = active.leader?.greet() ?? -1;
  return v1 + v2;
}

@test
func test_nested_trait_map_literal(): int {
  let grid: [int: [int: Greeter]] = {
    1: {2: FriendlyBot { code = 30 }},
    3: {4: FormalBot { code = 40 }},
  };
  let a = grid.get(1)?.get(2)?.greet() ?? 0;
  let b = grid.get(3)?.get(4)?.greet() ?? 0;
  return a + b;
}

trait Named {
  func label(): int;
  func bonus(): int;
}

struct BaseAgent {
  var base_val: int = 10;
}

impl Named for BaseAgent {
  func label(): int {
    return self.base_val;
  }

  func bonus(): int {
    return 5;
  }
}

struct SubAgent: BaseAgent {}

struct CustomAgent: SubAgent {}

impl Named for CustomAgent {
  func bonus(): int {
    return BaseAgent.bonus(self) + 20;
  }
}

func eval_named(n: Named): int {
  return n.label() + n.bonus();
}

@test
func test_inherited_trait_partial_override(): int {
  let s = SubAgent { base_val = 10 };
  let c = CustomAgent { base_val = 30 };
  return eval_named(s) + eval_named(c);
}

trait Scorable {
  func raw(): int;

  func bonus(): int {
    return 10;
  }

  func total(): int {
    return self.raw() + self.bonus();
  }
}

struct PlainScore {
  var v: int;
}

impl Scorable for PlainScore {
  func raw(): int {
    return self.v;
  }
}

struct ParentScore {
  var v: int;
}

impl Scorable for ParentScore {
  func raw(): int {
    return self.v;
  }

  func bonus(): int {
    return 25;
  }
}

struct ChildScore: ParentScore {}

impl Scorable for ChildScore {
  func raw(): int {
    return self.v * 2;
  }
}

func read_score(s: Scorable): int {
  return s.total();
}

@test
func test_trait_default_method_and_override(): int {
  let a = PlainScore { v = 5 };
  let b = ParentScore { v = 5 };
  let c = ChildScore { v = 5 };
  // a: 5 + 10 = 15, b: 5 + 25 = 30, c: (5*2) + 25 (Parent override > Trait default) = 35
  return read_score(a) + read_score(b) + read_score(c) + a.total();
}

enum StackStateKey {
  MAP = 1,
  MENU = 2,
}

struct ViewCamera {
  var zoom: int = 2;
}

trait StackGameState {
  var func update(var pop_requests: [bool]);
  func draw(camera: ViewCamera): int;
}

proto MapTag {
  var bonus: int = 10;
}

struct ArenaMapState {
  var arena: Arena;
  var tag: MapTag? = none;
  var ticks: int = 0;
}

impl StackGameState for ArenaMapState {
  var func update(var pop_requests: [bool]) {
    self.ticks += 1;
  }

  func draw(camera: ViewCamera): int {
    let b = self.tag?.bonus ?? 0;
    return (b + self.ticks) * camera.zoom;
  }
}

struct CopyMenuState {
  var selected: int = 5;
}

impl StackGameState for CopyMenuState {
  var func update(var pop_requests: [bool]) {
    pop_requests.push(true);
  }

  func draw(camera: ViewCamera): int {
    return self.selected * camera.zoom;
  }
}

trait StackStateFactory {
  func create_state(): StackGameState;
}

struct MapStateFactory {}

impl StackStateFactory for MapStateFactory {
  func create_state(): StackGameState {
    var st = ArenaMapState {
      arena = Arena(),
    };
    st.tag = MapTag { bonus = 12 } in st.arena;
    return move st;
  }
}

struct MenuStateFactory {}

impl StackStateFactory for MenuStateFactory {
  func create_state(): StackGameState {
    return CopyMenuState { selected = 7 };
  }
}

@test
func test_trait_stack_mixing_move_only_arena_and_copy_structs_with_factory(): int {
  let camera = ViewCamera { zoom = 2 };
  var factories: [StackStateKey: StackStateFactory] = {};
  factories[StackStateKey.MAP] = MapStateFactory {};
  factories[StackStateKey.MENU] = MenuStateFactory {};

  var stack: [StackGameState] = [];
  if let mf ?= factories.get(StackStateKey.MAP) {
    stack.push(mf.create_state());
  }
  if let menuf ?= factories.get(StackStateKey.MENU) {
    stack.push(menuf.create_state());
  }

  var total = 0;
  // Draw both: MapState (12 + 0)*2 = 24, MenuState 7*2 = 14 -> 38
  for i in range(0, stack.size()) {
    total += stack[i].draw(camera);
  }

  var pops: [bool] = [];
  let top = stack.size() - 1;
  stack[top].update(pops);
  if !pops.empty() {
    stack.remove(top);
  }

  // Update & draw remaining MapState: ticks=1 -> (12 + 1)*2 = 26
  var pops2: [bool] = [];
  stack[0].update(pops2);
  total += stack[0].draw(camera);
  // 38 + 26 = 64
  return total;
}
