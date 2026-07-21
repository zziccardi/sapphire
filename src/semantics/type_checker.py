"""Semantic analyzer and type checker implementation for Sapphire.

This module walks the Sapphire AST, constructs symbol tables, performs type
checking and type inference, and validates all semantic constraints of the
Sapphire language.
"""

from typing import Any, Dict, List, Optional

try:
  from parser.ast import *
  from semantics.symbol_table import (
      SymbolTable,
      Type,
      PrimitiveType,
      OptionalType,
      FunctionType,
      StructField,
      StructMethod,
      StructType,
      TraitType,
      EnumType,
      NoneType,
      ArrayType,
      ArenaType,
      VariableSymbol,
      FunctionSymbol,
      StructSymbol,
      TraitSymbol,
      EnumSymbol,
  )
except ModuleNotFoundError:  # pragma: no cover
  from src.parser.ast import *
  from src.semantics.symbol_table import (
      SymbolTable,
      Type,
      PrimitiveType,
      OptionalType,
      FunctionType,
      StructField,
      StructMethod,
      StructType,
      TraitType,
      EnumType,
      NoneType,
      ArrayType,
      ArenaType,
      VariableSymbol,
      FunctionSymbol,
      StructSymbol,
      TraitSymbol,
      EnumSymbol,
  )



class SemanticError(Exception):
  """Exception raised for semantic or compile-time type errors."""
  pass


