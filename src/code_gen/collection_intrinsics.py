"""Intrinsic code generation handlers for Sapphire Array and Map methods."""

from typing import Any
from src.parser.ast import CallNode
from src.code_gen.intrinsics import IntrinsicRegistry

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


@IntrinsicRegistry.register("Array", "swap", "python")
def _emit_arr_swap_py(transpiler: Any, node: CallNode) -> None:
  transpiler.emit("_sapphire_array_swap(")
  transpiler.visit(node.callee.receiver)
  i_expr = None
  j_expr = None
  for idx, arg in enumerate(node.arguments):
    if arg.name == "i" or (idx == 0 and not arg.name):
      i_expr = arg.expr
    elif arg.name == "j" or (idx == 1 and not arg.name):
      j_expr = arg.expr
  transpiler.emit(", ")
  transpiler.visit(i_expr)
  transpiler.emit(", ")
  transpiler.visit(j_expr)
  transpiler.emit(")")


@IntrinsicRegistry.register("Array", "swap", "lua")
def _emit_arr_swap_lua(transpiler: Any, node: CallNode) -> None:
  transpiler.emit("_sapphire_array_swap(")
  transpiler.visit(node.callee.receiver)
  i_expr = None
  j_expr = None
  for idx, arg in enumerate(node.arguments):
    if arg.name == "i" or (idx == 0 and not arg.name):
      i_expr = arg.expr
    elif arg.name == "j" or (idx == 1 and not arg.name):
      j_expr = arg.expr
  transpiler.emit(", ")
  transpiler.visit(i_expr)
  transpiler.emit(", ")
  transpiler.visit(j_expr)
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
