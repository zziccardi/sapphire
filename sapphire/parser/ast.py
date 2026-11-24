"""Sapphire Abstract Syntax Tree (AST) node definitions.

All AST node classes defined here inherit from a common ASTNode base class.
They are used to represent the syntactic structure of Sapphire programs
in a structured, easy-to-analyze form.
"""

from dataclasses import dataclass, field
from typing import Any, Optional, Union


@dataclass(frozen=True)
class SourceSpan:
  """Structured source location span (1-indexed lines, 0-indexed columns)."""

  start_line: int | None = None
  start_column: int | None = None
  end_line: int | None = None
  end_column: int | None = None
  length: int | None = None


@dataclass(eq=False)
class ASTNode:
  """Base class for all AST nodes."""

  is_parenthesized: bool = field(default=False, init=False, repr=False)

  # Source position metadata used by diagnostics, source maps, and the LSP.
  start_line: int | None = field(default=None, init=False, repr=False)
  start_column: int | None = field(default=None, init=False, repr=False)
  end_line: int | None = field(default=None, init=False, repr=False)
  end_column: int | None = field(default=None, init=False, repr=False)
  length: int | None = field(default=None, init=False, repr=False)
  name_span: SourceSpan | None = field(default=None, init=False, repr=False)

  @property
  def span(self) -> SourceSpan:
    """Returns a structured SourceSpan for this AST node."""
    return SourceSpan(
      start_line=self.start_line,
      start_column=self.start_column,
      end_line=self.end_line,
      end_column=self.end_column,
      length=self.length,
    )

  def to_dict(self) -> dict[str, Any]:
    """Returns a dictionary representation of the AST node for
    serialization/debugging.
    """

    def _serialize(v: Any) -> Any:
      if isinstance(v, ASTNode):
        return v.to_dict()
      elif isinstance(v, list):
        return [_serialize(item) for item in v]
      elif isinstance(v, tuple):
        return [_serialize(item) for item in v]
      elif isinstance(v, dict):
        return {k: _serialize(val) for k, val in v.items()}
      return v

    result = {"node_type": self.__class__.__name__}
    for key, value in self.__dict__.items():
      # Skip positioning and span metadata during standard AST serialization
      if key in (
        "start_line",
        "start_column",
        "end_line",
        "end_column",
        "length",
        "name_span",
      ):
        continue
      if key == "is_parenthesized" and not value:
        continue
      result[key] = _serialize(value)
    return result

  def __repr__(self) -> str:
    return str(self.to_dict())


# ==========================================
# Type AST Nodes
# ==========================================


@dataclass(eq=False)
class TypeNode(ASTNode):
  """Base class for all type representations in the AST."""

  pass


@dataclass(eq=False)
class BasicTypeNode(TypeNode):
  """Represents a basic type (e.g. 'int', 'float', 'bool', or a struct name like
  'Stack<int>').
  """

  name: str
  type_args: list[TypeNode] = field(default_factory=list)

  def __post_init__(self) -> None:
    if self.type_args is None:
      self.type_args = []


@dataclass(eq=False)
class OptionalTypeNode(TypeNode):
  """Represents an optional type wrapper (e.g. 'int?')."""

  base_type: TypeNode


@dataclass(eq=False)
class ArrayTypeNode(TypeNode):
  """Represents an array type wrapper (e.g. '[int]' or '[int; 3]')."""

  element_type: TypeNode
  size: int | None = None


@dataclass(eq=False)
class MapTypeNode(TypeNode):
  """Represents a map type wrapper (e.g. '[String: int]')."""

  key_type: TypeNode
  val_type: TypeNode


@dataclass(eq=False, init=False)
class FunctionTypeNode(TypeNode):
  """Represents a function type signature (e.g. '(int, int) -> float' or '(int)
  ->
  (float, float)').
  """

  def __init__(
    self,
    param_types: list[TypeNode],
    return_types: TypeNode | list[TypeNode],
  ):
    self.param_types = param_types
    if isinstance(return_types, list):
      self.return_types = return_types
    else:
      self.return_types = [return_types]

  @property
  def return_type(self) -> TypeNode | None:
    return self.return_types[0] if self.return_types else None


