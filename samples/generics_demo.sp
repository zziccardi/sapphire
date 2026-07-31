/*
 * Sample Sapphire program illustrating compile-time generics (parametric
   polymorphism).
 * Shows generic structs, generic impl blocks, generic functions, and contextual
   type inference.
 */

// 1. Generic struct definition
struct Stack<T> {
  var top: T;
}

// 2. Generic impl block for Stack<T>
impl<T> Stack<T> {
  func __init__(top: T) {
    self.top = top;
  }

  const func get_top(): T {
    return self.top;
  }
}

// 3. Multi-parameter generic struct
struct Pair<K, V> {
  var key: K;
  var value: V;
}

impl<K, V> Pair<K, V> {
  func __init__(key: K, value: V) {
    self.key = key;
    self.value = value;
  }
}

// 4. Generic standalone function
func identity<T>(val: T): T {
  return val;
}

// 5. Generic function creating generic struct
func make_pair<K, V>(k: K, v: V): Pair<K, V> {
  return Pair<K, V>(key = k, value = v);
}

func main() {
  // Explicit type argument instantiation for generic struct
  let int_stack = Stack<int>(top = 10);
  let string_stack = Stack<String>(top = "hello");

  // Explicit type argument function invocation
  let x = identity<int>(100);
  let pi = identity<float>(3.14);

  // Inferred type argument function invocation
  let y = identity(42);

  // Generic struct initializer syntax
  let pair = Pair<String, int> {
    key = "score",
    value = 95,
  };
}
