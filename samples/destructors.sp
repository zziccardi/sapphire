/*
 * Sample Sapphire program illustrating deterministic destructors (`__del__`)
 * for automatic stack RAII.
 *
 * Demonstrates:
 * 1. Defining `func __del__()` on a struct with implicit mutable `self`.
 * 2. Scope-bound deterministic LIFO (last-in, first-out) destruction.
 * 3. Return-value optimization (RVO) destructor elision when transferring
 *    ownership.
 * 4. Automatic cleanup of loop-scoped variables during iterations and early
 *    break.
 */

struct Resource {
  var id: int;
  var name: String;
  var is_active: bool;
}

impl Resource {
  func __init__(id: int, name: String) {
    self.id = id;
    self.name = name;
    self.is_active = true;
    print(f"  [Created] Resource #{self.id} ({self.name})");
  }

  func __del__() {
    if self.is_active {
      self.is_active = false;
      print(f"  [Destroyed] Resource #{self.id} ({self.name})");
    }
  }
}

// 1. Function demonstrating RVO (Return-Value Optimization) elision
func acquire_resource(id: int, name: String): Resource {
  print("Entering acquire_resource()...");
  let temp_helper = Resource(id = 999, name = "TempHelper");
  let main_res = Resource(id = id, name = name);
  print("Returning main_res (ownership transferred to caller)...");
  // temp_helper is destroyed here, but main_res destructor is elided via RVO
  return main_res;
}

func main() {
  print("=== 1. Block Scope & LIFO Destruction ===");
  if true {
    let first = Resource(id = 1, name = "First");
    let second = Resource(id = 2, name = "Second");
    print("Exiting block scope (expect Second destroyed before First)...");
  }
  print("Block scope exited.\n");

  print("=== 2. RVO & Transfer of Ownership ===");
  if true {
    let kept = acquire_resource(id = 42, name = "KeptResource");
    print(f"Caller received resource #{kept.id}");
    print("Exiting caller scope (KeptResource destroyed now)...");
  }
  print("Caller scope exited.\n");

  print("=== 3. Loop Iteration & Break Cleanup ===");
  for i in range(1, 4) {
    let item = Resource(id = i, name = f"LoopItem{i}");
    if i == 2 {
      print("Breaking loop early...");
      break;
    }
  }
  print("Loop finished.");
}