# ==========================================
# Declaration AST Nodes
# ==========================================


@dataclass(eq=False)
class DeclNode(ASTNode):
  """Base class for all declaration nodes."""

  pass


@dataclass(eq=False)
class ImportStmtNode(ASTNode):
  """Represents a module import statement (e.g. 'import lib.love2d.graphics as
  gfx;').
  """

  path: str
  alias: str | None = None


@dataclass(eq=False)
class ExportSpecifierNode(ASTNode):
  """Represents a specifier in an export manifest block (e.g. 'Image',
  'enums.DrawMode', or 'new_image as create_image').
  """

  symbol: str
  module_prefix: str | None = None
  alias: str | None = None

  @property
  def exported_name(self) -> str:
    return self.alias if self.alias else self.symbol


@dataclass(eq=False)
class ExportStmtNode(ASTNode):
  """Represents an explicit module export manifest block (e.g. 'export { Image,
  new_image };').
  """

  specifiers: list[ExportSpecifierNode]


@dataclass(eq=False)
class ProgramNode(ASTNode):
  """Root node of a Sapphire program, containing top-level declarations,
  imports,
  and optional export manifest.
  """

  declarations: list[ASTNode]
  imports: list[ImportStmtNode] = field(default_factory=list)
  export_block: ExportStmtNode | None = None

  def __post_init__(self) -> None:
    if self.imports is None:
      self.imports = []


@dataclass(eq=False)
class StructFieldNode(ASTNode):
  """Represents a single field in a struct declaration (e.g. 'var x: float;' or
  'var x = 0;').
  """

  is_mutable: bool
  name: str
  field_type: TypeNode | None = None
  default_expr: ASTNode | None = None


@dataclass(eq=False)
class AnnotationNode(ASTNode):
  """Represents an annotation decorator (e.g. '@extern' or
  '@export("love.update")').
  """

  name: str
  arg: str | None = None


@dataclass(eq=False, init=False)
class StructDeclNode(DeclNode):
  """Represents a struct declaration."""

  def __init__(
    self,
    name: str,
    parent_names: str | list[str] | None = None,
    fields: list[StructFieldNode] | None = None,
    is_prototype: bool = False,
    type_params: list[str] | None = None,
    parent_name: str | None = None,
  ):
    self.name = name
    if parent_names is None:
      self.parent_names = [parent_name] if parent_name else []
    elif isinstance(parent_names, str):
      self.parent_names = [parent_names]
    else:
      self.parent_names = list(parent_names)
    self.fields = fields or []
    self.is_prototype = is_prototype
    self.type_params = type_params or []
    self.parent_names_info: list[dict[str, Any]] = []

  @property
  def parent_name(self) -> str | None:
    return self.parent_names[0] if self.parent_names else None

  @parent_name.setter
  def parent_name(self, value: str | None) -> None:
    if value is None:
      self.parent_names = []
    else:
      self.parent_names = [value]


@dataclass(eq=False)
class EnumMemberNode(ASTNode):
  """Represents a member/variant in an enum declaration."""

  name: str
  value: int | str | None = None


@dataclass(eq=False)
class EnumDeclNode(DeclNode):
  """Represents an enum declaration."""

  name: str
  members: list[EnumMemberNode]


@dataclass(eq=False)
class ParameterNode(ASTNode):
  """Represents a parameter in a function signature."""

  is_mutable: bool
  name: str
  param_type: TypeNode | None = None
  default_expr: ASTNode | None = None


@dataclass(eq=False, init=False)
class FuncDeclNode(DeclNode):
  """Represents a function declaration, supporting single or multiple return
  types.
  """

  def __init__(
    self,
    name: str,
    parameters: list[ParameterNode],
    return_types: TypeNode | list[TypeNode] | None = None,
    body: Optional["BlockNode"] = None,
    annotations: list[AnnotationNode] | None = None,
    return_type: TypeNode | None = None,
    type_params: list[str] | None = None,
    base_initializers: list["CallNode"] | None = None,
  ):
    self.name = name
    self.parameters = parameters
    if return_types is not None:
      if isinstance(return_types, list):
        self.return_types = return_types
      else:
        self.return_types = [return_types]
    elif return_type is not None:
      self.return_types = [return_type]
    else:
      self.return_types = []
    self.body = body
    self.annotations = annotations or []
    self.type_params = type_params or []
    self.base_initializers = base_initializers or []

  @property
  def return_type(self) -> TypeNode | None:
    return self.return_types[0] if self.return_types else None


