"""Collection and builtin method type-checking helper for Sapphire.

Decouples Array and Map method resolution and call-site argument validation from
the core TypeChecker.
"""

from typing import Any
from src.parser.ast import CallNode, IdentifierNode, LiteralNode, MemberAccessNode
from src.semantics.arena_checker import ArenaChecker
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
  def resolve_array_member(checker: Any, node: MemberAccessNode, receiver_type: ArrayType) -> Type:
    """Resolves member access on an ArrayType receiver."""
    if node.member in ARRAY_METHODS:
      node.is_array_method = True
      node.array_method = node.member
      node.array_receiver_type = receiver_type
      elem_t = receiver_type.element_type
      if node.member == "size":
        return FunctionType([receiver_type], PrimitiveType("int"), param_names=["self"], has_self=True)
      elif node.member == "empty":
        return FunctionType([receiver_type], PrimitiveType("bool"), param_names=["self"], has_self=True)
      elif node.member == "get":
        return FunctionType([receiver_type, PrimitiveType("int")], OptionalType(elem_t), param_names=["self", "index"], has_self=True)
      elif node.member == "map":
        return FunctionType([receiver_type, FunctionType([elem_t], InferredType()), PrimitiveType("bool")], ArrayType(InferredType(), size=receiver_type.size), param_names=["self", "fn", "in_place"], has_self=True, num_defaults=1)
      elif node.member == "filter":
        return FunctionType([receiver_type, FunctionType([elem_t], PrimitiveType("bool")), PrimitiveType("bool")], ArrayType(elem_t), param_names=["self", "fn", "in_place"], has_self=True, num_defaults=1)
      elif node.member == "reduce":
        return FunctionType([receiver_type, InferredType(), FunctionType([InferredType(), elem_t], InferredType()), PrimitiveType("bool")], InferredType(), param_names=["self", "initial", "fn", "reverse"], has_self=True, num_defaults=1)
      elif node.member == "contains":
        return FunctionType([receiver_type, elem_t], PrimitiveType("bool"), param_names=["self", "element"], has_self=True)
      elif node.member == "reverse":
        return FunctionType([receiver_type, PrimitiveType("bool")], ArrayType(elem_t, size=receiver_type.size), param_names=["self", "in_place"], has_self=True, num_defaults=1)
      elif node.member == "sort":
        return FunctionType([receiver_type, OptionalType(FunctionType([elem_t, elem_t], PrimitiveType("int"))), PrimitiveType("bool"), PrimitiveType("bool")], ArrayType(elem_t, size=receiver_type.size), param_names=["self", "by", "reverse", "in_place"], has_self=True, num_defaults=3)
      elif node.member == "join":
        return FunctionType([receiver_type, OptionalType(StringType())], StringType(), param_names=["self", "sep"], has_self=True, num_defaults=1)
      elif node.member == "push":
        return FunctionType([receiver_type, elem_t], elem_t, param_names=["self", "element"], has_self=True)
      elif node.member == "pop":
        return FunctionType([receiver_type], OptionalType(elem_t), param_names=["self"], has_self=True)
      elif node.member == "insert":
        return FunctionType([receiver_type, PrimitiveType("int"), elem_t], elem_t, param_names=["self", "index", "element"], has_self=True)
      elif node.member == "remove":
        return FunctionType([receiver_type, PrimitiveType("int")], OptionalType(elem_t), param_names=["self", "index"], has_self=True)
      elif node.member == "clear":
        return FunctionType([receiver_type], PrimitiveType("none"), param_names=["self"], has_self=True)
    checker.error(f"Array has no method '{node.member}'.")
    return PrimitiveType("none")

  @staticmethod
  def resolve_map_member(checker: Any, node: MemberAccessNode, receiver_type: MapType) -> Type:
    """Resolves member access on a MapType receiver."""
    if node.member in MAP_METHODS:
      node.is_map_method = True
      node.map_method = node.member
      node.map_receiver_type = receiver_type
      k_type = receiver_type.key_type
      v_type = receiver_type.value_type
      if node.member == "size":
        return FunctionType([receiver_type], PrimitiveType("int"), param_names=["self"], has_self=True)
      elif node.member == "empty":
        return FunctionType([receiver_type], PrimitiveType("bool"), param_names=["self"], has_self=True)
      elif node.member == "contains":
        return FunctionType([receiver_type, k_type], PrimitiveType("bool"), param_names=["self", "key"], has_self=True)
      elif node.member == "get":
        return FunctionType([receiver_type, k_type], OptionalType(v_type), param_names=["self", "key"], has_self=True)
      elif node.member == "keys":
        return FunctionType([receiver_type], ArrayType(k_type), param_names=["self"], has_self=True)
      elif node.member == "values":
        return FunctionType([receiver_type], ArrayType(v_type), param_names=["self"], has_self=True)
      elif node.member == "insert":
        return FunctionType([receiver_type, k_type, v_type], v_type, param_names=["self", "key", "value"], has_self=True)
      elif node.member == "remove":
        return FunctionType([receiver_type, k_type], OptionalType(v_type), param_names=["self", "key"], has_self=True)
      elif node.member == "clear":
        return FunctionType([receiver_type], PrimitiveType("none"), param_names=["self"], has_self=True)
    checker.error(f"Map has no method '{node.member}'.")
    return PrimitiveType("none")

  @staticmethod
  def check_array_method_call(checker: Any, node: CallNode) -> Type:
    """Validates a call to a builtin Array method and returns its return Type."""
    method = node.callee.array_method
    receiver_type = node.callee.array_receiver_type
    elem_type = receiver_type.element_type

    if method == "size":
      if node.arguments:
        checker.error(".size() takes no arguments.")
      return PrimitiveType("int")

    elif method == "empty":
      if node.arguments:
        checker.error(".empty() takes no arguments.")
      return PrimitiveType("bool")

    elif method == "map":
      fn_arg = None
      in_place_arg = None
      for idx, arg in enumerate(node.arguments):
        if arg.name == "fn":
          fn_arg = arg
        elif arg.name == "in_place":
          in_place_arg = arg
        elif idx == 0 and not arg.name:
          fn_arg = arg
        elif idx == 1 and not arg.name:
          in_place_arg = arg

      if not fn_arg:
        checker.error(".map() requires at least 1 argument (fn).")
        return ArrayType(elem_type, size=receiver_type.size)

      old_expected = checker.expected_type
      checker.expected_type = FunctionType([elem_type], InferredType())
      fn_type = checker.visit(fn_arg.expr)
      checker.expected_type = old_expected

      ret_elem_type = PrimitiveType("none")
      if isinstance(fn_type, FunctionType):
        ret_elem_type = fn_type.return_type
        if fn_type.param_types and not elem_type.is_compatible(fn_type.param_types[0]):
          checker.error(f"Closure parameter type mismatch in .map(). Expected '{elem_type}', got '{fn_type.param_types[0]}'.")

      is_in_place = False
      if in_place_arg:
        in_p_type = checker.visit(in_place_arg.expr)
        if not in_p_type.is_compatible(PrimitiveType("bool")):
          checker.error(f"'in_place' parameter in .map() must be 'bool', got '{in_p_type}'.")
        if isinstance(in_place_arg.expr, LiteralNode) and in_place_arg.expr.value is True:
          is_in_place = True

      if is_in_place:
        receiver = node.callee.receiver
        if isinstance(receiver, IdentifierNode):
          sym = checker.symbol_table.lookup(receiver.name)
          if isinstance(sym, VariableSymbol) and not sym.is_mutable:
            checker.error(f"Cannot invoke in-place transformation '.map()' on constant variable '{receiver.name}'.")
        if isinstance(fn_type, FunctionType) and not ret_elem_type.is_compatible(elem_type):
          checker.error(f"In-place mapping requires closure return type to match element type '{elem_type}', got '{ret_elem_type}'.")
        return ArrayType(elem_type, size=receiver_type.size)

      if receiver_type.size is not None:
        return ArrayType(ret_elem_type, size=receiver_type.size)
      return ArrayType(ret_elem_type)

    elif method == "filter":
      fn_arg = None
      in_place_arg = None
      for idx, arg in enumerate(node.arguments):
        if arg.name == "fn":
          fn_arg = arg
        elif arg.name == "in_place":
          in_place_arg = arg
        elif idx == 0 and not arg.name:
          fn_arg = arg
        elif idx == 1 and not arg.name:
          in_place_arg = arg

      if not fn_arg:
        checker.error(".filter() requires at least 1 argument (fn).")
        return ArrayType(elem_type)

      old_expected = checker.expected_type
      checker.expected_type = FunctionType([elem_type], PrimitiveType("bool"))
      fn_type = checker.visit(fn_arg.expr)
      checker.expected_type = old_expected

      if isinstance(fn_type, FunctionType):
        if fn_type.param_types and not elem_type.is_compatible(fn_type.param_types[0]):
          checker.error(f"Closure parameter type mismatch in .filter(). Expected '{elem_type}', got '{fn_type.param_types[0]}'.")
        if not fn_type.return_type.is_compatible(PrimitiveType("bool")):
          checker.error(f".filter() predicate closure must return 'bool', got '{fn_type.return_type}'.")

      is_in_place = False
      if in_place_arg:
        in_p_type = checker.visit(in_place_arg.expr)
        if not in_p_type.is_compatible(PrimitiveType("bool")):
          checker.error(f"'in_place' parameter in .filter() must be 'bool', got '{in_p_type}'.")
        if isinstance(in_place_arg.expr, LiteralNode) and in_place_arg.expr.value is True:
          is_in_place = True

      if is_in_place:
        if receiver_type.is_fixed_size:
          checker.error(f"Cannot invoke in-place '.filter()' on fixed-size array '{receiver_type}'.")
        receiver = node.callee.receiver
        if isinstance(receiver, IdentifierNode):
          sym = checker.symbol_table.lookup(receiver.name)
          if isinstance(sym, VariableSymbol) and not sym.is_mutable:
            checker.error(f"Cannot invoke in-place transformation '.filter()' on constant variable '{receiver.name}'.")

      return ArrayType(elem_type)

    elif method == "reduce":
      initial_arg = None
      fn_arg = None
      reverse_arg = None
      for idx, arg in enumerate(node.arguments):
        if arg.name == "initial":
          initial_arg = arg
        elif arg.name == "fn":
          fn_arg = arg
        elif arg.name == "reverse":
          reverse_arg = arg
        elif idx == 0 and not arg.name:
          initial_arg = arg
        elif idx == 1 and not arg.name:
          fn_arg = arg
        elif idx == 2 and not arg.name:
          reverse_arg = arg

      if not initial_arg or not fn_arg:
        checker.error(".reduce() requires mandatory 'initial' and 'fn' arguments.")
        return elem_type

      acc_type = checker.visit(initial_arg.expr)

      old_expected = checker.expected_type
      checker.expected_type = FunctionType([acc_type, elem_type], acc_type)
      fn_type = checker.visit(fn_arg.expr)
      checker.expected_type = old_expected

      if isinstance(fn_type, FunctionType):
        if len(fn_type.param_types) >= 2:
          if not acc_type.is_compatible(fn_type.param_types[0]):
            checker.error(f"Closure accumulator parameter mismatch in .reduce(). Expected '{acc_type}', got '{fn_type.param_types[0]}'.")
          if not elem_type.is_compatible(fn_type.param_types[1]):
            checker.error(f"Closure item parameter mismatch in .reduce(). Expected '{elem_type}', got '{fn_type.param_types[1]}'.")
        if not fn_type.return_type.is_compatible(acc_type):
          checker.error(f"Closure return type in .reduce() must match initial value type '{acc_type}', got '{fn_type.return_type}'.")

      if reverse_arg:
        rev_type = checker.visit(reverse_arg.expr)
        if not rev_type.is_compatible(PrimitiveType("bool")):
          checker.error(f"'reverse' parameter in .reduce() must be 'bool', got '{rev_type}'.")

      return acc_type

    elif method in ("push", "pop", "insert", "remove", "clear"):
      if receiver_type.is_fixed_size:
        checker.error(f"Cannot invoke mutating method '{method}' on fixed-size array '{receiver_type}'.")
      receiver = node.callee.receiver
      if isinstance(receiver, IdentifierNode):
        sym = checker.symbol_table.lookup(receiver.name)
        if isinstance(sym, VariableSymbol) and not sym.is_mutable:
          checker.error(f"Cannot invoke mutating method '{method}' on constant variable '{receiver.name}'.")

      if method == "push":
        if len(node.arguments) != 1:
          checker.error(".push() requires exactly 1 argument (element).")
          return elem_type
        arg_t = checker.visit(node.arguments[0].expr)
        checker._check_value_ownership_transfer(node.arguments[0].expr, arg_t, node=node)
        if not arg_t.is_compatible(elem_type):
          checker.error(f"Argument type mismatch in .push(). Expected '{elem_type}', got '{arg_t}'.")
        ArenaChecker.validate_container_mutation(
            checker, node.callee.receiver, [node.arguments[0].expr], error_node=node
        )
        return elem_type

      elif method == "pop":
        if node.arguments:
          checker.error(".pop() takes no arguments.")
        return OptionalType(elem_type)

      elif method == "insert":
        index_arg = None
        element_arg = None
        for idx, arg in enumerate(node.arguments):
          if arg.name == "index":
            index_arg = arg
          elif arg.name == "element":
            element_arg = arg
          elif idx == 0 and not arg.name:
            index_arg = arg
          elif idx == 1 and not arg.name:
            element_arg = arg

        if not index_arg or not element_arg:
          checker.error(".insert() requires mandatory 'index' and 'element' arguments.")
          return elem_type

        idx_t = checker.visit(index_arg.expr)
        if not idx_t.is_compatible(PrimitiveType("int")):
          checker.error(f"Argument 'index' in .insert() must be 'int', got '{idx_t}'.")
        elem_t = checker.visit(element_arg.expr)
        checker._check_value_ownership_transfer(element_arg.expr, elem_t, node=node)
        if not elem_t.is_compatible(elem_type):
          checker.error(f"Argument type mismatch in .insert(). Expected '{elem_type}', got '{elem_t}'.")
        ArenaChecker.validate_container_mutation(
            checker, node.callee.receiver, [element_arg.expr], error_node=node
        )
        return elem_type

      elif method == "remove":
        if len(node.arguments) != 1:
          checker.error(".remove() requires exactly 1 argument (index).")
          return OptionalType(elem_type)
        idx_t = checker.visit(node.arguments[0].expr)
        if not idx_t.is_compatible(PrimitiveType("int")):
          checker.error(f"Argument 'index' in .remove() must be 'int', got '{idx_t}'.")
        return OptionalType(elem_type)

      elif method == "clear":
        if node.arguments:
          checker.error(".clear() takes no arguments.")
        return PrimitiveType("none")

    elif method == "contains":
      if len(node.arguments) != 1:
        checker.error(".contains() requires exactly 1 argument (element).")
        return PrimitiveType("bool")
      arg_t = checker.visit(node.arguments[0].expr)
      if not arg_t.is_compatible(elem_type):
        checker.error(f"Argument type mismatch in .contains(). Expected '{elem_type}', got '{arg_t}'.")
      return PrimitiveType("bool")

    elif method == "reverse":
      in_place_arg = None
      for idx, arg in enumerate(node.arguments):
        if arg.name == "in_place":
          in_place_arg = arg
        elif idx == 0 and not arg.name:
          in_place_arg = arg

      if len(node.arguments) > 1:
        checker.error(".reverse() takes at most 1 argument (in_place).")

      is_in_place = False
      if in_place_arg:
        in_p_type = checker.visit(in_place_arg.expr)
        if not in_p_type.is_compatible(PrimitiveType("bool")):
          checker.error(f"'in_place' parameter in .reverse() must be 'bool', got '{in_p_type}'.")
        if isinstance(in_place_arg.expr, LiteralNode) and in_place_arg.expr.value is True:
          is_in_place = True

      if is_in_place:
        receiver = node.callee.receiver
        if isinstance(receiver, IdentifierNode):
          sym = checker.symbol_table.lookup(receiver.name)
          if isinstance(sym, VariableSymbol) and not sym.is_mutable:
            checker.error(f"Cannot invoke in-place transformation '.reverse()' on constant variable '{receiver.name}'.")

      return ArrayType(elem_type, size=receiver_type.size)

    elif method == "sort":
      by_arg = None
      reverse_arg = None
      in_place_arg = None
      for idx, arg in enumerate(node.arguments):
        if arg.name == "by":
          by_arg = arg
        elif arg.name == "reverse":
          reverse_arg = arg
        elif arg.name == "in_place":
          in_place_arg = arg
        elif idx == 0 and not arg.name:
          by_arg = arg
        elif idx == 1 and not arg.name:
          reverse_arg = arg
        elif idx == 2 and not arg.name:
          in_place_arg = arg

      if by_arg:
        old_expected = checker.expected_type
        checker.expected_type = FunctionType([elem_type, elem_type], PrimitiveType("int"))
        by_type = checker.visit(by_arg.expr)
        checker.expected_type = old_expected
        if isinstance(by_type, FunctionType):
          if not by_type.return_type.is_compatible(PrimitiveType("int")):
            checker.error(f"Comparator closure in .sort() must return 'int', got '{by_type.return_type}'.")
      if reverse_arg:
        rev_t = checker.visit(reverse_arg.expr)
        if not rev_t.is_compatible(PrimitiveType("bool")):
          checker.error(f"'reverse' parameter in .sort() must be 'bool', got '{rev_t}'.")

      is_in_place = False
      if in_place_arg:
        in_p_type = checker.visit(in_place_arg.expr)
        if not in_p_type.is_compatible(PrimitiveType("bool")):
          checker.error(f"'in_place' parameter in .sort() must be 'bool', got '{in_p_type}'.")
        if isinstance(in_place_arg.expr, LiteralNode) and in_place_arg.expr.value is True:
          is_in_place = True

      if is_in_place:
        receiver = node.callee.receiver
        if isinstance(receiver, IdentifierNode):
          sym = checker.symbol_table.lookup(receiver.name)
          if isinstance(sym, VariableSymbol) and not sym.is_mutable:
            checker.error(f"Cannot invoke in-place transformation '.sort()' on constant variable '{receiver.name}'.")

      return ArrayType(elem_type, size=receiver_type.size)

    elif method == "join":
      if len(node.arguments) > 1:
        checker.error(".join() takes at most 1 argument (sep).")
      elif len(node.arguments) == 1:
        sep_t = checker.visit(node.arguments[0].expr)
        if not sep_t.is_compatible(StringType()):
          checker.error(f"Delimiter 'sep' in .join() must be 'String', got '{sep_t}'.")
      return StringType()

    return None

  @staticmethod
  def check_map_method_call(checker: Any, node: CallNode) -> Type:
    """Validates a call to a builtin Map method and returns its return Type."""
    method = node.callee.map_method
    receiver_type = node.callee.map_receiver_type
    k_type = receiver_type.key_type
    v_type = receiver_type.value_type

    if method in ("insert", "remove", "clear"):
      receiver = node.callee.receiver
      if isinstance(receiver, IdentifierNode):
        sym = checker.symbol_table.lookup(receiver.name)
        if isinstance(sym, VariableSymbol) and not sym.is_mutable:
          checker.error(f"Cannot invoke mutating method '{method}' on constant variable '{receiver.name}'.")

    if method == "size":
      if node.arguments:
        checker.error(".size() takes no arguments.")
      return PrimitiveType("int")

    elif method == "empty":
      if node.arguments:
        checker.error(".empty() takes no arguments.")
      return PrimitiveType("bool")

    elif method == "contains":
      if len(node.arguments) != 1:
        checker.error(".contains() requires exactly 1 argument (key).")
        return PrimitiveType("bool")
      key_arg_type = checker.visit(node.arguments[0].expr)
      if not key_arg_type.is_compatible(k_type):
        checker.error(f"Argument type mismatch in .contains(). Expected '{k_type}', got '{key_arg_type}'.")
      return PrimitiveType("bool")

    elif method == "keys":
      if node.arguments:
        checker.error(".keys() takes no arguments.")
      return ArrayType(k_type)

    elif method == "values":
      if node.arguments:
        checker.error(".values() takes no arguments.")
      return ArrayType(v_type)

    elif method == "insert":
      key_arg = None
      val_arg = None
      for idx, arg in enumerate(node.arguments):
        if arg.name == "key":
          key_arg = arg
        elif arg.name == "value":
          val_arg = arg
        elif idx == 0 and not arg.name:
          key_arg = arg
        elif idx == 1 and not arg.name:
          val_arg = arg

      if not key_arg or not val_arg:
        checker.error(".insert() requires mandatory 'key' and 'value' arguments.")
        return v_type

      k_arg_type = checker.visit(key_arg.expr)
      checker._check_value_ownership_transfer(key_arg.expr, k_arg_type, node=node)
      if not k_arg_type.is_compatible(k_type):
        checker.error(f"Argument 'key' in .insert() must be '{k_type}', got '{k_arg_type}'.")

      v_arg_type = checker.visit(val_arg.expr)
      checker._check_value_ownership_transfer(val_arg.expr, v_arg_type, node=node)
      if not v_arg_type.is_compatible(v_type):
        checker.error(f"Argument 'value' in .insert() must be '{v_type}', got '{v_arg_type}'.")
      ArenaChecker.validate_container_mutation(
          checker, node.callee.receiver, [key_arg.expr, val_arg.expr], error_node=node
      )

      return v_type

    elif method == "remove":
      if len(node.arguments) != 1:
        checker.error(".remove() requires exactly 1 argument (key).")
        return OptionalType(v_type)
      k_arg_type = checker.visit(node.arguments[0].expr)
      if not k_arg_type.is_compatible(k_type):
        checker.error(f"Argument 'key' in .remove() must be '{k_type}', got '{k_arg_type}'.")
      return OptionalType(v_type)

    elif method == "clear":
      if node.arguments:
        checker.error(".clear() takes no arguments.")
      return PrimitiveType("none")

    return None
