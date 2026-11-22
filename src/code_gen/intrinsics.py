"""Intrinsic method and standard library dispatch table for code generators.

Provides table-driven code emission for Sapphire built-in primitives and standard
data structures (String, Array, Map, Range, and Enum) across Python and Lua backends.
"""

from typing import Any, Callable, Dict, List, Tuple
from src.parser.ast import ASTNode, CallNode, IdentifierNode, LiteralNode, MemberAccessNode

BUILTIN_MODULES = (
    "std.testing",
    "std.math",
    "std.os",
    "std.fs",
    "std.time",
    "std.utf8",
)


def is_builtin_module(import_path: str) -> bool:
  """Returns True if the given import path belongs to Sapphire's built-in modules."""
  return any(
      import_path == mod or import_path.startswith(mod + ".")
      for mod in BUILTIN_MODULES
  )


def _is_trivial_expr(expr: Any) -> bool:
  """Returns True if *expr* has no observable evaluation-order side effects."""
  return isinstance(expr, (LiteralNode, IdentifierNode))


def emit_in_call_order(
    target: str,
    transpiler: Any,
    node: CallNode,
    canonical_exprs: List[Any],
    emit_fn: Callable[[List[Any]], None],
) -> None:
  """Emits an intrinsic call while preserving left-to-right source evaluation order.

  When named arguments reorder non-trivial expressions relative to canonical
  parameter order, evaluates the receiver and arguments in source order inside
  an immediately-invoked function and passes the bound temporaries to `emit_fn`.
  """
  source_exprs = [arg.expr for arg in node.arguments]
  source_pos = {id(expr): idx for idx, expr in enumerate(source_exprs)}
  emitted_positions = [
      source_pos[id(e)]
      for e in canonical_exprs
      if e is not None and id(e) in source_pos
  ]
  is_reordered = any(
      emitted_positions[i] > emitted_positions[i + 1]
      for i in range(len(emitted_positions) - 1)
  )
  if not is_reordered or not any(not _is_trivial_expr(e) for e in source_exprs):
    emit_fn(canonical_exprs)
    return

  next_tmp = getattr(transpiler, "_next_temp_name", None)
  params: List[str] = []
  source_vals: List[Any] = []
  has_recv = isinstance(node.callee, MemberAccessNode)
  orig_recv = node.callee.receiver if has_recv else None

  if has_recv:
    recv_tmp = next_tmp("_ir") if next_tmp else "_ir_1"
    params.append(recv_tmp)
    source_vals.append(orig_recv)

  expr_map: Dict[int, IdentifierNode] = {}
  for idx, expr in enumerate(source_exprs):
    arg_tmp = next_tmp("_ia") if next_tmp else f"_ia_{idx + 1}"
    params.append(arg_tmp)
    source_vals.append(expr)
    expr_map[id(expr)] = IdentifierNode(arg_tmp)

  rewritten = [
      expr_map[id(e)] if (e is not None and id(e) in expr_map) else e
      for e in canonical_exprs
  ]

  if has_recv:
    node.callee.receiver = IdentifierNode(params[0])
  try:
    if target == "python":
      transpiler.emit(f"((lambda {', '.join(params)}: ")
      emit_fn(rewritten)
      transpiler.emit(")(")
      for idx, val in enumerate(source_vals):
        if idx > 0:
          transpiler.emit(", ")
        transpiler.visit(val)
      transpiler.emit("))")
    elif target == "lua":
      transpiler.emit(f"(function({', '.join(params)}) return ")
      emit_fn(rewritten)
      transpiler.emit(" end)(")
      for idx, val in enumerate(source_vals):
        if idx > 0:
          transpiler.emit(", ")
        transpiler.visit(val)
      transpiler.emit(")")
    else:
      emit_fn(canonical_exprs)
  finally:
    if has_recv:
      node.callee.receiver = orig_recv