@dataclass(eq=False)
class ImplMemberNode(ASTNode):
  """Represents a member inside an impl block (e.g. static/var/immutable
  methods).
  """

  modifier: str | None
  func_decl: FuncDeclNode


@dataclass(eq=False)
class ImplBlockNode(DeclNode):
  """Represents a Rust-style implementation block."""

  struct_name: str
  trait_name: str | None
  members: list[ImplMemberNode]
  type_params: list[str] = field(default_factory=list)
  trait_type_args: list[TypeNode] = field(default_factory=list)
  struct_type_args: list[TypeNode] = field(default_factory=list)

  def __post_init__(self) -> None:
    if self.type_params is None:
      self.type_params = []
    if self.trait_type_args is None:
      self.trait_type_args = []
    if self.struct_type_args is None:
      self.struct_type_args = []


@dataclass(eq=False, init=False)
class TraitMemberNode(ASTNode):
  """Represents a method signature (and optional default body) inside a trait
  declaration.
  """

  def __init__(
    self,
    name: str,
    parameters: list[ParameterNode],
    return_types: TypeNode | list[TypeNode] | None = None,
    modifier: str | None = None,
    return_type: TypeNode | None = None,
    annotations: list[AnnotationNode] | None = None,
    type_params: list[str] | None = None,
    body: Optional["BlockNode"] = None,
  ):
    self.name = name
    self.parameters = parameters
    if return_types is not None:
      if isinstance(return_types, list):
        self.return_types = return_types
      else:
        self.return_types = [return_types]
    elif return_type is not None:
      self.return_types = [return_type]
    else:
      self.return_types = []
    self.modifier = modifier
    self.annotations = annotations or []
    self.type_params = type_params or []
    self.body = body

  @property
  def return_type(self) -> TypeNode | None:
    return self.return_types[0] if self.return_types else None


@dataclass(eq=False)
class TraitDeclNode(DeclNode):
  """Represents a trait declaration."""

  name: str
  members: list[TraitMemberNode]
  type_params: list[str] = field(default_factory=list)

  def __post_init__(self) -> None:
    if self.type_params is None:
      self.type_params = []


# ==========================================
# Statement AST Nodes
# ==========================================


@dataclass(eq=False)
class StmtNode(ASTNode):
  """Base class for all statement nodes."""

  pass


@dataclass(eq=False)
class BlockNode(StmtNode):
  """Represents a block of statements enclosed in curly braces."""

  statements: list[StmtNode]


@dataclass(eq=False, init=False)
class VarDeclNode(StmtNode):
  """Represents a variable declaration statement (let/var), supporting
  multi-variable bindings.
  """

  def __init__(
    self,
    is_mutable: bool,
    names: str | list[str] | None = None,
    val_types: TypeNode | list[TypeNode | None] | None = None,
    exprs: ASTNode | list[ASTNode] | None = None,
    annotations: list[AnnotationNode] | None = None,
    val_type: TypeNode | None = None,
    expr: ASTNode | None = None,
    name: str | None = None,
  ):
    self.is_mutable = is_mutable
    if names is not None:
      if isinstance(names, list):
        self.names = names
      else:
        self.names = [names]
    elif name is not None:
      self.names = [name]
    else:
      self.names = []

    if val_types is not None:
      if isinstance(val_types, list):
        self.val_types = val_types
      else:
        self.val_types = [val_types]
    elif val_type is not None:
      self.val_types = [val_type]
    else:
      self.val_types = [None] * len(self.names)

    if exprs is not None:
      if isinstance(exprs, list):
        self.exprs = exprs
      else:
        self.exprs = [exprs]
    elif expr is not None:
      self.exprs = [expr]
    else:
      self.exprs = []

    self.annotations = annotations or []

  @property
  def name(self) -> str:
    return self.names[0] if self.names else ""

  @property
  def val_type(self) -> TypeNode | None:
    return self.val_types[0] if self.val_types else None

  @property
  def expr(self) -> ASTNode | None:
    return self.exprs[0] if self.exprs else None

  def to_dict(self) -> dict[str, Any]:
    res = super().to_dict()
    res["name"] = self.name
    res["val_type"] = self.val_type.to_dict() if self.val_type else None
    res["expr"] = self.expr.to_dict() if self.expr else None
    return res


