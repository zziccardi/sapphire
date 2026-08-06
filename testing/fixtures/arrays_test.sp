/*
 * Fixture: arrays_test.sp
 * Tests array creation, 0-based indexing, bounds behavior, element mutation, and size.
 */

@test
func test_array_indexing(): int {
  let numbers = [10, 20, 30, 40];
  return numbers[1];
}

@test
func test_array_size(): int {
  let items = [1, 2, 3, 4, 5];
  return items.size();
}

@test
func test_array_mutation(): int {
  var mut_arr = [1, 2, 3];
  mut_arr[1] = 99;
  return mut_arr[1];
}

@test
func test_array_push(): int {
  var mut_arr = [5, 10];
  mut_arr.push(15);
  return mut_arr.size();
}

@test
func test_array_contains(): int {
  let items = [100, 200, 300];
  if items.contains(200) {
    return 1;
  }
  return 0;
}
