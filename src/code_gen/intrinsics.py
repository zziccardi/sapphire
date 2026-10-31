"""Intrinsic method and standard library dispatch table for code generators.

Provides table-driven code emission for Sapphire built-in primitives and standard
data structures (String, Array, Map, Range, and Enum) across Python and Lua backends.
"""

from typing import Any, Callable, Dict, Tuple
from src.parser.ast import CallNode, IdentifierNode, MemberAccessNode

BUILTIN_MODULES = ("std.testing", "std.math")


def is_builtin_module(import_path: str) -> bool:
  """Returns True if the given import path belongs to Sapphire's built-in modules."""
  return any(
      import_path == mod or import_path.startswith(mod + ".")
      for mod in BUILTIN_MODULES
  )


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

    if isinstance(node.callee, IdentifierNode) and node.callee.name == "range":
      category = "global"
      method = "range"
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
        handler(transpiler, node)
        return True

    return False


# ==============================================================================
# Global Intrinsics: range()
# ==============================================================================


@IntrinsicRegistry.register("global", "range", "python")
def _emit_range_py(transpiler: Any, node: CallNode) -> None:
  pos_args = [arg for arg in node.arguments if not arg.name]
  named_args = {arg.name: arg.expr for arg in node.arguments if arg.name}

  if len(pos_args) == 1 and not named_args:
    transpiler.emit("range(")
    transpiler.visit(pos_args[0].expr)
    transpiler.emit(")")
    return
  elif len(pos_args) == 2 and not named_args:
    transpiler.emit("range(")
    transpiler.visit(pos_args[0].expr)
    transpiler.emit(", ")
    transpiler.visit(pos_args[1].expr)
    transpiler.emit(")")
    return
  elif len(pos_args) == 3 and not named_args:
    transpiler.emit("range(")
    transpiler.visit(pos_args[0].expr)
    transpiler.emit(", ")
    transpiler.visit(pos_args[1].expr)
    transpiler.emit(", ")
    transpiler.visit(pos_args[2].expr)
    transpiler.emit(")")
    return

  start_expr = None
  stop_expr = None
  step_expr = None
  if len(pos_args) >= 1:
    if "stop" in named_args:
      start_expr = pos_args[0].expr
    else:
      if len(pos_args) == 1:
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

  transpiler.emit("range(")
  if step_expr is not None:
    if start_expr is not None:
      transpiler.visit(start_expr)
    else:
      transpiler.emit("0")
    transpiler.emit(", ")
    transpiler.visit(stop_expr)
    transpiler.emit(", ")
    transpiler.visit(step_expr)
  elif start_expr is not None:
    transpiler.visit(start_expr)
    transpiler.emit(", ")
    transpiler.visit(stop_expr)
  else:
    transpiler.visit(stop_expr)
  transpiler.emit(")")


@IntrinsicRegistry.register("global", "range", "lua")
def _emit_range_lua(transpiler: Any, node: CallNode) -> None:
  transpiler.emit("_sapphire_range(")
  for idx, arg in enumerate(node.arguments):
    if idx > 0:
      transpiler.emit(", ")
    transpiler.visit(arg.expr)
  transpiler.emit(")")


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
  transpiler.emit("(")
  transpiler.visit(node.arguments[0].expr)
  transpiler.emit(" in ")
  transpiler.visit(node.callee.receiver)
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
  transpiler.emit("_sapphire_string_find(")
  transpiler.visit(node.callee.receiver)
  args_by_param = [None, None, None]
  param_names = ["sub", "start", "reverse"]
  for idx, arg in enumerate(node.arguments):
    if arg.name and arg.name in param_names:
      p_idx = param_names.index(arg.name)
      args_by_param[p_idx] = arg.expr
    elif idx < 3:
      args_by_param[idx] = arg.expr
  while args_by_param and args_by_param[-1] is None:
    args_by_param.pop()
  for p_expr in args_by_param:
    transpiler.emit(", ")
    if p_expr is None:
      transpiler.emit("nil")
    else:
      transpiler.visit(p_expr)
  transpiler.emit(")")


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


# ==============================================================================
# Array Methods (Python & Lua)
# ==============================================================================


@IntrinsicRegistry.register("Array", "size", "python")
def _emit_arr_size_py(transpiler: Any, node: CallNode) -> None:
  transpiler.emit("len(")
  transpiler.visit(node.callee.receiver)
  transpiler.emit(")")


