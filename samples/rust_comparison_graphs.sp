/*
 * rust_comparison_graphs.sp
 *
 * Demonstrates how Sapphire solves Rust's infamous pain points around:
 * 1. Cyclic structures & graphs (Rust requires Rc<RefCell<T>> or unsafe).
 * 2. Doubly linked lists & parent pointers (Rust requires Weak<RefCell<T>>).
 * 3. Prototypal state delegation & lexical arenas (live delegation & CoW).
 *
 * Reference: docs/rust_comparison.md Section 2.2
 */

// ============================================================================
// 1. Cyclic Directed Graph
// In safe Rust, nodes pointing to other nodes in cyclic relationships
// cannot be represented with normal references (&T) due to the borrow checker.
// Rust requires Rc<RefCell<Node>>, generational arena indices, or unsafe.
// In Sapphire, reference types are passed by constant reference by default,
// and nodes can naturally hold arrays of neighbor nodes with direct mutation.
// ============================================================================

struct GraphNode {
  var id: String;
  var neighbors: [GraphNode];
}

impl GraphNode {
  var func add_edge(var neighbor: GraphNode) {
    self.neighbors.push(neighbor);
  }

  // Traversal with visited set to safely handle cycles
  func has_path_to(target_id: String, var visited: [String: bool]): bool {
    if self.id == target_id {
      return true;
    }
    visited.insert(self.id, true);

    for next_node in self.neighbors {
      if !visited.contains(next_node.id) {
        if next_node.has_path_to(target_id, visited) {
          return true;
        }
      }
    }
    return false;
  }
}

// ============================================================================
// 2. Doubly Linked List & Tree with Parent Pointers
// Doubly linked lists and parent pointers in Rust require Option<Weak<...>>
// to avoid memory leaks caused by reference counting cycles. Every access
// requires .upgrade() and runtime borrow checks (.borrow() / .borrow_mut()).
// In Sapphire, parent and neighbor pointers are natural optional references.
// ============================================================================

struct DoublyLinkedNode {
  var value: int;
  var prev: DoublyLinkedNode?;
  var next: DoublyLinkedNode?;
}

impl DoublyLinkedNode {
  var func link_next(var following: DoublyLinkedNode) {
    self.next = following;
    following.prev = self;
  }
}

struct TreeNode {
  var name: String;
  var parent: TreeNode?;
  var children: [TreeNode];
}

impl TreeNode {
  var func add_child(var child: TreeNode) {
    child.parent = self;
    self.children.push(child);
  }

  // Navigate upward from any child node to the root
  func path_to_root(): String {
    var path = self.name;
    var curr = self.parent;
    while curr != none {
      if let p ?= curr {
        path = p.name + "/" + path;
        curr = p.parent;
      }
    }
    return "/" + path;
  }
}

// ============================================================================
// 3. Prototypal State Delegation & Scoped Lexical Arenas
// Rust has no concept of prototype delegation; sharing state across entities
// requires duplicate copies or runtime pointer indirection.
// Sapphire provides opt-in `proto` and `clone`, where clones dynamically
// delegate field reads live to their prototype.
// Copy-on-Write (CoW) automatically protects base prototypes when nested fields
// are modified. Scoped Arenas deallocate all objects in bulk upon scope exit.
// ============================================================================

struct Transform {
  var x: float;
  var y: float;
}

proto EntityNode {
  var name: String;
  var hp: int;
  var transform: Transform;
  var parent: EntityNode?;
}

// ============================================================================
// Demonstrations
// ============================================================================

func demo_cyclic_graph() {
  print("=== 1. Cyclic Graph Traversal ===");
  var a = GraphNode { id = "NodeA", neighbors = [] };
  var b = GraphNode { id = "NodeB", neighbors = [] };
  var c = GraphNode { id = "NodeC", neighbors = [] };
  var d = GraphNode { id = "NodeD", neighbors = [] };

  // Create cycle: A -> B -> C -> A, plus a branch C -> D
  a.add_edge(b);
  b.add_edge(c);
  c.add_edge(a);
  c.add_edge(d);

  var visited1: [String: bool] = {};
  let path_a_to_d = a.has_path_to("NodeD", visited1);
  print(f"Path NodeA -> NodeD exists: {String.from(path_a_to_d)}");

  var visited2: [String: bool] = {};
  let path_d_to_a = d.has_path_to("NodeA", visited2);
  print(f"Path NodeD -> NodeA exists: {String.from(path_d_to_a)}");
}

func demo_doubly_linked_and_tree() {
  print("=== 2. Doubly Linked List & Tree Parent Pointers ===");

  // Doubly linked list setup
  var n1 = DoublyLinkedNode { value = 10, prev = none, next = none };
  var n2 = DoublyLinkedNode { value = 20, prev = none, next = none };
  var n3 = DoublyLinkedNode { value = 30, prev = none, next = none };

  n1.link_next(n2);
  n2.link_next(n3);

  // Backward traversal from tail node
  print("Backward traversal from tail:");
  var curr: DoublyLinkedNode? = n3;
  while curr != none {
    if let node ?= curr {
      print("  Node value: " + String.from(node.value));
      curr = node.prev;
    }
  }

  // Hierarchical tree with upward parent pointers
  var root = TreeNode { name = "root", parent = none, children = [] };
  var src = TreeNode { name = "src", parent = none, children = [] };
  var main_file = TreeNode { name = "main.sp", parent = none, children = [] };

  root.add_child(src);
  src.add_child(main_file);

  print("Path from main.sp to root: " + main_file.path_to_root());
}

func demo_prototypal_arenas() {
  print("=== 3. Prototypal State Delegation & Lexical Arenas ===");
  let scene_arena = Arena();

  // Base archetype allocated in explicit arena
  var base_goblin = EntityNode {
    name = "Goblin Archer",
    hp = 50,
    transform = Transform { x = 0.0, y = 0.0 },
    parent = none,
  } in scene_arena;

  // Clones inherit base state without copying memory upfront
  var elite_goblin = clone base_goblin {
    self.name = "Elite Goblin";
    self.parent = base_goblin;
  };

  print("Elite initial hp (delegated): " + String.from(elite_goblin.hp));

  // Live mutation: buffing base_goblin immediately updates elite_goblin
  base_goblin.hp = 65;
  print("Elite hp after base buff: " + String.from(elite_goblin.hp));

  // Copy-on-Write: mutating nested transform isolates elite's state
  elite_goblin.transform.x = 100.0;
  print("Elite pos x: " + String.from(elite_goblin.transform.x));
  print("Base goblin pos x: " + String.from(base_goblin.transform.x));

  // When scene_arena goes out of scope here, all allocated entities
  // are deallocated deterministically in bulk without reference-cycle leaks.
}

func main() {
  demo_cyclic_graph();
  demo_doubly_linked_and_tree();
  demo_prototypal_arenas();
}
