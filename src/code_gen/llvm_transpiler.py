"""Experimental LLVM IR transpiler for Sapphire ASTs."""

from llvmlite import ir


class LLVMTranspiler:
  """Transpiles a type-checked Sapphire AST into LLVM IR."""

  def __init__(self, module_name="sapphire_module"):
    # 1. Initialize the LLVM module
    self.module = ir.Module(name=module_name)
    self.module.triple = "x86_64-pc-linux-gnu"  # Default target triple

    # 2. Type-mapping cache
    self.struct_types = {}  # Maps Sapphire struct names to LLVM struct types
    self.named_values = {}  # Maps variable names in scope to LLVM IR Values
    self.builder = None     # Current IRBuilder instance

    # Primitive type mapping
    self.int_type = ir.IntType(64)
    self.float_type = ir.DoubleType()
    self.bool_type = ir.IntType(1)
    self.void_type = ir.VoidType()

  def get_llvm_type(self, type_node):
    """Maps Sapphire AST type nodes to LLVM IR types."""

    type_name = getattr(type_node, "name", str(type_node))

    if type_name == "int":
      return self.int_type
    elif type_name == "float":
      return self.float_type
    elif type_name == "bool":
      return self.bool_type
    elif type_name == "void":
      return self.void_type
    elif type_name in self.struct_types:
      # Struct types are passed by pointer in LLVM IR
      return self.struct_types[type_name].as_pointer()

    raise NotImplementedError(f"Unsupported type: {type_name}")

  # -------------------------------------------------------------------------
  # AST visitor dispatcher
  # -------------------------------------------------------------------------

  def visit(self, node):
    method_name = f"visit_{type(node).__name__}"
    visitor = getattr(self, method_name, self.generic_visit)
    return visitor(node)

  def generic_visit(self, node):
    raise NotImplementedError(f"No visit_{type(node).__name__} method defined.")

  # -------------------------------------------------------------------------
  # Top-level declarations
  # -------------------------------------------------------------------------

  def visit_ProgramNode(self, node):
    for declaration in node.declarations:
      self.visit(declaration)
    return str(self.module)

  def visit_StructDeclNode(self, node):
    """Lowers a Sapphire struct into a flat LLVM aggregate type:

    %struct.Player = type { i64, double }
    """

    struct_name = node.name
    llvm_struct = self.module.context.get_identified_type(
        f"struct.{struct_name}")

    field_types = []
    for field in node.fields:
      field_types.append(self.get_llvm_type(field.type_node))

    llvm_struct.set_body(*field_types)
    self.struct_types[struct_name] = llvm_struct

    return llvm_struct

  def visit_FuncDeclNode(self, node):
    """Lowers a Sapphire function declaration into an LLVM function:

    define i64 @add(i64 %a, i64 %b) { ... }
    """

    return_type = self.get_llvm_type(node.return_type)
    param_types = [self.get_llvm_type(p.type_node) for p in node.params]

    func_type = ir.FunctionType(return_type, param_types)
    func = ir.Function(self.module, func_type, name=node.name)

    # Name parameters and add them to the local scope
    self.named_values.clear()
    for i, param in enumerate(node.params):
      func.args[i].name = param.name
      self.named_values[param.name] = func.args[i]

    # Create the entry basic block and set the builder
    block = func.append_basic_block(name="entry")
    self.builder = ir.IRBuilder(block)

    # Visit function body statements
    for stmt in node.body:
      self.visit(stmt)

    return func

  # -------------------------------------------------------------------------
  # Statements & expressions
  # -------------------------------------------------------------------------

  def visit_ReturnNode(self, node):
    if node.value is None:
      return self.builder.ret_void()
    ret_val = self.visit(node.value)
    return self.builder.ret(ret_val)

  def visit_LiteralNode(self, node):
    if isinstance(node.value, int):
      return ir.Constant(self.int_type, node.value)
    elif isinstance(node.value, float):
      return ir.Constant(self.float_type, node.value)
    elif isinstance(node.value, bool):
      return ir.Constant(self.bool_type, int(node.value))

    raise NotImplementedError(f"Unsupported literal type: {type(node.value)}")

  def visit_IdentifierNode(self, node):
    if node.name in self.named_values:
      return self.named_values[node.name]
    raise NameError(f"Unknown symbol: {node.name}")

  def visit_BinaryOpNode(self, node):
    """Lowers binary arithmetic operations to LLVM instructions."""

    lhs = self.visit(node.left)
    rhs = self.visit(node.right)

    if node.op == "+":
      return self.builder.add(lhs, rhs, name="addtmp")
    elif node.op == "-":
      return self.builder.sub(lhs, rhs, name="subtmp")
    elif node.op == "*":
      return self.builder.mul(lhs, rhs, name="multmp")
    elif node.op == "/":
      return self.builder.sdiv(lhs, rhs, name="divtmp")

    raise NotImplementedError(f"Unsupported binary operator: {node.op}")
