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


def is_constant_expression(
    node: ASTNode, symbol_table: SymbolTable
) -> Tuple[bool, Optional[str]]:
  """Validates if an AST node is a compile-time constant expression.

  Args:
    node: The expression AST node to inspect.
    symbol_table: Active symbol table for looking up identifier bindings.

  Returns:
    A tuple of (is_constant, error_reason). If valid, error_reason is None.
  """
  if isinstance(node, LiteralNode):
    return True, None

  if isinstance(node, IdentifierNode):
    sym = symbol_table.lookup(node.name)
    if sym is None:
      # Could be an enum variant name if scoped, or an enum type
      type_obj = symbol_table.lookup_type(node.name)
      if type_obj is not None:
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

  if isinstance(node, MemberAccessNode):
    # e.g. Direction.North or module.CONSTANT
    if isinstance(node.receiver, IdentifierNode):
      # Check for enum access
      type_obj = symbol_table.lookup_type(node.receiver.name)
      if type_obj is not None and getattr(type_obj, "name", None):
        return True, None

      sym = symbol_table.lookup(node.receiver.name)
      if isinstance(sym, EnumSymbol):
        return True, None
      if isinstance(sym, ModuleSymbol):
        return True, None

    # General member access on constant struct
    rec_ok, rec_err = is_constant_expression(node.receiver, symbol_table)
    if not rec_ok:
      return False, rec_err
    return True, None

  if isinstance(node, UnaryOpNode):
    if node.op in ("-", "+", "!"):
      return is_constant_expression(node.expr, symbol_table)
    return False, (
        f"Unary operator '{node.op}' is not supported in a compile-time "
        "constant expression."
    )

  if isinstance(node, BinaryOpNode):
    left_ok, left_err = is_constant_expression(node.left, symbol_table)
    if not left_ok:
      return False, left_err
    right_ok, right_err = is_constant_expression(node.right, symbol_table)
    if not right_ok:
      return False, right_err
    return True, None

  if isinstance(node, TernaryExprNode):
    cond_ok, cond_err = is_constant_expression(node.condition, symbol_table)
    if not cond_ok:
      return False, cond_err
    true_ok, true_err = is_constant_expression(node.true_expr, symbol_table)
    if not true_ok:
      return False, true_err
    false_ok, false_err = is_constant_expression(node.false_expr, symbol_table)
    if not false_ok:
      return False, false_err
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
      k_ok, k_err = is_constant_expression(k, symbol_table)
      if not k_ok:
        return False, k_err
      v_ok, v_err = is_constant_expression(v, symbol_table)
      if not v_ok:
        return False, v_err
    return True, None

  if isinstance(node, StructInitializerNode):
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

  if isinstance(node, CallNode):
    return False, (
        "Function calls cannot be evaluated in a compile-time constant "
        "expression."
    )

  if isinstance(node, CloneNode):
    return False, (
        "Dynamic prototype cloning cannot be evaluated in a compile-time "
        "constant expression."
    )

  if isinstance(node, MoveNode):
    return False, (
        "Move expressions cannot be used in a compile-time constant "
        "expression."
    )

  if isinstance(node, LambdaNode):
    return False, (
        "Lambda expressions cannot be used in a compile-time constant "
        "expression."
    )

  return False, (
      f"Expression of type '{type(node).__name__}' is not permitted in a "
      "compile-time constant expression."
  )
