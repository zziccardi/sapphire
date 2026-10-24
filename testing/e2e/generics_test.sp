/*
 * E2E Test: generics_test.sp
 * Tests monomorphization and specialization of generic structs and functions.
 */

struct Box<T> {
  var item: T;
}

impl Box<T> {
  func get_item(): T {
    return self.item;
  }
}

func wrap_double<T>(val: int): int {
  return val * 2;
}

@test
func test_generic_struct_int(): int {
  let b = Box<int> { item = 42 };
  return b.get_item();
}

@test
func test_generic_struct_string_len(): int {
  let b = Box<String> { item = "Sapphire" };
  return b.item.size();
}

@test
func test_generic_function_specialization(): int {
  return wrap_double<int>(21);
}