@dataclass(eq=False, init=False)
class AssignmentNode(StmtNode):
  """Represents an assignment statement (e.g. 'x = 5;' or 'x, y = 10, 20;')."""

  def __init__(
    self,
    targets: ASTNode | list[ASTNode],
    op: str,
    exprs: ASTNode | list[ASTNode],
    target: ASTNode | None = None,
    expr: ASTNode | None = None,
  ):
    if targets is not None and not (
      isinstance(targets, list) and len(targets) == 0
    ):
      if isinstance(targets, list):
        self.targets = targets
      else:
        self.targets = [targets]
    elif target is not None:
      self.targets = [target]
    else:
      self.targets = []

    self.op = op

    if exprs is not None and not (isinstance(exprs, list) and len(exprs) == 0):
      if isinstance(exprs, list):
        self.exprs = exprs
      else:
        self.exprs = [exprs]
    elif expr is not None:
      self.exprs = [expr]
    else:
      self.exprs = []

  @property
  def target(self) -> ASTNode:
    return self.targets[0]

  @property
  def expr(self) -> ASTNode:
    return self.exprs[0]

  def to_dict(self) -> dict[str, Any]:
    res = super().to_dict()
    res["target"] = self.target.to_dict() if self.targets else None
    res["expr"] = self.expr.to_dict() if self.exprs else None
    return res


@dataclass(eq=False)
class ExprStmtNode(StmtNode):
  """Represents an expression evaluated as a statement."""

  expr: ASTNode


@dataclass(eq=False, init=False)
class ReturnNode(StmtNode):
  """Represents a return statement, supporting single or multiple returned
  expressions.
  """

  def __init__(
    self,
    exprs: ASTNode | list[ASTNode] | None = None,
    expr: ASTNode | None = None,
  ):
    if exprs is not None:
      if isinstance(exprs, list):
        self.expressions = exprs
      else:
        self.expressions = [exprs]
    elif expr is not None:
      self.expressions = [expr]
    else:
      self.expressions = []

  @property
  def expr(self) -> ASTNode | None:
    return self.expressions[0] if self.expressions else None

  def to_dict(self) -> dict[str, Any]:
    res = super().to_dict()
    res["expr"] = self.expr.to_dict() if self.expr is not None else None
    return res


@dataclass(eq=False, init=False)
class YieldNode(StmtNode):
  """Represents a yield statement, supporting single or multiple yielded
  expressions.
  """

  def __init__(
    self,
    exprs: ASTNode | list[ASTNode] | None = None,
    expr: ASTNode | None = None,
  ):
    if exprs is not None:
      if isinstance(exprs, list):
        self.expressions = exprs
      else:
        self.expressions = [exprs]
    elif expr is not None:
      self.expressions = [expr]
    else:
      self.expressions = []

  @property
  def expr(self) -> ASTNode | None:
    return self.expressions[0] if self.expressions else None

  def to_dict(self) -> dict[str, Any]:
    res = super().to_dict()
    res["exprs"] = [e.to_dict() for e in self.expressions]
    res["expr"] = self.expr.to_dict() if self.expr is not None else None
    return res


@dataclass(eq=False)
class BreakNode(StmtNode):
  """Represents a break statement (e.g. 'break;')."""

  pass


@dataclass(eq=False)
class ContinueNode(StmtNode):
  """Represents a continue statement (e.g. 'continue;')."""

  pass


