"""Compile-time constant expression evaluation and verification.

Validates whether an AST expression can be statically resolved at compile
time for module-level constants and declarations.
"""

from typing import Optional, Tuple
from src.parser.ast import (
    ASTNode,
    ArrayLiteralNode,
    BinaryOpNode,
    CallNode,
    CastExprNode,
    CloneNode,
    IdentifierNode,
    InterpolatedStringNode,
    LambdaNode,
    LiteralNode,
    MapLiteralNode,
    MemberAccessNode,
    MoveNode,
    StructInitializerNode,
    TernaryExprNode,
    UnaryOpNode,
)
from src.semantics.symbol_table import (
    EnumSymbol,
    ModuleSymbol,
    StructType,
    SymbolTable,
    VariableSymbol,
)

_DISALLOWED_CONST_NODES = {
    CallNode: (
        "Function calls cannot be evaluated in a compile-time constant "
        "expression."
    ),
    CloneNode: (
        "Dynamic prototype cloning cannot be evaluated in a compile-time "
        "constant expression."
    ),
    MoveNode: (
        "Move expressions cannot be used in a compile-time constant expression."
    ),
    LambdaNode: (
        "Lambda expressions cannot be used in a compile-time constant "
        "expression."
    ),
}


def _check_ident_const(
    node: IdentifierNode, symbol_table: SymbolTable
) -> Tuple[bool, Optional[str]]:
  sym = symbol_table.lookup(node.name)
  if sym is None:
    # Could be an enum variant name if scoped, or an enum type.
    if symbol_table.lookup_type(node.name) is not None:
      return True, None
    return False, (
        f"Identifier '{node.name}' is undefined and cannot be used in a "
        "compile-time constant expression."
    )
  if isinstance(sym, EnumSymbol):
    return True, None
  if isinstance(sym, VariableSymbol):
    if getattr(sym, "is_constant_expr", False) and not sym.is_mutable:
      return True, None
    return False, (
        f"Variable '{node.name}' is not a compile-time constant expression."
    )
  return False, (
      f"Symbol '{node.name}' cannot be used as a value in a "
      "compile-time constant expression."
  )


def _check_member_const(
    node: MemberAccessNode, symbol_table: SymbolTable
) -> Tuple[bool, Optional[str]]:
  # Allow Enum.Variant or module.CONSTANT without requiring value eval.
  if isinstance(node.receiver, IdentifierNode):
    type_obj = symbol_table.lookup_type(node.receiver.name)
    if type_obj is not None and getattr(type_obj, "name", None):
      return True, None
    sym = symbol_table.lookup(node.receiver.name)
    if isinstance(sym, (EnumSymbol, ModuleSymbol)):
      return True, None
  return is_constant_expression(node.receiver, symbol_table)


def _check_struct_init_const(
    node: StructInitializerNode, symbol_table: SymbolTable
) -> Tuple[bool, Optional[str]]:
  if node.arena_expr is not None:
    return False, (
        "Arena allocation is not permitted in a compile-time constant "
        "expression."
    )
  st_type = symbol_table.lookup_type(node.struct_name)
  if isinstance(st_type, StructType):
    if getattr(st_type, "is_prototype", False):
      return False, (
          f"Prototype struct '{node.struct_name}' cannot be allocated in a "
          "compile-time constant expression."
      )
    if "__init__" in getattr(st_type, "methods", {}):
      return False, (
          f"Struct '{node.struct_name}' defines an '__init__' constructor and "
          "cannot be instantiated in a compile-time constant expression."
      )
  for field_arg in node.fields:
    if field_arg.expr is not None:
      ok, err = is_constant_expression(field_arg.expr, symbol_table)
      if not ok:
        return False, err
  return True, None


def is_constant_expression(
    node: ASTNode, symbol_table: SymbolTable
) -> Tuple[bool, Optional[str]]:
  """Validates if an AST node is a compile-time constant expression."""
  if isinstance(node, LiteralNode):
    return True, None
  if isinstance(node, IdentifierNode):
    return _check_ident_const(node, symbol_table)
  if isinstance(node, MemberAccessNode):
    return _check_member_const(node, symbol_table)
  if isinstance(node, UnaryOpNode):
    if node.op in ("-", "+", "!"):
      return is_constant_expression(node.expr, symbol_table)
    return False, (
        f"Unary operator '{node.op}' is not supported in a compile-time "
        "constant expression."
    )
  if isinstance(node, BinaryOpNode):
    for child in (node.left, node.right):
      ok, err = is_constant_expression(child, symbol_table)
      if not ok:
        return False, err
    return True, None
  if isinstance(node, TernaryExprNode):
    for child in (node.condition, node.true_expr, node.false_expr):
      ok, err = is_constant_expression(child, symbol_table)
      if not ok:
        return False, err
    return True, None
  if isinstance(node, CastExprNode):
    return is_constant_expression(node.expr, symbol_table)
  if isinstance(node, InterpolatedStringNode):
    for part in node.parts:
      ok, err = is_constant_expression(part, symbol_table)
      if not ok:
        return False, err
    return True, None
  if isinstance(node, ArrayLiteralNode):
    for elem in node.elements:
      ok, err = is_constant_expression(elem, symbol_table)
      if not ok:
        return False, err
    return True, None
  if isinstance(node, MapLiteralNode):
    for entry in node.entries:
      k = entry.key if hasattr(entry, "key") else entry[0]
      v = entry.value if hasattr(entry, "value") else entry[1]
      for child in (k, v):
        ok, err = is_constant_expression(child, symbol_table)
        if not ok:
          return False, err
    return True, None
  if isinstance(node, StructInitializerNode):
    return _check_struct_init_const(node, symbol_table)

  disallowed_msg = _DISALLOWED_CONST_NODES.get(type(node))
  if disallowed_msg:
    return False, disallowed_msg

  return False, (
      f"Expression of type '{type(node).__name__}' is not permitted in a "
      "compile-time constant expression."
  )
