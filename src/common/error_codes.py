"""Centralized catalog of stable Sapphire compiler diagnostic codes."""

from enum import StrEnum


class ErrorCode(StrEnum):
  """Stable diagnostic codes emitted by the parser and semantic analyzer."""

  E_SYNTAX = "E_SYNTAX"
  E_IMMUTABLE_ASSIGN = "E_IMMUTABLE_ASSIGN"
  E_USE_AFTER_MOVE = "E_USE_AFTER_MOVE"
  E_BORROW_ALIAS = "E_BORROW_ALIAS"
  E_BORROW_ESCAPE = "E_BORROW_ESCAPE"
  E_ARENA_ESCAPE = "E_ARENA_ESCAPE"
  E_TYPE_MISMATCH = "E_TYPE_MISMATCH"
  E_UNDEFINED_SYMBOL = "E_UNDEFINED_SYMBOL"
  E_DUPLICATE_SYMBOL = "E_DUPLICATE_SYMBOL"
  E_ARITY_MISMATCH = "E_ARITY_MISMATCH"
  E_EXHAUSTIVENESS = "E_EXHAUSTIVENESS"
  E_INVALID_RETURN = "E_INVALID_RETURN"
  E_INVALID_CONTROL_FLOW = "E_INVALID_CONTROL_FLOW"
  E_INVALID_OPERATION = "E_INVALID_OPERATION"
  E_INVALID_CAST = "E_INVALID_CAST"
  E_INVALID_OPTIONAL = "E_INVALID_OPTIONAL"
  E_INVALID_MEMBER = "E_INVALID_MEMBER"
  E_INVALID_CALL = "E_INVALID_CALL"
  E_INVALID_GENERIC = "E_INVALID_GENERIC"
  E_INVALID_TRAIT_IMPL = "E_INVALID_TRAIT_IMPL"
  E_INVALID_STRUCT = "E_INVALID_STRUCT"
  E_INVALID_PROTO = "E_INVALID_PROTO"
  E_INVALID_MODULE = "E_INVALID_MODULE"
  E_INVALID_COROUTINE = "E_INVALID_COROUTINE"
  E_INVALID_CONST = "E_INVALID_CONST"
  E_INVALID_COLLECTION = "E_INVALID_COLLECTION"
  E_SEMANTIC = "E_SEMANTIC"


_CLASSIFICATION_RULES: tuple[tuple[tuple[str, ...], ErrorCode], ...] = (
  (("use of moved", "after move", "moved value"), ErrorCode.E_USE_AFTER_MOVE),
  (
    (
      "cannot assign to immutable",
      "cannot assign to constant",
      "cannot mutate immutable",
      "cannot mutate constant",
      "immutable variable",
      "immutable field",
      "immutable receiver",
      "cannot modify immutable",
      "mutating method",
      "requires mutable",
    ),
    ErrorCode.E_IMMUTABLE_ASSIGN,
  ),
  (
    ("aliasing", "aliased", "mutable borrow", "mutably borrowed"),
    ErrorCode.E_BORROW_ALIAS,
  ),
  (("escape", "arena"), ErrorCode.E_ARENA_ESCAPE),
  (("exhaustive", "missing match arm"), ErrorCode.E_EXHAUSTIVENESS),
  (
    ("undefined", "not defined", "unknown identifier", "unknown type"),
    ErrorCode.E_UNDEFINED_SYMBOL,
  ),
  (
    ("already defined", "duplicate", "redeclared", "redefinition"),
    ErrorCode.E_DUPLICATE_SYMBOL,
  ),
  (
    ("expects ", "expected ", "argument", "parameter count", "arity"),
    ErrorCode.E_ARITY_MISMATCH,
  ),
  (("cannot cast", "up-cast", "upcast"), ErrorCode.E_INVALID_CAST),
  (
    ("return ", "must return", "cannot return", "missing return"),
    ErrorCode.E_INVALID_RETURN,
  ),
  (
    ("'break'", "'continue'", "outside of loop", "guard "),
    ErrorCode.E_INVALID_CONTROL_FLOW,
  ),
  (("coroutine", "yield", "resume"), ErrorCode.E_INVALID_COROUTINE),
  (("trait", "impl "), ErrorCode.E_INVALID_TRAIT_IMPL),
  (("proto", "clone"), ErrorCode.E_INVALID_PROTO),
  (("import", "export", "module"), ErrorCode.E_INVALID_MODULE),
  (("generic", "type argument", "type parameter"), ErrorCode.E_INVALID_GENERIC),
  (("optional", "coalesce", "unwrap", "nil"), ErrorCode.E_INVALID_OPTIONAL),
  (
    ("no field", "no member", "no method", "has no attribute"),
    ErrorCode.E_INVALID_MEMBER,
  ),
  (("not callable", "cannot call"), ErrorCode.E_INVALID_CALL),
  (("constant", "const "), ErrorCode.E_INVALID_CONST),
  (("array", "map", "index"), ErrorCode.E_INVALID_COLLECTION),
  (("struct",), ErrorCode.E_INVALID_STRUCT),
  (
    ("type mismatch", "cannot assign", "incompatible type", "must be of type"),
    ErrorCode.E_TYPE_MISMATCH,
  ),
  (
    ("operator", "operand", "cannot apply", "invalid binary", "invalid unary"),
    ErrorCode.E_INVALID_OPERATION,
  ),
)


def classify_error_code(message: str) -> ErrorCode:
  """Infers a stable ErrorCode from a semantic error message."""
  lowered = message.lower()
  for needles, code in _CLASSIFICATION_RULES:
    if any(needle in lowered for needle in needles):
      return code
  return ErrorCode.E_SEMANTIC