@IntrinsicRegistry.register("Array", "size", "lua")
def _emit_arr_size_lua(transpiler: Any, node: CallNode) -> None:
  transpiler.emit("#")
  transpiler.visit(node.callee.receiver)


@IntrinsicRegistry.register("Array", "empty", "python")
def _emit_arr_empty_py(transpiler: Any, node: CallNode) -> None:
  transpiler.emit("(len(")
  transpiler.visit(node.callee.receiver)
  transpiler.emit(") == 0)")


@IntrinsicRegistry.register("Array", "empty", "lua")
def _emit_arr_empty_lua(transpiler: Any, node: CallNode) -> None:
  transpiler.emit("(#")
  transpiler.visit(node.callee.receiver)
  transpiler.emit(" == 0)")


@IntrinsicRegistry.register("Array", "get", "python")
def _emit_arr_get_py(transpiler: Any, node: CallNode) -> None:
  transpiler.emit("_sapphire_array_get(")
  transpiler.visit(node.callee.receiver)
  transpiler.emit(", ")
  transpiler.visit(node.arguments[0].expr)
  transpiler.emit(")")


@IntrinsicRegistry.register("Array", "get", "lua")
def _emit_arr_get_lua(transpiler: Any, node: CallNode) -> None:
  transpiler.emit("_sapphire_array_get(")
  transpiler.visit(node.callee.receiver)
  transpiler.emit(", ")
  transpiler.visit(node.arguments[0].expr)
  transpiler.emit(")")


@IntrinsicRegistry.register("Array", "map", "python")
def _emit_arr_map_py(transpiler: Any, node: CallNode) -> None:
  transpiler.emit("_sapphire_array_map(")
  transpiler.visit(node.callee.receiver)
  fn_expr = None
  in_place_expr = None
  for idx, arg in enumerate(node.arguments):
    if arg.name == "fn" or (idx == 0 and not arg.name):
      fn_expr = arg.expr
    elif arg.name == "in_place" or (idx == 1 and not arg.name):
      in_place_expr = arg.expr
  transpiler.emit(", ")
  transpiler.visit(fn_expr)
  if in_place_expr:
    transpiler.emit(", in_place=")
    transpiler.visit(in_place_expr)
  transpiler.emit(")")


@IntrinsicRegistry.register("Array", "map", "lua")
def _emit_arr_map_lua(transpiler: Any, node: CallNode) -> None:
  transpiler.emit("_sapphire_array_map(")
  transpiler.visit(node.callee.receiver)
  fn_expr = None
  in_place_expr = None
  for idx, arg in enumerate(node.arguments):
    if arg.name == "fn" or (idx == 0 and not arg.name):
      fn_expr = arg.expr
    elif arg.name == "in_place" or (idx == 1 and not arg.name):
      in_place_expr = arg.expr
  transpiler.emit(", ")
  transpiler.visit(fn_expr)
  if in_place_expr:
    transpiler.emit(", ")
    transpiler.visit(in_place_expr)
  transpiler.emit(")")


@IntrinsicRegistry.register("Array", "filter", "python")
def _emit_arr_filter_py(transpiler: Any, node: CallNode) -> None:
  transpiler.emit("_sapphire_array_filter(")
  transpiler.visit(node.callee.receiver)
  fn_expr = None
  in_place_expr = None
  for idx, arg in enumerate(node.arguments):
    if arg.name == "fn" or (idx == 0 and not arg.name):
      fn_expr = arg.expr
    elif arg.name == "in_place" or (idx == 1 and not arg.name):
      in_place_expr = arg.expr
  transpiler.emit(", ")
  transpiler.visit(fn_expr)
  if in_place_expr:
    transpiler.emit(", in_place=")
    transpiler.visit(in_place_expr)
  transpiler.emit(")")


@IntrinsicRegistry.register("Array", "filter", "lua")
def _emit_arr_filter_lua(transpiler: Any, node: CallNode) -> None:
  transpiler.emit("_sapphire_array_filter(")
  transpiler.visit(node.callee.receiver)
  fn_expr = None
  in_place_expr = None
  for idx, arg in enumerate(node.arguments):
    if arg.name == "fn" or (idx == 0 and not arg.name):
      fn_expr = arg.expr
    elif arg.name == "in_place" or (idx == 1 and not arg.name):
      in_place_expr = arg.expr
  transpiler.emit(", ")
  transpiler.visit(fn_expr)
  if in_place_expr:
    transpiler.emit(", ")
    transpiler.visit(in_place_expr)
  transpiler.emit(")")


