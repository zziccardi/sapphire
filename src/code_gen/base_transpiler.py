"""Abstract base class for all Sapphire transpiler backends.

Defines the visitor interface contract that every code-generation backend must
satisfy. Concrete subclasses that omit any `@abstractmethod` raise `TypeError`
at class definition time via `BaseTranspiler.__init_subclass__`, making backend
divergence impossible to miss.
"""

from abc import ABC, abstractmethod
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, Dict, List, Optional, Set

from src.code_gen.emitter_state import EmitterState, OutputBuffer
from src.parser.ast import (
  ArrayLiteralNode,
  AssignmentNode,
  ASTNode,
  BasicTypeNode,
  BinaryOpNode,
  BlockNode,
  BreakNode,
  CallNode,
  CastExprNode,
  CloneNode,
  ContinueNode,
  EllipsisPatternNode,
  EnumDeclNode,
  ExportStmtNode,
  ExprStmtNode,
  ForNode,
  FuncDeclNode,
  GuardClauseNode,
  GuardStmtNode,
  IdentifierNode,
  IfNode,
  ImplBlockNode,
  ImplMemberNode,
  ImportStmtNode,
  IndexExprNode,
  InterpolatedStringNode,
  LambdaNode,
  LiteralNode,
  MapLiteralNode,
  MatchExprNode,
  MemberAccessNode,
  MoveNode,
  OptionalTypeNode,
  ProgramNode,
  ReturnNode,
  StructDeclNode,
  StructFieldNode,
  StructInitializerNode,
  TernaryExprNode,
  TraitDeclNode,
  TypeNode,
  UnaryOpNode,
  VarDeclNode,
  WhileNode,
  YieldNode,
)


def get_default_value_for_type_node(
  type_node: Optional[TypeNode],
) -> Optional[ASTNode]:
  """Returns a reasonable default literal ASTNode for uninitialized variables
  and
  struct fields.
  """
  if type_node is None:
    return None
  if isinstance(type_node, OptionalTypeNode):
    return LiteralNode(value="none", lit_type="none")
  if isinstance(type_node, BasicTypeNode):
    if type_node.name == "int":
      return LiteralNode(value=0, lit_type="int")
    elif type_node.name == "float":
      return LiteralNode(value=0.0, lit_type="float")
    elif type_node.name == "bool":
      return LiteralNode(value=False, lit_type="bool")
  return None


def is_coroutine_func(node: Optional[ASTNode]) -> bool:
  """Returns True if a FuncDeclNode, ImplMemberNode, or FunctionType returns
  Coroutine.
  """
  if node is None:
    return False
  func_node = getattr(node, "func_decl", node)
  if getattr(func_node, "return_types", None):
    for t in func_node.return_types:
      if isinstance(t, BasicTypeNode) and t.name == "Coroutine":
        return True
  if getattr(func_node, "return_type", None):
    if (
      isinstance(func_node.return_type, BasicTypeNode)
      and func_node.return_type.name == "Coroutine"
    ):
      return True
  return False


def extract_type_name(t_node: Optional[ASTNode]) -> Optional[str]:
  """Extracts the base type name from a TypeNode."""
  if t_node is None:
    return None
  if hasattr(t_node, "base_type"):
    return extract_type_name(t_node.base_type)
  if hasattr(t_node, "name"):
    return t_node.name
  return None


def get_return_type_names(func_node: ASTNode) -> List[str]:
  """Extracts all return type names from a FuncDeclNode."""
  res: List[str] = []
  if hasattr(func_node, "return_types") and func_node.return_types:
    for t in func_node.return_types:
      name = extract_type_name(t)
      if name:
        res.append(name)
  elif hasattr(func_node, "return_type") and func_node.return_type:
    name = extract_type_name(func_node.return_type)
    if name:
      res.append(name)
  return res


