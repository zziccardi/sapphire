"""Experimental LLVM IR code-generation backend for Sapphire ASTs.

Current state:
  This module provides an experimental `LLVMTranspiler` that lowers type-checked
  Sapphire AST nodes into LLVM IR using `llvmlite`. It supports top-level
  declarations, functions, primitive types (`int` -> `i64`, `float` -> `double`,
  `bool` -> `i1`, `void`), stack-allocated local variables (`alloca` / `load` /
  `store`), integer/float arithmetic with implicit type promotion, basic block
  termination safeguards, and struct aggregate types.

  High-level features requiring dynamic runtime libraries (e.g. pattern
  matching, traits, lambdas) are currently unimplemented and gracefully raise
  `NotImplementedError`.

Key benefits of outputting to LLVM IR:
  1. Ahead-of-time (AOT) native compilation:
    Allows compiling Sapphire programs directly into optimized machine code and
    native standalone executables (via `clang` or `llc`), bypassing interpreter
    overhead.
  2. Just-in-time (JIT) execution:
    Enables high-performance in-memory execution via `llvmlite.binding` or
    LLVM's MCJIT/ORCJIT engine.
  3. Production-grade LLVM optimization passes:
    Unlocks LLVM's optimizer suite (e.g. `mem2reg` for promoting stack allocas
    to SSA registers, auto-vectorization, dead-code elimination, and loop
    unrolling).
  4. Hardware portability & C interop:
    Targets any architecture supported by LLVM (x86_64, ARM64/Apple Silicon,
    RISC-V, WebAssembly) and enables low-overhead C ABI interoperability.

Sample generated LLVM IR:
  Given Sapphire source code:
    ```
    func add(a: int, b: int): int {
      return a + b;
    }
    ```

  Generated LLVM IR output:
    ```
    ; ModuleID = "sapphire_module"
    target triple = "arm64-apple-macosx14.0.0"

    define i64 @"add"(i64 %"a", i64 %"b") {
    entry:
      %"a.1" = alloca i64
      store i64 %"a", i64* %"a.1"
      %"b.1" = alloca i64
      store i64 %"b", i64* %"b.1"
      %"a_val" = load i64, i64* %"a.1"
      %"b_val" = load i64, i64* %"b.1"
      %"addtmp" = add i64 %"a_val", %"b_val"
      ret i64 %"addtmp"
    }
    ```
"""

from typing import Any, Dict, Optional

from src.code_gen.base_transpiler import BaseTranspiler
from src.parser.ast import (
    ASTNode,
    AssignmentNode,
    BasicTypeNode,
    BinaryOpNode,
    BlockNode,
    ExprStmtNode,
    FuncDeclNode,
    IdentifierNode,
    LiteralNode,
    ProgramNode,
    ReturnNode,
    StructDeclNode,
    VarDeclNode,
)


from llvmlite import ir
try:
  import llvmlite.binding as llvm
  llvm.initialize_native_target()
  llvm.initialize_native_asmprinter()
  DEFAULT_TRIPLE = llvm.get_default_triple()
except Exception:  # pragma: no cover
  DEFAULT_TRIPLE = "x86_64-pc-linux-gnu"


from src.code_gen.transpiler_registry import TranspilerRegistry


