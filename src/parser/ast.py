"""Sapphire Abstract Syntax Tree (AST) node definitions.

All AST node classes defined here inherit from a common ASTNode base class.
They are used to represent the syntactic structure of Sapphire programs
in a structured, easy-to-analyze form.
"""

from typing import Any, Dict, List, Optional, Union


class ASTNode:
  """Base class for all AST nodes."""

  is_parenthesized: bool = False

  # The following position attributes are only needed for editor integrations
  # (Language Server Protocol) and are not used by the compiler transpiler.
  start_line: Optional[int] = None
  start_column: Optional[int] = None
  end_line: Optional[int] = None
  end_column: Optional[int] = None
  length: Optional[int] = None

  def to_dict(self) -> Dict[str, Any]:
    """Returns a dictionary representation of the AST node for serialization/debugging."""
    result = {"node_type": self.__class__.__name__}
    for key, value in self.__dict__.items():
      # Skip language-server specific positioning keys during standard AST serialization
      if key in ("start_line", "start_column", "end_line", "end_column", "length"):
        continue
      if isinstance(value, ASTNode):
        result[key] = value.to_dict()
      elif isinstance(value, list):
        result[key] = [
            item.to_dict() if isinstance(item, ASTNode) else item
            for item in value
        ]
      else:
        result[key] = value
    return result

  def __repr__(self) -> str:
    return str(self.to_dict())


# ==========================================
# Type AST Nodes
# ==========================================

class TypeNode(ASTNode):
  """Base class for all type representations in the AST."""
  pass


class BasicTypeNode(TypeNode):
  """Represents a basic type (e.g. 'int', 'float', 'bool', or a struct name like 'Stack<int>')."""

  def __init__(self, name: str, type_args: Optional[List[TypeNode]] = None):
    self.name = name
    self.type_args = type_args or []


class OptionalTypeNode(TypeNode):
  """Represents an optional type wrapper (e.g. 'int?')."""

  def __init__(self, base_type: TypeNode):
    self.base_type = base_type


class ArrayTypeNode(TypeNode):
  """Represents an array type wrapper (e.g. '[int]')."""

  def __init__(self, element_type: TypeNode):
    self.element_type = element_type


class MapTypeNode(TypeNode):
  """Represents a map type wrapper (e.g. '[String: int]')."""

  def __init__(self, key_type: TypeNode, val_type: TypeNode):
    self.key_type = key_type
    self.val_type = val_type



class FunctionTypeNode(TypeNode):
  """Represents a function type signature (e.g. '(int, int) -> float' or '(int) -> (float, float)')."""

  def __init__(self, param_types: List[TypeNode], return_types: Union[TypeNode, List[TypeNode]]):
    self.param_types = param_types
    if isinstance(return_types, list):
      self.return_types = return_types
    else:
      self.return_types = [return_types]

  @property
  def return_type(self) -> TypeNode:
    return self.return_types[0]


# ==========================================
# Declaration AST Nodes
# ==========================================

class DeclNode(ASTNode):
  """Base class for all declaration nodes."""
  pass


class ImportStmtNode(ASTNode):
  """Represents a module import statement (e.g. 'import lib.love2d.graphics as gfx;')."""

  def __init__(self, path: str, alias: Optional[str] = None):
    self.path = path
    self.alias = alias


class ExportSpecifierNode(ASTNode):
  """Represents a specifier in an export manifest block (e.g. 'Image', 'enums.DrawMode', or 'new_image as create_image')."""

  def __init__(self, symbol: str, module_prefix: Optional[str] = None, alias: Optional[str] = None):
    self.symbol = symbol
    self.module_prefix = module_prefix
    self.alias = alias

  @property
  def exported_name(self) -> str:
    return self.alias if self.alias else self.symbol


class ExportStmtNode(ASTNode):
  """Represents an explicit module export manifest block (e.g. 'export { Image, new_image };')."""

  def __init__(self, specifiers: List[ExportSpecifierNode]):
    self.specifiers = specifiers


class ProgramNode(ASTNode):
  """Root node of a Sapphire program, containing top-level declarations, imports, and optional export manifest."""

  def __init__(
      self,
      declarations: List[ASTNode],
      imports: Optional[List[ImportStmtNode]] = None,
      export_block: Optional[ExportStmtNode] = None,
  ):
    self.declarations = declarations
    self.imports = imports or []
    self.export_block = export_block


class StructFieldNode(ASTNode):
  """Represents a single field in a struct declaration (e.g. 'var x: float;')."""

  def __init__(self, is_mutable: bool, name: str, field_type: TypeNode, default_expr: Optional[ASTNode] = None):
    self.is_mutable = is_mutable
    self.name = name
    self.field_type = field_type
    self.default_expr = default_expr


