/*
 * Sample Sapphire program illustrating Scope-Bound RAII Resource Management.
 *
 * Demonstrates:
 * 1. Implementing the `__del__()` destructor for custom RAII structs.
 * 2. Scope-bound deterministic resource acquisition and LIFO cleanup using
 *    ordinary lexical blocks (`{ ... }`).
 * 3. Multi-resource acquisition with guaranteed reverse-order destruction.
 * 4. Fallible resource unwrapping (`?=`) via `if let` and `guard let`.
 * 5. Scope-bound memory arena lifecycle management using lexical `Arena()`.
 */

// 1. Define custom disposable resources
struct FileHandle {
  var path: String;
  var is_open: bool;
}

impl FileHandle {
  func __del__() {
    if self.is_open {
      self.is_open = false;
      print("  [FileHandle] Closed and flushed file: " + self.path);
    }
  }
}

struct DatabaseTransaction {
  var tx_id: String;
  var committed: bool;
}

impl DatabaseTransaction {
  func __del__() {
    if !self.committed {
      print("  [DatabaseTransaction] Rolling back uncommitted transaction: " +
            self.tx_id);
    } else {
      print("  [DatabaseTransaction] Transaction " + self.tx_id +
            " finalized successfully");
    }
  }
}

// 2. Helper factory functions
func open_file(path: String): FileHandle? {
  if path == "" {
    return none;
  }
  print("  [FileHandle] Opened: " + path);
  return FileHandle { path = path, is_open = true };
}

func begin_tx(tx_id: String): DatabaseTransaction {
  print("  [DatabaseTransaction] Began transaction: " + tx_id);
  return DatabaseTransaction { tx_id = tx_id, committed = false };
}

// 3. Demo functions
func demo_basic_scoped_raii() {
  print("--- 1. Basic Single Resource (Scoped Block) ---");
  {
    let f = FileHandle { path = "config.json", is_open = true };
    print("  Inside block: Reading from " + f.path);
  }
  print("  Exited block - resource has been disposed via __del__().");
}

func demo_multi_resource_lifo() {
  print("\n--- 2. Multi-Resource Block (LIFO Cleanup) ---");
  {
    let src = FileHandle { path = "source.dat", is_open = true };
    let dst = FileHandle { path = "backup.dat", is_open = true };
    print("  Inside block: Copying from " + src.path + " to " + dst.path);
  }
  print("  Exited block - resources disposed in reverse order (LIFO).");
}

func demo_fallible_unwrap_if_let(src_path: String) {
  print("\n--- 3. Fallible Resource Unwrapping (?=) with if let ---");
  if let src ?= open_file(path = src_path) {
    print("  Successfully acquired resource: " + src.path);
  } else {
    print("  Failed to acquire file! Fallback executed.");
  }
}

func demo_transaction_rollback() {
  print("\n--- 4. Transaction Management & Auto-Rollback ---");
  {
    var tx = begin_tx(tx_id = "TX-1001");
    print("  Executing database operations in transaction...");
    // Simulate committing the transaction
    tx.committed = true;
  }

  {
    var tx_fail = begin_tx(tx_id = "TX-1002");
    print("  Executing operations that fail before commit...");
    // tx_fail.committed remains false -> automatically rolls back upon block exit
  }
}

func demo_arena_lifetime() {
  print("\n--- 5. Arena Lifetime Management via Scoped Block ---");
  {
    let arena = Arena();
    print("  Allocated temporary arena for scoped memory management.");
  }
  print("  Arena destroyed and reclaimed upon scope exit.");
}

func main() {
  print("=================================================");
  print("  Sapphire RAII Resource Management Demo");
  print("=================================================");

  demo_basic_scoped_raii();
  demo_multi_resource_lifo();
  demo_fallible_unwrap_if_let(src_path = "data.csv");
  demo_fallible_unwrap_if_let(src_path = "");
  demo_transaction_rollback();
  demo_arena_lifetime();

  print("\nAll RAII demos completed successfully!");
}