@IntrinsicRegistry.register("Array", "reduce", "python")
def _emit_arr_reduce_py(transpiler: Any, node: CallNode) -> None:
  transpiler.emit("_sapphire_array_reduce(")
  transpiler.visit(node.callee.receiver)
  initial_expr = None
  fn_expr = None
  reverse_expr = None
  for idx, arg in enumerate(node.arguments):
    if arg.name == "initial" or (idx == 0 and not arg.name):
      initial_expr = arg.expr
    elif arg.name == "fn" or (idx == 1 and not arg.name):
      fn_expr = arg.expr
    elif arg.name == "reverse" or (idx == 2 and not arg.name):
      reverse_expr = arg.expr
  transpiler.emit(", ")
  transpiler.visit(initial_expr)
  transpiler.emit(", ")
  transpiler.visit(fn_expr)
  if reverse_expr:
    transpiler.emit(", reverse=")
    transpiler.visit(reverse_expr)
  transpiler.emit(")")


@IntrinsicRegistry.register("Array", "reduce", "lua")
def _emit_arr_reduce_lua(transpiler: Any, node: CallNode) -> None:
  transpiler.emit("_sapphire_array_reduce(")
  transpiler.visit(node.callee.receiver)
  initial_expr = None
  fn_expr = None
  reverse_expr = None
  for idx, arg in enumerate(node.arguments):
    if arg.name == "initial" or (idx == 0 and not arg.name):
      initial_expr = arg.expr
    elif arg.name == "fn" or (idx == 1 and not arg.name):
      fn_expr = arg.expr
    elif arg.name == "reverse" or (idx == 2 and not arg.name):
      reverse_expr = arg.expr
  transpiler.emit(", ")
  transpiler.visit(initial_expr)
  transpiler.emit(", ")
  transpiler.visit(fn_expr)
  if reverse_expr:
    transpiler.emit(", ")
    transpiler.visit(reverse_expr)
  transpiler.emit(")")


@IntrinsicRegistry.register("Array", "contains", "python")
def _emit_arr_contains_py(transpiler: Any, node: CallNode) -> None:
  transpiler.emit("_sapphire_array_contains(")
  transpiler.visit(node.callee.receiver)
  transpiler.emit(", ")
  transpiler.visit(node.arguments[0].expr)
  transpiler.emit(")")


@IntrinsicRegistry.register("Array", "contains", "lua")
def _emit_arr_contains_lua(transpiler: Any, node: CallNode) -> None:
  transpiler.emit("_sapphire_array_contains(")
  transpiler.visit(node.callee.receiver)
  transpiler.emit(", ")
  transpiler.visit(node.arguments[0].expr)
  transpiler.emit(")")


@IntrinsicRegistry.register("Array", "reverse", "python")
def _emit_arr_reverse_py(transpiler: Any, node: CallNode) -> None:
  transpiler.emit("_sapphire_array_reverse(")
  transpiler.visit(node.callee.receiver)
  if node.arguments:
    transpiler.emit(", in_place=")
    transpiler.visit(node.arguments[0].expr)
  transpiler.emit(")")


@IntrinsicRegistry.register("Array", "reverse", "lua")
def _emit_arr_reverse_lua(transpiler: Any, node: CallNode) -> None:
  transpiler.emit("_sapphire_array_reverse(")
  transpiler.visit(node.callee.receiver)
  if node.arguments:
    transpiler.emit(", ")
    transpiler.visit(node.arguments[0].expr)
  transpiler.emit(")")


