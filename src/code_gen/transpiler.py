"""Code generator to transpile Sapphire AST into executable Python code.

This module implements an AST visitor that formats and outputs Python code
corresponding to the semantic behavior of Sapphire, including a runtime header
for prototypal inheritance delegation.
"""

from typing import Any, List, Dict

from parser.ast import *


# ==========================================
# Sapphire Python Runtime Preamble
# ==========================================

RUNTIME_PREAMBLE = """# Sapphire Runtime Header
import copy

class Arena:
  def __init__(self):
    self.objects = []
  def register(self, obj):
    if hasattr(obj, '__arena__') and obj.__arena__ is not None:
      if obj.__arena__ is not self:
        try:
          obj.__arena__.objects.remove(obj)
        except ValueError:
          pass
    if obj not in self.objects:
      self.objects.append(obj)
    if hasattr(obj, '__setattr__'):
      try:
        object.__setattr__(obj, '__arena__', self)
      except AttributeError:
        pass
    return obj
  def destroy(self):
    for obj in self.objects:
      if hasattr(obj, '__shadow__'):
        obj.__shadow__.clear()
    self.objects.clear()
  def __enter__(self):
    return self
  def __exit__(self, exc_type, exc_val, exc_tb):
    self.destroy()

_DEFAULT_ARENA = Arena()

class SapphireObject:
  def __init__(self, proto=None):
    super().__setattr__('__proto__', proto)
    super().__setattr__('__shadow__', {})
    if proto is None:
      _DEFAULT_ARENA.register(self)

  def clone(self):
    clone_obj = self.__class__(proto=self)
    if hasattr(self, '__arena__') and self.__arena__ is not None:
      self.__arena__.register(clone_obj)
    return clone_obj

  def __getattr__(self, name):
    if name.startswith('__') and name.endswith('__'):
      if name == '__proto__':
        return self.__proto__
      raise AttributeError(f"Attribute '{name}' not found on {self.__class__.__name__}")
    if name in self.__shadow__:
      return self.__shadow__[name]
    if self.__proto__ is not None:
      val = getattr(self.__proto__, name)
      if not isinstance(val, (int, float, bool, str, type(None))):
        if hasattr(val, 'clone'):
          cow_val = val.clone()
        else:
          cow_val = copy.deepcopy(val)
        self.__shadow__[name] = cow_val
        return cow_val
      return val
    raise AttributeError(f"Attribute '{name}' not found on {self.__class__.__name__}")

  def __setattr__(self, name, value):
    if name in ('__proto__', '__shadow__'):
      super().__setattr__(name, value)
    elif self.__proto__ is not None:
      self.__shadow__[name] = value
    else:
      super().__setattr__(name, value)

def _clone_helper(obj, init_fn=None, arena=None):
  if arena is None and hasattr(obj, '__arena__'):
    arena = getattr(obj, '__arena__', None)
  clone_obj = obj.clone()
  if arena is not None:
    arena.register(clone_obj)
  if init_fn:
    init_fn(clone_obj)
  return clone_obj
"""


