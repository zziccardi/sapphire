/*
 * Sample Sapphire program illustrating Implicit Trait Subtyping.
 * Demonstrates passing structs to trait-typed parameters, returning structs
 * from trait-typed functions, handling optional trait parameters, and creating
 * heterogeneous trait collections (e.g. [Renderable]).
 */

// 1. Define trait contracts
trait Renderable {
  func render();
}

trait Describable {
  func get_description(): String;
}

// 2. Define concrete structures
struct Circle {
  var radius: float;
}

struct Rectangle {
  var width: float;
  var height: float;
}

// 3. Implement traits for concrete structures
impl Renderable for Circle {
  func render() {
    print("Rendering circle");
  }
}

impl Describable for Circle {
  func get_description(): String {
    return "Circle shape";
  }
}

impl Renderable for Rectangle {
  func render() {
    print("Rendering rectangle");
  }
}

impl Describable for Rectangle {
  func get_description(): String {
    return "Rectangle shape";
  }
}

// 4. Function accepting a trait parameter (Implicit Trait Subtyping)
func render_shape(shape: Renderable) {
  shape.render();
}

// 5. Function returning a trait type (Interface Erasure)
func create_circle(r: float): Renderable {
  return Circle { radius = r };
}

// 6. Function taking and returning an optional trait parameter
func describe_item(item: Describable?): Describable? {
  if let unwrapped ?= item {
    print(unwrapped.get_description());
  }
  return item;
}

func main() {
  let c = Circle { radius = 5.0 };
  let r = Rectangle { width = 10.0, height = 4.0 };

  // Pass concrete structs to trait parameter
  render_shape(c);
  render_shape(r);

  // Receive concrete struct as trait return type
  let shape = create_circle(2.5);
  shape.render();

  // Optional trait subtyping
  let c_opt: Circle? = c;
  let res = describe_item(c_opt);

  // Heterogeneous trait collection ([Renderable])
  // Holds different concrete struct types (Circle & Rectangle) in same array
  print("--- Iterating Heterogeneous Trait Collection ---");
  let scene: [Renderable] = [c, r, create_circle(1.5)];
  for item in scene {
    item.render();
  }
}