class IntrinsicRegistry:
  """Registry for target-specific code generation emitters for intrinsic operations."""

  _handlers: Dict[Tuple[str, str, str], Callable[[Any, CallNode], None]] = {}

  @classmethod
  def register(cls, category: str, method: str, target: str):
    """Decorator to register a code generation handler for (category, method, target)."""

    def decorator(fn: Callable[[Any, CallNode], None]):
      cls._handlers[(category, method, target)] = fn
      return fn

    return decorator

  @classmethod
  def try_emit(cls, target: str, transpiler: Any, node: CallNode) -> bool:
    """Attempts to match an intrinsic call and invoke its registered emitter.

    Returns True if an intrinsic was handled and emitted, False otherwise.
    """
    category = None
    method = None

    if isinstance(node.callee, IdentifierNode) and node.callee.name in ("range", "assert"):
      category = "global"
      method = node.callee.name
    elif isinstance(node.callee, MemberAccessNode):
      if getattr(node.callee, "is_string_from", False):
        category = "String"
        method = "from"
      elif getattr(node.callee, "is_enum_from", False):
        category = "Enum"
        method = "from"
      elif getattr(node.callee, "is_string_method", False):
        category = "String"
        method = node.callee.member
      elif getattr(node.callee, "is_array_method", False):
        category = "Array"
        method = node.callee.array_method
      elif getattr(node.callee, "is_map_method", False):
        category = "Map"
        method = node.callee.map_method

    if category and method:
      handler = cls._handlers.get((category, method, target))
      if handler:
        if isinstance(node.callee, MemberAccessNode) and node.callee.is_optional:
          next_tmp = getattr(transpiler, "_next_temp_name", None)
          tmp_name = next_tmp("_opt") if next_tmp else "_opt_recv"
          orig_recv = node.callee.receiver
          node.callee.receiver = IdentifierNode(tmp_name)
          try:
            if target == "python":
              transpiler.emit(f"((lambda {tmp_name}: ")
              handler(transpiler, node)
              transpiler.emit(f" if {tmp_name} is not None else None)(")
              transpiler.visit(orig_recv)
              transpiler.emit("))")
            elif target == "lua":
              transpiler.emit(
                  f"(function({tmp_name}) if {tmp_name} ~= nil then return "
              )
              handler(transpiler, node)
              transpiler.emit(" end return nil end)(")
              transpiler.visit(orig_recv)
              transpiler.emit(")")
            else:
              node.callee.receiver = orig_recv
              handler(transpiler, node)
          finally:
            node.callee.receiver = orig_recv
        else:
          handler(transpiler, node)
        return True

    return False


# ==============================================================================
# Global Intrinsics: range()
# ==============================================================================


def _resolve_range_args(node: CallNode) -> List[ASTNode]:
  """Resolves range() arguments into canonical (stop) / (start, stop[, step])."""
  pos_args = [arg for arg in node.arguments if not arg.name]
  named_args = {arg.name: arg.expr for arg in node.arguments if arg.name}

  if len(pos_args) <= 3 and not named_args:
    return [arg.expr for arg in pos_args]

  start_expr: Any = None
  stop_expr: Any = None
  step_expr: Any = None
  if len(pos_args) >= 1:
    if "stop" in named_args:
      start_expr = pos_args[0].expr
    elif len(pos_args) == 1:
      stop_expr = pos_args[0].expr
    else:
      start_expr = pos_args[0].expr
      stop_expr = pos_args[1].expr
  if "start" in named_args:
    start_expr = named_args["start"]
  if "stop" in named_args:
    stop_expr = named_args["stop"]
  if "step" in named_args:
    step_expr = named_args["step"]
  elif len(pos_args) == 3:
    step_expr = pos_args[2].expr

  if step_expr is not None:
    if start_expr is None:
      start_expr = LiteralNode(0, "int")
    return [start_expr, stop_expr, step_expr]
  if start_expr is not None:
    return [start_expr, stop_expr]
  return [stop_expr]


@IntrinsicRegistry.register("global", "range", "python")
def _emit_range_py(transpiler: Any, node: CallNode) -> None:
  args = _resolve_range_args(node)

  def _emit(exprs: List[Any]) -> None:
    transpiler.emit("range(")
    for idx, expr in enumerate(exprs):
      if idx > 0:
        transpiler.emit(", ")
      transpiler.visit(expr)
    transpiler.emit(")")

  emit_in_call_order("python", transpiler, node, args, _emit)


@IntrinsicRegistry.register("global", "range", "lua")
def _emit_range_lua(transpiler: Any, node: CallNode) -> None:
  args = _resolve_range_args(node)

  def _emit(exprs: List[Any]) -> None:
    transpiler.emit("_sapphire_range(")
    for idx, expr in enumerate(exprs):
      if idx > 0:
        transpiler.emit(", ")
      transpiler.visit(expr)
    transpiler.emit(")")

  emit_in_call_order("lua", transpiler, node, args, _emit)


