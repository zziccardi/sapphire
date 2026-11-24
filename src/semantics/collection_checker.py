"""Collection and builtin method type-checking helper for Sapphire.

Decouples Array and Map method resolution and call-site argument validation from
the core TypeChecker.
"""

from typing import Any, Dict, List, Optional

from src.parser.ast import (
  CallNode,
  IdentifierNode,
  LiteralNode,
  MemberAccessNode,
)
from src.semantics.arena_checker import ArenaChecker
from src.semantics.semantic_context import TypeCheckerProtocol
from src.semantics.symbol_table import (
  ARRAY_METHODS,
  MAP_METHODS,
  ArrayType,
  FunctionType,
  InferredType,
  MapType,
  OptionalType,
  PrimitiveType,
  StringType,
  Type,
  VariableSymbol,
)


class CollectionChecker:
  """Helper class for resolving and validating Array and Map method calls."""

  @staticmethod
  def resolve_array_member(
    checker: TypeCheckerProtocol,
    node: MemberAccessNode,
    receiver_type: ArrayType,
  ) -> Type:
    """Resolves member access on an ArrayType receiver."""
    if node.member in ARRAY_METHODS:
      # Attach resolved metadata so downstream codegen can emit intrinsic calls.
      node.is_array_method = True
      node.array_method = node.member
      node.array_receiver_type = receiver_type
      elem_t = receiver_type.element_type
      if node.member == "size":
        return FunctionType(
          [receiver_type],
          PrimitiveType("int"),
          param_names=["self"],
          has_self=True,
        )
      elif node.member == "empty":
        return FunctionType(
          [receiver_type],
          PrimitiveType("bool"),
          param_names=["self"],
          has_self=True,
        )
      elif node.member == "get":
        return FunctionType(
          [receiver_type, PrimitiveType("int")],
          OptionalType(elem_t),
          param_names=["self", "index"],
          has_self=True,
        )
      elif node.member == "map":
        return FunctionType(
          [
            receiver_type,
            FunctionType([elem_t], InferredType()),
            PrimitiveType("bool"),
          ],
          ArrayType(InferredType(), size=receiver_type.size),
          param_names=["self", "fn", "in_place"],
          has_self=True,
          num_defaults=1,
        )
      elif node.member == "filter":
        return FunctionType(
          [
            receiver_type,
            FunctionType([elem_t], PrimitiveType("bool")),
            PrimitiveType("bool"),
          ],
          ArrayType(elem_t),
          param_names=["self", "fn", "in_place"],
          has_self=True,
          num_defaults=1,
        )
      elif node.member == "reduce":
        return FunctionType(
          [
            receiver_type,
            InferredType(),
            FunctionType([InferredType(), elem_t], InferredType()),
            PrimitiveType("bool"),
          ],
          InferredType(),
          param_names=["self", "initial", "fn", "reverse"],
          has_self=True,
          num_defaults=1,
        )
      elif node.member == "contains":
        return FunctionType(
          [receiver_type, elem_t],
          PrimitiveType("bool"),
          param_names=["self", "element"],
          has_self=True,
        )
      elif node.member == "reverse":
        return FunctionType(
          [receiver_type, PrimitiveType("bool")],
          ArrayType(elem_t, size=receiver_type.size),
          param_names=["self", "in_place"],
          has_self=True,
          num_defaults=1,
        )
      elif node.member == "sort":
        return FunctionType(
          [
            receiver_type,
            OptionalType(FunctionType([elem_t, elem_t], PrimitiveType("int"))),
            PrimitiveType("bool"),
            PrimitiveType("bool"),
          ],
          ArrayType(elem_t, size=receiver_type.size),
          param_names=["self", "by", "reverse", "in_place"],
          has_self=True,
          num_defaults=3,
        )
      elif node.member == "join":
        return FunctionType(
          [receiver_type, OptionalType(StringType())],
          StringType(),
          param_names=["self", "sep"],
          has_self=True,
          num_defaults=1,
        )
      elif node.member == "push":
        return FunctionType(
          [receiver_type, elem_t],
          elem_t,
          param_names=["self", "element"],
          has_self=True,
        )
      elif node.member == "pop":
        return FunctionType(
          [receiver_type],
          OptionalType(elem_t),
          param_names=["self"],
          has_self=True,
        )
      elif node.member == "insert":
        return FunctionType(
          [receiver_type, PrimitiveType("int"), elem_t],
          elem_t,
          param_names=["self", "index", "element"],
          has_self=True,
        )
      elif node.member == "remove":
        return FunctionType(
          [receiver_type, PrimitiveType("int")],
          OptionalType(elem_t),
          param_names=["self", "index"],
          has_self=True,
        )
      elif node.member == "clear":
        return FunctionType(
          [receiver_type],
          PrimitiveType("none"),
          param_names=["self"],
          has_self=True,
        )
      elif node.member == "swap":
        return FunctionType(
          [receiver_type, PrimitiveType("int"), PrimitiveType("int")],
          PrimitiveType("none"),
          param_names=["self", "i", "j"],
          has_self=True,
        )
    checker.error(f"Array has no method '{node.member}'.")
    return PrimitiveType("none")

  @staticmethod
  def resolve_map_member(
    checker: Any, node: MemberAccessNode, receiver_type: MapType
  ) -> Type:
    """Resolves member access on a MapType receiver."""
    if node.member in MAP_METHODS:
      # Attach resolved metadata so downstream codegen can emit intrinsic calls.
      node.is_map_method = True
      node.map_method = node.member
      node.map_receiver_type = receiver_type
      k_type = receiver_type.key_type
      v_type = receiver_type.value_type
      if node.member == "size":
        return FunctionType(
          [receiver_type],
          PrimitiveType("int"),
          param_names=["self"],
          has_self=True,
        )
      elif node.member == "empty":
        return FunctionType(
          [receiver_type],
          PrimitiveType("bool"),
          param_names=["self"],
          has_self=True,
        )
      elif node.member == "contains":
        return FunctionType(
          [receiver_type, k_type],
          PrimitiveType("bool"),
          param_names=["self", "key"],
          has_self=True,
        )
      elif node.member == "get":
        return FunctionType(
          [receiver_type, k_type],
          OptionalType(v_type),
          param_names=["self", "key"],
          has_self=True,
        )
      elif node.member == "keys":
        return FunctionType(
          [receiver_type],
          ArrayType(k_type),
          param_names=["self"],
          has_self=True,
        )
      elif node.member == "values":
        return FunctionType(
          [receiver_type],
          ArrayType(v_type),
          param_names=["self"],
          has_self=True,
        )
      elif node.member == "insert":
        return FunctionType(
          [receiver_type, k_type, v_type],
          v_type,
          param_names=["self", "key", "value"],
          has_self=True,
        )
      elif node.member == "remove":
        return FunctionType(
          [receiver_type, k_type],
          OptionalType(v_type),
          param_names=["self", "key"],
          has_self=True,
        )
      elif node.member == "clear":
        return FunctionType(
          [receiver_type],
          PrimitiveType("none"),
          param_names=["self"],
          has_self=True,
        )
    checker.error(f"Map has no method '{node.member}'.")
    return PrimitiveType("none")

  @staticmethod
  def _bind_args(
    arguments: List[Any],
    param_names: List[str],
    checker: Optional[Any] = None,
    method_name: Optional[str] = None,
  ) -> Dict[str, Any]:
    """Maps positional and named call arguments to parameter names and validates
    arity/names.
    """
    bound: Dict[str, Any] = {}
    label = f".{method_name}()" if method_name else "collection method"
    reported_too_many = False
    for idx, arg in enumerate(arguments):
      if arg.name:
        if arg.name not in param_names:
          if checker is not None:
            checker.error(f"Unknown named argument '{arg.name}' in {label}.")
          continue
        if arg.name in bound:
          if checker is not None:
            checker.error(f"Duplicate argument '{arg.name}' in {label}.")
          continue
        bound[arg.name] = arg
      elif idx < len(param_names):
        pname = param_names[idx]
        if pname in bound:
          if checker is not None:
            checker.error(f"Duplicate argument '{pname}' in {label}.")
          continue
        bound[pname] = arg
      else:
        if checker is not None and not reported_too_many:
          noun = "argument" if len(param_names) == 1 else "arguments"
          checker.error(
            f"{label} takes at most {len(param_names)} {noun}, "
            f"got {len(arguments)}."
          )
          reported_too_many = True
    return bound

  @staticmethod
  def _check_mutating_receiver(
    checker: Any,
    receiver: Any,
    method_label: str,
    action_desc: str,
    include_iteration_hint: bool = False,
  ) -> None:
    """Validates that a collection receiver is mutable and not frozen."""
    if checker.has_shared_ref_base(receiver):
      checker.error(
        f"Cannot invoke {action_desc} '{method_label}' through deeply "
        "immutable 'SharedRef'."
      )
    res = ArenaChecker.get_lvalue_path(checker.symbol_table, receiver)
    if res:
      r, path = res
      sym = checker.symbol_table.lookup(r)
      if isinstance(sym, VariableSymbol) and not sym.is_mutable:
        checker.error(
          f"Cannot invoke {action_desc} '{method_label}' on constant "
          f"variable '{r}'."
        )
      else:
        immut = checker.find_immutable_field_in_chain(receiver)
        if immut is not None:
          field_name, struct_name = immut
          checker.error(
            f"Cannot invoke {action_desc} '{method_label}' through constant "
            f"field '{field_name}' of '{struct_name}'."
          )
      reason = checker.get_frozen_lvalue_reason(r, path)
      if reason:
        hint = ""
        if include_iteration_hint and "for-in loop iteration" in reason:
          hint = (
            f" Hint: Collections are frozen during iteration to prevent "
            f"iterator invalidation. To remove elements matching a "
            f"predicate, use '{r}.filter(fn, in_place = true)'. To spawn "
            f"or insert elements, stage them in a separate array and "
            f"append after the loop."
          )
        checker.error(
          f"Cannot invoke {action_desc} '{method_label}' on '{r}' "
          f"while it is frozen ({reason}).{hint}"
        )
    elif isinstance(receiver, IdentifierNode):
      sym = checker.symbol_table.lookup(receiver.name)
      if isinstance(sym, VariableSymbol) and not sym.is_mutable:
        checker.error(
          f"Cannot invoke {action_desc} '{method_label}' on constant "
          f"variable '{receiver.name}'."
        )

  @staticmethod
  def _visit_callback_with_frozen_receiver(
    checker: Any,
    receiver: Any,
    callback_expr: Any,
    expected_fn_type: FunctionType,
    freeze_label: str,
  ) -> Type:
    """Evaluates a collection callback while freezing the receiver lvalue.

    Freezing prevents mutations to the iterated collection from inside the
    callback (e.g. arr.map(x -> arr.push(x))).
    """
    old_expected = checker.expected_type
    checker.expected_type = expected_fn_type
    recv_res = ArenaChecker.get_lvalue_path(checker.symbol_table, receiver)
    if recv_res:
      checker.temporary_frozen_lvalues.append(
        (recv_res[0], recv_res[1], freeze_label)
      )
    try:
      return checker.visit(callback_expr)
    finally:
      if recv_res:
        checker.temporary_frozen_lvalues.pop()
      checker.expected_type = old_expected

  @staticmethod
  def _check_in_place_arg(
    checker: Any, in_place_arg: Any, method_name: str
  ) -> bool:
    """Validates an optional 'in_place' bool argument; returns True if
    potentially
    mutating.
    """
    if not in_place_arg:
      return False
    in_p_type = checker.visit(in_place_arg.expr)
    if not in_p_type.is_compatible(PrimitiveType("bool")):
      checker.error(
        f"'in_place' parameter in .{method_name}() must be 'bool', got "
        f"'{in_p_type}'."
      )
    # Any expression other than literal `false` may evaluate to `true` at
    # runtime and must satisfy all in-place mutability/type constraints.
    return not (
      isinstance(in_place_arg.expr, LiteralNode)
      and in_place_arg.expr.value is False
    )

  @staticmethod
  def _check_container_self_aliasing(
    checker: Any,
    receiver: Any,
    arg_expr: Any,
    item_label: str,
    method_name: str,
    node: CallNode,
  ) -> None:
    """Rejects passing an element/projection borrowed from the mutated
    container.

    Prevents reallocation use-after-free when a container mutates its buffer
    while holding a reference into its own storage (e.g. arr.push(arr[0])).
    """
    recv_res = ArenaChecker.get_lvalue_path(checker.symbol_table, receiver)
    arg_res = ArenaChecker.get_lvalue_path(checker.symbol_table, arg_expr)
    if recv_res and arg_res:
      r1, p1 = recv_res
      r2, p2 = arg_res
      if r1 == r2 and (p1[: len(p2)] == p2 or p2[: len(p1)] == p1):
        checker.error(
          f"Aliasing conflict: cannot pass {item_label} borrowed from "
          f"'{r1}' into mutating method '{method_name}' on the same "
          "container.",
          node=node,
        )

  @staticmethod
  def _check_array_map(
    checker: Any, node: CallNode, receiver_type: ArrayType
  ) -> Type:
    elem_type = receiver_type.element_type
    args = CollectionChecker._bind_args(
      node.arguments, ["fn", "in_place"], checker=checker, method_name="map"
    )
    fn_arg = args.get("fn")
    in_place_arg = args.get("in_place")

    if not fn_arg:
      checker.error(".map() requires at least 1 argument (fn).")
      return ArrayType(elem_type, size=receiver_type.size)

    fn_type = CollectionChecker._visit_callback_with_frozen_receiver(
      checker,
      node.callee.receiver,
      fn_arg.expr,
      FunctionType([elem_type], InferredType()),
      ".map() callback",
    )

    ret_elem_type: Type = PrimitiveType("none")
    if not isinstance(fn_type, FunctionType):
      checker.error(f".map() callback must be a function, got '{fn_type}'.")
    else:
      ret_elem_type = fn_type.return_type
      if len(fn_type.param_types) != 1:
        checker.error(
          ".map() callback must take 1 parameter, got "
          f"{len(fn_type.param_types)}."
        )
      elif not elem_type.is_compatible(fn_type.param_types[0]):
        checker.error(
          "Closure parameter type mismatch in .map(). "
          f"Expected '{elem_type}', got '{fn_type.param_types[0]}'."
        )

    is_in_place = CollectionChecker._check_in_place_arg(
      checker, in_place_arg, "map"
    )
    if is_in_place:
      CollectionChecker._check_mutating_receiver(
        checker, node.callee.receiver, ".map()", "in-place transformation"
      )
      if isinstance(fn_type, FunctionType) and not ret_elem_type.is_compatible(
        elem_type
      ):
        checker.error(
          "In-place mapping requires closure return type to match element "
          f"type '{elem_type}', got '{ret_elem_type}'."
        )
      return ArrayType(elem_type, size=receiver_type.size)

    if receiver_type.size is not None:
      return ArrayType(ret_elem_type, size=receiver_type.size)
    return ArrayType(ret_elem_type)

  @staticmethod
  def _check_array_filter(
    checker: Any, node: CallNode, receiver_type: ArrayType
  ) -> Type:
    elem_type = receiver_type.element_type
    args = CollectionChecker._bind_args(
      node.arguments, ["fn", "in_place"], checker=checker, method_name="filter"
    )
    fn_arg = args.get("fn")
    in_place_arg = args.get("in_place")

    if not fn_arg:
      checker.error(".filter() requires at least 1 argument (fn).")
      return ArrayType(elem_type)

    fn_type = CollectionChecker._visit_callback_with_frozen_receiver(
      checker,
      node.callee.receiver,
      fn_arg.expr,
      FunctionType([elem_type], PrimitiveType("bool")),
      ".filter() callback",
    )

    if not isinstance(fn_type, FunctionType):
      checker.error(f".filter() predicate must be a function, got '{fn_type}'.")
    else:
      if len(fn_type.param_types) != 1:
        checker.error(
          ".filter() predicate must take 1 parameter, got "
          f"{len(fn_type.param_types)}."
        )
      elif not elem_type.is_compatible(fn_type.param_types[0]):
        checker.error(
          "Closure parameter type mismatch in .filter(). Expected "
          f"'{elem_type}', got '{fn_type.param_types[0]}'."
        )
      if not fn_type.return_type.is_compatible(PrimitiveType("bool")):
        checker.error(
          ".filter() predicate closure must return 'bool', got "
          f"'{fn_type.return_type}'."
        )

    is_in_place = CollectionChecker._check_in_place_arg(
      checker, in_place_arg, "filter"
    )
    if is_in_place:
      # In-place filter changes array length, so fixed-size arrays cannot use
      # it.
      if receiver_type.is_fixed_size:
        checker.error(
          "Cannot invoke in-place '.filter()' on fixed-size array "
          f"'{receiver_type}'."
        )
      CollectionChecker._check_mutating_receiver(
        checker, node.callee.receiver, ".filter()", "in-place transformation"
      )

    return ArrayType(elem_type)

  @staticmethod
  def _check_array_reduce(
    checker: Any, node: CallNode, receiver_type: ArrayType
  ) -> Type:
    elem_type = receiver_type.element_type
    args = CollectionChecker._bind_args(
      node.arguments,
      ["initial", "fn", "reverse"],
      checker=checker,
      method_name="reduce",
    )
    initial_arg = args.get("initial")
    fn_arg = args.get("fn")
    reverse_arg = args.get("reverse")

    if not initial_arg or not fn_arg:
      checker.error(
        ".reduce() requires mandatory 'initial' and 'fn' arguments."
      )
      return elem_type

    acc_type = checker.visit(initial_arg.expr)
    fn_type = CollectionChecker._visit_callback_with_frozen_receiver(
      checker,
      node.callee.receiver,
      fn_arg.expr,
      FunctionType([acc_type, elem_type], acc_type),
      ".reduce() callback",
    )

    if not isinstance(fn_type, FunctionType):
      checker.error(f".reduce() callback must be a function, got '{fn_type}'.")
    else:
      if len(fn_type.param_types) != 2:
        checker.error(
          ".reduce() callback must take 2 parameters, got "
          f"{len(fn_type.param_types)}."
        )
      else:
        if not acc_type.is_compatible(fn_type.param_types[0]):
          checker.error(
            "Closure accumulator parameter mismatch in .reduce(). Expected "
            f"'{acc_type}', got '{fn_type.param_types[0]}'."
          )
        if not elem_type.is_compatible(fn_type.param_types[1]):
          checker.error(
            "Closure item parameter mismatch in .reduce(). Expected "
            f"'{elem_type}', got '{fn_type.param_types[1]}'."
          )
      if not fn_type.return_type.is_compatible(acc_type):
        checker.error(
          "Closure return type in .reduce() must match initial value type "
          f"'{acc_type}', got '{fn_type.return_type}'."
        )

    if reverse_arg:
      rev_type = checker.visit(reverse_arg.expr)
      if not rev_type.is_compatible(PrimitiveType("bool")):
        checker.error(
          f"'reverse' parameter in .reduce() must be 'bool', got '{rev_type}'."
        )

    return acc_type

  @staticmethod
  def _check_array_mutating(
    checker: Any, node: CallNode, receiver_type: ArrayType, method: str
  ) -> Type:
    elem_type = receiver_type.element_type
    # swap preserves array length, so it is permitted on fixed-size arrays.
    if receiver_type.is_fixed_size and method != "swap":
      checker.error(
        f"Cannot invoke mutating method '{method}' on fixed-size array "
        f"'{receiver_type}'."
      )
    CollectionChecker._check_mutating_receiver(
      checker,
      node.callee.receiver,
      method,
      "mutating method",
      include_iteration_hint=True,
    )

    if method == "push":
      if len(node.arguments) != 1:
        checker.error(".push() requires exactly 1 argument (element).")
        return elem_type
      arg_expr = node.arguments[0].expr
      arg_t = checker.visit(arg_expr)
      checker.check_value_ownership_transfer(arg_expr, arg_t, node=node)
      if not arg_t.is_compatible(elem_type):
        checker.error(
          f"Argument type mismatch in .push(). Expected '{elem_type}', "
          f"got '{arg_t}'."
        )
      if ArenaChecker.is_reference_type(elem_type):
        CollectionChecker._check_container_self_aliasing(
          checker, node.callee.receiver, arg_expr, "element", "push", node
        )
      ArenaChecker.validate_container_mutation(
        checker, node.callee.receiver, [arg_expr], error_node=node
      )
      return elem_type

    if method == "pop":
      if node.arguments:
        checker.error(".pop() takes no arguments.")
      return OptionalType(elem_type)

    if method == "insert":
      args = CollectionChecker._bind_args(
        node.arguments,
        ["index", "element"],
        checker=checker,
        method_name="insert",
      )
      index_arg = args.get("index")
      element_arg = args.get("element")
      if not index_arg or not element_arg:
        checker.error(
          ".insert() requires mandatory 'index' and 'element' arguments."
        )
        return elem_type
      idx_t = checker.visit(index_arg.expr)
      if not idx_t.is_compatible(PrimitiveType("int")):
        checker.error(
          f"Argument 'index' in .insert() must be 'int', got '{idx_t}'."
        )
      elem_t = checker.visit(element_arg.expr)
      checker.check_value_ownership_transfer(
        element_arg.expr, elem_t, node=node
      )
      if not elem_t.is_compatible(elem_type):
        checker.error(
          f"Argument type mismatch in .insert(). Expected '{elem_type}', "
          f"got '{elem_t}'."
        )
      if ArenaChecker.is_reference_type(elem_type):
        CollectionChecker._check_container_self_aliasing(
          checker,
          node.callee.receiver,
          element_arg.expr,
          "element",
          "insert",
          node,
        )
      ArenaChecker.validate_container_mutation(
        checker, node.callee.receiver, [element_arg.expr], error_node=node
      )
      return elem_type

    if method == "remove":
      if len(node.arguments) != 1:
        checker.error(".remove() requires exactly 1 argument (index).")
        return OptionalType(elem_type)
      idx_t = checker.visit(node.arguments[0].expr)
      if not idx_t.is_compatible(PrimitiveType("int")):
        checker.error(
          f"Argument 'index' in .remove() must be 'int', got '{idx_t}'."
        )
      return OptionalType(elem_type)

    if method == "clear":
      if node.arguments:
        checker.error(".clear() takes no arguments.")
      return PrimitiveType("none")

    # method == "swap"
    args = CollectionChecker._bind_args(
      node.arguments, ["i", "j"], checker=checker, method_name="swap"
    )
    i_arg = args.get("i")
    j_arg = args.get("j")
    if not i_arg or not j_arg:
      checker.error(".swap() requires mandatory 'i' and 'j' arguments.")
      return PrimitiveType("none")
    i_t = checker.visit(i_arg.expr)
    if not i_t.is_compatible(PrimitiveType("int")):
      checker.error(f"Argument 'i' in .swap() must be 'int', got '{i_t}'.")
    j_t = checker.visit(j_arg.expr)
    if not j_t.is_compatible(PrimitiveType("int")):
      checker.error(f"Argument 'j' in .swap() must be 'int', got '{j_t}'.")
    return PrimitiveType("none")

  @staticmethod
  def _check_array_reverse(
    checker: Any, node: CallNode, receiver_type: ArrayType
  ) -> Type:
    elem_type = receiver_type.element_type
    args = CollectionChecker._bind_args(
      node.arguments, ["in_place"], checker=checker, method_name="reverse"
    )
    in_place_arg = args.get("in_place")

    if CollectionChecker._check_in_place_arg(checker, in_place_arg, "reverse"):
      CollectionChecker._check_mutating_receiver(
        checker, node.callee.receiver, ".reverse()", "in-place transformation"
      )
    return ArrayType(elem_type, size=receiver_type.size)

  @staticmethod
  def _check_array_sort(
    checker: Any, node: CallNode, receiver_type: ArrayType
  ) -> Type:
    elem_type = receiver_type.element_type
    args = CollectionChecker._bind_args(
      node.arguments,
      ["by", "reverse", "in_place"],
      checker=checker,
      method_name="sort",
    )
    by_arg = args.get("by")
    reverse_arg = args.get("reverse")
    in_place_arg = args.get("in_place")

    if by_arg:
      by_type = CollectionChecker._visit_callback_with_frozen_receiver(
        checker,
        node.callee.receiver,
        by_arg.expr,
        FunctionType([elem_type, elem_type], PrimitiveType("int")),
        ".sort() callback",
      )
      if not isinstance(by_type, FunctionType):
        checker.error(
          f".sort() comparator must be a function, got '{by_type}'."
        )
      else:
        if len(by_type.param_types) != 2:
          checker.error(
            ".sort() comparator must take 2 parameters, got "
            f"{len(by_type.param_types)}."
          )
        else:
          if not elem_type.is_compatible(by_type.param_types[0]):
            checker.error(
              "Comparator parameter 1 mismatch in .sort(). Expected "
              f"'{elem_type}', got '{by_type.param_types[0]}'."
            )
          if not elem_type.is_compatible(by_type.param_types[1]):
            checker.error(
              "Comparator parameter 2 mismatch in .sort(). Expected "
              f"'{elem_type}', got '{by_type.param_types[1]}'."
            )
        if not by_type.return_type.is_compatible(PrimitiveType("int")):
          checker.error(
            "Comparator closure in .sort() must return 'int', got "
            f"'{by_type.return_type}'."
          )
    if reverse_arg:
      rev_t = checker.visit(reverse_arg.expr)
      if not rev_t.is_compatible(PrimitiveType("bool")):
        checker.error(
          f"'reverse' parameter in .sort() must be 'bool', got '{rev_t}'."
        )

    if CollectionChecker._check_in_place_arg(checker, in_place_arg, "sort"):
      CollectionChecker._check_mutating_receiver(
        checker, node.callee.receiver, ".sort()", "in-place transformation"
      )
    return ArrayType(elem_type, size=receiver_type.size)

  @staticmethod
  def check_array_method_call(checker: Any, node: CallNode) -> Optional[Type]:
    """Validates a call to a builtin Array method and returns its return Type.
    """
    method = node.callee.array_method
    receiver_type = node.callee.array_receiver_type
    elem_type = receiver_type.element_type

    if method == "size":
      if node.arguments:
        checker.error(".size() takes no arguments.")
      return PrimitiveType("int")
    if method == "empty":
      if node.arguments:
        checker.error(".empty() takes no arguments.")
      return PrimitiveType("bool")
    if method == "map":
      return CollectionChecker._check_array_map(checker, node, receiver_type)
    if method == "filter":
      return CollectionChecker._check_array_filter(checker, node, receiver_type)
    if method == "reduce":
      return CollectionChecker._check_array_reduce(checker, node, receiver_type)
    if method in ("push", "pop", "insert", "remove", "clear", "swap"):
      return CollectionChecker._check_array_mutating(
        checker, node, receiver_type, method
      )
    if method == "contains":
      if len(node.arguments) != 1:
        checker.error(".contains() requires exactly 1 argument (element).")
        return PrimitiveType("bool")
      arg_t = checker.visit(node.arguments[0].expr)
      if not arg_t.is_compatible(elem_type):
        checker.error(
          "Argument type mismatch in .contains(). "
          f"Expected '{elem_type}', got '{arg_t}'."
        )
      return PrimitiveType("bool")
    if method == "reverse":
      return CollectionChecker._check_array_reverse(
        checker, node, receiver_type
      )
    if method == "sort":
      return CollectionChecker._check_array_sort(checker, node, receiver_type)
    if method == "join":
      if len(node.arguments) > 1:
        checker.error(".join() takes at most 1 argument (sep).")
      elif len(node.arguments) == 1:
        sep_t = checker.visit(node.arguments[0].expr)
        if not sep_t.is_compatible(StringType()):
          checker.error(
            f"Delimiter 'sep' in .join() must be 'String', got '{sep_t}'."
          )
      return StringType()

    return None

  @staticmethod
  def _check_map_insert(
    checker: Any, node: CallNode, receiver_type: MapType
  ) -> Type:
    k_type = receiver_type.key_type
    v_type = receiver_type.value_type
    args = CollectionChecker._bind_args(
      node.arguments, ["key", "value"], checker=checker, method_name="insert"
    )
    key_arg = args.get("key")
    val_arg = args.get("value")

    if not key_arg or not val_arg:
      checker.error(".insert() requires mandatory 'key' and 'value' arguments.")
      return v_type

    k_arg_type = checker.visit(key_arg.expr)
    checker.check_value_ownership_transfer(key_arg.expr, k_arg_type, node=node)
    if not k_arg_type.is_compatible(k_type):
      checker.error(
        f"Argument 'key' in .insert() must be '{k_type}', got '{k_arg_type}'."
      )

    v_arg_type = checker.visit(val_arg.expr)
    checker.check_value_ownership_transfer(val_arg.expr, v_arg_type, node=node)
    if not v_arg_type.is_compatible(v_type):
      checker.error(
        f"Argument 'value' in .insert() must be '{v_type}', got '{v_arg_type}'."
      )

    if ArenaChecker.is_reference_type(k_type):
      CollectionChecker._check_container_self_aliasing(
        checker, node.callee.receiver, key_arg.expr, "key", "insert", node
      )
    if ArenaChecker.is_reference_type(v_type):
      CollectionChecker._check_container_self_aliasing(
        checker, node.callee.receiver, val_arg.expr, "value", "insert", node
      )
    ArenaChecker.validate_container_mutation(
      checker,
      node.callee.receiver,
      [key_arg.expr, val_arg.expr],
      error_node=node,
    )
    return v_type

  @staticmethod
  def check_map_method_call(checker: Any, node: CallNode) -> Optional[Type]:
    """Validates a call to a builtin Map method and returns its return Type."""
    method = node.callee.map_method
    receiver_type = node.callee.map_receiver_type
    k_type = receiver_type.key_type
    v_type = receiver_type.value_type

    if method in ("insert", "remove", "clear"):
      CollectionChecker._check_mutating_receiver(
        checker, node.callee.receiver, method, "mutating method"
      )

    if method == "size":
      if node.arguments:
        checker.error(".size() takes no arguments.")
      return PrimitiveType("int")
    if method == "empty":
      if node.arguments:
        checker.error(".empty() takes no arguments.")
      return PrimitiveType("bool")
    if method == "contains":
      if len(node.arguments) != 1:
        checker.error(".contains() requires exactly 1 argument (key).")
        return PrimitiveType("bool")
      key_arg_type = checker.visit(node.arguments[0].expr)
      if not key_arg_type.is_compatible(k_type):
        checker.error(
          f"Argument type mismatch in .contains(). Expected '{k_type}', got "
          f"'{key_arg_type}'."
        )
      return PrimitiveType("bool")
    if method == "keys":
      if node.arguments:
        checker.error(".keys() takes no arguments.")
      return ArrayType(k_type)
    if method == "values":
      if node.arguments:
        checker.error(".values() takes no arguments.")
      return ArrayType(v_type)
    if method == "insert":
      return CollectionChecker._check_map_insert(checker, node, receiver_type)
    if method == "remove":
      if len(node.arguments) != 1:
        checker.error(".remove() requires exactly 1 argument (key).")
        return OptionalType(v_type)
      k_arg_type = checker.visit(node.arguments[0].expr)
      if not k_arg_type.is_compatible(k_type):
        checker.error(
          f"Argument 'key' in .remove() must be '{k_type}', got '{k_arg_type}'."
        )
      return OptionalType(v_type)
    if method == "clear":
      if node.arguments:
        checker.error(".clear() takes no arguments.")
      return PrimitiveType("none")

    return None
