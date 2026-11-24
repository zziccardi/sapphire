"""Shared mutable code-generation state and scoped output buffers.

Provides `EmitterState` (a typed container for all state shared between
`PythonTranspiler` and `LuaTranspiler`) and `OutputBuffer` (a stackable text
buffer used to capture sub-expression output without instantiating cloned
transpilers).
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class OutputBuffer:
  """Accumulates emitted source code chunks and tracks indentation level."""

  chunks: list[str] = field(default_factory=list)
  indent_level: int = 0

  def emit(self, text: str) -> None:
    """Appends *text* to this output buffer."""
    self.chunks.append(text)

  def indent(self) -> None:
    """Increases the indentation level by one."""
    self.indent_level += 1

  def dedent(self) -> None:
    """Decreases the indentation level by one (clamped at 0)."""
    if self.indent_level > 0:
      self.indent_level -= 1

  def get_output(self) -> str:
    """Returns the concatenated contents of this buffer."""
    return "".join(self.chunks)


@dataclass
class EmitterState:
  """Shared mutable state for Sapphire transpiler backends."""

  test_mode: bool = False
  use_runtime_module: bool = False

  # Struct, method, and RAII metadata collected from the AST
  struct_methods: dict[str, list[Any]] = field(default_factory=dict)
  structs_with_destructor: set[str] = field(
    default_factory=lambda: {"Arena", "Ref", "SharedRef"}
  )
  proto_structs: set[str] = field(default_factory=set)
  struct_destructible_fields: dict[str, list[str]] = field(default_factory=dict)
  struct_parent_names: dict[str, list[str]] = field(default_factory=dict)

  # Destructor, move, and branch tracking
  destructor_stack: list[list[str]] = field(default_factory=list)
  loop_destructor_depth: list[int] = field(default_factory=list)
  moved_vars: set[str] = field(default_factory=set)
  branch_depth: int = 0
  var_branch_depth: dict[str, int] = field(default_factory=dict)
  pending_null_vars: list[str] = field(default_factory=list)
  pending_unconditional_null_vars: list[str] = field(default_factory=list)
  pending_destroy_moved_vars: list[str] = field(default_factory=list)

  # Type & identifier resolution tables
  func_return_types: dict[str, Any] = field(default_factory=dict)
  method_return_types: dict[Any, Any] = field(default_factory=dict)
  variable_types: dict[str, str] = field(default_factory=dict)
  identifier_map: dict[str, str] = field(default_factory=dict)

  # Expression lifting & temporary naming
  lifted_matches: dict[int, str] = field(default_factory=dict)
  lifted_short_circuits: dict[int, str] = field(default_factory=dict)
  temp_name_counters: dict[str, int] = field(default_factory=dict)

  # Active match & unwrap writeback context
  current_match_target: str | None = None
  current_match_node: Any = None
  current_match_done_flag: str | None = None
  match_loop_depth: int = 0
  unwrap_writebacks: dict[str, Any] = field(default_factory=dict)
