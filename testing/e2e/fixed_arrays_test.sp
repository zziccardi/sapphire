/*
 * E2E Test: fixed_arrays_test.sp
 * Tests fixed-size array declarations [T; N] and negative indexing.
 */

@test
func test_fixed_array_indexing(): int {
  let scores: [int; 3] = [10, 20, 30];
  return scores[0] + scores[1] + scores[2];
}

@test
func test_fixed_array_negative_indexing(): int {
  let scores: [int; 3] = [10, 20, 30];
  let last = scores[-1];
  let mid = scores[-2];
  let first = scores[-3];
  return last + mid + first;
}

@test
func test_dynamic_array_negative_indexing(): int {
  let items = [100, 200, 300, 400];
  return items[-1] + items[-4];
}

@test
func test_fixed_array_assignment_to_dynamic(): int {
  let fixed: [int; 3] = [1, 2, 3];
  let dyn: [int] = fixed;
  return dyn.size();
}

@test
func test_fixed_array_mutation_with_negative_index(): int {
  var fixed: [int; 3] = [10, 20, 30];
  fixed[-1] = 99;
  return fixed[2];
}
