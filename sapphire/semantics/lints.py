"""Semantic lint checks for Sapphire."""

from typing import Any

from sapphire.parser.ast import (
  AssignmentNode,
  ASTNode,
  BinaryOpNode,
  CallNode,
  FuncDeclNode,
  GuardStmtNode,
  IdentifierNode,
  IfNode,
  IndexExprNode,
  LambdaNode,
  LiteralNode,
  MemberAccessNode,
  UnaryOpNode,
)
from sapphire.semantics.arena_checker import ArenaChecker
from sapphire.semantics.symbol_table import (
  MapType,
  OptionalType,
  RefType,
  StructType,
  TraitType,
  VariableSymbol,
)

_STRUCTURAL_MAP_MUTATIONS = frozenset({"remove", "clear", "insert", "set"})
_BUILTIN_MUTATING_METHODS = frozenset(
  {"push", "pop", "insert", "remove", "clear", "set", "sort"}
)


def _exprs_equal(a: ASTNode | None, b: ASTNode | None) -> bool:
  """Returns True when two AST expressions are structurally identical."""
  if a is None or b is None or type(a) is not type(b):
    return False
  if isinstance(a, IdentifierNode):
    return a.name == b.name
  if isinstance(a, MemberAccessNode):
    return (
      a.member == b.member
      and a.is_optional == b.is_optional
      and _exprs_equal(a.receiver, b.receiver)
    )
  if isinstance(a, LiteralNode):
    return a.value == b.value and a.lit_type == b.lit_type
  if isinstance(a, IndexExprNode):
    return _exprs_equal(a.array, b.array) and _exprs_equal(a.index, b.index)
  if isinstance(a, UnaryOpNode):
    return a.op == b.op and _exprs_equal(a.expr, b.expr)
  if isinstance(a, BinaryOpNode):
    return (
      a.op == b.op
      and _exprs_equal(a.left, b.left)
      and _exprs_equal(a.right, b.right)
    )
  return False


def _extract_map_contains(
  expr: ASTNode | None, node_types: dict[ASTNode, Any]
) -> tuple[CallNode, ASTNode, ASTNode] | None:
  """Extracts `(call, receiver, key_expr)` if `expr` is `map.contains(k)`."""
  if not (
    isinstance(expr, CallNode)
    and isinstance(expr.callee, MemberAccessNode)
    and expr.callee.member == "contains"
    and not expr.callee.is_optional
    and len(expr.arguments) == 1
  ):
    return None
  recv = expr.callee.receiver
  if not isinstance(node_types.get(recv), MapType):
    return None
  arg = expr.arguments[0]
  key_expr = arg.expr if hasattr(arg, "expr") else arg
  return (expr, recv, key_expr)


def _collect_contains_in_and_chain(
  cond: ASTNode | None, node_types: dict[ASTNode, Any]
) -> list[tuple[CallNode, ASTNode, ASTNode, list[ASTNode]]]:
  """Finds `map.contains(k)` checks in `cond` and the RHS subtrees guarded by
  them.
  """
  results: list[tuple[CallNode, ASTNode, ASTNode, list[ASTNode]]] = []
  if cond is None:
    return results

  # Flatten left- or right-associated `&&` chains in evaluation order.
  terms: list[ASTNode] = []

  def _flatten_and(node: ASTNode) -> None:
    if isinstance(node, BinaryOpNode) and node.op == "&&":
      _flatten_and(node.left)
      _flatten_and(node.right)
    else:
      terms.append(node)

  _flatten_and(cond)
  for idx, term in enumerate(terms):
    extracted = _extract_map_contains(term, node_types)
    if extracted:
      call_node, recv, key_expr = extracted
      results.append((call_node, recv, key_expr, terms[idx + 1 :]))
  return results


def _is_matching_map_get(node: ASTNode, recv: ASTNode, key: ASTNode) -> bool:
  if not (
    isinstance(node, CallNode)
    and isinstance(node.callee, MemberAccessNode)
    and node.callee.member == "get"
    and not node.callee.is_optional
    and len(node.arguments) == 1
  ):
    return False
  arg = node.arguments[0]
  arg_expr = arg.expr if hasattr(arg, "expr") else arg
  return _exprs_equal(node.callee.receiver, recv) and _exprs_equal(
    arg_expr, key
  )


def _is_rooted_at_matching_index(
  node: ASTNode | None, recv: ASTNode, key: ASTNode
) -> bool:
  """Returns True if `node` is `recv[key]` or a member/index chain rooted at it.
  """
  cur = node
  while cur is not None:
    if isinstance(cur, IndexExprNode):
      if _exprs_equal(cur.array, recv) and _exprs_equal(cur.index, key):
        return True
      cur = cur.array
    elif isinstance(cur, MemberAccessNode):
      cur = cur.receiver
    else:
      return False
  return False