class AnnotationNode(ASTNode):
  """Represents an annotation decorator (e.g. '@extern' or '@export("love.update")')."""

  def __init__(self, name: str, arg: Optional[str] = None):
    self.name = name
    self.arg = arg


class StructDeclNode(DeclNode):
  """Represents a struct declaration."""

  def __init__(self, name: str, parent_names: Optional[Union[str, List[str]]] = None, fields: List[StructFieldNode] = None, is_prototype: bool = False, type_params: Optional[List[str]] = None, parent_name: Optional[str] = None):
    self.name = name
    if parent_names is None:
      self.parent_names = [parent_name] if parent_name else []
    elif isinstance(parent_names, str):
      self.parent_names = [parent_names]
    else:
      self.parent_names = parent_names
    self.fields = fields or []
    self.is_prototype = is_prototype
    self.type_params = type_params or []
    self.parent_names_info: List[Dict[str, Any]] = []

  @property
  def parent_name(self) -> Optional[str]:
    return self.parent_names[0] if self.parent_names else None

  @parent_name.setter
  def parent_name(self, value: Optional[str]) -> None:
    if value is None:
      self.parent_names = []
    else:
      self.parent_names = [value]


class EnumMemberNode(ASTNode):
  """Represents a member/variant in an enum declaration."""

  def __init__(self, name: str, value: Optional[Union[int, str]] = None):
    self.name = name
    self.value = value


class EnumDeclNode(DeclNode):
  """Represents an enum declaration."""

  def __init__(self, name: str, members: List[EnumMemberNode]):
    self.name = name
    self.members = members


class ParameterNode(ASTNode):
  """Represents a parameter in a function signature."""

  def __init__(self, is_mutable: bool, name: str, param_type: Optional[TypeNode] = None, default_expr: Optional[ASTNode] = None):
    self.is_mutable = is_mutable
    self.name = name
    self.param_type = param_type
    self.default_expr = default_expr


class FuncDeclNode(DeclNode):
  """Represents a function declaration, supporting single or multiple return types."""

  def __init__(self, name: str, parameters: List[ParameterNode], return_types: Optional[Union[TypeNode, List[TypeNode]]] = None, body: Optional['BlockNode'] = None, annotations: Optional[List[AnnotationNode]] = None, return_type: Optional[TypeNode] = None, type_params: Optional[List[str]] = None):
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

  @property
  def return_type(self) -> Optional[TypeNode]:
    return self.return_types[0] if self.return_types else None


class ImplMemberNode(ASTNode):
  """Represents a member inside an impl block (e.g. static/const/mutable methods)."""

  def __init__(self, modifier: Optional[str], func_decl: FuncDeclNode):
    self.modifier = modifier  # 'static', 'const', or None
    self.func_decl = func_decl


class ImplBlockNode(DeclNode):
  """Represents a Rust-style implementation block."""

  def __init__(self, struct_name: str, trait_name: Optional[str], members: List[ImplMemberNode], type_params: Optional[List[str]] = None, trait_type_args: Optional[List[TypeNode]] = None, struct_type_args: Optional[List[TypeNode]] = None):
    self.struct_name = struct_name
    self.trait_name = trait_name
    self.members = members
    self.type_params = type_params or []
    self.trait_type_args = trait_type_args or []
    self.struct_type_args = struct_type_args or []


class TraitMemberNode(ASTNode):
  """Represents a method signature inside a trait declaration."""

  def __init__(self, name: str, parameters: List[ParameterNode], return_types: Optional[Union[TypeNode, List[TypeNode]]] = None, modifier: Optional[str] = None, return_type: Optional[TypeNode] = None, annotations: Optional[List[AnnotationNode]] = None, type_params: Optional[List[str]] = None):
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

  @property
  def return_type(self) -> Optional[TypeNode]:
    return self.return_types[0] if self.return_types else None


class TraitDeclNode(DeclNode):
  """Represents a trait declaration."""

  def __init__(self, name: str, members: List[TraitMemberNode], type_params: Optional[List[str]] = None):
    self.name = name
    self.members = members
    self.type_params = type_params or []


# ==========================================
# Statement AST Nodes
# ==========================================

class StmtNode(ASTNode):
  """Base class for all statement nodes."""
  pass


class BlockNode(StmtNode):
  """Represents a block of statements enclosed in curly braces."""

  def __init__(self, statements: List[StmtNode]):
    self.statements = statements