def _resolve_assert_args(node: CallNode) -> Tuple[Any, Any]:
  """Resolves assert(cond, msg?) arguments."""
  pos_args = [arg.expr for arg in node.arguments if not arg.name]
  named_args = {arg.name: arg.expr for arg in node.arguments if arg.name}
  cond_expr = named_args.get("cond") if "cond" in named_args else pos_args[0]
  if "msg" in named_args:
    msg_expr = named_args["msg"]
  elif len(pos_args) > 1:
    msg_expr = pos_args[1]
  else:
    msg_expr = None
  return cond_expr, msg_expr


@IntrinsicRegistry.register("global", "assert", "python")
def _emit_assert_py(transpiler: Any, node: CallNode) -> None:
  cond_expr, msg_expr = _resolve_assert_args(node)

  def _emit(exprs: List[Any]) -> None:
    transpiler.emit("_sapphire_assert(")
    transpiler.visit(exprs[0])
    transpiler.emit(", ")
    if exprs[1] is not None:
      transpiler.visit(exprs[1])
    else:
      transpiler.emit('"assertion failed"')
    transpiler.emit(")")

  emit_in_call_order("python", transpiler, node, [cond_expr, msg_expr], _emit)


@IntrinsicRegistry.register("global", "assert", "lua")
def _emit_assert_lua(transpiler: Any, node: CallNode) -> None:
  cond_expr, msg_expr = _resolve_assert_args(node)

  def _emit(exprs: List[Any]) -> None:
    transpiler.emit("assert(")
    transpiler.visit(exprs[0])
    transpiler.emit(", ")
    if exprs[1] is not None:
      transpiler.visit(exprs[1])
    else:
      transpiler.emit('"assertion failed"')
    transpiler.emit(")")

  emit_in_call_order("lua", transpiler, node, [cond_expr, msg_expr], _emit)


# ==============================================================================
# String & Enum .from()
# ==============================================================================


@IntrinsicRegistry.register("String", "from", "python")
def _emit_string_from_py(transpiler: Any, node: CallNode) -> None:
  transpiler.emit("_sapphire_string_from(")
  transpiler.visit(node.arguments[0].expr)
  transpiler.emit(")")


@IntrinsicRegistry.register("String", "from", "lua")
def _emit_string_from_lua(transpiler: Any, node: CallNode) -> None:
  transpiler.emit("tostring(")
  transpiler.visit(node.arguments[0].expr)
  transpiler.emit(")")


@IntrinsicRegistry.register("Enum", "from", "python")
def _emit_enum_from_py(transpiler: Any, node: CallNode) -> None:
  transpiler.emit("_sapphire_enum_from(")
  transpiler.visit(node.callee.receiver)
  transpiler.emit(", ")
  transpiler.visit(node.arguments[0].expr)
  transpiler.emit(")")


@IntrinsicRegistry.register("Enum", "from", "lua")
def _emit_enum_from_lua(transpiler: Any, node: CallNode) -> None:
  transpiler.emit("_sapphire_enum_from(")
  transpiler.visit(node.callee.receiver)
  transpiler.emit(", ")
  transpiler.visit(node.arguments[0].expr)
  transpiler.emit(")")


# ==============================================================================
# String Methods (Python & Lua)
# ==============================================================================


@IntrinsicRegistry.register("String", "size", "python")
def _emit_str_size_py(transpiler: Any, node: CallNode) -> None:
  transpiler.emit("len(")
  transpiler.visit(node.callee.receiver)
  transpiler.emit(")")


@IntrinsicRegistry.register("String", "size", "lua")
def _emit_str_size_lua(transpiler: Any, node: CallNode) -> None:
  transpiler.emit("(#")
  transpiler.visit(node.callee.receiver)
  transpiler.emit(")")


@IntrinsicRegistry.register("String", "empty", "python")
def _emit_str_empty_py(transpiler: Any, node: CallNode) -> None:
  transpiler.emit("(len(")
  transpiler.visit(node.callee.receiver)
  transpiler.emit(") == 0)")


@IntrinsicRegistry.register("String", "empty", "lua")
def _emit_str_empty_lua(transpiler: Any, node: CallNode) -> None:
  transpiler.emit("(#")
  transpiler.visit(node.callee.receiver)
  transpiler.emit(" == 0)")


