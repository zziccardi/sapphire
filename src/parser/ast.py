"""Sapphire Abstract Syntax Tree (AST) node definitions.

All AST node classes defined here inherit from a common ASTNode base class.
They are used to represent the syntactic structure of Sapphire programs
in a structured, easy-to-analyze form.
"""

from typing import Any, Dict, List, Optional, Union


class ASTNode:
  """Base class for all AST nodes."""

  def to_dict(self) -> Dict[str, Any]:
    """Returns a dictionary representation of the AST node for serialization/debugging."""
    result = {"node_type": self.__class__.__name__}
    for key, value in self.__dict__.items():
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
  """Represents a basic type (e.g. 'int', 'float', 'bool', or a struct name)."""

  def __init__(self, name: str):
    self.name = name


class OptionalTypeNode(TypeNode):
  """Represents an optional type wrapper (e.g. 'int?')."""

  def __init__(self, base_type: TypeNode):
    self.base_type = base_type


class FunctionTypeNode(TypeNode):
  """Represents a function type signature (e.g. '(int, int) -> float')."""

  def __init__(self, param_types: List[TypeNode], return_type: TypeNode):
    self.param_types = param_types
    self.return_type = return_type


# ==========================================
# Declaration AST Nodes
# ==========================================

class DeclNode(ASTNode):
  """Base class for all declaration nodes."""
  pass


class ProgramNode(ASTNode):
  """Root node of a Sapphire program, containing top-level declarations."""

  def __init__(self, declarations: List[DeclNode]):
    self.declarations = declarations


class StructFieldNode(ASTNode):
  """Represents a single field in a struct declaration (e.g. 'var x: float;')."""

  def __init__(self, is_mutable: bool, name: str, field_type: TypeNode, default_expr: Optional[ASTNode] = None):
    self.is_mutable = is_mutable
    self.name = name
    self.field_type = field_type
    self.default_expr = default_expr


class StructDeclNode(DeclNode):
  """Represents a struct declaration."""

  def __init__(self, name: str, parent_name: Optional[str], fields: List[StructFieldNode]):
    self.name = name
    self.parent_name = parent_name
    self.fields = fields


class ParameterNode(ASTNode):
  """Represents a parameter in a function signature."""

  def __init__(self, is_mutable: bool, name: str, param_type: TypeNode, default_expr: Optional[ASTNode] = None):
    self.is_mutable = is_mutable
    self.name = name
    self.param_type = param_type
    self.default_expr = default_expr


class FuncDeclNode(DeclNode):
  """Represents a function declaration."""

  def __init__(self, name: str, parameters: List[ParameterNode], return_type: Optional[TypeNode], body: 'BlockNode'):
    self.name = name
    self.parameters = parameters
    self.return_type = return_type
    self.body = body


class ImplMemberNode(ASTNode):
  """Represents a member inside an impl block (e.g. static/const/mutable methods)."""

  def __init__(self, modifier: Optional[str], func_decl: FuncDeclNode):
    self.modifier = modifier  # 'static', 'const', or None
    self.func_decl = func_decl


class ImplBlockNode(DeclNode):
  """Represents a Rust-style implementation block."""

  def __init__(self, struct_name: str, trait_name: Optional[str], members: List[ImplMemberNode]):
    self.struct_name = struct_name
    self.trait_name = trait_name
    self.members = members


class TraitMemberNode(ASTNode):
  """Represents a method signature inside a trait declaration."""

  def __init__(self, name: str, parameters: List[ParameterNode], return_type: Optional[TypeNode]):
    self.name = name
    self.parameters = parameters
    self.return_type = return_type


class TraitDeclNode(DeclNode):
  """Represents a trait declaration."""

  def __init__(self, name: str, members: List[TraitMemberNode]):
    self.name = name
    self.members = members


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
  """Represents a variable declaration statement (let/var)."""

  def __init__(self, is_mutable: bool, name: str, val_type: Optional[TypeNode], expr: ASTNode):
    self.is_mutable = is_mutable
    self.name = name
    self.val_type = val_type
    self.expr = expr


class AssignmentNode(StmtNode):
  """Represents an assignment statement (e.g. 'x = 5;' or 'y += 1;')."""

  def __init__(self, target: ASTNode, op: str, expr: ASTNode):
    self.target = target
    self.op = op  # '=', '+=', '-=', etc.
    self.expr = expr


class ExprStmtNode(StmtNode):
  """Represents an expression evaluated as a statement."""

  def __init__(self, expr: ASTNode):
    self.expr = expr


class ReturnNode(StmtNode):
  """Represents a return statement."""

  def __init__(self, expr: Optional[ASTNode]):
    self.expr = expr


class IfNode(StmtNode):
  """Represents an if/else conditional statement, supporting swift-style 'if let'."""

  def __init__(self, condition_or_expr: ASTNode, then_block: BlockNode, else_block: Optional[Union[BlockNode, 'IfNode']] = None, is_if_let: bool = False, let_name: Optional[str] = None):
    self.condition_or_expr = condition_or_expr
    self.then_block = then_block
    self.else_block = else_block
    self.is_if_let = is_if_let
    self.let_name = let_name


class WhileNode(StmtNode):
  """Represents a while loop."""

  def __init__(self, condition: ASTNode, block: BlockNode):
    self.condition = condition
    self.block = block


class ForNode(StmtNode):
  """Represents a for-in loop."""

  def __init__(self, is_mutable: bool, loop_var: str, iterable: ASTNode, block: BlockNode):
    self.is_mutable = is_mutable
    self.loop_var = loop_var
    self.iterable = iterable
    self.block = block


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


class UnaryOpNode(ExprNode):
  """Represents a unary operation (e.g. '-', '!')."""

  def __init__(self, op: str, expr: ASTNode):
    self.op = op
    self.expr = expr


class ArgumentNode(ASTNode):
  """Represents an argument passed to a function call, potentially named (e.g. 'x = 5')."""

  def __init__(self, name: Optional[str], expr: ASTNode):
    self.name = name
    self.expr = expr


class CallNode(ExprNode):
  """Represents a function or method call."""

  def __init__(self, callee: ASTNode, arguments: List[ArgumentNode]):
    self.callee = callee
    self.arguments = arguments


class MemberAccessNode(ExprNode):
  """Represents a member or property access (e.g. 'obj.field' or 'obj?.field' or 'obj.__proto__')."""

  def __init__(self, receiver: ASTNode, member: str, is_optional: bool):
    self.receiver = receiver
    self.member = member
    self.is_optional = is_optional


class CloneNode(ExprNode):
  """Represents a clone expression (e.g. 'clone prototype_enemy { self.health = 25; }')."""

  def __init__(self, expr: ASTNode, initializer_block: Optional[List[StmtNode]] = None):
    self.expr = expr
    self.initializer_block = initializer_block


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


class IndexExprNode(ExprNode):
  """Represents an array indexing expression (e.g. 'arr[0]')."""

  def __init__(self, array: ASTNode, index: ASTNode):
    self.array = array
    self.index = index