@IntrinsicRegistry.register("Array", "sort", "python")
def _emit_arr_sort_py(transpiler: Any, node: CallNode) -> None:
  transpiler.emit("_sapphire_array_sort(")
  transpiler.visit(node.callee.receiver)
  by_expr = None
  reverse_expr = None
  in_place_expr = None
  for idx, arg in enumerate(node.arguments):
    if arg.name == "by" or (idx == 0 and not arg.name):
      by_expr = arg.expr
    elif arg.name == "reverse" or (idx == 1 and not arg.name):
      reverse_expr = arg.expr
    elif arg.name == "in_place" or (idx == 2 and not arg.name):
      in_place_expr = arg.expr

  transpiler.emit(", ")
  if by_expr:
    transpiler.visit(by_expr)
  else:
    transpiler.emit("None")
  if reverse_expr:
    transpiler.emit(", reverse=")
    transpiler.visit(reverse_expr)
  else:
    transpiler.emit(", reverse=False")
  if in_place_expr:
    transpiler.emit(", in_place=")
    transpiler.visit(in_place_expr)
  transpiler.emit(")")


@IntrinsicRegistry.register("Array", "sort", "lua")
def _emit_arr_sort_lua(transpiler: Any, node: CallNode) -> None:
  transpiler.emit("_sapphire_array_sort(")
  transpiler.visit(node.callee.receiver)
  by_expr = None
  reverse_expr = None
  in_place_expr = None
  for idx, arg in enumerate(node.arguments):
    if arg.name == "by" or (idx == 0 and not arg.name):
      by_expr = arg.expr
    elif arg.name == "reverse" or (idx == 1 and not arg.name):
      reverse_expr = arg.expr
    elif arg.name == "in_place" or (idx == 2 and not arg.name):
      in_place_expr = arg.expr

  transpiler.emit(", ")
  if by_expr:
    transpiler.visit(by_expr)
  else:
    transpiler.emit("nil")
  if reverse_expr:
    transpiler.emit(", ")
    transpiler.visit(reverse_expr)
  else:
    transpiler.emit(", false")
  if in_place_expr:
    transpiler.emit(", ")
    transpiler.visit(in_place_expr)
  transpiler.emit(")")


@IntrinsicRegistry.register("Array", "join", "python")
def _emit_arr_join_py(transpiler: Any, node: CallNode) -> None:
  transpiler.emit("_sapphire_array_join(")
  transpiler.visit(node.callee.receiver)
  if node.arguments:
    transpiler.emit(", ")
    transpiler.visit(node.arguments[0].expr)
  transpiler.emit(")")


@IntrinsicRegistry.register("Array", "join", "lua")
def _emit_arr_join_lua(transpiler: Any, node: CallNode) -> None:
  transpiler.emit("_sapphire_array_join(")
  transpiler.visit(node.callee.receiver)
  if node.arguments:
    transpiler.emit(", ")
    transpiler.visit(node.arguments[0].expr)
  transpiler.emit(")")


@IntrinsicRegistry.register("Array", "push", "python")
def _emit_arr_push_py(transpiler: Any, node: CallNode) -> None:
  transpiler.emit("_sapphire_array_push(")
  transpiler.visit(node.callee.receiver)
  transpiler.emit(", ")
  transpiler.visit(node.arguments[0].expr)
  transpiler.emit(")")


@IntrinsicRegistry.register("Array", "push", "lua")
def _emit_arr_push_lua(transpiler: Any, node: CallNode) -> None:
  transpiler.emit("_sapphire_array_push(")
  transpiler.visit(node.callee.receiver)
  transpiler.emit(", ")
  transpiler.visit(node.arguments[0].expr)
  transpiler.emit(")")


@IntrinsicRegistry.register("Array", "pop", "python")
def _emit_arr_pop_py(transpiler: Any, node: CallNode) -> None:
  transpiler.emit("_sapphire_array_pop(")
  transpiler.visit(node.callee.receiver)
  transpiler.emit(")")


@IntrinsicRegistry.register("Array", "pop", "lua")
def _emit_arr_pop_lua(transpiler: Any, node: CallNode) -> None:
  transpiler.emit("_sapphire_array_pop(")
  transpiler.visit(node.callee.receiver)
  transpiler.emit(")")


@IntrinsicRegistry.register("Array", "insert", "python")
def _emit_arr_insert_py(transpiler: Any, node: CallNode) -> None:
  transpiler.emit("_sapphire_array_insert(")
  transpiler.visit(node.callee.receiver)
  index_expr = None
  element_expr = None
  for idx, arg in enumerate(node.arguments):
    if arg.name == "index" or (idx == 0 and not arg.name):
      index_expr = arg.expr
    elif arg.name == "element" or (idx == 1 and not arg.name):
      element_expr = arg.expr
  transpiler.emit(", ")
  transpiler.visit(index_expr)
  transpiler.emit(", ")
  transpiler.visit(element_expr)
  transpiler.emit(")")


