"""Array, map, indexing, and collection builtin semantic tests."""

import unittest

from src.parser.ast import (
  ArgumentNode,
  BasicTypeNode,
  CallNode,
  IdentifierNode,
  LiteralNode,
  MemberAccessNode,
)
from src.semantics.symbol_table import (
  ArrayType,
  PrimitiveType,
  VariableSymbol,
)
from src.semantics.type_checker import SemanticError, TypeChecker
from testing.test_utils import TypeCheckerTestBase


class TestTypeCheckerCollections(TypeCheckerTestBase, unittest.TestCase):
  """Array, map, indexing, and collection builtin semantic tests."""

  def test_inconsistent_array_literal(self):
    """Enforces that array literals have consistent element types."""
    code = """
    func test() {
      let arr = [1, "hello"];
    }
    """
    with self.assertRaises(SemanticError) as context:
      self._check(code)
    self.assertIn("Inconsistent element types in array literal", str(context.exception))

  def test_index_non_array(self):
    """Enforces that indexing is only allowed on array types."""
    code = """
    func test() {
      let x = 10;
      let y = x[0];
    }
    """
    with self.assertRaises(SemanticError) as context:
      self._check(code)
    self.assertIn("Cannot index non-array type", str(context.exception))

  def test_assign_index_const_array(self):
    """Enforces that indexing assignment requires a mutable array variable."""
    code = """
    func test() {
      let arr = [10, 20];
      arr[0] = 30;
    }
    """
    with self.assertRaises(SemanticError) as context:
      self._check(code)
    self.assertIn("Cannot assign to index of constant array 'arr'", str(context.exception))

  def test_for_target_not_array(self):
    """Enforces that for loop iterables must be arrays."""
    code = """
    func test() {
      let x = 10;
      for item in x {
        let y = item;
      }
    }
    """
    with self.assertRaises(SemanticError) as context:
      self._check(code)
    self.assertIn("For-in loop source must be an array, map, or range type", str(context.exception))

  def test_for_map_iteration_valid(self):
    """Verifies type checking for valid map iteration."""
    code = """
    func test() {
      let m = {"a": 1, "b": 2};
      for k, v in m {
        let k_copy: String = k;
        let v_copy: int = v;
      }
    }
    """
    self._check(code)

  def test_for_map_iteration_single_var_error(self):
    """Enforces that iterating over a map requires dual key-value loop variables."""
    code = """
    func test() {
      let m = {"a": 1};
      for item in m {
      }
    }
    """
    with self.assertRaises(SemanticError) as context:
      self._check(code)
    self.assertIn("Map iteration requires key and value loop variables", str(context.exception))

  def test_for_array_iteration_dual_var_error(self):
    """Enforces that iterating over an array prohibits dual key-value loop variables."""
    code = """
    func test() {
      let arr = [1, 2, 3];
      for k, v in arr {
      }
    }
    """
    with self.assertRaises(SemanticError) as context:
      self._check(code)
    self.assertIn("Cannot iterate over an array with key-value syntax", str(context.exception))

  def test_arrays_and_indexing(self):
    """Verifies that array literal types and indexing resolve successfully."""
    self._check("""
    func test() {
      let arr = [10, 20];
      let first = arr[0];
    }
    """)

  def test_map_literal_type_checking(self):
    """Verifies type checking for map literals, key type restrictions, homogeneity, and indexing."""
    # 1. Valid string, int, and enum keyed maps
    self._check("""
    enum Direction { North, South }

    func test() {
      let string_map = {"alice": 100, "bob": 95,};
      let int_map = {1: "low", 2: "high"};
      let enum_map = {Direction.North: 10, Direction.South: 20};

      let score: int = string_map["alice"];
      let level: String = int_map[1];
      let speed: int = enum_map[Direction.North];
    }
    """)

    # 2. Invalid key type (boolean key)
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func test() {
        let bad_map = {true: 1};
      }
      """)
    self.assertIn("Map key must be a string, int, or enum.", str(ctx.exception))

    # 3. Inconsistent key types (mixed int and string keys)
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func test() {
        let bad_map = {"alice": 100, 2: 95};
      }
      """)
    self.assertIn("Inconsistent key types in map literal.", str(ctx.exception))

    # 4. Inconsistent value types (mixed int and string values)
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func test() {
        let bad_map = {"alice": 100, "bob": "95"};
      }
      """)
    self.assertIn("Inconsistent value types in map literal.", str(ctx.exception))

    # 5. Map index type mismatch
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func test() {
        let string_map = {"alice": 100};
        let val = string_map[123];
      }
      """)
    self.assertIn("Map index type 'int' is not compatible with key type 'String'.", str(ctx.exception))

    # 6. Empty map literal
    self._check("""
    func test() {
      let empty_map = {};
    }
    """)

    # 7. Invalid key type on subsequent entry
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func test() {
        let bad_map = {"alice": 100, true: 200};
      }
      """)
    self.assertIn("Map key must be a string, int, or enum.", str(ctx.exception))

  def test_array_compile_time_bounds_checking(self):
    """Verifies compile-time bounds checking for array indexing."""
    # 1. Out of bounds index on array literal
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func test() {
        let x = [10, 20, 30][3];
      }
      """)
    self.assertIn("Array index out of bounds: index 3 is out of bounds for array of size 3.", str(ctx.exception))

    # 2. Valid negative indexing and out of bounds negative index on array literal
    self._check("""
    func test() {
      let last = [10, 20, 30][-1];
      let first = [10, 20, 30][-3];
    }
    """)

    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func test() {
        let x = [10, 20, 30][-4];
      }
      """)
    self.assertIn("Array index out of bounds: index -4 is out of bounds for array of size 3.", str(ctx.exception))

    # 3. Out of bounds index on array variable
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func test() {
        let arr = [10, 20];
        let val = arr[5];
      }
      """)
    self.assertIn("Array index out of bounds: index 5 is out of bounds for array of size 2.", str(ctx.exception))

    # 4. Out of bounds assignment to array variable
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func test() {
        var arr = [1, 2, 3];
        arr[10] = 50;
      }
      """)
    self.assertIn("Array index out of bounds: index 10 is out of bounds for array of size 3.", str(ctx.exception))

    # 5. Valid constant indexing
    self._check("""
    func test() {
      let arr = [10, 20, 30];
      let first = arr[0];
      let last = arr[2];
      let back = arr[-1];
    }
    """)

  def test_fixed_size_array_type_checking(self):
    """Verifies semantic analysis and bounds rules for [T; N] fixed-size arrays."""
    # 1. Valid declaration, literal assignment, and indexing
    self._check("""
    func test() {
      let scores: [int; 3] = [95, 88, 72];
      let first = scores[0];
      let last = scores[2];
      let back = scores[-1];
      let front_neg = scores[-3];
    }
    """)

    # 2. Literal size mismatch
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func test() {
        let scores: [int; 3] = [95, 88];
      }
      """)
    self.assertIn("Fixed-size array '[int; 3]' requires exactly 3 element(s), got 2.", str(ctx.exception))

    # 3. Constant out of bounds positive index
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func test() {
        let scores: [int; 3] = [95, 88, 72];
        let val = scores[3];
      }
      """)
    self.assertIn("Array index out of bounds: index 3 is out of bounds for array of size 3.", str(ctx.exception))

    # 4. Constant out of bounds negative index
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func test() {
        let scores: [int; 3] = [95, 88, 72];
        let val = scores[-4];
      }
      """)
    self.assertIn("Array index out of bounds: index -4 is out of bounds for array of size 3.", str(ctx.exception))

    # 5. Assignable from [T; N] to unbounded [T]
    self._check("""
    func test() {
      let scores: [int; 3] = [95, 88, 72];
      let dynamic: [int] = scores;
    }
    """)

    # 6. Rejection of assigning unbounded [T] to [T; N]
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func test() {
        let dynamic: [int] = [1, 2, 3];
        let fixed: [int; 3] = dynamic;
      }
      """)
    self.assertIn("Cannot assign expression of type '[int]' to variable 'fixed' of type '[int; 3]'.", str(ctx.exception))

    # 7. Rejection of size mismatch between fixed arrays
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func test() {
        let fixed3: [int; 3] = [1, 2, 3];
        let fixed4: [int; 4] = fixed3;
      }
      """)
    self.assertIn("Cannot assign expression of type '[int; 3]' to variable 'fixed4' of type '[int; 4]'.", str(ctx.exception))

  def test_map_compile_time_key_validation(self):
    """Verifies compile-time key checking for map literals."""
    # 1. Missing key in map literal
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func test() {
        let val = {"alice": 100, "bob": 95}["charlie"];
      }
      """)
    self.assertIn("Key 'charlie' not found in map literal.", str(ctx.exception))

    # 2. Valid key in map literal
    self._check("""
    func test() {
      let score = {"alice": 100, "bob": 95}["alice"];
    }
    """)

  def test_array_type_node_resolution_and_none_inference(self):
    """Verifies ArrayTypeNode resolution and error when inferring type from none alone."""
    from src.parser.ast import (
      ArrayLiteralNode,
      ArrayTypeNode,
      LiteralNode,
      VarDeclNode,
    )
    from src.semantics.symbol_table import ArrayType, PrimitiveType


    checker = TypeChecker()
    res = checker._resolve_type_node(ArrayTypeNode(BasicTypeNode("int")))
    self.assertEqual(res, ArrayType(PrimitiveType("int")))

    var_decl = VarDeclNode(
        is_mutable=False,
        names=["arr"],
        val_types=[ArrayTypeNode(BasicTypeNode("int"))],
        exprs=[ArrayLiteralNode([LiteralNode(10, "int"), LiteralNode(20, "int")])],
    )
    checker.visit_VarDeclNode(var_decl)
    sym = checker.symbol_table.lookup("arr")
    self.assertEqual(sym.symbol_type, ArrayType(PrimitiveType("int"), size=2, is_fixed_size=False))

    with self.assertRaises(SemanticError):
      self._check("""
      func test() {
        let x = none;
      }
      """)

  def test_shorthand_collection_types(self):
    """Verifies semantic type checking for [T], [K: V], Array<T>, and Map<K, V>."""
    self._check("""
    func test() {
      let numbers: [int] = [10, 20, 30];
      let legacy_numbers: Array<int> = [40, 50];
      let counts: [String: int] = {"apples": 5, "oranges": 10};
      let legacy_counts: Map<String, int> = {"bananas": 3};
    }
    """)

  def test_collection_type_inference(self):
    """Verifies type inference for implicit array/map literals, empty literals, and type mismatch errors."""
    self._check("""
    func test() {
      let numbers = [1, 2, 3];
      let counts = {"a": 1, "b": 2};
      let empty_arr: [int] = [];
      let empty_map: [String: float] = {};
    }
    """)

    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func test() {
        let arr = [10, "string"];
      }
      """)
    self.assertIn("Inconsistent element types in array literal", str(ctx.exception))

    with self.assertRaises(SemanticError) as ctx2:
      self._check("""
      func test() {
        let m = {"a": 10, "b": "string"};
      }
      """)
    self.assertIn("Inconsistent value types in map literal", str(ctx2.exception))

  def test_array_builtin_methods(self):
    """Verifies type checking for Array built-in methods (size, empty, map, filter, reduce)."""
    # 1. Valid method usage & chaining
    self._check("""
    func main() {
      let numbers = [1, 2, 3, 4, 5];
      let sz: int = numbers.size();
      let is_empty: bool = numbers.empty();

      let doubled: [int] = numbers.map(x -> x * 2);
      let evens: [int] = numbers.filter(x -> x % 2 == 0);
      let sum: int = numbers.reduce(0, (acc, x) -> acc + x);
      let sum_rev: int = numbers.reduce(0, (acc, x) -> acc + x, reverse = true);

      let chained_sum: int = numbers
          .filter(x -> x % 2 == 0)
          .map(x -> x * 10)
          .reduce(0, (acc, x) -> acc + x);

      let named_reduce: int = numbers.reduce(initial = 0, fn = (acc, x) -> acc + x, reverse = false);
      let pos3_reduce: int = numbers.reduce(0, (acc, x) -> acc + x, true);

      let has_three: bool = numbers.contains(3);
      let rev_arr: [int] = numbers.reverse();
      let sorted_arr: [int] = numbers.sort();
      let custom_sort: [int] = numbers.sort(by = (a, b) -> b - a, reverse = false);
      let joined: String = numbers.join(", ");

      var mut_arr = [10, 20];
      let p_val: int = mut_arr.push(30);
      let i_val: int = mut_arr.insert(1, 15);
      let pop_val: int? = mut_arr.pop();
      let rem_val: int? = mut_arr.remove(0);
      mut_arr.clear();
    }
    """)

    # 1b. Mutating methods on constant binding (error)
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func main() {
        let arr = [1, 2];
        let p = arr.push(3);
      }
      """)
    self.assertIn("Cannot invoke mutating method 'push' on constant variable 'arr'", str(ctx.exception))

    # 1c. Mutating methods on fixed-size array (error)
    checker = TypeChecker()
    checker.symbol_table.define("fixed_arr", VariableSymbol("fixed_arr", ArrayType(PrimitiveType("int"), size=2, is_fixed_size=True), is_mutable=True))
    call_node = CallNode(MemberAccessNode(IdentifierNode("fixed_arr"), "push", is_optional=False), [ArgumentNode(None, LiteralNode(3, "int"))])
    checker.visit(call_node)
    self.assertTrue(any("Cannot invoke mutating method 'push' on fixed-size array" in e for e in checker.errors))

    # 2. Invalid size and empty call with arguments
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func main() {
        let arr = [1, 2];
        let sz = arr.size(123);
      }
      """)
    self.assertIn(".size() takes no arguments", str(ctx.exception))

    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func main() {
        let arr = [1, 2];
        let is_emp = arr.empty(123);
      }
      """)
    self.assertIn(".empty() takes no arguments", str(ctx.exception))

    # 3. Invalid map call (wrong argument count or param type mismatch)
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func main() {
        let arr = [1, 2];
        let res = arr.map();
      }
      """)
    self.assertIn(".map() requires at least 1 argument (fn)", str(ctx.exception))

    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func main() {
        let arr = [1, 2];
        let res = arr.map((x: String) -> "str");
      }
      """)
    self.assertIn("Closure parameter type mismatch in .map()", str(ctx.exception))

    # 4. Invalid filter call (wrong argument count, param type mismatch, or return type)
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func main() {
        let arr = [1, 2];
        let res = arr.filter();
      }
      """)
    self.assertIn(".filter() requires at least 1 argument (fn)", str(ctx.exception))

    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func main() {
        let arr = [1, 2];
        let res = arr.filter((x: String) -> true);
      }
      """)
    self.assertIn("Closure parameter type mismatch in .filter()", str(ctx.exception))

    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func main() {
        let arr = [1, 2];
        let res = arr.filter(x -> "not a bool");
      }
      """)
    self.assertIn(".filter() predicate closure must return 'bool'", str(ctx.exception))

    # 5. Invalid reduce call (missing initial, param mismatch, or return mismatch)
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func main() {
        let arr = [1, 2];
        let res = arr.reduce(fn = (acc, x) -> acc + x);
      }
      """)
    self.assertIn(".reduce() requires mandatory 'initial' and 'fn' arguments", str(ctx.exception))

    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func main() {
        let arr = [1, 2];
        let res = arr.reduce(0, (acc: String, x: int) -> "str");
      }
      """)
    self.assertIn("Closure accumulator parameter mismatch in .reduce()", str(ctx.exception))

    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func main() {
        let arr = [1, 2];
        let res = arr.reduce(0, (acc: int, x: String) -> acc);
      }
      """)
    self.assertIn("Closure item parameter mismatch in .reduce()", str(ctx.exception))

    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func main() {
        let arr = [1, 2];
        let res = arr.reduce(0, (acc: int, x: int) -> "str");
      }
      """)
    self.assertIn("Closure return type in .reduce() must match initial value type", str(ctx.exception))

    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func main() {
        let arr = [1, 2];
        let res = arr.reduce(0, (acc, x) -> acc + x, reverse = 123);
      }
      """)
    self.assertIn("'reverse' parameter in .reduce() must be 'bool'", str(ctx.exception))

    # 6. Phase 2 method errors
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func main() {
        let arr = [1, 2];
        let c = arr.contains("str");
      }
      """)
    self.assertIn("Argument type mismatch in .contains()", str(ctx.exception))

    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func main() {
        let arr = [1, 2];
        let r = arr.reverse(123);
      }
      """)
    self.assertIn("'in_place' parameter in .reverse() must be 'bool'", str(ctx.exception))

    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func main() {
        let arr = [1, 2];
        let s = arr.sort(by = (a, b) -> "not int");
      }
      """)
    self.assertIn("Comparator closure in .sort() must return 'int'", str(ctx.exception))

    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func main() {
        let arr = [1, 2];
        let j = arr.join(123);
      }
      """)
    self.assertIn("Delimiter 'sep' in .join() must be 'String'", str(ctx.exception))

    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func main() {
        var arr = [1, 2];
        let i = arr.insert(index = 0);
      }
      """)
    self.assertIn(".insert() requires mandatory 'index' and 'element' arguments", str(ctx.exception))

    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func main() {
        var arr = [1, 2];
        let rem = arr.remove("not int");
      }
      """)
    self.assertIn("Argument 'index' in .remove() must be 'int'", str(ctx.exception))

    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func main() {
        var arr = [1, 2];
        arr.push();
      }
      """)
    self.assertIn(".push() requires exactly 1 argument", str(ctx.exception))

    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func main() {
        var arr = [1, 2];
        arr.push("str");
      }
      """)
    self.assertIn("Argument type mismatch in .push()", str(ctx.exception))

    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func main() {
        var arr = [1, 2];
        arr.pop(123);
      }
      """)
    self.assertIn(".pop() takes no arguments", str(ctx.exception))

    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func main() {
        var arr = [1, 2];
        arr.insert(index = 0, element = "str");
      }
      """)
    self.assertIn("Argument type mismatch in .insert()", str(ctx.exception))

    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func main() {
        var arr = [1, 2];
        arr.remove();
      }
      """)
    self.assertIn(".remove() requires exactly 1 argument", str(ctx.exception))

    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func main() {
        let arr = [1, 2];
        arr.contains();
      }
      """)
    self.assertIn(".contains() requires exactly 1 argument", str(ctx.exception))

    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func main() {
        let arr = [1, 2];
        arr.sort(by = (a, b) -> a - b, reverse = 123);
      }
      """)
    self.assertIn("'reverse' parameter in .sort() must be 'bool'", str(ctx.exception))

    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func main() {
        var arr = [1, 2];
        arr.insert("not int", 10);
      }
      """)
    self.assertIn("Argument 'index' in .insert() must be 'int'", str(ctx.exception))

    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func main() {
        var arr = [1, 2];
        arr.clear(123);
      }
      """)
    self.assertIn(".clear() takes no arguments", str(ctx.exception))

    self._check("""
    func main() {
      var in_p_arr = [1, 2, 3];
      in_p_arr.map(x -> x * 2, in_place = true);
      in_p_arr.map(fn = x -> x * 2, in_place = true);
      in_p_arr.map(x -> x * 2, true);
      in_p_arr.map(x -> x * 2, in_place = false);
      in_p_arr.filter(x -> x > 1, in_place = true);
      in_p_arr.filter(fn = x -> x > 1, in_place = true);
      in_p_arr.filter(x -> x > 1, true);
      in_p_arr.filter(x -> x > 1, in_place = false);
      in_p_arr.reverse(in_place = true);
      in_p_arr.reverse(true);
      in_p_arr.reverse(in_place = false);
      in_p_arr.sort(in_place = true);
      in_p_arr.sort((a, b) -> a - b, false, false);
      in_p_arr.sort((a, b) -> a - b, false, true);
    }
    """)

    # In-place error checks
    checker = TypeChecker()
    checker.symbol_table.define("fixed_arr", VariableSymbol("fixed_arr", ArrayType(PrimitiveType("int"), size=2, is_fixed_size=True), is_mutable=True))
    call_node = CallNode(
        MemberAccessNode(IdentifierNode("fixed_arr"), "filter", is_optional=False),
        [ArgumentNode(None, IdentifierNode("fn")), ArgumentNode("in_place", LiteralNode(True, "bool"))]
    )
    checker.visit(call_node)
    self.assertTrue(any("Cannot invoke in-place '.filter()' on fixed-size array" in e for e in checker.errors))

    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func main() {
        var arr = [1, 2];
        arr.map(x -> x, in_place = 123);
      }
      """)
    self.assertIn("'in_place' parameter in .map() must be 'bool'", str(ctx.exception))

    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func main() {
        var arr = [1, 2];
        arr.filter(x -> true, in_place = 123);
      }
      """)
    self.assertIn("'in_place' parameter in .filter() must be 'bool'", str(ctx.exception))

    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func main() {
        var arr = [1, 2];
        arr.sort(in_place = 123);
      }
      """)
    self.assertIn("'in_place' parameter in .sort() must be 'bool'", str(ctx.exception))

    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func main() {
        var arr = [1, 2];
        arr.reverse(true, false);
      }
      """)
    self.assertIn(".reverse() takes at most 1 argument", str(ctx.exception))

    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func main() {
        let arr = ["a"];
        arr.join("a", "b");
      }
      """)
    self.assertIn(".join() takes at most 1 argument", str(ctx.exception))

    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func main() {
        let arr = [1, 2];
        arr.map(x -> x * 2, in_place = true);
      }
      """)
    self.assertIn("Cannot invoke in-place transformation '.map()' on constant variable 'arr'", str(ctx.exception))

    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func main() {
        let arr = [1, 2];
        arr.filter(x -> x > 1, in_place = true);
      }
      """)
    self.assertIn("Cannot invoke in-place transformation '.filter()' on constant variable 'arr'", str(ctx.exception))

    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func main() {
        let arr = [1, 2];
        arr.reverse(in_place = true);
      }
      """)
    self.assertIn("Cannot invoke in-place transformation '.reverse()' on constant variable 'arr'", str(ctx.exception))

    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func main() {
        let arr = [1, 2];
        arr.sort(in_place = true);
      }
      """)
    self.assertIn("Cannot invoke in-place transformation '.sort()' on constant variable 'arr'", str(ctx.exception))

    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func main() {
        var arr = [1, 2];
        arr.map(x -> String.from(x), in_place = true);
      }
      """)
    self.assertIn("In-place mapping requires closure return type to match element type 'int'", str(ctx.exception))

    # 7. Non-existent array method
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func main() {
        let arr = [1, 2];
        let res = arr.non_existent_method();
      }
      """)
    self.assertIn("Array has no method 'non_existent_method'", str(ctx.exception))

  def test_map_builtin_methods(self):
    """Verifies type checking for Map built-in methods (size, empty, contains, keys, values, insert, remove, clear)."""
    self._check("""
    func main() {
      let m = {"a": 1, "b": 2};
      let sz: int = m.size();
      let is_empty: bool = m.empty();
      let has_a: bool = m.contains("a");
      let k_list: [String] = m.keys();
      let v_list: [int] = m.values();

      var mut_m = {"x": 10};
      let ins_val: int = mut_m.insert("y", 20);
      let ins_named: int = mut_m.insert(key = "z", value = 30);
      let rem_val: int? = mut_m.remove("x");
      mut_m.clear();
    }
    """)

    # Invalid Map methods & mutability error checks
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func main() {
        let m = {"a": 1};
        m.size(123);
      }
      """)
    self.assertIn(".size() takes no arguments", str(ctx.exception))

    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func main() {
        let m = {"a": 1};
        m.empty(123);
      }
      """)
    self.assertIn(".empty() takes no arguments", str(ctx.exception))

    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func main() {
        let m = {"a": 1};
        m.contains("a", "b");
      }
      """)
    self.assertIn(".contains() requires exactly 1 argument", str(ctx.exception))

    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func main() {
        let m = {"a": 1};
        m.contains(123);
      }
      """)
    self.assertIn("Argument type mismatch in .contains()", str(ctx.exception))

    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func main() {
        let m = {"a": 1};
        m.keys(123);
      }
      """)
    self.assertIn(".keys() takes no arguments", str(ctx.exception))

    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func main() {
        let m = {"a": 1};
        m.values(123);
      }
      """)
    self.assertIn(".values() takes no arguments", str(ctx.exception))

    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func main() {
        let m = {"a": 1};
        m.insert("b", 2);
      }
      """)
    self.assertIn("Cannot invoke mutating method 'insert' on constant variable 'm'", str(ctx.exception))

    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func main() {
        var m = {"a": 1};
        m.insert("b");
      }
      """)
    self.assertIn(".insert() requires mandatory 'key' and 'value' arguments", str(ctx.exception))

    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func main() {
        var m = {"a": 1};
        m.insert(123, 2);
      }
      """)
    self.assertIn("Argument 'key' in .insert() must be 'String'", str(ctx.exception))

    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func main() {
        var m = {"a": 1};
        m.insert("b", "not_int");
      }
      """)
    self.assertIn("Argument 'value' in .insert() must be 'int'", str(ctx.exception))

    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func main() {
        let m = {"a": 1};
        m.remove("a");
      }
      """)
    self.assertIn("Cannot invoke mutating method 'remove' on constant variable 'm'", str(ctx.exception))

    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func main() {
        var m = {"a": 1};
        m.remove();
      }
      """)
    self.assertIn(".remove() requires exactly 1 argument", str(ctx.exception))

    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func main() {
        var m = {"a": 1};
        m.remove(123);
      }
      """)
    self.assertIn("Argument 'key' in .remove() must be 'String'", str(ctx.exception))

    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func main() {
        let m = {"a": 1};
        m.clear();
      }
      """)
    self.assertIn("Cannot invoke mutating method 'clear' on constant variable 'm'", str(ctx.exception))

    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func main() {
        var m = {"a": 1};
        m.clear(123);
      }
      """)
    self.assertIn(".clear() takes no arguments", str(ctx.exception))

    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func main() {
        let m = {"a": 1};
        m.invalid_map_method();
      }
      """)
    self.assertIn("Map has no method 'invalid_map_method'", str(ctx.exception))

  def test_dynamic_indexing_type_checking(self):
    """Verifies standard indexing returns concrete types while .get() returns optional types."""
    # 1. Standard indexing returns concrete type
    self._check("""
    func test(arr: [int], idx: int, m: [String: int], k: String) {
      let val1: int = arr[idx];
      let val2: int = m[k];
    }
    """)

    # 2. get() method returns Optional type
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func test(arr: [int], idx: int) {
        let val: int = arr.get(idx); // get() returns int?, cannot assign directly to int
      }
      """)
    self.assertIn("Cannot assign expression of type 'int?' to variable 'val' of type 'int'.", str(ctx.exception))

    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func test(m: [String: int], k: String) {
        let val: int = m.get(k); // get() returns int?, cannot assign directly to int
      }
      """)
    self.assertIn("Cannot assign expression of type 'int?' to variable 'val' of type 'int'.", str(ctx.exception))

    # 3. get() handled safely via guard
    self._check("""
    func test(arr: [int], idx: int, m: [String: int], k: String): int {
      guard let a_val ?= arr.get(idx); let m_val ?= m.get(k) else {
        return -1;
      }
      return a_val + m_val;
    }
    """)

  def test_array_and_map_get_method(self):
    """Verifies that array.get and map.get resolve to OptionalType."""
    self._check("""
    func test_get() {
      let arr = [10, 20, 30];
      let val_arr: int? = arr.get(0);

      let m = {"a": 1, "b": 2};
      let val_map: int? = m.get("a");
    }
    """)

  def test_subscript_and_container_aliasing(self):
    struct_push_alias = """
    struct Item { var val: int; }
    func main() {
      var arr = [Item { val = 1 }];
      arr.push(arr[0]);
    }
    """
    with self.assertRaises(SemanticError) as ctx:
      self._check(struct_push_alias)
    self.assertIn("cannot pass element borrowed from 'arr'", str(ctx.exception))

    struct_insert_alias = """
    struct Item { var val: int; }
    func main() {
      var arr = [Item { val = 1 }];
      arr.insert(0, arr[0]);
    }
    """
    with self.assertRaises(SemanticError) as ctx:
      self._check(struct_insert_alias)
    self.assertIn("cannot pass element borrowed from 'arr'", str(ctx.exception))

    primitive_push_ok = """
    func main() {
      var nums = [1, 2, 3];
      nums.push(nums[0]);
    }
    """
    self._check(primitive_push_ok)

  def test_array_swap_semantics(self):
    """Verifies type checking and semantic constraints for Array.swap(i, j)."""
    # 1. Valid swap on dynamic array
    self._check("""
    func main() {
      var arr = [10, 20, 30];
      arr.swap(0, 2);
      arr.swap(i = 1, j = -1);
    }
    """)

    # 2. Valid swap on fixed-size array
    checker = TypeChecker()
    checker.symbol_table.define(
        "fixed",
        VariableSymbol(
            "fixed",
            ArrayType(PrimitiveType("int"), size=3, is_fixed_size=True),
            is_mutable=True,
        ),
    )
    call_node = CallNode(
        MemberAccessNode(IdentifierNode("fixed"), "swap", is_optional=False),
        [ArgumentNode(None, LiteralNode(0, "int")), ArgumentNode(None, LiteralNode(2, "int"))],
    )
    res_t = checker.visit(call_node)
    self.assertEqual(res_t, PrimitiveType("none"))
    self.assertEqual(checker.errors, [])

    # 3. Valid swap on array of move-only structs
    self._check("""
    struct Resource {
      var handle: int;
    }
    impl Resource {
      func __del__() {}
    }
    func main() {
      var res_arr = [Resource { handle = 1 }, Resource { handle = 2 }];
      res_arr.swap(0, 1);
    }
    """)

    # 4. Error: Calling swap on immutable array
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func main() {
        let arr = [1, 2, 3];
        arr.swap(0, 1);
      }
      """)
    self.assertIn("Cannot invoke mutating method 'swap' on constant variable 'arr'", str(ctx.exception))

    # 5. Error: Calling swap through deeply immutable SharedRef
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func main() {
        let s = SharedRef([1, 2, 3]);
        s.swap(0, 1);
      }
      """)
    self.assertIn("Cannot invoke mutating method 'swap' through deeply immutable 'SharedRef'", str(ctx.exception))

    # 6. Error: Argument types must be int
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func main() {
        var arr = [1, 2, 3];
        arr.swap("first", 1);
      }
      """)
    self.assertIn("Argument 'i' in .swap() must be 'int'", str(ctx.exception))

    # 7. Error: Missing arguments
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func main() {
        var arr = [1, 2, 3];
        arr.swap(0);
      }
      """)
    self.assertIn(".swap() requires mandatory 'i' and 'j' arguments", str(ctx.exception))

  def test_map_bracket_assignment(self):
    """Verifies map[k] = v assignment, key type checks, and constness."""
    self._check("""
    func main() {
      var counts: [String: int] = {};
      counts["a"] = 1;
      counts["a"] += 2;
      var nested: [int: [int: bool]] = {};
      nested[0] = { 1: true };
      nested[0][2] = false;
    }
    """)

    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func main() {
        let m: [String: int] = { "a": 1 };
        m["b"] = 2;
      }
      """)
    self.assertIn("Cannot assign to key of constant map 'm'", str(ctx.exception))

    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func main() {
        var m: [String: int] = {};
        m[123] = 2;
      }
      """)
    self.assertIn("Map index type 'int' is not compatible with key type 'String'", str(ctx.exception))

    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func main() {
        var m: [String: int] = {};
        m["a"] = "wrong";
      }
      """)
    self.assertIn("Cannot assign type 'String' to target of type 'int'", str(ctx.exception))

  def test_array_bounds_invalidated_after_mutation(self):
    code_push = """
    func main() {
      var arr: [int] = [];
      arr.push(42);
      let x = arr[0];
    }
    """
    self._check(code_push)

    code_var_param = """
    func fill(var a: [int]) {
      a.push(1);
    }
    func main() {
      var arr: [int] = [];
      fill(arr);
      let x = arr[0];
    }
    """
    self._check(code_var_param)

  def test_contains_and_access_map_warnings(self):
    # 1. Immutable read via if map.contains(k) { ... map[k] ... } -> suggests 'if let'
    c1 = self._check("""
    func lookup(m: [String: int], k: String): int {
      if m.contains(k) {
        return m[k];
      }
      return 0;
    }
    """)
    self.assertEqual(len(c1.warnings), 1)
    self.assertIn("if let v ?= <map>.get(<key>)", c1.warnings[0])

    # 2. Short-circuit && in if condition: if m.contains(k) && m[k] > 0
    c2 = self._check("""
    func positive(m: [String: int], k: String): bool {
      if m.contains(k) && m[k] > 0 {
        return true;
      }
      return false;
    }
    """)
    self.assertEqual(len(c2.warnings), 1)
    self.assertIn("if let v ?= <map>.get(<key>)", c2.warnings[0])

    # 3. Mutable in-place mutation via if m.contains(k) { m[k].push(1); } -> suggests 'if var'
    c3 = self._check("""
    func append_val(var m: [String: [int]], k: String) {
      if m.contains(k) {
        m[k].push(1);
      }
    }
    """)
    self.assertEqual(len(c3.warnings), 1)
    self.assertIn("if var v ?= <map>.get(<key>)", c3.warnings[0])

    # 4. Guard statement: guard m.contains(k) else { return; } followed by m[k].push(1)
    c4 = self._check("""
    func guard_append(var m: [String: [int]], k: String) {
      guard m.contains(k) else { return; }
      m[k].push(1);
    }
    """)
    self.assertEqual(len(c4.warnings), 1)
    self.assertIn("guard var v ?= <map>.get(<key>) else { ... }", c4.warnings[0])

    # 5. Negative: Array.contains(val) + arr[i] must NOT warn
    c5 = self._check("""
    func arr_check(arr: [int], v: int, i: int): int {
      if arr.contains(v) {
        return arr[i];
      }
      return 0;
    }
    """)
    self.assertEqual(c5.warnings, [])

    # 6. Negative: Direct overwrite m[k] = val must NOT warn
    c6 = self._check("""
    func overwrite(var m: [String: int], k: String) {
      if m.contains(k) {
        m[k] = 42;
      }
    }
    """)
    self.assertEqual(c6.warnings, [])

    # 7. Negative: Structural mutation on map (m.remove(k)) in same block must NOT warn
    c7 = self._check("""
    func pop_entry(var m: [String: int], k: String): int {
      if m.contains(k) {
        let val = m[k];
        m.remove(k);
        return val;
      }
      return 0;
    }
    """)
    self.assertEqual(c7.warnings, [])

    # 8. Negative: Single-lookup if let / if var .get(k) must NOT warn
    c8 = self._check("""
    func single_lookup(var m: [String: [int]], k: String): int {
      if var arr ?= m.get(k) {
        arr.push(1);
      }
      if let arr ?= m.get(k) {
        return arr.size();
      }
      return 0;
    }
    """)
    self.assertEqual(c8.warnings, [])

  def test_subscript_mutating_method_call(self):
    self._check("""
    struct Item {
      var x: int = 0;
    }
    impl Item {
      var func inc() {
        self.x += 1;
      }
    }
    func main() {
      var arr = [Item { x = 1 }];
      arr[0].inc();
      var m = {"a": Item { x = 1 }};
      m["a"].inc();
    }
    """)

  def test_double_lookup_lint_with_literal_and_unary_keys(self):
    """Verifies map double-lookup lint handles LiteralNode and UnaryOpNode keys without crashing."""
    checker = self._check("""
    func main() {
      let m1: [String: int] = {"a": 1};
      if m1.contains("a") {
        let v1 = m1["a"];
      }
      let m2: [int: String] = {-1: "neg"};
      if m2.contains(-1) {
        let v2 = m2[-1];
      }
    }
    """)
    self.assertEqual(len(checker.warnings), 2)


if __name__ == "__main__":
  unittest.main()
