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
  AssignmentNode,
  ASTNode,
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

try:
  from llvmlite import ir
except ImportError:  # pragma: no cover
  ir = None  # type: ignore[assignment]

try:
  import llvmlite.binding as llvm

  llvm.initialize_native_target()
  llvm.initialize_native_asmprinter()
  DEFAULT_TRIPLE = llvm.get_default_triple()
except Exception:  # pragma: no cover
  DEFAULT_TRIPLE = "x86_64-pc-linux-gnu"


from src.code_gen.transpiler_registry import TranspilerRegistry


@TranspilerRegistry.register(
  aliases=["llvm", "llvmir", "ir"],
  display_name="LLVM IR",
  default_extension=".ll",
)
class LLVMTranspiler(BaseTranspiler):
  """Transpiles a type-checked Sapphire AST into LLVM IR."""

  def __init__(
    self,
    module_name="sapphire_module",
    target_triple=None,
    semantic_context: Any = None,
  ):
    if ir is None:  # pragma: no cover
      raise ImportError(
        "The experimental LLVM backend requires 'llvmlite'. "
        "Install it with: pip install 'sapphire-lang[llvm]'"
      )
    super().__init__(semantic_context=semantic_context)
    # 1. Initialize an isolated LLVM context and module per transpiler instance
    self.context = ir.Context()
    self.module = ir.Module(name=module_name, context=self.context)
    self.module.triple = target_triple or DEFAULT_TRIPLE

    # 2. Type-mapping & symbol table cache
    self.struct_types: Dict[str, Any] = {}
    self.struct_field_types: Dict[str, list] = {}
    self.named_values: Dict[str, Any] = {}
    self.builder: Optional[Any] = None
    self.current_function: Optional[Any] = None

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
      f"AST node '{type(node).__name__}' is not supported by the experimental "
      "LLVM transpiler backend yet."
    )

  # -------------------------------------------------------------------------
  # Helper utilities
  # -------------------------------------------------------------------------

  def get_llvm_type(self, type_node: Any) -> ir.Type:
    """Maps Sapphire AST type nodes or semantic Type objects to LLVM IR types.
    """
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

  def _infer_expr_llvm_type(self, expr: Any) -> Optional[ir.Type]:
    """Infers an LLVM IR type from an expression's semantic type or literal
    kind.
    """
    if expr is None:
      return None
    inferred = self.get_inferred_type(expr)
    if inferred is not None:
      return self.get_llvm_type(inferred)
    if isinstance(expr, LiteralNode):
      if expr.lit_type == "bool" or isinstance(expr.value, bool):
        return self.bool_type
      if expr.lit_type == "int" or isinstance(expr.value, int):
        return self.int_type
      if expr.lit_type == "float" or isinstance(expr.value, float):
        return self.float_type
    return None

  def _zero_constant(self, llvm_type: ir.Type) -> ir.Constant:
    """Returns the Sapphire default zero constant for *llvm_type*."""
    if llvm_type == self.int_type:
      return ir.Constant(self.int_type, 0)
    if llvm_type == self.float_type:
      return ir.Constant(self.float_type, 0.0)
    if llvm_type == self.bool_type:
      return ir.Constant(self.bool_type, 0)
    if isinstance(llvm_type, ir.PointerType):
      return ir.Constant(llvm_type, None)
    return ir.Constant(llvm_type, None)

  def _match_type(self, val: ir.Value, target_type: ir.Type) -> ir.Value:
    """Helper to convert values when types differ (e.g. sitofp for int->float).
    """
    if val.type == target_type:
      return val
    if val.type == self.int_type and target_type == self.float_type:
      return self.builder.sitofp(val, self.float_type, name="sitofp_tmp")
    return val

  def _emit_binary_op(self, op: str, lhs: ir.Value, rhs: ir.Value) -> ir.Value:
    """Emits an LLVM arithmetic or comparison instruction for *op*."""
    # Type promotion if operating on mixed int and float
    if lhs.type == self.float_type and rhs.type == self.int_type:
      rhs = self.builder.sitofp(rhs, self.float_type, name="conv_rhs")
    elif lhs.type == self.int_type and rhs.type == self.float_type:
      lhs = self.builder.sitofp(lhs, self.float_type, name="conv_lhs")

    is_float = lhs.type == self.float_type or rhs.type == self.float_type

    if op == "+":
      return (
        self.builder.fadd(lhs, rhs, name="faddtmp")
        if is_float
        else self.builder.add(lhs, rhs, name="addtmp")
      )
    elif op == "-":
      return (
        self.builder.fsub(lhs, rhs, name="fsubtmp")
        if is_float
        else self.builder.sub(lhs, rhs, name="subtmp")
      )
    elif op == "*":
      return (
        self.builder.fmul(lhs, rhs, name="fmultmp")
        if is_float
        else self.builder.mul(lhs, rhs, name="multmp")
      )
    elif op == "/":
      return (
        self.builder.fdiv(lhs, rhs, name="fdivtmp")
        if is_float
        else self.builder.sdiv(lhs, rhs, name="sdivtmp")
      )
    elif op == "%":
      return (
        self.builder.frem(lhs, rhs, name="fremtmp")
        if is_float
        else self.builder.srem(lhs, rhs, name="sremtmp")
      )
    elif op in ("==", "!=", "<", "<=", ">", ">="):
      if is_float:
        if op == "!=":
          return self.builder.fcmp_unordered("!=", lhs, rhs, name="cmptmp")
        return self.builder.fcmp_ordered(op, lhs, rhs, name="cmptmp")
      return self.builder.icmp_signed(op, lhs, rhs, name="cmptmp")

    raise NotImplementedError(f"Unsupported binary operator: {op}")

  # -------------------------------------------------------------------------
  # Top-level declarations
  # -------------------------------------------------------------------------

  def visit_ProgramNode(self, node: ProgramNode) -> str:
    for declaration in node.declarations:
      self.visit(declaration)
    return str(self.module)

  def visit_StructDeclNode(self, node: StructDeclNode) -> ir.Type:
    """Lowers a Sapphire struct (including parent fields) into a flat LLVM
    aggregate type.
    """
    struct_name = node.name
    llvm_struct = self.module.context.get_identified_type(
      f"struct.{struct_name}"
    )

    field_types = []
    for parent_name in getattr(node, "parent_names", None) or []:
      if parent_name not in self.struct_field_types:
        raise NotImplementedError(
          f"Parent struct '{parent_name}' must be declared before child "
          f"struct '{struct_name}' in LLVM backend."
        )
      field_types.extend(self.struct_field_types[parent_name])

    for field in node.fields:
      f_type = getattr(field, "field_type", getattr(field, "type_node", None))
      if f_type is not None:
        field_types.append(self.get_llvm_type(f_type))
      else:
        inferred_llvm = self._infer_expr_llvm_type(
          getattr(field, "default_expr", None)
        )
        if inferred_llvm is None:
          raise NotImplementedError(
            "Cannot infer LLVM type for struct field "
            f"'{struct_name}.{field.name}'."
          )
        field_types.append(inferred_llvm)

    llvm_struct.set_body(*field_types)
    self.struct_types[struct_name] = llvm_struct
    self.struct_field_types[struct_name] = list(field_types)
    return llvm_struct

  def visit_FuncDeclNode(self, node: FuncDeclNode) -> ir.Function:
    """Lowers a Sapphire function declaration or `@extern` prototype into LLVM
    IR.
    """
    return_types = getattr(node, "return_types", None) or []
    if len(return_types) > 1:
      raise NotImplementedError(
        "Multiple return values are not supported by the experimental LLVM "
        "backend yet."
      )
    ret_type_node = return_types[0] if return_types else node.return_type
    return_type = self.get_llvm_type(ret_type_node)
    params = getattr(node, "parameters", getattr(node, "params", []))
    param_types = [
      self.get_llvm_type(
        getattr(p, "param_type", getattr(p, "type_node", None))
      )
      for p in params
    ]

    anns = getattr(node, "annotations", None) or []
    extern_ann = next(
      (a for a in anns if getattr(a, "name", "") == "extern"), None
    )
    llvm_name = (
      extern_ann.arg
      if extern_ann and getattr(extern_ann, "arg", None)
      else node.name
    )

    func_type = ir.FunctionType(return_type, param_types)
    func = ir.Function(self.module, func_type, name=llvm_name)
    for i, param in enumerate(params):
      func.args[i].name = param.name

    # External declarations emit `declare ...` prototypes without a body.
    if extern_ann is not None or node.body is None:
      return func

    self.current_function = func

    # Clear symbol table for local function scope
    self.named_values.clear()

    # Create the entry basic block and IRBuilder
    entry_block = func.append_basic_block(name="entry")
    self.builder = ir.IRBuilder(entry_block)

    # Allocate stack slots (`alloca`) for parameters and store arguments
    for i, param in enumerate(params):
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
      elif isinstance(return_type, ir.PointerType):
        self.builder.ret(ir.Constant(return_type, None))
      else:
        self.builder.ret_void()

    self.builder = None
    self.current_function = None
    return func

  # -------------------------------------------------------------------------
  # Statements
  # -------------------------------------------------------------------------

  def visit_BlockNode(self, node: BlockNode) -> Any:
    prev_named = self.named_values.copy()
    last_val = None
    try:
      for stmt in node.statements:
        if self.builder and self.builder.block.is_terminated:
          break
        last_val = self.visit(stmt)
    finally:
      self.named_values = prev_named
    return last_val

  def visit_ExprStmtNode(self, node: ExprStmtNode) -> Any:
    return self.visit(node.expr)

  def visit_VarDeclNode(self, node: VarDeclNode) -> ir.AllocaInstr:
    """Allocates a stack slot for a local variable, inferring type and
    zero-initializing.
    """
    if self.builder is None:
      raise NotImplementedError(
        "Top-level module variables are not supported by the "
        "experimental LLVM backend yet."
      )
    names = getattr(node, "names", None) or (
      [node.name] if getattr(node, "name", None) else []
    )
    if len(names) > 1:
      raise NotImplementedError(
        "Multi-variable declarations are not supported by the experimental "
        "LLVM backend yet."
      )
    name = names[0] if names else ""

    val_type = getattr(node, "val_type", None)
    if val_type is None and hasattr(node, "val_types") and node.val_types:
      val_type = node.val_types[0]
    if val_type is None:
      val_type = getattr(node, "type_node", None)

    init_expr = getattr(node, "expr", getattr(node, "initializer", None))
    init_val = self.visit(init_expr) if init_expr is not None else None

    if val_type is not None:
      var_type = self.get_llvm_type(val_type)
    elif init_val is not None:
      var_type = init_val.type
    else:
      var_type = self.int_type

    alloca = self.builder.alloca(var_type, name=name)

    if init_val is not None:
      init_val = self._match_type(init_val, var_type)
      self.builder.store(init_val, alloca)
    else:
      self.builder.store(self._zero_constant(var_type), alloca)

    self.named_values[name] = alloca
    return alloca

  def visit_AssignmentNode(self, node: AssignmentNode) -> ir.Value:
    """Updates the value stored in a variable's stack slot (`alloca`),
    supporting
    compound ops.
    """
    targets = getattr(node, "targets", None) or (
      [node.target] if getattr(node, "target", None) else []
    )
    if len(targets) > 1:
      raise NotImplementedError(
        "Multi-target assignments are not supported by the experimental LLVM "
        "backend yet."
      )
    target = targets[0] if targets else None
    val_expr = getattr(node, "expr", getattr(node, "value", None))

    if isinstance(target, IdentifierNode):
      if target.name not in self.named_values:
        raise NameError(f"Undefined variable: {target.name}")
      ptr = self.named_values[target.name]
      rhs = self.visit(val_expr)
      op = getattr(node, "op", "=")
      if op == "=":
        val = self._match_type(rhs, ptr.type.pointee)
      elif op in ("+=", "-=", "*=", "/=", "%="):
        cur = self.builder.load(ptr, name=f"{target.name}_cur")
        val = self._emit_binary_op(op[:-1], cur, rhs)
        val = self._match_type(val, ptr.type.pointee)
      else:
        raise NotImplementedError(f"Unsupported assignment operator: {op}")
      self.builder.store(val, ptr)
      return val

    raise NotImplementedError(
      f"Assignment to {type(target).__name__} is not supported yet."
    )

  def visit_ReturnNode(self, node: ReturnNode) -> ir.Instruction:
    exprs = getattr(node, "expressions", None)
    if exprs and len(exprs) > 1:
      raise NotImplementedError(
        "Multiple return values are not supported by the experimental LLVM "
        "backend yet."
      )
    ret_expr = (
      exprs[0] if exprs else getattr(node, "expr", getattr(node, "value", None))
    )
    if ret_expr is None:
      return self.builder.ret_void()

    ret_val = self.visit(ret_expr)
    if (
      self.current_function
      and self.current_function.type.pointee.return_type != self.void_type
    ):
      ret_val = self._match_type(
        ret_val, self.current_function.type.pointee.return_type
      )
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
      if hasattr(val_or_ptr, "type") and isinstance(
        val_or_ptr.type, ir.PointerType
      ):
        return self.builder.load(val_or_ptr, name=f"{node.name}_val")
      return val_or_ptr

    raise NameError(f"Unknown symbol: {node.name}")

  def visit_BinaryOpNode(self, node: BinaryOpNode) -> ir.Value:
    """Lowers binary arithmetic and comparison operations to LLVM IR
    instructions.
    """
    lhs = self.visit(node.left)
    rhs = self.visit(node.right)
    return self._emit_binary_op(node.op, lhs, rhs)

  # -------------------------------------------------------------------------
  # Remaining BaseTranspiler visitor stubs (route to generic_visit)
  # -------------------------------------------------------------------------

  def visit_EnumDeclNode(self, node: Any) -> Any:
    return self.generic_visit(node)

  def visit_ImportStmtNode(self, node: Any) -> Any:
    return self.generic_visit(node)

  def visit_ExportStmtNode(self, node: Any) -> Any:
    return self.generic_visit(node)

  def visit_StructFieldNode(self, node: Any) -> Any:
    return self.generic_visit(node)

  def visit_ImplMemberNode(self, node: Any) -> Any:
    return self.generic_visit(node)

  def visit_TraitDeclNode(self, node: Any) -> Any:
    return self.generic_visit(node)

  def visit_YieldNode(self, node: Any) -> Any:
    return self.generic_visit(node)

  def visit_MatchExprNode(self, node: Any) -> Any:
    return self.generic_visit(node)

  def visit_EllipsisPatternNode(self, node: Any) -> Any:
    return self.generic_visit(node)

  def visit_IfNode(self, node: Any) -> Any:
    return self.generic_visit(node)

  def visit_WhileNode(self, node: Any) -> Any:
    return self.generic_visit(node)

  def visit_ForNode(self, node: Any) -> Any:
    return self.generic_visit(node)

  def visit_BreakNode(self, node: Any) -> Any:
    return self.generic_visit(node)

  def visit_ContinueNode(self, node: Any) -> Any:
    return self.generic_visit(node)

  def visit_InterpolatedStringNode(self, node: Any) -> Any:
    return self.generic_visit(node)

  def visit_TernaryExprNode(self, node: Any) -> Any:
    return self.generic_visit(node)

  def visit_UnaryOpNode(self, node: Any) -> Any:
    return self.generic_visit(node)

  def visit_CastExprNode(self, node: Any) -> Any:
    return self.generic_visit(node)

  def visit_CallNode(self, node: Any) -> Any:
    return self.generic_visit(node)

  def visit_MemberAccessNode(self, node: Any) -> Any:
    return self.generic_visit(node)

  def visit_CloneNode(self, node: Any) -> Any:
    return self.generic_visit(node)

  def visit_MoveNode(self, node: Any) -> Any:
    return self.generic_visit(node)

  def visit_LambdaNode(self, node: Any) -> Any:
    return self.generic_visit(node)

  def visit_ArrayLiteralNode(self, node: Any) -> Any:
    return self.generic_visit(node)

  def visit_MapLiteralNode(self, node: Any) -> Any:
    return self.generic_visit(node)

  def visit_IndexExprNode(self, node: Any) -> Any:
    return self.generic_visit(node)

  def visit_StructInitializerNode(self, node: Any) -> Any:
    return self.generic_visit(node)

  def visit_GuardClauseNode(self, node: Any) -> Any:
    return self.generic_visit(node)

  def visit_GuardStmtNode(self, node: Any) -> Any:
    return self.generic_visit(node)