@IntrinsicRegistry.register("Array", "insert", "lua")
def _emit_arr_insert_lua(transpiler: Any, node: CallNode) -> None:
  transpiler.emit("_sapphire_array_insert(")
  transpiler.visit(node.callee.receiver)
  index_expr = None
  element_expr = None
  for idx, arg in enumerate(node.arguments):
    if arg.name == "index" or (idx == 0 and not arg.name):
      index_expr = arg.expr
    elif arg.name == "element" or (idx == 1 and not arg.name):
      element_expr = arg.expr
  transpiler.emit(", ")
  transpiler.visit(index_expr)
  transpiler.emit(", ")
  transpiler.visit(element_expr)
  transpiler.emit(")")


@IntrinsicRegistry.register("Array", "remove", "python")
def _emit_arr_remove_py(transpiler: Any, node: CallNode) -> None:
  transpiler.emit("_sapphire_array_remove(")
  transpiler.visit(node.callee.receiver)
  transpiler.emit(", ")
  transpiler.visit(node.arguments[0].expr)
  transpiler.emit(")")


@IntrinsicRegistry.register("Array", "remove", "lua")
def _emit_arr_remove_lua(transpiler: Any, node: CallNode) -> None:
  transpiler.emit("_sapphire_array_remove(")
  transpiler.visit(node.callee.receiver)
  transpiler.emit(", ")
  transpiler.visit(node.arguments[0].expr)
  transpiler.emit(")")


@IntrinsicRegistry.register("Array", "clear", "python")
def _emit_arr_clear_py(transpiler: Any, node: CallNode) -> None:
  transpiler.emit("_sapphire_array_clear(")
  transpiler.visit(node.callee.receiver)
  transpiler.emit(")")


@IntrinsicRegistry.register("Array", "clear", "lua")
def _emit_arr_clear_lua(transpiler: Any, node: CallNode) -> None:
  transpiler.emit("_sapphire_array_clear(")
  transpiler.visit(node.callee.receiver)
  transpiler.emit(")")


# ==============================================================================
# Map Methods (Python & Lua)
# ==============================================================================


@IntrinsicRegistry.register("Map", "size", "python")
def _emit_map_size_py(transpiler: Any, node: CallNode) -> None:
  transpiler.emit("_sapphire_map_size(")
  transpiler.visit(node.callee.receiver)
  transpiler.emit(")")


@IntrinsicRegistry.register("Map", "size", "lua")
def _emit_map_size_lua(transpiler: Any, node: CallNode) -> None:
  transpiler.emit("_sapphire_map_size(")
  transpiler.visit(node.callee.receiver)
  transpiler.emit(")")


@IntrinsicRegistry.register("Map", "empty", "python")
def _emit_map_empty_py(transpiler: Any, node: CallNode) -> None:
  transpiler.emit("_sapphire_map_empty(")
  transpiler.visit(node.callee.receiver)
  transpiler.emit(")")


@IntrinsicRegistry.register("Map", "empty", "lua")
def _emit_map_empty_lua(transpiler: Any, node: CallNode) -> None:
  transpiler.emit("_sapphire_map_empty(")
  transpiler.visit(node.callee.receiver)
  transpiler.emit(")")


@IntrinsicRegistry.register("Map", "contains", "python")
def _emit_map_contains_py(transpiler: Any, node: CallNode) -> None:
  transpiler.emit("_sapphire_map_contains(")
  transpiler.visit(node.callee.receiver)
  transpiler.emit(", ")
  transpiler.visit(node.arguments[0].expr)
  transpiler.emit(")")


@IntrinsicRegistry.register("Map", "contains", "lua")
def _emit_map_contains_lua(transpiler: Any, node: CallNode) -> None:
  transpiler.emit("_sapphire_map_contains(")
  transpiler.visit(node.callee.receiver)
  transpiler.emit(", ")
  transpiler.visit(node.arguments[0].expr)
  transpiler.emit(")")


@IntrinsicRegistry.register("Map", "get", "python")
def _emit_map_get_py(transpiler: Any, node: CallNode) -> None:
  transpiler.emit("_sapphire_map_get(")
  transpiler.visit(node.callee.receiver)
  transpiler.emit(", ")
  transpiler.visit(node.arguments[0].expr)
  transpiler.emit(")")


