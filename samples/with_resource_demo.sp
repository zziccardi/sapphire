/*
 * Sample Sapphire program illustrating General RAII Resource Management using
 * `with` statements.
 *
 * Demonstrates:
 * 1. Implementing the built-in `Disposable` trait for custom structs.
 * 2. Scope-bound deterministic resource acquisition and LIFO cleanup.
 * 3. Multi-clause `with` blocks (semicolon-separated) to manage multiple
 *    resources without nesting.
 * 4. Fallible resource unwrapping (`?=`) with `else` fallback error handling.
 * 5. Scope-bound memory arena lifecycle management using `with Arena()`.
 */

// 1. Define custom disposable resources
struct FileHandle {
  var path: String;
  var is_open: bool;
}

impl Disposable for FileHandle {
  func dispose(var self) {
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

impl Disposable for DatabaseTransaction {
  func dispose(var self) {
    if !self.committed {
      print("  [DatabaseTransaction] Rolling back uncommitted transaction: " + self.tx_id);
    } else {
      print("  [DatabaseTransaction] Transaction " + self.tx_id + " finalized successfully");
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
func demo_basic_with() {
  print("--- 1. Basic Single Resource with Block ---");
  with let f = FileHandle { path = "config.json", is_open = true } {
    print("  Inside with block: Reading from " + f.path);
  }
  print("  Exited with block - resource has been disposed.");
}

func demo_multi_resource_with() {
  print("\n--- 2. Multi-Resource with Block (LIFO Cleanup) ---");
  with let src = FileHandle { path = "source.dat", is_open = true };
       let dst = FileHandle { path = "backup.dat", is_open = true } {
    print("  Inside with block: Copying from " + src.path + " to " + dst.path);
  }
  print("  Exited with block - resources disposed in reverse acquisition order (LIFO).");
}

func demo_fallible_unwrap_with(src_path: String, dst_path: String) {
  print("\n--- 3. Fallible Resource Unwrapping (?=) with else Fallback ---");
  with let src ?= open_file(path = src_path);
       let dst ?= open_file(path = dst_path) {
    print("  Successfully acquired both resources: " + src.path + " -> " + dst.path);
  } else {
    print("  Failed to acquire one or more files! Fallback executed.");
  }
}

func demo_transaction_with() {
  print("\n--- 4. Transaction Management & Auto-Rollback ---");
  with var tx = begin_tx(tx_id = "TX-1001") {
    print("  Executing database operations in transaction...");
    // Simulate committing the transaction
    tx.committed = true;
  }

  with var tx_fail = begin_tx(tx_id = "TX-1002") {
    print("  Executing operations that fail before commit...");
    // tx_fail.committed remains false -> automatically rolls back upon leaving with block
  }
}

func demo_arena_with() {
  print("\n--- 5. Arena Lifetime Management via with Block ---");
  with let arena = Arena() {
    print("  Allocated temporary arena for scoped memory management.");
  }
  print("  Arena destroyed and reclaimed upon with block exit.");
}

func main() {
  print("=================================================");
  print("  Sapphire RAII Resource Management (with demo)");
  print("=================================================");

  demo_basic_with();
  demo_multi_resource_with();
  demo_fallible_unwrap_with(src_path = "data.csv", dst_path = "out.csv");
  demo_fallible_unwrap_with(src_path = "", dst_path = "out.csv");
  demo_transaction_with();
  demo_arena_with();

  print("\nAll RAII with statement demos completed successfully!");
}