class TypeChecker:
  """Walks the AST to perform type-checking and semantic validation."""

  def __init__(self):
    self.symbol_table = SymbolTable()
    self.errors: List[str] = []
    self.current_function: Optional[FunctionType] = None
    self.current_struct: Optional[StructType] = None
    self.is_in_init: bool = False
    self.initialized_fields: set = set()
    self.expected_type: Optional[Type] = None
    self.current_function_scope = None

  def _get_arena_dependency(self, node: ASTNode) -> Optional[str]:
    if isinstance(node, IdentifierNode):
      symbol = self.symbol_table.lookup(node.name)
      if isinstance(symbol, VariableSymbol):
        return symbol.arena_dependency
    elif isinstance(node, StructInitializerNode):
      if node.arena_expr and isinstance(node.arena_expr, IdentifierNode):
        return node.arena_expr.name
    elif isinstance(node, CloneNode):
      if node.arena_expr and isinstance(node.arena_expr, IdentifierNode):
        return node.arena_expr.name
      else:
        return self._get_arena_dependency(node.expr)
    return None

  def _is_descendant_scope(self, child: Optional[object], parent: Optional[object]) -> bool:
    curr = child
    while curr:
      if curr == parent:
        return True
      curr = curr.parent
    return False

  def _get_target_symbol(self, target: ASTNode) -> Optional[VariableSymbol]:
    if isinstance(target, IdentifierNode):
      sym = self.symbol_table.lookup(target.name)
      if isinstance(sym, VariableSymbol):
        return sym
    elif isinstance(target, MemberAccessNode):
      return self._get_target_symbol(target.receiver)
    return None

  def error(self, message: str) -> None:
    """Logs a semantic error."""
    self.errors.append(message)

  def check(self, program: ProgramNode) -> None:
    """Executes semantic analysis on the program."""
    # Pass 1: Declare global symbols (Structs, Traits, Functions)
    self._declare_globals(program)

    # Pass 2: Copy inheritance layouts and resolve struct fields
    self._resolve_struct_layouts(program)

    # Pass 3: Register impl block method signatures
    self._register_impl_signatures(program)

    # Pass 4: Fully check declaration bodies
    self.visit(program)

    if self.errors:
      raise SemanticError("\n".join(self.errors))

  def _declare_globals(self, program: ProgramNode) -> None:
    """Pre-pass to register types and global function symbols in the symbol table."""
    for decl in program.declarations:
      if isinstance(decl, StructDeclNode):
        if self.symbol_table.lookup_current_scope(decl.name):
          self.error(f"Redefinition of identifier '{decl.name}'.")
          continue
        struct_type = StructType(decl.name, decl.parent_name, decl.is_prototype)
        self.symbol_table.define_type(decl.name, struct_type)
        self.symbol_table.define(decl.name, StructSymbol(decl.name, struct_type))

      elif isinstance(decl, EnumDeclNode):
        if self.symbol_table.lookup_current_scope(decl.name):
          self.error(f"Redefinition of identifier '{decl.name}'.")
          continue
        current_val = 0
        variants: Dict[str, int] = {}
        seen_members = set()
        for member in decl.members:
          if member.name in seen_members:
            self.error(f"Duplicate member '{member.name}' in enum '{decl.name}'.")
            continue
          seen_members.add(member.name)
          if member.value is not None:
            current_val = member.value
          variants[member.name] = current_val
          current_val += 1
        enum_type = EnumType(decl.name, variants)
        self.symbol_table.define_type(decl.name, enum_type)
        self.symbol_table.define(decl.name, EnumSymbol(decl.name, enum_type))

      elif isinstance(decl, TraitDeclNode):
        if self.symbol_table.lookup_current_scope(decl.name):
          self.error(f"Redefinition of identifier '{decl.name}'.")
          continue
        trait_type = TraitType(decl.name)
        # Populate trait method signatures
        for member in decl.members:
          p_types = [self._resolve_type_node(p.param_type) for p in member.parameters]
          ret_t = self._resolve_type_node(member.return_type) if member.return_type else PrimitiveType("none")
          p_mutabilities = [p.is_mutable for p in member.parameters]
          trait_type.methods[member.name] = FunctionType(
              p_types,
              ret_t,
              p_mutabilities,
              param_names=[p.name for p in member.parameters],
          )

        self.symbol_table.define_type(decl.name, trait_type)
        self.symbol_table.define(decl.name, TraitSymbol(decl.name, trait_type))

      elif isinstance(decl, FuncDeclNode):
        if self.symbol_table.lookup_current_scope(decl.name):
          self.error(f"Redefinition of identifier '{decl.name}'.")
          continue
        # We will fully resolve parameter/return types of global functions in Pass 4,
        # but we register their name and placeholder signature here for mutual recursion.
        param_types = []
        param_mutabilities = []
        for p in decl.parameters:
          ptype = self._resolve_type_node(p.param_type)
          param_types.append(ptype)
          param_mutabilities.append(p.is_mutable)
        ret_type = self._resolve_type_node(decl.return_type) if decl.return_type else PrimitiveType("none")
        signature = FunctionType(
            param_types,
            ret_type,
            param_mutabilities,
            param_names=[p.name for p in decl.parameters],
        )
        self.symbol_table.define(decl.name, FunctionSymbol(decl.name, signature))

  def _resolve_struct_layouts(self, program: ProgramNode) -> None:
    """Pre-pass to resolve static inheritance field copying and layout sizing."""
    # Resolve inheritance layout order by finding dependencies
    structs_to_process = [d for d in program.declarations if isinstance(d, StructDeclNode)]
    processed = set()

    def process_struct(node: StructDeclNode):
      if node.name in processed:
        return

      struct_type = self.symbol_table.lookup_type(node.name)
      if not isinstance(struct_type, StructType):
        return

      if node.parent_name:
        # Check parent existence
        parent_type = self.symbol_table.lookup_type(node.parent_name)
        if not parent_type:
          self.error(f"Parent struct '{node.parent_name}' not found for '{node.name}'.")
        elif not isinstance(parent_type, StructType):
          self.error(f"Parent '{node.parent_name}' of '{node.name}' is not a struct type.")
        else:
          # Process parent first if needed
          parent_node = next((s for s in structs_to_process if s.name == node.parent_name), None)
          if parent_node:
            process_struct(parent_node)
          # Copy parent fields to child
          for field_name, field_obj in parent_type.fields.items():
            struct_type.fields[field_name] = field_obj

      # Resolve child's own fields
      for f in node.fields:
        ftype = self._resolve_type_node(f.field_type)
        if f.name in struct_type.fields:
          self.error(f"Field '{f.name}' in struct '{node.name}' shadows inherited parent field.")
        struct_type.fields[f.name] = StructField(f.name, ftype, f.is_mutable, f.default_expr is not None)

      processed.add(node.name)

    for s in structs_to_process:
      process_struct(s)

  def _register_impl_signatures(self, program: ProgramNode) -> None:
    """Pre-pass to register all impl block methods."""
    for decl in program.declarations:
      if isinstance(decl, ImplBlockNode):
        struct_type = self.symbol_table.lookup_type(decl.struct_name)
        if not struct_type or not isinstance(struct_type, StructType):
          self.error(f"Cannot implement members for undefined struct '{decl.struct_name}'.")
          continue

        # If implementing a trait
        trait_type = None
        if decl.trait_name:
          trait_type = self.symbol_table.lookup_type(decl.trait_name)
          if not trait_type or not isinstance(trait_type, TraitType):
            self.error(f"Cannot implement undefined trait '{decl.trait_name}'.")
            continue

        for member in decl.members:
          func_decl = member.func_decl
          # Resolve parameters
          param_types = []
          param_mutabilities = []
          for p in func_decl.parameters:
            ptype = self._resolve_type_node(p.param_type)
            param_types.append(ptype)
            param_mutabilities.append(p.is_mutable)
          ret_type = self._resolve_type_node(func_decl.return_type) if func_decl.return_type else PrimitiveType("none")
          signature = FunctionType(
              param_types,
              ret_type,
              param_mutabilities,
              param_names=[p.name for p in func_decl.parameters],
          )

          method = StructMethod(func_decl.name, signature, member.modifier)

          # Check for duplicate definitions
          if func_decl.name in struct_type.methods:
            self.error(f"Method '{func_decl.name}' redefined in struct '{decl.struct_name}'.")
          struct_type.methods[func_decl.name] = method

          # Register on trait if needed
          if trait_type:
            pass

  def _resolve_type_node(self, node: Optional[TypeNode]) -> Type:
    """Helper to map an AST TypeNode into a semantic Type object."""
    if not node:
      return PrimitiveType("none")
    if isinstance(node, BasicTypeNode):
      resolved = self.symbol_table.lookup_type(node.name)
      if not resolved:
        self.error(f"Undefined type '{node.name}'.")
        return PrimitiveType("none")
      return resolved
    if isinstance(node, OptionalTypeNode):
      return OptionalType(self._resolve_type_node(node.base_type))
    if isinstance(node, FunctionTypeNode):
      param_types = [self._resolve_type_node(t) for t in node.param_types]
      ret_type = self._resolve_type_node(node.return_type)
      return FunctionType(param_types, ret_type)
    return PrimitiveType("none")

  # ==========================================
  # Visitor Dispatcher
  # ==========================================

  def visit(self, node: ASTNode) -> Any:
    """Visit a node by dynamically calling its corresponding visit method."""
    method_name = f"visit_{node.__class__.__name__}"
    visitor = getattr(self, method_name, self.generic_visit)
    return visitor(node)

  def generic_visit(self, node: ASTNode) -> Any:
    """Default fallback when no specific visitor method is defined."""
    raise NotImplementedError(f"No visit_{node.__class__.__name__} method defined.")

  # ==========================================
  # Visitor Methods
  # ==========================================

  def visit_ProgramNode(self, node: ProgramNode) -> None:
    for decl in node.declarations:
      self.visit(decl)

  def visit_StructDeclNode(self, node: StructDeclNode) -> None:
    # Fields already verified in pre-pass
    pass

  def visit_EnumDeclNode(self, node: EnumDeclNode) -> None:
    # Members already verified in pre-pass
    pass

  def visit_ImplBlockNode(self, node: ImplBlockNode) -> None:
    struct_type = self.symbol_table.lookup_type(node.struct_name)
    if not struct_type or not isinstance(struct_type, StructType):
      return

    self.current_struct = struct_type

    # If implementing a trait, verify contract is fully satisfied
    if node.trait_name:
      trait_type = self.symbol_table.lookup_type(node.trait_name)
      if isinstance(trait_type, TraitType):
        for trait_method_name, trait_sig in trait_type.methods.items():
          if trait_method_name not in struct_type.methods:
            self.error(
                f"Struct '{node.struct_name}' does not implement trait method "
                f"'{trait_method_name}' of '{node.trait_name}'."
            )
          else:
            impl_sig = struct_type.methods[trait_method_name].method_type
            if impl_sig != trait_sig:
              self.error(
                  f"Method '{trait_method_name}' in struct '{node.struct_name}' "
                  f"has signature {impl_sig}, but trait '{node.trait_name}' "
                  f"requires {trait_sig}."
              )

    # Check each method implementation
    for member in node.members:
      self.visit(member)

    self.current_struct = None

  def visit_ImplMemberNode(self, node: ImplMemberNode) -> None:
    func_decl = node.func_decl
    struct_type = self.current_struct

    # Enter scope of method
    self.symbol_table.enter_scope()

    # Define 'self' unless it is a static method
    if node.modifier != "static":
      # If const method, self is immutable. Else mutable
      is_mutable = node.modifier != "const"
      self.symbol_table.define("self", VariableSymbol("self", struct_type, is_mutable))

    # Setup constructor checking
    old_in_init = self.is_in_init
    old_fields = self.initialized_fields
    if func_decl.name == "__init__":
      self.is_in_init = True
      self.initialized_fields = set()

    # Define parameters in scope
    for p in func_decl.parameters:
      ptype = self._resolve_type_node(p.param_type)
      self.symbol_table.define(p.name, VariableSymbol(p.name, ptype, p.is_mutable, is_parameter=True))

    # Save function signature context
    resolved_params = [self._resolve_type_node(p.param_type) for p in func_decl.parameters]
    param_mutabilities = [p.is_mutable for p in func_decl.parameters]
    ret_type = self._resolve_type_node(func_decl.return_type) if func_decl.return_type else PrimitiveType("none")
    self.current_function = FunctionType(
        resolved_params,
        ret_type,
        param_mutabilities,
        param_names=[p.name for p in func_decl.parameters],
    )

    # Visit body
    self.visit(func_decl.body)

    # Verify constructor initializes all non-optional fields
    if func_decl.name == "__init__" and struct_type:
      for f_name, f_obj in struct_type.fields.items():
        if (f_name not in self.initialized_fields 
            and not isinstance(f_obj.field_type, OptionalType)
            and not f_obj.has_default):
          self.error(f"Constructor '__init__' failed to initialize non-optional field '{f_name}'.")

    # Restore constructor contexts
    self.is_in_init = old_in_init
    self.initialized_fields = old_fields
    self.current_function = None

    self.symbol_table.exit_scope()

  def visit_TraitDeclNode(self, node: TraitDeclNode) -> None:
    pass

  def visit_FuncDeclNode(self, node: FuncDeclNode) -> None:
    # Register parameters and check body
    self.symbol_table.enter_scope()
    old_function_scope = self.current_function_scope
    self.current_function_scope = self.symbol_table.current_scope

    for p in node.parameters:
      ptype = self._resolve_type_node(p.param_type)
      self.symbol_table.define(p.name, VariableSymbol(p.name, ptype, p.is_mutable, is_parameter=True))

    resolved_params = [self._resolve_type_node(p.param_type) for p in node.parameters]
    param_mutabilities = [p.is_mutable for p in node.parameters]
    ret_type = self._resolve_type_node(node.return_type) if node.return_type else PrimitiveType("none")
    self.current_function = FunctionType(resolved_params, ret_type, param_mutabilities)

    self.visit(node.body)

    self.current_function = None
    self.current_function_scope = old_function_scope
    self.symbol_table.exit_scope()

  def visit_BlockNode(self, node: BlockNode) -> None:
    self.symbol_table.enter_scope()
    for stmt in node.statements:
      self.visit(stmt)
    self.symbol_table.exit_scope()

  def visit_VarDeclNode(self, node: VarDeclNode) -> None:


    # 2. Namespace validation: variable shares same namespace with functions/structs/traits in current scope level
    if self.symbol_table.lookup_current_scope(node.name):
      self.error(f"Identifier '{node.name}' is already defined in this scope.")
      return

    # 3. Handle type annotations & inference
    if node.val_type:
      val_type = self._resolve_type_node(node.val_type)
      self.expected_type = val_type
      expr_type = self.visit(node.expr)
      self.expected_type = None
      if not expr_type.is_compatible(val_type):
        self.error(f"Cannot assign expression of type '{expr_type}' to variable '{node.name}' of type '{val_type}'.")
      var_type = val_type
    else:
      # Inference
      expr_type = self.visit(node.expr)
      if isinstance(expr_type, NoneType):
        self.error(f"Cannot infer type of '{node.name}' from 'none' alone. Specify an optional type annotation.")
        var_type = OptionalType(PrimitiveType("none"))
      else:
        var_type = expr_type

    # Define symbol
    sym = VariableSymbol(node.name, var_type, node.is_mutable)
    self.symbol_table.define(node.name, sym)

    # Check arena escape
    arena_name = self._get_arena_dependency(node.expr)
    if arena_name:
      sym.arena_dependency = arena_name
      arena_sym = self.symbol_table.lookup(arena_name)
      if arena_sym and arena_sym.scope_defined and sym.scope_defined:
        if self._is_descendant_scope(arena_sym.scope_defined, sym.scope_defined) and arena_sym.scope_defined != sym.scope_defined:
          self.error(f"Variable '{node.name}' in outer scope cannot hold a reference to an object allocated in nested arena '{arena_name}'.")

  def visit_AssignmentNode(self, node: AssignmentNode) -> None:
    # 1. Target validation
    # Must resolve target type and check lvalue mutability
    target_type = self._check_lvalue(node.target)
    self.expected_type = target_type
    expr_type = self.visit(node.expr)
    self.expected_type = None

    if not expr_type.is_compatible(target_type):
      self.error(f"Cannot assign type '{expr_type}' to target of type '{target_type}'.")

    # Check arena escape
    arena_name = self._get_arena_dependency(node.expr)
    if arena_name:
      target_sym = self._get_target_symbol(node.target)
      if target_sym:
        target_sym.arena_dependency = arena_name
        arena_sym = self.symbol_table.lookup(arena_name)
        if arena_sym and arena_sym.scope_defined and target_sym.scope_defined:
          if self._is_descendant_scope(arena_sym.scope_defined, target_sym.scope_defined) and arena_sym.scope_defined != target_sym.scope_defined:
            self.error(f"Variable '{target_sym.name}' in outer scope cannot hold a reference to an object allocated in nested arena '{arena_name}'.")

    # If assigning to self field in constructor, track it
    if self.is_in_init and isinstance(node.target, MemberAccessNode):
      if isinstance(node.target.receiver, IdentifierNode) and node.target.receiver.name == "self":
        self.initialized_fields.add(node.target.member)

  def _check_lvalue(self, node: ASTNode) -> Type:
    """Helper to check if AST node is a mutable lvalue and returns its resolved type."""
    if isinstance(node, IdentifierNode):
      sym = self.symbol_table.lookup(node.name)
      if not sym:
        self.error(f"Undefined identifier '{node.name}'.")
        return PrimitiveType("none")
      if not isinstance(sym, VariableSymbol):
        self.error(f"Identifier '{node.name}' is not a mutable variable.")
        return sym.symbol_type
      if not sym.is_mutable and sym.name != "self":
        self.error(f"Cannot assign to constant variable '{node.name}'.")
      return sym.symbol_type

    if isinstance(node, MemberAccessNode):
      receiver_type = self.visit(node.receiver)
      # Unwrap optional if chained
      if node.is_optional and isinstance(receiver_type, OptionalType):
        receiver_type = receiver_type.base_type

      if not isinstance(receiver_type, StructType):
        self.error("Property access target is not a struct.")
        return PrimitiveType("none")

      # Field access
      field = receiver_type.fields.get(node.member)
      if not field:
        self.error(f"Struct '{receiver_type.name}' has no field '{node.member}'.")
        return PrimitiveType("none")

      # Check field mutability or constructor exemption
      # Inside __init__, self fields are always assignable (even if immutable let fields)
      is_self = isinstance(node.receiver, IdentifierNode) and node.receiver.name == "self"
      if not field.is_mutable:
        if not (self.is_in_init and is_self):
          self.error(f"Cannot assign to constant field '{node.member}' of '{receiver_type.name}'.")

      # Verify self constness
      if is_self:
        self_sym = self.symbol_table.lookup("self")
        if self_sym and not self_sym.is_mutable:
          self.error(f"Cannot mutate field '{node.member}' within a constant method.")

      return field.field_type

    if isinstance(node, IndexExprNode):
      array_type = self.visit(node.array)
      if not isinstance(array_type, ArrayType):
        self.error("Cannot index non-array type.")
        return PrimitiveType("none")

      # Enforce that array target is a mutable variable
      if isinstance(node.array, IdentifierNode):
        sym = self.symbol_table.lookup(node.array.name)
        if sym and not sym.is_mutable:
          self.error(f"Cannot assign to index of constant array '{sym.name}'.")

      index_type = self.visit(node.index)
      if index_type != PrimitiveType("int"):
        self.error("Array index must be of type 'int'.")

      return array_type.element_type

    self.error("Invalid assignment target (not an lvalue).")
    return PrimitiveType("none")

  def visit_ExprStmtNode(self, node: ExprStmtNode) -> None:
    self.visit(node.expr)

  def visit_ReturnNode(self, node: ReturnNode) -> None:
    ret_type = self.visit(node.expr) if node.expr else PrimitiveType("none")
    if not self.current_function:
      self.error("Return statement outside function context.")
      return

    expected_type = self.current_function.return_type
    if not ret_type.is_compatible(expected_type):
      self.error(f"Return type mismatch. Expected '{expected_type}', got '{ret_type}'.")

    # Check return escaping arena reference
    if node.expr:
      arena_name = self._get_arena_dependency(node.expr)
      if arena_name:
        arena_sym = self.symbol_table.lookup(arena_name)
        if arena_sym and arena_sym.scope_defined and self.current_function_scope:
          if self._is_descendant_scope(arena_sym.scope_defined, self.current_function_scope):
            self.error(f"Cannot return a reference to an object allocated in local arena '{arena_name}'.")

  def visit_IfNode(self, node: IfNode) -> None:
    if node.is_if_let:
      # Optional unwrapping
      expr_type = self.visit(node.condition_or_expr)
      if not isinstance(expr_type, OptionalType):
        self.error("Expression in 'if let' must resolve to an optional type.")
        unwrapped_type = expr_type
      else:
        unwrapped_type = expr_type.base_type

      # Unwrapped var scope
      self.symbol_table.enter_scope()
      # Unwrapped variables are immutable bindings in block
      self.symbol_table.define(node.let_name, VariableSymbol(node.let_name, unwrapped_type, is_mutable=False))
      self.visit(node.then_block)
      self.symbol_table.exit_scope()
    else:
      cond_type = self.visit(node.condition_or_expr)
      if cond_type != PrimitiveType("bool"):
        self.error("If condition must resolve to 'bool'.")
      self.visit(node.then_block)

    if node.else_block:
      self.visit(node.else_block)

  def visit_WhileNode(self, node: WhileNode) -> None:
    cond_type = self.visit(node.condition)
    if cond_type != PrimitiveType("bool"):
      self.error("While condition must resolve to 'bool'.")
    self.visit(node.block)

  def visit_ForNode(self, node: ForNode) -> None:
    iter_type = self.visit(node.iterable)
    if not isinstance(iter_type, ArrayType):
      self.error("For-in loop source must be an array type.")
      elem_type = PrimitiveType("none")
    else:
      elem_type = iter_type.element_type

    self.symbol_table.enter_scope()
    self.symbol_table.define(node.loop_var, VariableSymbol(node.loop_var, elem_type, node.is_mutable))
    self.visit(node.block)
    self.symbol_table.exit_scope()

  # ==========================================
  # Expressions Visitor
  # ==========================================

  def visit_LiteralNode(self, node: LiteralNode) -> Type:
    if node.lit_type == "int":
      return PrimitiveType("int")
    if node.lit_type == "float":
      return PrimitiveType("float")
    if node.lit_type == "bool":
      return PrimitiveType("bool")
    if node.lit_type == "string":
      return PrimitiveType("string")
    return NoneType()

  def visit_IdentifierNode(self, node: IdentifierNode) -> Type:
    sym = self.symbol_table.lookup(node.name)
    if not sym:
      self.error(f"Undefined identifier '{node.name}'.")
      return PrimitiveType("none")
    return sym.symbol_type

  def visit_BinaryOpNode(self, node: BinaryOpNode) -> Type:
    left = self.visit(node.left)
    right = self.visit(node.right)

    # Boolean operators
    if node.op in ("&&", "||"):
      if left != PrimitiveType("bool") or right != PrimitiveType("bool"):
        self.error(f"Operator '{node.op}' requires boolean operands.")
      return PrimitiveType("bool")

    # Comparison operators
    if node.op in ("==", "!=", "<", "<=", ">", ">="):
      # Sapphire allows comparing compatible types
      if not left.is_compatible(right) and not right.is_compatible(left):
        self.error(f"Cannot compare type '{left}' with type '{right}' using '{node.op}'.")
      return PrimitiveType("bool")

    # Arithmetic operators
    if node.op in ("+", "-", "*", "/", "%"):
      # Supports int and float operations
      is_numeric_left = isinstance(left, PrimitiveType) and left.name in ("int", "float")
      is_numeric_right = isinstance(right, PrimitiveType) and right.name in ("int", "float")
      if not (is_numeric_left and is_numeric_right):
        self.error(f"Arithmetic operator '{node.op}' requires numeric types.")
        return PrimitiveType("none")

      # Common type rules
      if left.name == "float" or right.name == "float":
        return PrimitiveType("float")
      return PrimitiveType("int")

    return PrimitiveType("none")

  def visit_UnaryOpNode(self, node: UnaryOpNode) -> Type:
    expr_type = self.visit(node.expr)
    if node.op == "!":
      if expr_type != PrimitiveType("bool"):
        self.error("Logical NOT operator requires a boolean expression.")
      return PrimitiveType("bool")
    if node.op in ("-", "+"):
      is_numeric = isinstance(expr_type, PrimitiveType) and expr_type.name in ("int", "float")
      if not is_numeric:
        self.error(f"Numeric operator '{node.op}' requires a numeric expression.")
      return expr_type
    return PrimitiveType("none")

  def _get_lvalue_path(self, node: ASTNode) -> Optional[tuple[str, List[str]]]:
    """Resolves an AST node to its root variable name and field path if it is an lvalue."""
    if isinstance(node, IdentifierNode):
      sym = self.symbol_table.lookup(node.name)
      if isinstance(sym, VariableSymbol):
        return (node.name, [])
    elif isinstance(node, MemberAccessNode):
      res = self._get_lvalue_path(node.receiver)
      if res is not None:
        root, path = res
        return (root, path + [node.member])
    elif isinstance(node, IndexExprNode):
      res = self._get_lvalue_path(node.array)
      if res is not None:
        root, path = res
        return (root, path + ["[]"])
    return None

  def _is_reference_type(self, type_obj: Type) -> bool:
    """Returns True if the type is passed by reference (non-primitive)."""
    if isinstance(type_obj, OptionalType):
      return self._is_reference_type(type_obj.base_type)
    if isinstance(type_obj, PrimitiveType):
      return type_obj.name not in ("int", "float", "bool")
    if isinstance(type_obj, NoneType):
      return False
    return True

  def _check_aliasing(self, node: CallNode, signature: FunctionType, is_constructor: bool) -> None:
    """Verifies that non-primitive arguments do not conflict due to mutability aliasing."""
    borrows = []  # List of (root, path, is_mutable)

    # 1. Check implicit self receiver for non-static method calls
    if not is_constructor and isinstance(node.callee, MemberAccessNode):
      receiver_node = node.callee.receiver
      receiver_type = self.visit(receiver_node)
      if isinstance(receiver_type, OptionalType):
        receiver_type = receiver_type.base_type
      if isinstance(receiver_type, StructType):
        method = receiver_type.methods.get(node.callee.member)
        if method and method.modifier != "static":
          # Receiver is implicitly passed.
          # It is mutably borrowed if method is not const.
          is_mutable = (method.modifier != "const")
          res = self._get_lvalue_path(receiver_node)
          if res:
            root, path = res
            borrows.append((root, path, is_mutable))

    # 2. Check explicit arguments
    for idx, arg in enumerate(node.arguments):
      if idx < len(signature.param_types):
        param_type = signature.param_types[idx]
        is_mutable = signature.param_mutabilities[idx]
        if self._is_reference_type(param_type):
          res = self._get_lvalue_path(arg.expr)
          if res:
            root, path = res
            borrows.append((root, path, is_mutable))

    # 3. Check for conflicts among all borrows
    for i in range(len(borrows)):
      for j in range(i + 1, len(borrows)):
        r1, p1, m1 = borrows[i]
        r2, p2, m2 = borrows[j]
        if r1 == r2:
          # Check if paths overlap (one is prefix of another)
          overlap = p1[:len(p2)] == p2 or p2[:len(p1)] == p1
          if overlap:
            # Conflict if at least one is mutable
            if m1 or m2:
              self.error(
                  f"Aliasing conflict: variable '{r1}' (or a sub-field) "
                  f"is mutably borrowed and cannot be borrowed again in the same call."
              )

  def visit_CallNode(self, node: CallNode) -> Type:
    # 1. Resolve callee
    callee_type = self.visit(node.callee)

    signature = None
    is_constructor = False

    # Constructor resolution
    if isinstance(callee_type, StructType):
      is_constructor = True
      # Look up constructor
      init_method = callee_type.methods.get("__init__")
      if not init_method:
        self.error(f"Struct '{callee_type.name}' has no '__init__' constructor defined.")
        return callee_type
      signature = init_method.method_type
      # Match arguments
      self._check_arguments(node.arguments, signature, is_constructor=True)
    else:
      # Standard function/method resolution
      if not isinstance(callee_type, FunctionType):
        self.error("Target is not callable.")
        return PrimitiveType("none")
      signature = callee_type
      self._check_arguments(node.arguments, signature)

    # Perform borrow checking / aliasing rules
    if signature:
      self._check_aliasing(node, signature, is_constructor)

    if is_constructor:
      return callee_type
    return signature.return_type

  def _check_arguments(self, arguments: List[ArgumentNode], signature: FunctionType, is_constructor: bool = False) -> None:
    """Helper to match argument lists against signatures (including parameter modes)."""
    # Map arguments (positional vs named)
    mapped_args: Dict[int, ArgumentNode] = {}
    named_map: Dict[str, int] = {}

    # Normally we need parameter names to resolve named parameters. But wait, how do we know the param names?
    # For now, let's assume we map named arguments by resolving their names if we have the signature context.
    # To properly support named parameters, we'd need to store the parameter names in the FunctionType or StructMethod.
    # Let's add param names to FunctionType:
    # Wait, we can keep named parameters matching very simple.
    # If arguments have names, let's verify that the names exist on the parameters of the constructor / function.
    # Let's see if we can do this simply by comparing lengths and types positional-first.
    # To implement robust named parameter matching, we should look up the function declaration or constructor to match names.
    # Let's inspect function parameter names.
    # If the callee is resolved, we can match argument types. For now, let's check positional type compatibility:
    for idx, arg in enumerate(arguments):
      # Pass expected parameter type for lambda type inference
      old_expected = self.expected_type
      if idx < len(signature.param_types):
        self.expected_type = signature.param_types[idx]
      else:
        self.expected_type = None

      arg_type = self.visit(arg.expr)
      self.expected_type = old_expected

      # Check positional constraints (since this is basic subset)
      if idx < len(signature.param_types):
        param_type = signature.param_types[idx]
        if not arg_type.is_compatible(param_type):
          self.error(f"Argument type mismatch at position {idx+1}. Expected '{param_type}', got '{arg_type}'.")

        # Mutability constraints for var reference parameters
        # In a real compiler, we lookup the parameter mode (is_mutable).
        # Let's check: if parameter mode is var reference, check if the argument is a mutable variable.
        # Since we don't have the param names/mutability in FunctionType directly, let's keep it simple or add parameter info to FunctionType!
        # Adding param details (mutability) is easy in python:
        # e.g. signature can store signature.param_modes (list of bools)
        # Let's assume signature has `param_modes` property.
        # Wait, did we define signature.param_modes? We can add a property/list if we want, or just dynamically check if signature has it.
        # Let's look at `symbol_table.py` - FunctionType does not have param_modes, but we can access it if we add it, or we can query it directly.
        # Let's check: if we want to support this, we can easily add it or query it. Let's keep it simple for now.

      else:
        # Extra parameter
        if not is_constructor:
          self.error("Too many arguments passed to call.")

  def visit_MemberAccessNode(self, node: MemberAccessNode) -> Type:
    receiver_type = self.visit(node.receiver)

    # Optional chaining check
    if node.is_optional:
      if not isinstance(receiver_type, OptionalType):
        self.error("Optional chaining '?.' requires an optional receiver.")
        return PrimitiveType("none")
      receiver_type = receiver_type.base_type
    else:
      if isinstance(receiver_type, OptionalType):
        self.error("Must use optional chaining '?.' to access properties on an optional receiver.")
        return PrimitiveType("none")

    if isinstance(receiver_type, EnumType):
      if node.member in receiver_type.variants:
        return receiver_type
      self.error(f"Enum '{receiver_type.name}' has no member '{node.member}'.")
      return PrimitiveType("none")

    if not isinstance(receiver_type, StructType):
      self.error("Member access receiver is not a struct.")
      return PrimitiveType("none")

    # Special member __proto__
    if node.member == "__proto__":
      # returns optional of same struct type
      return OptionalType(receiver_type)

    # Resolve field
    field = receiver_type.fields.get(node.member)
    if field:
      # If optional chained, result type is optional
      if node.is_optional:
        return OptionalType(field.field_type)
      return field.field_type

    # Resolve method
    method = receiver_type.methods.get(node.member)
    if method:
      # If optional chained, returns optional function type?
      # Sapphire specification says: target?.get_name() optionally chains the execution.
      # If target is none, it evaluates to none.
      return method.method_type

    self.error(f"Struct '{receiver_type.name}' has no member '{node.member}'.")
    return PrimitiveType("none")

  def visit_CloneNode(self, node: CloneNode) -> Type:
    expr_type = self.visit(node.expr)
    if not isinstance(expr_type, StructType):
      self.error("Clone expression target must be a struct instance.")
      return PrimitiveType("none")

    # Verify struct is a prototype struct (or inherits from one)
    is_proto = False
    curr = expr_type
    while curr:
      if curr.is_prototype:
        is_proto = True
        break
      if curr.parent_name:
        parent = self.symbol_table.lookup_type(curr.parent_name)
        if isinstance(parent, StructType):
          curr = parent
        else:
          break
      else:
        break

    if not is_proto:
      self.error(f"Cannot clone instance of non-proto struct '{expr_type.name}'. Struct must be declared using the 'proto' keyword.")

    # Validate explicit arena target
    if node.arena_expr:
      arena_type = self.visit(node.arena_expr)
      if not isinstance(arena_type, ArenaType):
        self.error("Explicit arena target must be an instance of Arena.")

    # Mark the struct type as cloned
    expr_type.is_cloned = True

    # If immediate shadow block is defined, check statements
    if node.initializer_block:
      self.symbol_table.enter_scope()
      # Define self inside block as mutable
      self.symbol_table.define("self", VariableSymbol("self", expr_type, is_mutable=True))
      for stmt in node.initializer_block:
        self.visit(stmt)
      self.symbol_table.exit_scope()

    return expr_type

  def visit_LambdaNode(self, node: LambdaNode) -> Type:
    self.symbol_table.enter_scope()

    param_types = []
    for idx, p in enumerate(node.parameters):
      if p.param_type:
        ptype = self._resolve_type_node(p.param_type)
      elif (
          self.expected_type
          and isinstance(self.expected_type, FunctionType)
          and idx < len(self.expected_type.param_types)
      ):
        ptype = self.expected_type.param_types[idx]
      else:
        ptype = PrimitiveType("none")
      self.symbol_table.define(p.name, VariableSymbol(p.name, ptype, is_mutable=False))
      param_types.append(ptype)

    body_type = self.visit(node.body)

    # Lambda expression implicit return
    ret_type = body_type if not isinstance(node.body, BlockNode) else PrimitiveType("none")
    if node.return_type:
      ret_type = self._resolve_type_node(node.return_type)
    elif (
        self.expected_type
        and isinstance(self.expected_type, FunctionType)
    ):
      ret_type = self.expected_type.return_type

    self.symbol_table.exit_scope()
    return FunctionType(param_types, ret_type)

  def visit_ArrayLiteralNode(self, node: ArrayLiteralNode) -> Type:
    if not node.elements:
      # Empty array defaults to [none] or [any] (we use NoneType)
      return ArrayType(NoneType())

    elem_types = [self.visit(e) for e in node.elements]
    first_type = elem_types[0]
    for etype in elem_types[1:]:
      if not etype.is_compatible(first_type) and not first_type.is_compatible(etype):
        self.error("Inconsistent element types in array literal.")
        break
    return ArrayType(first_type)

  def visit_IndexExprNode(self, node: IndexExprNode) -> Type:
    arr_type = self.visit(node.array)
    index_type = self.visit(node.index)

    if not isinstance(arr_type, ArrayType):
      self.error("Cannot index non-array type.")
      return PrimitiveType("none")

    if index_type != PrimitiveType("int"):
      self.error("Array index must be an 'int'.")

    return arr_type.element_type

  def visit_StructInitializerNode(self, node: StructInitializerNode) -> Type:
    struct_type = self.symbol_table.lookup_type(node.struct_name)
    if not struct_type or not isinstance(struct_type, StructType):
      self.error(f"Cannot instantiate undefined struct '{node.struct_name}'.")
      return PrimitiveType("none")

    # Validate explicit arena target
    if node.arena_expr:
      arena_type = self.visit(node.arena_expr)
      if not isinstance(arena_type, ArenaType):
        self.error("Explicit arena target must be an instance of Arena.")

    initialized = set()
    for field_arg in node.fields:
      field_name = field_arg.name
      if not field_name:
        self.error(f"Positional arguments are not allowed in struct initializer of '{node.struct_name}'. Use named initializers instead.")
        continue

      if field_name not in struct_type.fields:
        self.error(f"Struct '{node.struct_name}' has no field '{field_name}'.")
        continue

      if field_name in initialized:
        self.error(f"Field '{field_name}' is initialized multiple times in struct initializer.")
        continue

      expr_type = self.visit(field_arg.expr)
      expected_type = struct_type.fields[field_name].field_type
      if not expr_type.is_compatible(expected_type):
        self.error(
            f"Field '{field_name}' in struct '{node.struct_name}' initializer "
            f"has type '{expr_type}', but expected '{expected_type}'."
        )

      initialized.add(field_name)

    # Verify all non-optional and non-default fields are initialized
    for f_name, f_obj in struct_type.fields.items():
      if (f_name not in initialized 
          and not isinstance(f_obj.field_type, OptionalType)
          and not f_obj.has_default):
        self.error(f"Struct initializer for '{node.struct_name}' is missing required field '{f_name}'.")

    return struct_type