@dataclass(eq=False)
class HeaderBindingNode(ASTNode):
  """Represents a variable binding inside control-flow headers (e.g. let x ?= y
  or
  let x, y ?= pair).
  """

  is_mutable: bool
  let_name: str
  type_node: ASTNode | None
  expr: ASTNode
  is_unwrap: bool
  let_names: list[str] | None = None

  def __post_init__(self) -> None:
    if self.let_names is None:
      self.let_names = [self.let_name]


@dataclass(eq=False)
class GuardClauseNode(ASTNode):
  """Represents a single clause within a guard statement (binding or boolean
  condition).
  """

  binding: HeaderBindingNode | None = None
  condition: ASTNode | None = None


@dataclass(eq=False, init=False)
class GuardStmtNode(StmtNode):
  """Represents a guard statement (e.g.
  'guard let a ?= x; a > 0 else { ... }').
  """

  def __init__(
    self,
    clauses: list[GuardClauseNode] | None = None,
    else_block: BlockNode | None = None,
    bindings: list[HeaderBindingNode] | None = None,
    condition: ASTNode | None = None,
  ):
    if clauses is not None:
      self.clauses = clauses
      self.bindings = [c.binding for c in clauses if c.binding is not None]
      conds = [c.condition for c in clauses if c.condition is not None]
      self.condition = conds[0] if conds else None
    else:
      self.bindings = bindings or []
      self.condition = condition
      self.clauses = [GuardClauseNode(binding=b) for b in self.bindings]
      if self.condition:
        self.clauses.append(GuardClauseNode(condition=self.condition))
    self.else_block = else_block


@dataclass(eq=False, init=False)
class IfNode(StmtNode):
  """Represents an if/else conditional statement, supporting multi-bindings and
  conditions.
  """

  def __init__(
    self,
    init_binding: HeaderBindingNode | None = None,
    condition: ASTNode | None = None,
    then_block: BlockNode | None = None,
    else_block: Union[BlockNode, "IfNode"] | None = None,
    bindings: list[HeaderBindingNode] | None = None,
  ):
    if bindings is not None:
      self.bindings = bindings
    elif init_binding is not None:
      self.bindings = [init_binding]
    else:
      self.bindings = []
    self.condition = condition
    self.then_block = then_block
    self.else_block = else_block

  @property
  def init_binding(self) -> HeaderBindingNode | None:
    return self.bindings[0] if self.bindings else None

  @init_binding.setter
  def init_binding(self, val: HeaderBindingNode | None):
    if val is not None:
      self.bindings = [val]
    else:
      self.bindings = []


@dataclass(eq=False)
class WhileNode(StmtNode):
  """Represents a while loop."""

  condition: ASTNode
  block: BlockNode


@dataclass(eq=False)
class ForNode(StmtNode):
  """Represents a for-in loop."""

  is_mutable: bool
  loop_var: str
  iterable: ASTNode
  block: BlockNode
  key_var: str | None = None
  val_var: str | None = None

  def __post_init__(self) -> None:
    if self.val_var is None:
      self.val_var = self.loop_var


# ==========================================
# Expression AST Nodes
# ==========================================


@dataclass(eq=False)
class ExprNode(ASTNode):
  """Base class for all expression nodes."""

  pass


@dataclass(eq=False)
class LiteralNode(ExprNode):
  """Represents a literal value (int, float, string, bool, none)."""

  value: Any
  lit_type: str


@dataclass(eq=False)
class InterpolatedStringNode(ExprNode):
  """Represents an interpolated string (f"Hello {name}")."""

  parts: list[ASTNode]


@dataclass(eq=False)
class IdentifierNode(ExprNode):
  """Represents an identifier/variable reference."""

  name: str


@dataclass(eq=False)
class BinaryOpNode(ExprNode):
  """Represents a binary operation (e.g. '+', '-', '==', '&&')."""

  left: ASTNode
  op: str
  right: ASTNode


@dataclass(eq=False)
class TernaryExprNode(ExprNode):
  """Represents a ternary conditional expression (e.g. 'condition ? true_expr :
  false_expr').
  """

  condition: ASTNode
  true_expr: ASTNode
  false_expr: ASTNode


@dataclass(eq=False)
class UnaryOpNode(ExprNode):
  """Represents a unary operation (e.g. '-', '!')."""

  op: str
  expr: ASTNode