class VarDeclNode(StmtNode):
  """Represents a variable declaration statement (let/var), supporting multi-variable bindings."""

  def __init__(
      self,
      is_mutable: bool,
      names: Optional[Union[str, List[str]]] = None,
      val_types: Optional[Union[TypeNode, List[Optional[TypeNode]]]] = None,
      exprs: Optional[Union[ASTNode, List[ASTNode]]] = None,
      annotations: Optional[List[AnnotationNode]] = None,
      val_type: Optional[TypeNode] = None,
      expr: Optional[ASTNode] = None,
      name: Optional[str] = None,
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
  def val_type(self) -> Optional[TypeNode]:
    return self.val_types[0] if self.val_types else None

  @property
  def expr(self) -> Optional[ASTNode]:
    return self.exprs[0] if self.exprs else None

  def to_dict(self) -> Dict[str, Any]:
    res = super().to_dict()
    res["name"] = self.name
    res["val_type"] = self.val_type.to_dict() if self.val_type else None
    res["expr"] = self.expr.to_dict() if self.expr else None
    return res


class AssignmentNode(StmtNode):
  """Represents an assignment statement (e.g. 'x = 5;' or 'x, y = 10, 20;')."""

  def __init__(self, targets: Union[ASTNode, List[ASTNode]], op: str, exprs: Union[ASTNode, List[ASTNode]], target: Optional[ASTNode] = None, expr: Optional[ASTNode] = None):
    if targets is not None and not (isinstance(targets, list) and len(targets) == 0):
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

  def to_dict(self) -> Dict[str, Any]:
    res = super().to_dict()
    res["target"] = self.target.to_dict() if self.targets else None
    res["expr"] = self.expr.to_dict() if self.exprs else None
    return res


class ExprStmtNode(StmtNode):
  """Represents an expression evaluated as a statement."""

  def __init__(self, expr: ASTNode):
    self.expr = expr


class ReturnNode(StmtNode):
  """Represents a return statement, supporting single or multiple returned expressions."""

  def __init__(self, exprs: Optional[Union[ASTNode, List[ASTNode]]] = None, expr: Optional[ASTNode] = None):
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
  def expr(self) -> Optional[ASTNode]:
    return self.expressions[0] if self.expressions else None

  def to_dict(self) -> Dict[str, Any]:
    res = super().to_dict()
    res["expr"] = self.expr.to_dict() if self.expressions else None
    return res


class YieldNode(StmtNode):
  """Represents a yield statement (e.g. 'yield "Success";')."""

  def __init__(self, expr: ASTNode):
    self.expr = expr


class BreakNode(StmtNode):
  """Represents a break statement (e.g. 'break;')."""
  pass


class ContinueNode(StmtNode):
  """Represents a continue statement (e.g. 'continue;')."""
  pass


class HeaderBindingNode(ASTNode):
  """Represents a variable binding inside control-flow headers (e.g. let x ?= y)."""

  def __init__(self, is_mutable: bool, let_name: str, type_node: Optional[ASTNode], expr: ASTNode, is_unwrap: bool):
    self.is_mutable = is_mutable
    self.let_name = let_name
    self.type_node = type_node
    self.expr = expr
    self.is_unwrap = is_unwrap


class IfNode(StmtNode):
  """Represents an if/else conditional statement, supporting init-statements."""

  def __init__(self, init_binding: Optional[HeaderBindingNode], condition: Optional[ASTNode], then_block: BlockNode, else_block: Optional[Union[BlockNode, 'IfNode']] = None):
    self.init_binding = init_binding
    self.condition = condition
    self.then_block = then_block
    self.else_block = else_block


class WhileNode(StmtNode):
  """Represents a while loop, supporting init-statements."""

  def __init__(self, init_binding: Optional[HeaderBindingNode], condition: Optional[ASTNode], block: BlockNode):
    self.init_binding = init_binding
    self.condition = condition
    self.block = block


class ForNode(StmtNode):
  """Represents a for-in loop."""

  def __init__(
      self,
      is_mutable: bool,
      loop_var: str,
      iterable: ASTNode,
      block: BlockNode,
      key_var: Optional[str] = None,
      val_var: Optional[str] = None,
  ):
    self.is_mutable = is_mutable
    self.loop_var = loop_var
    self.iterable = iterable
    self.block = block
    self.key_var = key_var
    self.val_var = val_var if val_var is not None else loop_var


# ==========================================
# Expression AST Nodes
# ==========================================

class ExprNode(ASTNode):
  """Base class for all expression nodes."""
  pass


class LiteralNode(ExprNode):
  """Represents a literal value (int, float, string, bool, none)."""

  def __init__(self, value: Any, lit_type: str):
    self.value = value
    self.lit_type = lit_type  # 'int', 'float', 'string', 'bool', 'none'


class InterpolatedStringNode(ExprNode):
  """Represents an interpolated string (f"Hello {name}")."""

  def __init__(self, parts: List[ASTNode]):
    self.parts = parts  # Sequence of LiteralNode('string') and ExprNode


class IdentifierNode(ExprNode):
  """Represents an identifier/variable reference."""

  def __init__(self, name: str):
    self.name = name


class BinaryOpNode(ExprNode):
  """Represents a binary operation (e.g. '+', '-', '==', '&&')."""

  def __init__(self, left: ASTNode, op: str, right: ASTNode):
    self.left = left
    self.op = op
    self.right = right


class TernaryExprNode(ExprNode):
  """Represents a ternary conditional expression (e.g. 'condition ? true_expr : false_expr')."""

  def __init__(self, condition: ASTNode, true_expr: ASTNode, false_expr: ASTNode):
    self.condition = condition
    self.true_expr = true_expr
    self.false_expr = false_expr


class UnaryOpNode(ExprNode):
  """Represents a unary operation (e.g. '-', '!')."""

  def __init__(self, op: str, expr: ASTNode):
    self.op = op
    self.expr = expr


class CastExprNode(ExprNode):
  """Represents an explicit type cast expression (e.g. 'x as float')."""

  def __init__(self, expr: ASTNode, target_type: TypeNode):
    self.expr = expr
    self.target_type = target_type


class ArgumentNode(ASTNode):
  """Represents an argument passed to a function call, potentially named (e.g. 'x = 5')."""

  def __init__(self, name: Optional[str], expr: ASTNode):
    self.name = name
    self.expr = expr


class CallNode(ExprNode):
  """Represents a function or method call."""

  def __init__(self, callee: ASTNode, arguments: List[ArgumentNode], type_args: Optional[List[TypeNode]] = None):
    self.callee = callee
    self.arguments = arguments
    self.type_args = type_args or []


class MemberAccessNode(ExprNode):
  """Represents a member or property access (e.g. 'obj.field' or 'obj?.field' or 'obj.__proto__')."""

  def __init__(self, receiver: ASTNode, member: str, is_optional: bool):
    self.receiver = receiver
    self.member = member
    self.is_optional = is_optional


class CloneNode(ExprNode):
  """Represents a clone expression (e.g. 'clone prototype_enemy { self.health = 25; }')."""

  def __init__(self, expr: ASTNode, initializer_block: Optional[List[StmtNode]] = None, arena_expr: Optional[ASTNode] = None):
    self.expr = expr
    self.initializer_block = initializer_block
    self.arena_expr = arena_expr


class LambdaParamNode(ASTNode):
  """Represents a parameter in a lambda expression."""

  def __init__(self, name: str, param_type: Optional[TypeNode] = None):
    self.name = name
    self.param_type = param_type


class LambdaNode(ExprNode):
  """Represents an anonymous lambda function (e.g. '(x: int) -> int { return x; }')."""

  def __init__(self, parameters: List[LambdaParamNode], return_type: Optional[TypeNode], body: Union[BlockNode, ASTNode]):
    self.parameters = parameters
    self.return_type = return_type
    self.body = body  # Can be a BlockNode or a single expression (shorthand)


class ArrayLiteralNode(ExprNode):
  """Represents an array literal (e.g. '[1, 2, 3]')."""

  def __init__(self, elements: List[ASTNode]):
    self.elements = elements


class MapEntryNode(ASTNode):
  """Represents an entry in a map literal (key: value)."""

  def __init__(self, key: ASTNode, value: ASTNode):
    self.key = key
    self.value = value


class MapLiteralNode(ExprNode):
  """Represents a map literal (e.g. '{"a": 1, "b": 2}')."""

  def __init__(self, entries: List[MapEntryNode]):
    self.entries = entries


class IndexExprNode(ExprNode):
  """Represents an array indexing expression (e.g. 'arr[0]')."""

  def __init__(self, array: ASTNode, index: ASTNode):
    self.array = array
    self.index = index


class StructInitializerNode(ExprNode):
  """Represents a curly-brace struct initializer expression (e.g. 'Weapon { damage = 10 }')."""

  def __init__(self, struct_name: str, fields: List[ArgumentNode], arena_expr: Optional[ASTNode] = None, type_args: Optional[List[TypeNode]] = None):
    self.struct_name = struct_name
    self.fields = fields
    self.arena_expr = arena_expr
    self.type_args = type_args or []


class EllipsisPatternNode(ASTNode):
  """Represents the '...' wildcard pattern in a match case."""
  pass


class MatchCaseNode(ASTNode):
  """Represents a single case branch in a match expression."""

  def __init__(self, pattern: ASTNode, body: Union[BlockNode, ASTNode]):
    self.pattern = pattern
    self.body = body  # BlockNode or single ExprNode


class MatchExprNode(ExprNode):
  """Represents a match expression (e.g. 'match status { HttpStatus.Ok -> "Success", ... -> "Error", }')."""

  def __init__(self, subject: ASTNode, cases: List[MatchCaseNode]):
    self.subject = subject
    self.cases = cases