@TranspilerRegistry.register(aliases=["llvm", "llvmir", "ir"], display_name="LLVM IR", default_extension=".ll")
class LLVMTranspiler(BaseTranspiler):

  """Transpiles a type-checked Sapphire AST into LLVM IR."""

  def __init__(self, module_name="sapphire_module", target_triple=None):
    # 1. Initialize the LLVM module
    self.module = ir.Module(name=module_name)
    self.module.triple = target_triple or DEFAULT_TRIPLE

    # 2. Type-mapping & symbol table cache
    self.struct_types: Dict[str, ir.Type] = {}
    self.named_values: Dict[str, Any] = {}
    self.builder: Optional[ir.IRBuilder] = None
    self.current_function: Optional[ir.Function] = None

    # Primitive type mapping
    self.int_type = ir.IntType(64)
    self.float_type = ir.DoubleType()
    self.bool_type = ir.IntType(1)
    self.void_type = ir.VoidType()

  # -------------------------------------------------------------------------
  # Core BaseTranspiler interface implementation
  # -------------------------------------------------------------------------

  def transpile(self, program: ProgramNode) -> str:
    """Transpiles a Sapphire ProgramNode into LLVM IR string representation."""
    return self.visit(program)

  def emit(self, text: str) -> None:
    pass

  def newline(self) -> None:
    pass

  def indent(self) -> None:
    pass

  def dedent(self) -> None:
    pass

  def get_output(self) -> str:
    return str(self.module)

  # -------------------------------------------------------------------------
  # AST visitor dispatcher
  # -------------------------------------------------------------------------

  def visit(self, node: ASTNode) -> Any:
    method_name = f"visit_{type(node).__name__}"
    visitor = getattr(self, method_name, self.generic_visit)
    return visitor(node)

  def generic_visit(self, node: ASTNode) -> Any:
    raise NotImplementedError(
        f"AST node '{type(node).__name__}' is not supported by the experimental LLVM transpiler backend yet."
    )

  # -------------------------------------------------------------------------
  # Helper utilities
  # -------------------------------------------------------------------------

  def get_llvm_type(self, type_node: Any) -> ir.Type:
    """Maps Sapphire AST type nodes to LLVM IR types."""
    if type_node is None:
      return self.void_type

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
      return self.struct_types[type_name].as_pointer()

    raise NotImplementedError(f"Unsupported type: {type_name}")

  def _match_type(self, val: ir.Value, target_type: ir.Type) -> ir.Value:
    """Helper to convert values when types differ (e.g. sitofp for int->float)."""
    if val.type == target_type:
      return val
    if val.type == self.int_type and target_type == self.float_type:
      return self.builder.sitofp(val, self.float_type, name="sitofp_tmp")
    return val

  # -------------------------------------------------------------------------
  # Top-level declarations
  # -------------------------------------------------------------------------

  def visit_ProgramNode(self, node: ProgramNode) -> str:
    for declaration in node.declarations:
      self.visit(declaration)
    return str(self.module)

  def visit_StructDeclNode(self, node: StructDeclNode) -> ir.Type:
    """Lowers a Sapphire struct into a flat LLVM aggregate type."""
    struct_name = node.name
    llvm_struct = self.module.context.get_identified_type(f"struct.{struct_name}")

    field_types = []
    for field in node.fields:
      f_type = getattr(field, "field_type", getattr(field, "type_node", None))
      field_types.append(self.get_llvm_type(f_type))

    llvm_struct.set_body(*field_types)
    self.struct_types[struct_name] = llvm_struct
    return llvm_struct

  def visit_FuncDeclNode(self, node: FuncDeclNode) -> ir.Function:
    """Lowers a Sapphire function declaration into an LLVM function."""
    return_type = self.get_llvm_type(node.return_type)
    params = getattr(node, "parameters", getattr(node, "params", []))
    param_types = [
        self.get_llvm_type(getattr(p, "param_type", getattr(p, "type_node", None)))
        for p in params
    ]

    func_type = ir.FunctionType(return_type, param_types)
    func = ir.Function(self.module, func_type, name=node.name)
    self.current_function = func

    # Clear symbol table for local function scope
    self.named_values.clear()

    # Create the entry basic block and IRBuilder
    entry_block = func.append_basic_block(name="entry")
    self.builder = ir.IRBuilder(entry_block)

    # Allocate stack slots (`alloca`) for parameters and store arguments
    for i, param in enumerate(params):
      func.args[i].name = param.name
      alloca = self.builder.alloca(param_types[i], name=param.name)
      self.builder.store(func.args[i], alloca)
      self.named_values[param.name] = alloca

    # Visit function body block
    if node.body:
      self.visit(node.body)

    # Guarantee basic block termination if not already terminated
    if not self.builder.block.is_terminated:
      if return_type == self.void_type:
        self.builder.ret_void()
      elif return_type == self.int_type:
        self.builder.ret(ir.Constant(self.int_type, 0))
      elif return_type == self.float_type:
        self.builder.ret(ir.Constant(self.float_type, 0.0))
      elif return_type == self.bool_type:
        self.builder.ret(ir.Constant(self.bool_type, 0))
      else:
        self.builder.ret_void()

    return func

  # -------------------------------------------------------------------------
  # Statements
  # -------------------------------------------------------------------------

  def visit_BlockNode(self, node: BlockNode) -> Any:
    last_val = None
    for stmt in node.statements:
      if self.builder and self.builder.block.is_terminated:
        break
      last_val = self.visit(stmt)
    return last_val

  def visit_ExprStmtNode(self, node: ExprStmtNode) -> Any:
    return self.visit(node.expr)

  def visit_VarDeclNode(self, node: VarDeclNode) -> ir.AllocaInstr:
    """Allocates a stack slot for a local variable and stores its initial value."""
    val_type = getattr(node, "val_type", None)
    if val_type is None and hasattr(node, "val_types") and node.val_types:
      val_type = node.val_types[0]
    if val_type is None:
      val_type = getattr(node, "type_node", None)

    name = getattr(node, "name", node.names[0] if hasattr(node, "names") and node.names else "")
    var_type = self.get_llvm_type(val_type) if val_type else self.int_type
    alloca = self.builder.alloca(var_type, name=name)

    init_expr = getattr(node, "expr", getattr(node, "initializer", None))
    if init_expr:
      init_val = self.visit(init_expr)
      init_val = self._match_type(init_val, var_type)
      self.builder.store(init_val, alloca)

    self.named_values[name] = alloca
    return alloca

  def visit_AssignmentNode(self, node: AssignmentNode) -> ir.Value:
    """Updates the value stored in a variable's stack slot (`alloca`)."""
    target = getattr(node, "target", node.targets[0] if hasattr(node, "targets") and node.targets else None)
    val_expr = getattr(node, "expr", getattr(node, "value", None))

    if isinstance(target, IdentifierNode):
      if target.name not in self.named_values:
        raise NameError(f"Undefined variable: {target.name}")
      ptr = self.named_values[target.name]
      val = self.visit(val_expr)
      val = self._match_type(val, ptr.type.pointee)
      self.builder.store(val, ptr)
      return val

    raise NotImplementedError(f"Assignment to {type(target).__name__} is not supported yet.")

  def visit_ReturnNode(self, node: ReturnNode) -> ir.Instruction:
    ret_expr = getattr(node, "expr", getattr(node, "value", None))
    if ret_expr is None:
      return self.builder.ret_void()

    ret_val = self.visit(ret_expr)
    if self.current_function and self.current_function.type.pointee.return_type != self.void_type:
      ret_val = self._match_type(ret_val, self.current_function.type.pointee.return_type)
    return self.builder.ret(ret_val)

  # -------------------------------------------------------------------------
  # Expressions
  # -------------------------------------------------------------------------

  def visit_LiteralNode(self, node: LiteralNode) -> ir.Constant:
    if isinstance(node.value, bool):
      return ir.Constant(self.bool_type, int(node.value))
    elif isinstance(node.value, int):
      return ir.Constant(self.int_type, node.value)
    elif isinstance(node.value, float):
      return ir.Constant(self.float_type, node.value)

    raise NotImplementedError(f"Unsupported literal type: {type(node.value)}")

  def visit_IdentifierNode(self, node: IdentifierNode) -> ir.Value:
    """Loads and returns the value stored in an identifier's stack location."""
    if node.name in self.named_values:
      val_or_ptr = self.named_values[node.name]
      if hasattr(val_or_ptr, "type") and isinstance(val_or_ptr.type, ir.PointerType):
        return self.builder.load(val_or_ptr, name=f"{node.name}_val")
      return val_or_ptr

    raise NameError(f"Unknown symbol: {node.name}")

  def visit_BinaryOpNode(self, node: BinaryOpNode) -> ir.Value:
    """Lowers binary arithmetic and comparison operations to LLVM IR instructions."""
    lhs = self.visit(node.left)
    rhs = self.visit(node.right)

    # Type promotion if operating on mixed int and float
    if lhs.type == self.float_type and rhs.type == self.int_type:
      rhs = self.builder.sitofp(rhs, self.float_type, name="conv_rhs")
    elif lhs.type == self.int_type and rhs.type == self.float_type:
      lhs = self.builder.sitofp(lhs, self.float_type, name="conv_lhs")

    is_float = (lhs.type == self.float_type or rhs.type == self.float_type)

    if node.op == "+":
      return self.builder.fadd(lhs, rhs, name="faddtmp") if is_float else self.builder.add(lhs, rhs, name="addtmp")
    elif node.op == "-":
      return self.builder.fsub(lhs, rhs, name="fsubtmp") if is_float else self.builder.sub(lhs, rhs, name="subtmp")
    elif node.op == "*":
      return self.builder.fmul(lhs, rhs, name="fmultmp") if is_float else self.builder.mul(lhs, rhs, name="multmp")
    elif node.op == "/":
      return self.builder.fdiv(lhs, rhs, name="fdivtmp") if is_float else self.builder.sdiv(lhs, rhs, name="sdivtmp")
    elif node.op in ("==", "!=", "<", "<=", ">", ">="):
      if is_float:
        return self.builder.fcmp_ordered(node.op, lhs, rhs, name="cmptmp")
      return self.builder.icmp_signed(node.op, lhs, rhs, name="cmptmp")

    raise NotImplementedError(f"Unsupported binary operator: {node.op}")

  # -------------------------------------------------------------------------
  # Remaining BaseTranspiler visitor stubs (route to generic_visit)
  # -------------------------------------------------------------------------

  def visit_EnumDeclNode(self, node: Any) -> Any: return self.generic_visit(node)
  def visit_ImportStmtNode(self, node: Any) -> Any: return self.generic_visit(node)
  def visit_ExportStmtNode(self, node: Any) -> Any: return self.generic_visit(node)
  def visit_StructFieldNode(self, node: Any) -> Any: return self.generic_visit(node)
  def visit_ImplMemberNode(self, node: Any) -> Any: return self.generic_visit(node)
  def visit_TraitDeclNode(self, node: Any) -> Any: return self.generic_visit(node)
  def visit_YieldNode(self, node: Any) -> Any: return self.generic_visit(node)
  def visit_MatchExprNode(self, node: Any) -> Any: return self.generic_visit(node)
  def visit_EllipsisPatternNode(self, node: Any) -> Any: return self.generic_visit(node)
  def visit_IfNode(self, node: Any) -> Any: return self.generic_visit(node)
  def visit_WhileNode(self, node: Any) -> Any: return self.generic_visit(node)
  def visit_ForNode(self, node: Any) -> Any: return self.generic_visit(node)
  def visit_BreakNode(self, node: Any) -> Any: return self.generic_visit(node)
  def visit_ContinueNode(self, node: Any) -> Any: return self.generic_visit(node)
  def visit_InterpolatedStringNode(self, node: Any) -> Any: return self.generic_visit(node)
  def visit_TernaryExprNode(self, node: Any) -> Any: return self.generic_visit(node)
  def visit_UnaryOpNode(self, node: Any) -> Any: return self.generic_visit(node)
  def visit_CastExprNode(self, node: Any) -> Any: return self.generic_visit(node)
  def visit_CallNode(self, node: Any) -> Any: return self.generic_visit(node)
  def visit_MemberAccessNode(self, node: Any) -> Any: return self.generic_visit(node)
  def visit_CloneNode(self, node: Any) -> Any: return self.generic_visit(node)
  def visit_LambdaNode(self, node: Any) -> Any: return self.generic_visit(node)
  def visit_ArrayLiteralNode(self, node: Any) -> Any: return self.generic_visit(node)
  def visit_MapLiteralNode(self, node: Any) -> Any: return self.generic_visit(node)
  def visit_IndexExprNode(self, node: Any) -> Any: return self.generic_visit(node)
  def visit_StructInitializerNode(self, node: Any) -> Any: return self.generic_visit(node)
  def visit_GuardClauseNode(self, node: Any) -> Any: return self.generic_visit(node)
  def visit_GuardStmtNode(self, node: Any) -> Any: return self.generic_visit(node)