@IntrinsicRegistry.register("String", "lower", "python")
def _emit_str_lower_py(transpiler: Any, node: CallNode) -> None:
  transpiler.visit(node.callee.receiver)
  transpiler.emit(".lower()")


@IntrinsicRegistry.register("String", "lower", "lua")
def _emit_str_lower_lua(transpiler: Any, node: CallNode) -> None:
  transpiler.emit("string.lower(")
  transpiler.visit(node.callee.receiver)
  transpiler.emit(")")


@IntrinsicRegistry.register("String", "upper", "python")
def _emit_str_upper_py(transpiler: Any, node: CallNode) -> None:
  transpiler.visit(node.callee.receiver)
  transpiler.emit(".upper()")


@IntrinsicRegistry.register("String", "upper", "lua")
def _emit_str_upper_lua(transpiler: Any, node: CallNode) -> None:
  transpiler.emit("string.upper(")
  transpiler.visit(node.callee.receiver)
  transpiler.emit(")")


@IntrinsicRegistry.register("String", "strip", "python")
def _emit_str_strip_py(transpiler: Any, node: CallNode) -> None:
  transpiler.visit(node.callee.receiver)
  transpiler.emit(".strip(")
  if node.arguments:
    transpiler.visit(node.arguments[0].expr)
  transpiler.emit(")")


@IntrinsicRegistry.register("String", "strip", "lua")
def _emit_str_strip_lua(transpiler: Any, node: CallNode) -> None:
  transpiler.emit("_sapphire_string_strip(")
  transpiler.visit(node.callee.receiver)
  if node.arguments:
    transpiler.emit(", ")
    transpiler.visit(node.arguments[0].expr)
  transpiler.emit(")")


def _resolve_slice_args(node: CallNode) -> Tuple[Any, Any]:
  """Resolves String.slice(start, end?) arguments."""
  pos_args = [arg.expr for arg in node.arguments if not arg.name]
  named_args = {arg.name: arg.expr for arg in node.arguments if arg.name}
  start_expr = named_args.get("start") if "start" in named_args else pos_args[0]
  end_expr = None
  if "end" in named_args:
    end_expr = named_args["end"]
  elif len(pos_args) > 1:
    end_expr = pos_args[1]
  return start_expr, end_expr


@IntrinsicRegistry.register("String", "slice", "python")
def _emit_str_slice_py(transpiler: Any, node: CallNode) -> None:
  start_expr, end_expr = _resolve_slice_args(node)

  def _emit(exprs: List[Any]) -> None:
    transpiler.visit(node.callee.receiver)
    transpiler.emit("[")
    transpiler.visit(exprs[0])
    transpiler.emit(":")
    if exprs[1] is not None:
      transpiler.visit(exprs[1])
    transpiler.emit("]")

  emit_in_call_order("python", transpiler, node, [start_expr, end_expr], _emit)


@IntrinsicRegistry.register("String", "slice", "lua")
def _emit_str_slice_lua(transpiler: Any, node: CallNode) -> None:
  start_expr, end_expr = _resolve_slice_args(node)

  def _emit(exprs: List[Any]) -> None:
    transpiler.emit("_sapphire_string_slice(")
    transpiler.visit(node.callee.receiver)
    transpiler.emit(", ")
    transpiler.visit(exprs[0])
    if exprs[1] is not None:
      transpiler.emit(", ")
      transpiler.visit(exprs[1])
    transpiler.emit(")")

  emit_in_call_order("lua", transpiler, node, [start_expr, end_expr], _emit)


@IntrinsicRegistry.register("String", "split", "python")
def _emit_str_split_py(transpiler: Any, node: CallNode) -> None:
  transpiler.emit("_sapphire_string_split(")
  transpiler.visit(node.callee.receiver)
  if node.arguments:
    transpiler.emit(", ")
    transpiler.visit(node.arguments[0].expr)
  transpiler.emit(")")


@IntrinsicRegistry.register("String", "split", "lua")
def _emit_str_split_lua(transpiler: Any, node: CallNode) -> None:
  transpiler.emit("_sapphire_string_split(")
  transpiler.visit(node.callee.receiver)
  if node.arguments:
    transpiler.emit(", ")
    transpiler.visit(node.arguments[0].expr)
  transpiler.emit(")")