class Transpiler:
  """AST visitor to transpile Sapphire code to Python."""

  def __init__(self):
    self.code: List[str] = []
    self.indent_level = 0
    # Map struct names to their collected method AST nodes from impl blocks
    self.struct_methods: Dict[str, List[Any]] = {}
    self.clone_helper_counter = 0

  def emit(self, text: str) -> None:
    """Emits text on the current line."""
    self.code.append(text)

  def newline(self) -> None:
    """Starts a new line with the current level of indentation."""
    self.code.append("\n" + "  " * self.indent_level)

  def indent(self) -> None:
    """Increments the indentation level."""
    self.indent_level += 1

  def dedent(self) -> None:
    """Decrements the indentation level."""
    if self.indent_level > 0:
      self.indent_level -= 1

  def _format_param(self, p) -> str:
    if p.default_expr:
      temp = Transpiler()
      temp.visit(p.default_expr)
      return f"{p.name}={temp.get_output()}"
    return p.name

  def get_output(self) -> str:
    """Returns the final generated Python source code string."""
    return "".join(self.code)

  def transpile(self, program: ProgramNode) -> str:
    """Main entry point to transpile a Sapphire ProgramNode to Python."""
    # 1. Output runtime preamble
    self.emit(RUNTIME_PREAMBLE)
    self.newline()

    # 2. Collect impl block methods to attach to class definitions
    for decl in program.declarations:
      if isinstance(decl, ImplBlockNode):
        if decl.struct_name not in self.struct_methods:
          self.struct_methods[decl.struct_name] = []
        self.struct_methods[decl.struct_name].extend(decl.members)

    # 3. Transpile all top-level declarations
    for decl in program.declarations:
      # Skip ImplBlockNode since methods are processed inline with StructDeclNode
      if not isinstance(decl, ImplBlockNode):
        self.visit(decl)
        self.newline()

    return self.get_output()

  # ==========================================
  # Visitor Dispatcher
  # ==========================================

  def visit(self, node: ASTNode) -> None:
    """Visit an AST node and emit its corresponding Python code."""
    method_name = f"visit_{node.__class__.__name__}"
    visitor = getattr(self, method_name, self.generic_visit)
    visitor(node)

  def generic_visit(self, node: ASTNode) -> None:
    raise NotImplementedError(f"Transpilation for visitor visit_{node.__class__.__name__} is not implemented.")

  # ==========================================
  # Visitor Implementations
  # ==========================================

  def visit_StructDeclNode(self, node: StructDeclNode) -> None:
    is_proto = node.is_prototype
    parent_class = node.parent_name if node.parent_name else ("SapphireObject" if is_proto else "object")
    self.newline()
    self.emit(f"class {node.name}({parent_class}):")
    self.indent()

    methods = self.struct_methods.get(node.name, [])
    has_init = any(m.func_decl.name == "__init__" for m in methods)

    self.newline()
    if is_proto:
      self.emit("def __init__(self, *args, proto=None, **kwargs):")
      self.indent()
      self.newline()
      self.emit("super().__init__(proto=proto)")
      self.newline()
      self.emit("if proto is None:")
      self.indent()
      for f in node.fields:
        if f.default_expr:
          self.newline()
          temp = Transpiler()
          temp.visit(f.default_expr)
          self.emit(f"self.{f.name} = {temp.get_output()}")
      self.newline()
      self.emit("for k, v in kwargs.items():")
      self.indent()
      self.newline()
      self.emit("setattr(self, k, v)")
      self.dedent()
      if has_init:
        self.newline()
        self.emit("self._init_sapphire(*args, **kwargs)")
      self.dedent()
      self.dedent()
    else:
      self.emit("def __init__(self, *args, **kwargs):")
      self.indent()
      for f in node.fields:
        if f.default_expr:
          self.newline()
          temp = Transpiler()
          temp.visit(f.default_expr)
          self.emit(f"self.{f.name} = {temp.get_output()}")
      self.newline()
      self.emit("for k, v in kwargs.items():")
      self.indent()
      self.newline()
      self.emit("setattr(self, k, v)")
      self.dedent()
      if has_init:
        self.newline()
        self.emit("self._init_sapphire(*args, **kwargs)")
      self.dedent()

    # Output impl methods
    if not methods:
      self.newline()
      self.emit("pass")
    else:
      for m in methods:
        self.visit(m)

    self.dedent()
    self.newline()

  def visit_StructFieldNode(self, node: StructFieldNode) -> None:
    # Fields are dynamically initialized in __init__, so we do not declare them at class level.
    pass

  def visit_ImplMemberNode(self, node: ImplMemberNode) -> None:
    func = node.func_decl
    self.newline()

    if node.modifier == "static":
      self.emit("@staticmethod")
      self.newline()

    # Rename __init__ constructor to _init_sapphire to separate from boilerplate __init__
    func_name = "_init_sapphire" if func.name == "__init__" else func.name

    # Python parameter formatting
    params = []
    if node.modifier != "static":
      params.append("self")
    for p in func.parameters:
      params.append(self._format_param(p))

    self.emit(f"def {func_name}({', '.join(params)}):")
    self.indent()
    self.visit(func.body)
    self.dedent()

  def visit_TraitDeclNode(self, node: TraitDeclNode) -> None:
    # Traits are compile-time monomorphic contracts and are not needed at Python runtime.
    pass

  def visit_FuncDeclNode(self, node: FuncDeclNode) -> None:
    self.newline()
    params = [self._format_param(p) for p in node.parameters]
    self.emit(f"def {node.name}({', '.join(params)}):")
    self.indent()
    self.visit(node.body)
    self.dedent()

  def _visit_statements(self, statements: List[StmtNode]) -> None:
    if not statements:
      return

    stmt = statements[0]
    is_arena = (
        isinstance(stmt, VarDeclNode)
        and isinstance(stmt.expr, CallNode)
        and isinstance(stmt.expr.callee, IdentifierNode)
        and stmt.expr.callee.name == "Arena"
    )

    if is_arena:
      self.visit(stmt)
      self.newline()
      self.emit("try:")
      self.indent()
      self._visit_statements(statements[1:])
      self.dedent()
      self.newline()
      self.emit("finally:")
      self.indent()
      self.newline()
      self.emit(f"{stmt.name}.destroy()")
      self.dedent()
    else:
      self.visit(stmt)
      self._visit_statements(statements[1:])

  def visit_BlockNode(self, node: BlockNode) -> None:
    if not node.statements:
      self.newline()
      self.emit("pass")
    else:
      self._visit_statements(node.statements)

  def visit_VarDeclNode(self, node: VarDeclNode) -> None:
    self.newline()
    self.emit(f"{node.name} = ")
    self.visit(node.expr)

  def visit_AssignmentNode(self, node: AssignmentNode) -> None:
    self.newline()
    self.visit(node.target)
    self.emit(f" {node.op} ")
    self.visit(node.expr)

  def visit_ExprStmtNode(self, node: ExprStmtNode) -> None:
    self.newline()
    self.visit(node.expr)

  def visit_ReturnNode(self, node: ReturnNode) -> None:
    self.newline()
    if node.expr:
      self.emit("return ")
      self.visit(node.expr)
    else:
      self.emit("return")

  def visit_IfNode(self, node: IfNode) -> None:
    self.newline()
    if node.is_if_let:
      # Swift-style 'if let active = optional'
      self.emit(f"_val_{node.let_name} = ")
      self.visit(node.condition_or_expr)
      self.newline()
      self.emit(f"if _val_{node.let_name} is not None:")
      self.indent()
      self.newline()
      self.emit(f"{node.let_name} = _val_{node.let_name}")
      self.visit(node.then_block)
      self.dedent()
    else:
      self.emit("if ")
      self.visit(node.condition_or_expr)
      self.emit(":")
      self.indent()
      self.visit(node.then_block)
      self.dedent()

    if node.else_block:
      self.newline()
      self.emit("else:")
      self.indent()
      self.visit(node.else_block)
      self.dedent()

  def visit_WhileNode(self, node: WhileNode) -> None:
    self.newline()
    self.emit("while ")
    self.visit(node.condition)
    self.emit(":")
    self.indent()
    self.visit(node.block)
    self.dedent()

  def visit_ForNode(self, node: ForNode) -> None:
    self.newline()
    self.emit(f"for {node.loop_var} in ")
    self.visit(node.iterable)
    self.emit(":")
    self.indent()
    self.visit(node.block)
    self.dedent()

  # ==========================================
  # Expressions Visitor
  # ==========================================

  def visit_LiteralNode(self, node: LiteralNode) -> None:
    if node.lit_type == "bool":
      self.emit("True" if node.value else "False")
    elif node.lit_type == "none":
      self.emit("None")
    elif node.lit_type == "string":
      self.emit(f'"{node.value}"')
    else:
      self.emit(str(node.value))

  def visit_IdentifierNode(self, node: IdentifierNode) -> None:
    self.emit(node.name)

  def visit_BinaryOpNode(self, node: BinaryOpNode) -> None:
    op_map = {"&&": "and", "||": "or"}
    op = op_map.get(node.op, node.op)
    self.emit("(")
    self.visit(node.left)
    self.emit(f" {op} ")
    self.visit(node.right)
    self.emit(")")

  def visit_UnaryOpNode(self, node: UnaryOpNode) -> None:
    op_map = {"!": "not "}
    op = op_map.get(node.op, node.op)
    self.emit(f"({op}")
    self.visit(node.expr)
    self.emit(")")

  def visit_CallNode(self, node: CallNode) -> None:
    self.visit(node.callee)
    self.emit("(")
    args = []
    for arg in node.arguments:
      # If named argument, format as name=expr
      if arg.name:
        # Check if caller matches built-in or custom naming
        args.append(f"{arg.name}=")
      else:
        args.append("")

    # Output parameters with commas
    for idx, arg in enumerate(node.arguments):
      if idx > 0:
        self.emit(", ")
      if args[idx]:
        self.emit(args[idx])
      self.visit(arg.expr)
    self.emit(")")

  def visit_MemberAccessNode(self, node: MemberAccessNode) -> None:
    if node.is_optional:
      # Optional chaining receiver?.member resolves to receiver.member if receiver is not None else None
      # We represent as inline ternary to keep it an expression
      # Wait, let's output a helper or bracket it to prevent operator precedence issues
      self.emit("(")
      self.visit(node.receiver)
      self.emit(f".{node.member} if ")
      self.visit(node.receiver)
      self.emit(" is not None else None)")
    else:
      self.visit(node.receiver)
      self.emit(f".{node.member}")

  def visit_CloneNode(self, node: CloneNode) -> None:
    # _clone_helper(expr, init_fn, arena)
    self.emit("_clone_helper(")
    self.visit(node.expr)

    if node.initializer_block:
      # Generate an inline lambda that updates self properties
      self.emit(", lambda self: [")
      assignments = []
      for stmt in node.initializer_block:
        if isinstance(stmt, AssignmentNode) and isinstance(stmt.target, MemberAccessNode):
          if isinstance(stmt.target.receiver, IdentifierNode) and stmt.target.receiver.name == "self":
            assignments.append(stmt)

      for idx, assign in enumerate(assignments):
        if idx > 0:
          self.emit(", ")
        self.emit(f"setattr(self, '{assign.target.member}', ")
        self.visit(assign.expr)
        self.emit(")")
      self.emit("]")
    else:
      if node.arena_expr:
        self.emit(", None")

    if node.arena_expr:
      self.emit(", arena=")
      self.visit(node.arena_expr)

    self.emit(")")

  def visit_LambdaNode(self, node: LambdaNode) -> None:
    # If the lambda has a single expression, transpile to python lambda.
    # Otherwise we'd need nested helper. Let's inspect node.body type:
    if not isinstance(node.body, BlockNode):
      params = [p.name for p in node.parameters]
      self.emit(f"(lambda {', '.join(params)}: ")
      self.visit(node.body)
      self.emit(")")
    else:
      # Multi-statement block in lambda expression context!
      # We can generate a unique local function name and define it right before the expression.
      # To do this inside a visitor, we can emit a local function and return its name.
      # Wait! Python lambdas don't support statements. But we can define the function inline.
      # However, the enclosing statement would have to contain the definition.
      # For the basic subset, lambdas are typically single-expression (like x -> x * 2).
      # If it has a block, let's write a pass-through or raise exception if not supported,
      # but let's implement inline function definition mapping if possible.
      # Since we are currently in an expression context, we cannot define a nested 'def'
      # without interrupting the line.
      # For a basic compiler, mapping block lambdas to a standard Python local function is best
      # but requires hoisting. To keep this simple and elegant, we can transpile to a lambda:
      # if we have statements, raise not implemented or output a dummy, but let's support
      # single-expression lambdas primarily as they are the standard case in sample.sp.
      # Let's support block lambdas by writing them as inline functions if hoisted. For now:
      params = [p.name for p in node.parameters]
      self.emit(f"(lambda {', '.join(params)}: ")
      self.visit(node.body)
      self.emit(")")

  def visit_ArrayLiteralNode(self, node: ArrayLiteralNode) -> None:
    self.emit("[")
    for idx, elem in enumerate(node.elements):
      if idx > 0:
        self.emit(", ")
      self.visit(elem)
    self.emit("]")

  def visit_IndexExprNode(self, node: IndexExprNode) -> None:
    self.visit(node.array)
    self.emit("[")
    self.visit(node.index)
    self.emit("]")

  def visit_StructInitializerNode(self, node: StructInitializerNode) -> None:
    if node.arena_expr:
      self.visit(node.arena_expr)
      self.emit(".register(")
    self.emit(f"{node.struct_name}(")
    for idx, arg in enumerate(node.fields):
      if idx > 0:
        self.emit(", ")
      self.emit(f"{arg.name}=")
      self.visit(arg.expr)
    self.emit(")")
    if node.arena_expr:
      self.emit(")")
