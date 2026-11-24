"""Unit tests for src/common/error_codes.py."""

import unittest

from src.common.error_codes import ErrorCode, classify_error_code
from testing.test_utils import parse_source


class TestErrorCodes(unittest.TestCase):
  """Verifies ErrorCode classification and TypeChecker diagnostic codes."""

  def test_classify_error_code_matches_major_categories(self):
    cases = [
      ("Use of moved variable 'x'", ErrorCode.E_USE_AFTER_MOVE),
      ("Cannot assign to immutable variable 'x'", ErrorCode.E_IMMUTABLE_ASSIGN),
      ("Mutable borrow aliasing violation", ErrorCode.E_BORROW_ALIAS),
      ("Proto value cannot escape arena scope", ErrorCode.E_ARENA_ESCAPE),
      ("Non-exhaustive match expression", ErrorCode.E_EXHAUSTIVENESS),
      ("Undefined variable 'foo'", ErrorCode.E_UNDEFINED_SYMBOL),
      ("Duplicate field 'x'", ErrorCode.E_DUPLICATE_SYMBOL),
      ("Function 'f' expects 2 arguments, got 1", ErrorCode.E_ARITY_MISMATCH),
      ("Cannot cast Child as Parent", ErrorCode.E_INVALID_CAST),
      ("Function must return 'int'", ErrorCode.E_INVALID_RETURN),
      ("Cannot assign 'String' to 'int'", ErrorCode.E_TYPE_MISMATCH),
      ("Something completely unexpected", ErrorCode.E_SEMANTIC),
    ]
    for msg, expected in cases:
      with self.subTest(msg=msg):
        self.assertEqual(classify_error_code(msg), expected)

  def test_type_checker_populates_diagnostic_codes(self):
    from src.semantics.type_checker import SemanticError, TypeChecker

    cases = [
      (
        "func f() { let x = 1; x = 2; }",
        ErrorCode.E_IMMUTABLE_ASSIGN,
      ),
      (
        "func f() { let y = unknown_var; }",
        ErrorCode.E_UNDEFINED_SYMBOL,
      ),
      (
        "func f() { let x: int = \"hi\"; }",
        ErrorCode.E_TYPE_MISMATCH,
      ),
      (
        "func add(a: int, b: int): int { return a + b; }\n"
        "func f() { let r = add(1); }",
        ErrorCode.E_ARITY_MISMATCH,
      ),
    ]
    for source, expected_code in cases:
      with self.subTest(expected_code=expected_code):
        ast = parse_source(source)
        checker = TypeChecker(source_content=source)
        with self.assertRaises(SemanticError):
          checker.check(ast)
        self.assertTrue(len(checker.diagnostics) >= 1)
        self.assertEqual(checker.diagnostics[0].code, expected_code)


if __name__ == "__main__":
  unittest.main()