@dataclass(eq=False)
class CastExprNode(ExprNode):
  """Represents an explicit type cast expression (e.g. 'x as float')."""

  expr: ASTNode
  target_type: TypeNode


@dataclass(eq=False)
class ArgumentNode(ASTNode):
  """Represents an argument passed to a function call, potentially named (e.g.
  'x =
  5').
  """

  name: str | None
  expr: ASTNode


@dataclass(eq=False)
class CallNode(ExprNode):
  """Represents a function or method call."""

  callee: ASTNode
  arguments: list[ArgumentNode]
  type_args: list[TypeNode] = field(default_factory=list)
  arena_expr: ASTNode | None = None

  def __post_init__(self) -> None:
    if self.type_args is None:
      self.type_args = []


@dataclass(eq=False)
class MemberAccessNode(ExprNode):
  """Represents a member or property access (e.g. 'obj.field' or 'obj?.field' or
  'obj.__proto__').
  """

  receiver: ASTNode
  member: str
  is_optional: bool


@dataclass(eq=False)
class CloneNode(ExprNode):
  """Represents a clone expression (e.g. 'clone prototype_enemy { self.health =
  25;
  }').
  """

  expr: ASTNode
  initializer_block: list[StmtNode] | None = None
  arena_expr: ASTNode | None = None


@dataclass(eq=False)
class MoveNode(ExprNode):
  """Represents an explicit ownership transfer expression (e.g. 'move
  resource').
  """

  name: str


@dataclass(eq=False)
class LambdaParamNode(ASTNode):
  """Represents a parameter in a lambda expression."""

  name: str
  param_type: TypeNode | None = None


@dataclass(eq=False)
class LambdaNode(ExprNode):
  """Represents an anonymous lambda function (e.g. '(x: int) -> int { return x;
  }').
  """

  parameters: list[LambdaParamNode]
  return_type: TypeNode | None
  body: BlockNode | ASTNode


@dataclass(eq=False)
class ArrayLiteralNode(ExprNode):
  """Represents an array literal (e.g. '[1, 2, 3]')."""

  elements: list[ASTNode]


@dataclass(eq=False)
class MapEntryNode(ASTNode):
  """Represents an entry in a map literal (key: value)."""

  key: ASTNode
  value: ASTNode


@dataclass(eq=False)
class MapLiteralNode(ExprNode):
  """Represents a map literal (e.g. '{"a": 1, "b": 2}')."""

  entries: list[MapEntryNode]


@dataclass(eq=False)
class IndexExprNode(ExprNode):
  """Represents an array indexing expression (e.g. 'arr[0]')."""

  array: ASTNode
  index: ASTNode


@dataclass(eq=False)
class StructInitializerNode(ExprNode):
  """Represents a curly-brace struct initializer expression (e.g. 'Weapon {
  damage
  = 10 }').
  """

  struct_name: str
  fields: list[ArgumentNode]
  arena_expr: ASTNode | None = None
  type_args: list[TypeNode] = field(default_factory=list)

  def __post_init__(self) -> None:
    if self.type_args is None:
      self.type_args = []


@dataclass(eq=False)
class EllipsisPatternNode(ASTNode):
  """Represents the '...' wildcard pattern in a match case."""

  pass


@dataclass(eq=False, init=False)
class MatchCaseNode(ASTNode):
  """Represents a single case branch in a match expression."""

  def __init__(
    self,
    pattern: ASTNode | list[ASTNode],
    body: BlockNode | ASTNode,
  ):
    self.patterns: list[ASTNode] = (
      pattern if isinstance(pattern, list) else [pattern]
    )
    self.body = body  # BlockNode or single ExprNode

  @property
  def pattern(self) -> ASTNode:
    """Compatibility accessor returning the first pattern in this arm."""
    return self.patterns[0]


@dataclass(eq=False)
class MatchExprNode(ExprNode):
  """Represents a match expression (e.g. 'match status { HttpStatus.Ok ->
  "Success", ... -> "Error", }').
  """

  subject: ASTNode
  cases: list[MatchCaseNode]
  is_statement: bool = False