@IntrinsicRegistry.register("String", "contains", "python")
def _emit_str_contains_py(transpiler: Any, node: CallNode) -> None:
  transpiler.emit("_sapphire_string_contains(")
  transpiler.visit(node.callee.receiver)
  transpiler.emit(", ")
  transpiler.visit(node.arguments[0].expr)
  transpiler.emit(")")


@IntrinsicRegistry.register("String", "contains", "lua")
def _emit_str_contains_lua(transpiler: Any, node: CallNode) -> None:
  transpiler.emit("(string.find(")
  transpiler.visit(node.callee.receiver)
  transpiler.emit(", ")
  transpiler.visit(node.arguments[0].expr)
  transpiler.emit(", 1, true) ~= nil)")


@IntrinsicRegistry.register("String", "find", "python")
def _emit_str_find_py(transpiler: Any, node: CallNode) -> None:
  transpiler.emit("_sapphire_string_find(")
  transpiler.visit(node.callee.receiver)
  for arg in node.arguments:
    transpiler.emit(", ")
    if arg.name:
      transpiler.emit(f"{arg.name}=")
    transpiler.visit(arg.expr)
  transpiler.emit(")")


@IntrinsicRegistry.register("String", "find", "lua")
def _emit_str_find_lua(transpiler: Any, node: CallNode) -> None:
  args_by_param: List[Any] = [None, None, None]
  param_names = ["sub", "start", "reverse"]
  for idx, arg in enumerate(node.arguments):
    if arg.name and arg.name in param_names:
      p_idx = param_names.index(arg.name)
      args_by_param[p_idx] = arg.expr
    elif idx < 3:
      args_by_param[idx] = arg.expr
  while args_by_param and args_by_param[-1] is None:
    args_by_param.pop()

  def _emit(exprs: List[Any]) -> None:
    transpiler.emit("_sapphire_string_find(")
    transpiler.visit(node.callee.receiver)
    for p_expr in exprs:
      transpiler.emit(", ")
      if p_expr is None:
        transpiler.emit("nil")
      else:
        transpiler.visit(p_expr)
    transpiler.emit(")")

  emit_in_call_order("lua", transpiler, node, args_by_param, _emit)


@IntrinsicRegistry.register("String", "to_int", "python")
def _emit_str_to_int_py(transpiler: Any, node: CallNode) -> None:
  transpiler.emit("_sapphire_string_to_int(")
  transpiler.visit(node.callee.receiver)
  if node.arguments:
    for arg in node.arguments:
      transpiler.emit(", ")
      if arg.name:
        transpiler.emit(f"{arg.name}=")
      transpiler.visit(arg.expr)
  transpiler.emit(")")


@IntrinsicRegistry.register("String", "to_int", "lua")
def _emit_str_to_int_lua(transpiler: Any, node: CallNode) -> None:
  transpiler.emit("_sapphire_string_to_int(")
  transpiler.visit(node.callee.receiver)
  if node.arguments:
    for arg in node.arguments:
      transpiler.emit(", ")
      transpiler.visit(arg.expr)
  transpiler.emit(")")


@IntrinsicRegistry.register("String", "to_float", "python")
def _emit_str_to_float_py(transpiler: Any, node: CallNode) -> None:
  transpiler.emit("_sapphire_string_to_float(")
  transpiler.visit(node.callee.receiver)
  transpiler.emit(")")


@IntrinsicRegistry.register("String", "to_float", "lua")
def _emit_str_to_float_lua(transpiler: Any, node: CallNode) -> None:
  transpiler.emit("_sapphire_string_to_float(")
  transpiler.visit(node.callee.receiver)
  transpiler.emit(")")


@IntrinsicRegistry.register("String", "to_bool", "python")
def _emit_str_to_bool_py(transpiler: Any, node: CallNode) -> None:
  transpiler.emit("_sapphire_string_to_bool(")
  transpiler.visit(node.callee.receiver)
  transpiler.emit(")")


@IntrinsicRegistry.register("String", "to_bool", "lua")
def _emit_str_to_bool_lua(transpiler: Any, node: CallNode) -> None:
  transpiler.emit("_sapphire_string_to_bool(")
  transpiler.visit(node.callee.receiver)
  transpiler.emit(")")



# Register Array and Map intrinsic handlers on import.
import src.code_gen.collection_intrinsics as _collection_intrinsics  # noqa: E402, F401