@IntrinsicRegistry.register("Map", "get", "lua")
def _emit_map_get_lua(transpiler: Any, node: CallNode) -> None:
  transpiler.emit("_sapphire_map_get(")
  transpiler.visit(node.callee.receiver)
  transpiler.emit(", ")
  transpiler.visit(node.arguments[0].expr)
  transpiler.emit(")")


@IntrinsicRegistry.register("Map", "keys", "python")
def _emit_map_keys_py(transpiler: Any, node: CallNode) -> None:
  transpiler.emit("_sapphire_map_keys(")
  transpiler.visit(node.callee.receiver)
  transpiler.emit(")")


@IntrinsicRegistry.register("Map", "keys", "lua")
def _emit_map_keys_lua(transpiler: Any, node: CallNode) -> None:
  transpiler.emit("_sapphire_map_keys(")
  transpiler.visit(node.callee.receiver)
  transpiler.emit(")")


@IntrinsicRegistry.register("Map", "values", "python")
def _emit_map_values_py(transpiler: Any, node: CallNode) -> None:
  transpiler.emit("_sapphire_map_values(")
  transpiler.visit(node.callee.receiver)
  transpiler.emit(")")


@IntrinsicRegistry.register("Map", "values", "lua")
def _emit_map_values_lua(transpiler: Any, node: CallNode) -> None:
  transpiler.emit("_sapphire_map_values(")
  transpiler.visit(node.callee.receiver)
  transpiler.emit(")")


@IntrinsicRegistry.register("Map", "insert", "python")
def _emit_map_insert_py(transpiler: Any, node: CallNode) -> None:
  transpiler.emit("_sapphire_map_insert(")
  transpiler.visit(node.callee.receiver)
  key_expr = None
  val_expr = None
  for idx, arg in enumerate(node.arguments):
    if arg.name == "key" or (idx == 0 and not arg.name):
      key_expr = arg.expr
    elif arg.name == "value" or (idx == 1 and not arg.name):
      val_expr = arg.expr
  transpiler.emit(", ")
  transpiler.visit(key_expr)
  transpiler.emit(", ")
  transpiler.visit(val_expr)
  transpiler.emit(")")


@IntrinsicRegistry.register("Map", "insert", "lua")
def _emit_map_insert_lua(transpiler: Any, node: CallNode) -> None:
  transpiler.emit("_sapphire_map_insert(")
  transpiler.visit(node.callee.receiver)
  key_expr = None
  val_expr = None
  for idx, arg in enumerate(node.arguments):
    if arg.name == "key" or (idx == 0 and not arg.name):
      key_expr = arg.expr
    elif arg.name == "value" or (idx == 1 and not arg.name):
      val_expr = arg.expr
  transpiler.emit(", ")
  transpiler.visit(key_expr)
  transpiler.emit(", ")
  transpiler.visit(val_expr)
  transpiler.emit(")")


@IntrinsicRegistry.register("Map", "remove", "python")
def _emit_map_remove_py(transpiler: Any, node: CallNode) -> None:
  transpiler.emit("_sapphire_map_remove(")
  transpiler.visit(node.callee.receiver)
  transpiler.emit(", ")
  transpiler.visit(node.arguments[0].expr)
  transpiler.emit(")")


@IntrinsicRegistry.register("Map", "remove", "lua")
def _emit_map_remove_lua(transpiler: Any, node: CallNode) -> None:
  transpiler.emit("_sapphire_map_remove(")
  transpiler.visit(node.callee.receiver)
  transpiler.emit(", ")
  transpiler.visit(node.arguments[0].expr)
  transpiler.emit(")")


@IntrinsicRegistry.register("Map", "clear", "python")
def _emit_map_clear_py(transpiler: Any, node: CallNode) -> None:
  transpiler.emit("_sapphire_map_clear(")
  transpiler.visit(node.callee.receiver)
  transpiler.emit(")")


@IntrinsicRegistry.register("Map", "clear", "lua")
def _emit_map_clear_lua(transpiler: Any, node: CallNode) -> None:
  transpiler.emit("_sapphire_map_clear(")
  transpiler.visit(node.callee.receiver)
  transpiler.emit(")")