class BaseTranspiler(ABC):
  """Abstract base for all Sapphire code-generation backends.

  Every concrete backend (e.g. `PythonTranspiler`, `LuaTranspiler`) must
  implement all visitor methods declared here. While Python's `ABCMeta` only
  raises `TypeError` at instantiation time, `__init_subclass__` enforces
  `@abstractmethod` completeness at *class definition time* for concrete
  subclasses (pass `allow_abstract=True` or inherit directly from `ABC` for
  intermediate abstract bases), catching backend divergence at import time.
  """

  def __init_subclass__(
    cls, *, allow_abstract: bool = False, **kwargs: Any
  ) -> None:
    """Enforces @abstractmethod completeness at class definition time."""
    super().__init_subclass__(**kwargs)
    if allow_abstract or ABC in cls.__bases__:
      return
    abstracts: Set[str] = set()
    for base in cls.__mro__[1:]:
      for name in getattr(base, "__abstractmethods__", ()):
        value = getattr(cls, name, None)
        if getattr(value, "__isabstractmethod__", False):
          abstracts.add(name)
    for name, value in cls.__dict__.items():
      if getattr(value, "__isabstractmethod__", False):
        abstracts.add(name)
    if abstracts:
      missing = ", ".join(sorted(abstracts))
      raise TypeError(
        f"Can't define concrete transpiler class {cls.__name__} "
        f"without implementing abstract methods: {missing}"
      )

  def __init__(
    self,
    *,
    test_mode: bool = False,
    use_runtime_module: bool = False,
  ) -> None:
    """Initializes shared transpiler state and the root output buffer."""
    self.state = EmitterState(
      test_mode=test_mode,
      use_runtime_module=use_runtime_module,
    )
    self._buffers: list[OutputBuffer] = [OutputBuffer()]

  # ------------------------------------------------------------------
  # Scoped output buffer management
  # ------------------------------------------------------------------

  @property
  def is_root_buffer(self) -> bool:
    """Returns True when emitting into the primary (non-captured) buffer."""
    return len(self._buffers) == 1

  def push_buffer(self) -> OutputBuffer:
    """Pushes a fresh isolated OutputBuffer onto the buffer stack."""
    buf = OutputBuffer()
    self._buffers.append(buf)
    return buf

  def pop_buffer(self) -> str:
    """Pops the top OutputBuffer and returns its accumulated text."""
    if len(self._buffers) <= 1:
      raise RuntimeError("Cannot pop the root output buffer.")
    return self._buffers.pop().get_output()

  @contextmanager
  def scoped_buffer(self) -> Iterator[OutputBuffer]:
    """Context manager that isolates emitted output into a temporary buffer."""
    buf = self.push_buffer()
    try:
      yield buf
    finally:
      self._buffers.pop()

  def capture_expr(self, node: ASTNode) -> str:
    """Visits *node* in a fresh scoped buffer and returns its emitted text."""
    with self.scoped_buffer() as buf:
      self.visit(node)
      return buf.get_output()

  @property
  def code(self) -> list[str]:
    """Active output buffer chunk list."""
    return self._buffers[-1].chunks

  @code.setter
  def code(self, value: list[str]) -> None:
    self._buffers[-1].chunks = value

  @property
  def indent_level(self) -> int:
    """Indentation level of the active output buffer."""
    return self._buffers[-1].indent_level

  @indent_level.setter
  def indent_level(self, value: int) -> None:
    self._buffers[-1].indent_level = value

  # ------------------------------------------------------------------
  # Shared EmitterState property delegates
  # ------------------------------------------------------------------

  @property
  def test_mode(self) -> bool:
    return self.state.test_mode

  @test_mode.setter
  def test_mode(self, value: bool) -> None:
    self.state.test_mode = value

  @property
  def use_runtime_module(self) -> bool:
    return self.state.use_runtime_module

  @use_runtime_module.setter
  def use_runtime_module(self, value: bool) -> None:
    self.state.use_runtime_module = value

  @property
  def struct_methods(self) -> dict[str, list[Any]]:
    return self.state.struct_methods

  @struct_methods.setter
  def struct_methods(self, value: dict[str, list[Any]]) -> None:
    self.state.struct_methods = value

  @property
  def structs_with_destructor(self) -> set[str]:
    return self.state.structs_with_destructor

  @structs_with_destructor.setter
  def structs_with_destructor(self, value: set[str]) -> None:
    self.state.structs_with_destructor = value

  @property
  def proto_structs(self) -> set[str]:
    return self.state.proto_structs

  @proto_structs.setter
  def proto_structs(self, value: set[str]) -> None:
    self.state.proto_structs = value

  @property
  def struct_destructible_fields(self) -> dict[str, list[str]]:
    return self.state.struct_destructible_fields

  @struct_destructible_fields.setter
  def struct_destructible_fields(self, value: dict[str, list[str]]) -> None:
    self.state.struct_destructible_fields = value

  @property
  def struct_parent_names(self) -> dict[str, list[str]]:
    return self.state.struct_parent_names

  @struct_parent_names.setter
  def struct_parent_names(self, value: dict[str, list[str]]) -> None:
    self.state.struct_parent_names = value

  @property
  def destructor_stack(self) -> list[list[str]]:
    return self.state.destructor_stack

  @destructor_stack.setter
  def destructor_stack(self, value: list[list[str]]) -> None:
    self.state.destructor_stack = value

  @property
  def loop_destructor_depth(self) -> list[int]:
    return self.state.loop_destructor_depth

  @loop_destructor_depth.setter
  def loop_destructor_depth(self, value: list[int]) -> None:
    self.state.loop_destructor_depth = value

  @property
  def moved_vars(self) -> set[str]:
    return self.state.moved_vars

  @moved_vars.setter
  def moved_vars(self, value: set[str]) -> None:
    self.state.moved_vars = value

  @property
  def _branch_depth(self) -> int:
    return self.state.branch_depth

  @_branch_depth.setter
  def _branch_depth(self, value: int) -> None:
    self.state.branch_depth = value

  @property
  def _var_branch_depth(self) -> dict[str, int]:
    return self.state.var_branch_depth

  @_var_branch_depth.setter
  def _var_branch_depth(self, value: dict[str, int]) -> None:
    self.state.var_branch_depth = value

  @property
  def _pending_null_vars(self) -> list[str]:
    return self.state.pending_null_vars

  @_pending_null_vars.setter
  def _pending_null_vars(self, value: list[str]) -> None:
    self.state.pending_null_vars = value

  @property
  def _pending_unconditional_null_vars(self) -> list[str]:
    return self.state.pending_unconditional_null_vars

  @_pending_unconditional_null_vars.setter
  def _pending_unconditional_null_vars(self, value: list[str]) -> None:
    self.state.pending_unconditional_null_vars = value

  @property
  def _pending_destroy_moved_vars(self) -> list[str]:
    return self.state.pending_destroy_moved_vars

  @_pending_destroy_moved_vars.setter
  def _pending_destroy_moved_vars(self, value: list[str]) -> None:
    self.state.pending_destroy_moved_vars = value

  @property
  def func_return_types(self) -> dict[str, Any]:
    return self.state.func_return_types

  @func_return_types.setter
  def func_return_types(self, value: dict[str, Any]) -> None:
    self.state.func_return_types = value

  @property
  def method_return_types(self) -> dict[Any, Any]:
    return self.state.method_return_types

  @method_return_types.setter
  def method_return_types(self, value: dict[Any, Any]) -> None:
    self.state.method_return_types = value

  @property
  def variable_types(self) -> dict[str, str]:
    return self.state.variable_types

  @variable_types.setter
  def variable_types(self, value: dict[str, str]) -> None:
    self.state.variable_types = value

  @property
  def _identifier_map(self) -> dict[str, str]:
    return self.state.identifier_map

  @_identifier_map.setter
  def _identifier_map(self, value: dict[str, str]) -> None:
    self.state.identifier_map = value

  @property
  def _lifted_matches(self) -> dict[int, str]:
    return self.state.lifted_matches

  @_lifted_matches.setter
  def _lifted_matches(self, value: dict[int, str]) -> None:
    self.state.lifted_matches = value

  @property
  def _lifted_short_circuits(self) -> dict[int, str]:
    return self.state.lifted_short_circuits

  @_lifted_short_circuits.setter
  def _lifted_short_circuits(self, value: dict[int, str]) -> None:
    self.state.lifted_short_circuits = value

  @property
  def _temp_name_counters(self) -> dict[str, int]:
    return self.state.temp_name_counters

  @_temp_name_counters.setter
  def _temp_name_counters(self, value: dict[str, int]) -> None:
    self.state.temp_name_counters = value

  @property
  def _current_match_target(self) -> str | None:
    return self.state.current_match_target

  @_current_match_target.setter
  def _current_match_target(self, value: str | None) -> None:
    self.state.current_match_target = value

  @property
  def _current_match_node(self) -> Any:
    return self.state.current_match_node

  @_current_match_node.setter
  def _current_match_node(self, value: Any) -> None:
    self.state.current_match_node = value

  @property
  def _current_match_done_flag(self) -> str | None:
    return self.state.current_match_done_flag

  @_current_match_done_flag.setter
  def _current_match_done_flag(self, value: str | None) -> None:
    self.state.current_match_done_flag = value

  @property
  def _match_loop_depth(self) -> int:
    return self.state.match_loop_depth

  @_match_loop_depth.setter
  def _match_loop_depth(self, value: int) -> None:
    self.state.match_loop_depth = value

  @property
  def _unwrap_writebacks(self) -> dict[str, Any]:
    return self.state.unwrap_writebacks

  @_unwrap_writebacks.setter
  def _unwrap_writebacks(self, value: dict[str, Any]) -> None:
    self.state.unwrap_writebacks = value

  # ------------------------------------------------------------------
  # Core interface & shared helpers
  # ------------------------------------------------------------------

  @abstractmethod
  def transpile(self, program: ProgramNode) -> str:
    """Transpile a fully-typed `ProgramNode` into target source code."""

  def visit(self, node: ASTNode) -> Any:
    """Dispatch *node* to the appropriate `visit_*` method."""
    method_name = f"visit_{node.__class__.__name__}"
    visitor = getattr(self, method_name, self.generic_visit)
    return visitor(node)

  @abstractmethod
  def generic_visit(self, node: ASTNode) -> None:
    """Called when no specific visitor exists; should raise
    `NotImplementedError`.
    """

  def emit(self, text: str) -> None:
    """Append *text* to the active output buffer."""
    self._buffers[-1].emit(text)

  @abstractmethod
  def newline(self) -> None:
    """Emit a newline followed by the current indentation."""

  def indent(self) -> None:
    """Increase the indentation level of the active buffer by one."""
    self._buffers[-1].indent()

  def dedent(self) -> None:
    """Decrease the indentation level of the active buffer by one."""
    self._buffers[-1].dedent()

  def get_output(self) -> str:
    """Return the accumulated output of the active buffer as a single string."""
    return self._buffers[-1].get_output()

  def _next_temp_name(self, prefix: str = "_sp_tmp") -> str:
    """Generates a unique temporary identifier name for this transpiler
    instance.
    """
    counts = self.state.temp_name_counters
    n = counts.get(prefix, 0) + 1
    counts[prefix] = n
    return f"{prefix}_{n}"

  def _type_needs_destructor(
    self, type_obj: Any, _seen: Optional[Set[str]] = None
  ) -> Optional[str]:
    """Returns the destructible type name if *type_obj* requires deterministic
    teardown.
    """
    if type_obj is None:
      return None
    from src.semantics.types import (
      ArenaType,
      OptionalType,
      RefType,
      SharedRefType,
      StructType,
    )

    if isinstance(type_obj, OptionalType):
      return self._type_needs_destructor(type_obj.base_type, _seen)
    if isinstance(type_obj, ArenaType):
      return "Arena"
    if isinstance(type_obj, RefType):
      return "Ref"
    if isinstance(type_obj, SharedRefType):
      return "SharedRef"
    if isinstance(type_obj, StructType):
      if type_obj.is_prototype:
        return None
      if type_obj.name in self.structs_with_destructor:
        return type_obj.name
      if type_obj.has_any_destructor():
        return type_obj.name
      seen = set() if _seen is None else set(_seen)
      if type_obj.name in seen:
        return None
      seen.add(type_obj.name)
      for field in type_obj.fields.values():
        if self._type_needs_destructor(field.field_type, seen):
          return type_obj.name
    return None

  def _expr_destructible_struct(
    self, expr: Any, return_index: int = 0
  ) -> Optional[str]:
    """Determines if *expr* evaluates to a destructible type (RAII struct,
    Arena,
    Ref, SharedRef).
    """
    if expr is None:
      return None
    inferred = getattr(expr, "inferred_type", None)
    if inferred is not None:
      from src.semantics.types import MultiReturnType

      if isinstance(inferred, MultiReturnType):
        if return_index < len(inferred.types):
          inferred = inferred.types[return_index]
        else:
          return None
      return self._type_needs_destructor(inferred)

    if isinstance(expr, StructInitializerNode):
      if expr.struct_name in self.structs_with_destructor:
        return expr.struct_name
    elif isinstance(expr, CallNode):
      if isinstance(expr.callee, IdentifierNode):
        if expr.callee.name in self.structs_with_destructor:
          return expr.callee.name
        if expr.callee.name in self.func_return_types:
          rets = self.func_return_types[expr.callee.name]
          if (
            return_index < len(rets)
            and rets[return_index] in self.structs_with_destructor
          ):
            return rets[return_index]
      elif isinstance(expr.callee, MemberAccessNode):
        if getattr(expr.callee, "is_shared_ref_share", False) or getattr(
          expr.callee, "is_weak_ref_upgrade", False
        ):
          return "SharedRef"
        m_name = expr.callee.member
        recv_struct = None
        if isinstance(expr.callee.receiver, IdentifierNode):
          rm = (
            self._mangle_name(expr.callee.receiver.name)
            if hasattr(self, "_mangle_name")
            else expr.callee.receiver.name
          )
          recv_struct = self.variable_types.get(rm) or self.variable_types.get(
            expr.callee.receiver.name
          )
        rets = (
          self.method_return_types.get((recv_struct, m_name))
          if recv_struct
          else None
        )
        if (
          rets
          and return_index < len(rets)
          and rets[return_index] in self.structs_with_destructor
        ):
          return rets[return_index]
    elif isinstance(expr, (IdentifierNode, MoveNode)):
      m_name = (
        self._mangle_name(expr.name)
        if hasattr(self, "_mangle_name")
        else expr.name
      )
      if m_name in self.variable_types:
        st = self.variable_types[m_name]
        if st in self.structs_with_destructor:
          return st
      if expr.name in self.variable_types:
        st = self.variable_types[expr.name]
        if st in self.structs_with_destructor:
          return st
    elif isinstance(expr, TernaryExprNode):
      return self._expr_destructible_struct(
        expr.true_expr, return_index=return_index
      ) or self._expr_destructible_struct(
        expr.false_expr, return_index=return_index
      )
    elif isinstance(expr, MatchExprNode):
      for case in expr.cases:
        if isinstance(case.body, BlockNode):
          for stmt in case.body.statements:
            if isinstance(stmt, YieldNode):
              y_exprs = getattr(stmt, "expressions", None) or (
                [stmt.expr] if getattr(stmt, "expr", None) else []
              )
              if return_index < len(y_exprs):
                st = self._expr_destructible_struct(y_exprs[return_index])
                if st:
                  return st
        else:
          st = self._expr_destructible_struct(
            case.body, return_index=return_index
          )
          if st:
            return st
    return None

  @staticmethod
  def _is_owned_unwrap_expr(expr: Any) -> bool:
    """Returns True if an optional unwrap expression owns the unwrapped value.
    """
    if isinstance(expr, MoveNode):
      return True
    if isinstance(expr, (IdentifierNode, MemberAccessNode, IndexExprNode)):
      return False
    # Array.get(...) and Map.get(...) return borrowed views into the container,
    # never owned values to be destroyed at the end of an `if let`/`if var`
    # block.
    if (
      isinstance(expr, CallNode)
      and isinstance(expr.callee, MemberAccessNode)
      and expr.callee.member == "get"
      and (
        getattr(expr.callee, "is_array_method", False)
        or getattr(expr.callee, "is_map_method", False)
      )
    ):
      return False
    return True

  def _register_binding_destructibles(
    self,
    binding_expr: Any,
    let_names: List[str],
    then_block: Any,
    is_unwrap: bool,
  ) -> List[str]:
    """Registers destructible struct bindings on *then_block* if owned."""
    st_name = self._expr_destructible_struct(binding_expr)
    if not st_name:
      return []
    if is_unwrap and not self._is_owned_unwrap_expr(binding_expr):
      return []
    if not hasattr(then_block, "_block_destructibles"):
      then_block._block_destructibles = []
    for name in let_names:
      self.variable_types[name] = st_name
      then_block._block_destructibles.append(name)
    return list(let_names)

  def _is_active_destructible_var(self, m_name: str) -> bool:
    """Returns True if *m_name* is tracked in an active destructor stack frame.
    """
    return any(m_name in frame for frame in self.destructor_stack)

  def _record_move(self, m_name: str) -> None:
    """Tracks unconditional vs conditional move of *m_name* for RAII drop flags.
    """
    branch_depth = getattr(self, "_branch_depth", 0)
    var_depths = getattr(self, "_var_branch_depth", None)
    decl_depth = (
      var_depths.get(m_name, branch_depth)
      if var_depths is not None
      else branch_depth
    )
    if decl_depth < branch_depth:
      pending = getattr(self, "_pending_null_vars", None)
      if pending is not None and m_name not in pending:
        pending.append(m_name)
    else:
      self.moved_vars.add(m_name)
      # Also emit nulling on unconditional moves of tracked destructible vars
      # so a subsequent conditional reassignment cannot leave an aliased live
      # handle.
      pending_uncond = getattr(self, "_pending_unconditional_null_vars", None)
      if (
        pending_uncond is not None
        and self._is_active_destructible_var(m_name)
        and m_name not in pending_uncond
      ):
        pending_uncond.append(m_name)

  def _is_struct_constructor_call(self, node: CallNode) -> bool:
    """Returns True if *node* invokes a struct constructor (which takes
    ownership
    of args).
    """
    if getattr(node, "_is_struct_constructor", False):
      return True
    if isinstance(node.callee, IdentifierNode):
      name = node.callee.name
      if name in getattr(self, "known_structs", ()) or name in getattr(
        self, "struct_parent_names", ()
      ):
        return True
    return False

  def _record_consumed_call_moves(self, args: List[Any]) -> None:
    """Schedules deterministic teardown for destructible vars moved into
    borrowed
    calls.
    """
    pending_del = getattr(self, "_pending_destroy_moved_vars", None)
    if pending_del is None:
      pending_del = []
      self._pending_destroy_moved_vars = pending_del
    for arg in args:
      expr = arg.expr if hasattr(arg, "expr") else arg
      if isinstance(expr, MoveNode):
        m_name = (
          self._resolve_var_name(expr.name)
          if hasattr(self, "_resolve_var_name")
          else self._identifier_map.get(expr.name, self._mangle_name(expr.name))
        )
        if (
          self._is_active_destructible_var(m_name) and m_name not in pending_del
        ):
          pending_del.append(m_name)

  def _drain_pending_destroy_moved_vars(
    self, exclude: Optional[Set[str]] = None
  ) -> None:
    """Emits destructors for destructible vars moved into borrowed calls."""
    pending_del = getattr(self, "_pending_destroy_moved_vars", None)
    if not pending_del:
      return
    for var_name in list(pending_del):
      if not exclude or var_name not in exclude:
        self.newline()
        self._emit_destructor_call(var_name)
    pending_del.clear()

  def _drain_pending_null_vars(
    self,
    null_literal: str,
    exclude: Optional[Set[str]] = None,
  ) -> None:
    """Emits post-statement teardown & drop-flag clearing (`v = None` / `v =
    nil`)
    for moved vars.
    """
    self._drain_pending_destroy_moved_vars(exclude=exclude)
    for attr in ("_pending_null_vars", "_pending_unconditional_null_vars"):
      pending = getattr(self, attr, None)
      if not pending:
        continue
      for var_name in list(pending):
        if not exclude or var_name not in exclude:
          self.newline()
          self.emit(f"{var_name} = {null_literal}")
      pending.clear()

  def _visit_in_branch(self, node: ASTNode) -> None:
    """Visits *node* inside a conditional branch depth for move drop-flag
    tracking.
    """
    self._branch_depth = getattr(self, "_branch_depth", 0) + 1
    try:
      self.visit(node)
    finally:
      self._branch_depth -= 1

  def _emit_destructor_call(self, var_name: str) -> None:
    """Emits the teardown statement for a single destructible variable."""
    self.emit(f"_sapphire_del({var_name})")

  def _emit_loop_destructors(self) -> None:
    """Emits destructors for variables in the active loop scopes."""
    if self.loop_destructor_depth:
      loop_depth = self.loop_destructor_depth[-1]
      for frame in reversed(self.destructor_stack[loop_depth:]):
        for var_name in reversed(frame):
          if not hasattr(self, "moved_vars") or var_name not in self.moved_vars:
            self.newline()
            self._emit_destructor_call(var_name)

  def _collect_struct_metadata(
    self, program: ProgramNode, track_known_structs: bool = False
  ) -> None:
    """Collects struct methods, traits, return types, and destructors from
    program
    declarations.
    """
    self.struct_default_trait_methods: Dict[str, List[Any]] = {}
    for decl in program.declarations:
      if getattr(decl, "type_params", None):
        continue
      if track_known_structs and isinstance(decl, StructDeclNode):
        self.known_structs.add(decl.name)
      elif isinstance(decl, ImplBlockNode):
        if decl.struct_name not in self.struct_methods:
          self.struct_methods[decl.struct_name] = []
        self.struct_methods[decl.struct_name].extend(decl.members)
        if decl.trait_name and hasattr(self, "struct_traits"):
          if decl.struct_name not in self.struct_traits:
            self.struct_traits[decl.struct_name] = set()
          self.struct_traits[decl.struct_name].add(decl.trait_name)
        for m in decl.members:
          if getattr(m, "func_decl", None):
            ret_names = get_return_type_names(m.func_decl)
            if ret_names:
              self.method_return_types[(decl.struct_name, m.func_decl.name)] = (
                ret_names
              )
        default_bindings = getattr(decl, "default_trait_members", None)
        if default_bindings:
          self.struct_default_trait_methods.setdefault(
            decl.struct_name, []
          ).extend(default_bindings)
          for _trait_ref, m_name, _modifier, trait_member in default_bindings:
            ret_names = get_return_type_names(trait_member)
            if ret_names:
              self.method_return_types[(decl.struct_name, m_name)] = ret_names
      elif isinstance(decl, FuncDeclNode):
        ret_names = get_return_type_names(decl)
        if ret_names:
          self.func_return_types[decl.name] = ret_names

    self.proto_structs: Set[str] = set()
    self.struct_destructible_fields: Dict[str, List[str]] = {}
    self.struct_parent_names: Dict[str, List[str]] = {}
    self.structs_with_destructor = {"Arena", "Ref", "SharedRef"}

    for decl in program.declarations:
      if isinstance(decl, StructDeclNode):
        if decl.is_prototype:
          self.proto_structs.add(decl.name)
        self.struct_parent_names[decl.name] = list(decl.parent_names or [])

    for s_name, members in self.struct_methods.items():
      if s_name in self.proto_structs:
        continue
      for m in members:
        if getattr(m, "func_decl", None) and m.func_decl.name == "__del__":
          self.structs_with_destructor.add(s_name)
          break

    changed = True
    while changed:
      changed = False
      for decl in program.declarations:
        if isinstance(decl, StructDeclNode) and not decl.is_prototype:
          destructible_fields = [
            f.name
            for f in decl.fields
            if extract_type_name(f.field_type) in self.structs_with_destructor
          ]
          self.struct_destructible_fields[decl.name] = destructible_fields
          if decl.name not in self.structs_with_destructor and (
            destructible_fields
            or any(
              p in self.structs_with_destructor
              for p in (decl.parent_names or [])
            )
          ):
            self.structs_with_destructor.add(decl.name)
            changed = True

  # ------------------------------------------------------------------
  # Declaration visitors
  # ------------------------------------------------------------------

  @abstractmethod
  def visit_EnumDeclNode(self, node: EnumDeclNode) -> None: ...

  @abstractmethod
  def visit_ImportStmtNode(self, node: ImportStmtNode) -> None: ...

  @abstractmethod
  def visit_ExportStmtNode(self, node: ExportStmtNode) -> None: ...

  @abstractmethod
  def visit_StructDeclNode(self, node: StructDeclNode) -> None: ...

  @abstractmethod
  def visit_StructFieldNode(self, node: StructFieldNode) -> None: ...

  @abstractmethod
  def visit_ImplMemberNode(self, node: ImplMemberNode) -> None: ...

  @abstractmethod
  def visit_TraitDeclNode(self, node: TraitDeclNode) -> None: ...

  @abstractmethod
  def visit_FuncDeclNode(self, node: FuncDeclNode) -> None: ...

  # ------------------------------------------------------------------
  # Statement visitors
  # ------------------------------------------------------------------

  @abstractmethod
  def visit_BlockNode(self, node: BlockNode) -> None: ...

  @abstractmethod
  def visit_VarDeclNode(self, node: VarDeclNode) -> None: ...

  @abstractmethod
  def visit_AssignmentNode(self, node: AssignmentNode) -> None: ...

  @abstractmethod
  def visit_ExprStmtNode(self, node: ExprStmtNode) -> None: ...

  @abstractmethod
  def visit_ReturnNode(self, node: ReturnNode) -> None: ...

  @abstractmethod
  def visit_YieldNode(self, node: YieldNode) -> None: ...

  @abstractmethod
  def visit_MatchExprNode(self, node: MatchExprNode) -> None: ...

  @abstractmethod
  def visit_EllipsisPatternNode(self, node: EllipsisPatternNode) -> None: ...

  @abstractmethod
  def visit_IfNode(self, node: IfNode) -> None: ...

  @abstractmethod
  def visit_WhileNode(self, node: WhileNode) -> None: ...

  @abstractmethod
  def visit_ForNode(self, node: ForNode) -> None: ...

  @abstractmethod
  def visit_BreakNode(self, node: BreakNode) -> None: ...

  @abstractmethod
  def visit_ContinueNode(self, node: ContinueNode) -> None: ...

  # ------------------------------------------------------------------
  # Expression visitors
  # ------------------------------------------------------------------

  @abstractmethod
  def visit_LiteralNode(self, node: LiteralNode) -> None: ...

  @abstractmethod
  def visit_InterpolatedStringNode(
    self, node: InterpolatedStringNode
  ) -> None: ...

  @abstractmethod
  def visit_IdentifierNode(self, node: IdentifierNode) -> None: ...

  @abstractmethod
  def visit_BinaryOpNode(self, node: BinaryOpNode) -> None: ...

  @abstractmethod
  def visit_TernaryExprNode(self, node: TernaryExprNode) -> None: ...

  @abstractmethod
  def visit_UnaryOpNode(self, node: UnaryOpNode) -> None: ...

  @abstractmethod
  def visit_CastExprNode(self, node: CastExprNode) -> None: ...

  @abstractmethod
  def visit_CallNode(self, node: CallNode) -> None: ...

  @abstractmethod
  def visit_MemberAccessNode(self, node: MemberAccessNode) -> None: ...

  @abstractmethod
  def visit_CloneNode(self, node: CloneNode) -> None: ...

  @abstractmethod
  def visit_MoveNode(self, node: MoveNode) -> None: ...

  @abstractmethod
  def visit_LambdaNode(self, node: LambdaNode) -> None: ...

  @abstractmethod
  def visit_ArrayLiteralNode(self, node: ArrayLiteralNode) -> None: ...

  @abstractmethod
  def visit_MapLiteralNode(self, node: MapLiteralNode) -> None: ...

  @abstractmethod
  def visit_IndexExprNode(self, node: IndexExprNode) -> None: ...

  @abstractmethod
  def visit_StructInitializerNode(
    self, node: StructInitializerNode
  ) -> None: ...

  @abstractmethod
  def visit_GuardClauseNode(self, node: GuardClauseNode) -> None: ...

  @abstractmethod
  def visit_GuardStmtNode(self, node: GuardStmtNode) -> None: ...