def _scan_subtrees_for_map_access(
  checker: Any, roots: list[ASTNode], recv: ASTNode, key: ASTNode
) -> tuple[bool, bool, bool, bool]:
  """Scans AST subtrees for matching map accesses and conflicting mutations.

  Returns `(has_access, has_in_place_mutation, has_direct_overwrite,
  has_recv_mutation)`.
  """
  state = {
    "has_access": False,
    "has_in_place_mutation": False,
    "has_direct_overwrite": False,
    "has_recv_mutation": False,
  }

  def _walk(node: Any, in_assign_target: bool = False) -> None:
    if node is None:
      return
    if isinstance(node, list):
      for item in node:
        _walk(item, in_assign_target=in_assign_target)
      return
    if not isinstance(node, ASTNode):
      return
    if isinstance(node, (FuncDeclNode, LambdaNode)):
      return

    if isinstance(node, AssignmentNode):
      for tgt in node.targets:
        if isinstance(tgt, IndexExprNode) and _exprs_equal(tgt.array, recv):
          if _exprs_equal(tgt.index, key):
            if node.op == "=":
              state["has_direct_overwrite"] = True
            else:
              state["has_access"] = True
              state["has_in_place_mutation"] = True
          else:
            state["has_recv_mutation"] = True
        elif _is_rooted_at_matching_index(tgt, recv, key):
          state["has_access"] = True
          state["has_in_place_mutation"] = True
        _walk(tgt, in_assign_target=True)
      for expr in node.exprs:
        _walk(expr, in_assign_target=False)
      return

    if isinstance(node, IndexExprNode):
      if _exprs_equal(node.array, recv) and _exprs_equal(node.index, key):
        if not in_assign_target:
          state["has_access"] = True
        return
    elif _is_matching_map_get(node, recv, key):
      state["has_access"] = True
      return
    elif isinstance(node, CallNode) and isinstance(
      node.callee, MemberAccessNode
    ):
      callee_recv = node.callee.receiver
      if (
        _exprs_equal(callee_recv, recv)
        and node.callee.member in _STRUCTURAL_MAP_MUTATIONS
      ):
        state["has_recv_mutation"] = True
      elif _is_rooted_at_matching_index(callee_recv, recv, key):
        state["has_access"] = True
        recv_t = checker.node_types.get(callee_recv)
        if isinstance(recv_t, OptionalType):
          recv_t = recv_t.base_type
        if isinstance(recv_t, RefType):
          recv_t = recv_t.inner_type
        is_mut_method = node.callee.member in _BUILTIN_MUTATING_METHODS
        if not is_mut_method and isinstance(recv_t, StructType):
          m = recv_t.get_method(node.callee.member, checker.symbol_table)
          if m is not None and m.modifier == "var":
            is_mut_method = True
        elif not is_mut_method and isinstance(recv_t, TraitType):
          tm = recv_t.methods.get(node.callee.member)
          if tm is not None and getattr(tm.ast_decl, "modifier", None) == "var":
            is_mut_method = True
        if is_mut_method:
          state["has_in_place_mutation"] = True

    for attr_name, value in node.__dict__.items():
      if attr_name.startswith("_"):
        continue
      if isinstance(value, (ASTNode, list)):
        _walk(value, in_assign_target=in_assign_target)

  _walk(roots)
  return (
    state["has_access"],
    state["has_in_place_mutation"],
    state["has_direct_overwrite"],
    state["has_recv_mutation"],
  )


def _is_mutable_lvalue(checker: Any, recv: ASTNode) -> bool:
  res = ArenaChecker.get_lvalue_path(checker.symbol_table, recv)
  if not res:
    return False
  sym = checker.symbol_table.lookup(res[0])
  if isinstance(sym, VariableSymbol):
    return sym.is_mutable
  return False


def _maybe_warn_contains_access(
  checker: Any,
  call_node: CallNode,
  recv: ASTNode,
  key_expr: ASTNode,
  subtrees: list[ASTNode],
  kind: str,
) -> None:
  has_access, has_in_place_mutation, has_direct_overwrite, has_recv_mutation = (
    _scan_subtrees_for_map_access(checker, subtrees, recv, key_expr)
  )
  if not has_access or has_direct_overwrite or has_recv_mutation:
    return
  if has_in_place_mutation and not _is_mutable_lvalue(checker, recv):
    return

  kw = f"{kind} var" if has_in_place_mutation else f"{kind} let"
  else_hint = " else { ... }" if kind == "guard" else ""
  checker.warning(
    "Double lookup on map via '.contains(...)' followed by "
    "indexing/'.get(...)'. "
    f"Prefer '{kw} v ?= <map>.get(<key>){else_hint}' for a single lookup.",
    node=call_node,
  )


def check_if_contains_access(checker: Any, node: IfNode) -> None:
  """Warns on `if map.contains(k)` followed by `map[k]` / `map.get(k)`."""
  if not node.condition or not node.then_block:
    return
  for call_node, recv, key_expr, rhs_exprs in _collect_contains_in_and_chain(
    node.condition, checker.node_types
  ):
    subtrees: list[ASTNode] = list(rhs_exprs)
    subtrees.append(node.then_block)
    _maybe_warn_contains_access(
      checker, call_node, recv, key_expr, subtrees, "if"
    )


def check_guard_contains_access(
  checker: Any, guard_node: GuardStmtNode, remaining_stmts: list[ASTNode]
) -> None:
  """Warns on `guard map.contains(k)` followed by `map[k]` / `map.get(k)`."""
  if not remaining_stmts:
    return
  clauses = getattr(guard_node, "clauses", None) or []
  conds = [
    c.condition for c in clauses if getattr(c, "condition", None) is not None
  ]
  if not conds and getattr(guard_node, "condition", None) is not None:
    conds = [guard_node.condition]
  for cond in conds:
    for call_node, recv, key_expr, rhs_exprs in _collect_contains_in_and_chain(
      cond, checker.node_types
    ):
      subtrees: list[ASTNode] = list(rhs_exprs) + list(remaining_stmts)
      _maybe_warn_contains_access(
        checker, call_node, recv, key_expr, subtrees, "guard"
      )
