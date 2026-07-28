"""Semantic tokens extraction and LSP delta encoding for Sapphire.

This module subclass the Sapphire TypeChecker to gather semantic symbols during the
type-checking pass and converts them into the 5-integer delta-encoded format required
by the Language Server Protocol.
"""

from typing import List, Tuple, Optional

try:
  from parser.ast import ASTNode
  from semantics.type_checker import TypeChecker
  from semantics.symbol_table import VariableSymbol, FunctionSymbol, StructSymbol, TraitSymbol, EnumSymbol, EnumType, ModuleSymbol, ModuleType
except ImportError:  # pragma: no cover
  from src.parser.ast import ASTNode
  from src.semantics.type_checker import TypeChecker
  from src.semantics.symbol_table import VariableSymbol, FunctionSymbol, StructSymbol, TraitSymbol, EnumSymbol, EnumType, ModuleSymbol, ModuleType

# Legend mappings for the LSP client
TOKEN_TYPES = [
    "type",         # 0
    "class",        # 1
    "struct",       # 2
    "interface",    # 3
    "parameter",    # 4
    "variable",     # 5
    "property",     # 6
    "function",     # 7
    "method",       # 8
    "keyword",      # 9
    "enum",         # 10
    "enumMember",   # 11
    "decorator",    # 12
]

TOKEN_MODIFIERS = [
    "declaration",  # 1 << 0 = 1
    "static",       # 1 << 1 = 2
    "readonly",     # 1 << 2 = 4
    "modification", # 1 << 3 = 8
]


def extract_comments_above(doc_text: str, start_line: Optional[int]) -> str:
  """Extracts comments directly above start_line (1-based)."""
  if start_line is None:
    return ""
  lines = doc_text.splitlines()
  idx = start_line - 1
  if idx <= 0:
    return ""

  comments = []
  idx -= 1

  in_block_comment = False
  block_comment_lines = []

  while idx >= 0:
    line = lines[idx].strip()

    if not line and not in_block_comment:
      break

    if line.endswith("*/"):
      in_block_comment = True
      block_comment_lines.insert(0, lines[idx])
      if line.startswith("/*"):
        in_block_comment = False
      idx -= 1
      continue

    if in_block_comment:
      block_comment_lines.insert(0, lines[idx])
      if line.startswith("/*"):
        in_block_comment = False
      idx -= 1
      continue

    if line.startswith("//"):
      comment_content = line[2:].strip()
      comments.insert(0, comment_content)
      idx -= 1
    else:
      break

  if block_comment_lines:
    block_text = "\n".join(block_comment_lines).strip()
    if block_text.startswith("/*") and block_text.endswith("*/"):
      block_content = block_text[2:-2].strip()
      cleaned_lines = []
      for line in block_content.splitlines():
        line = line.strip()
        if line.startswith("*"):
          line = line[1:].strip()
        cleaned_lines.append(line)
      return "\n".join(cleaned_lines)

  if comments:
    return "\n".join(comments)

  return ""


class SemanticTokensTypeChecker(TypeChecker):
  """Subclass of TypeChecker that extracts semantic tokens during analysis."""

  def __init__(self, doc_text: Optional[str] = None):
    super().__init__()
    self.doc_text = doc_text
    # List of raw tokens: (line, column, length, token_type, modifier_bitmask)
    self.raw_tokens: List[Tuple[int, int, int, str, int]] = []
    self.current_node: Optional[ASTNode] = None
    self.lsp_errors: List[dict] = []
    self.node_types: dict = {}
    self.current_trait: Optional[Any] = None

  def visit(self, node: ASTNode) -> Any:
    old_node = self.current_node
    self.current_node = node
    try:
      res = super().visit(node)
      if res is not None:
        self.node_types[node] = res
      return res
    finally:
      self.current_node = old_node

  def generic_visit(self, node: ASTNode) -> Any:
    # Safely traverse sub-nodes for semantic token generation without raising NotImplementedError
    for key, value in node.__dict__.items():
      if isinstance(value, ASTNode):
        self.visit(value)
      elif isinstance(value, list):  # pragma: no cover
        for item in value:
          if isinstance(item, ASTNode):
            self.visit(item)
    return None

  def _resolve_type_node(self, node: Optional[ASTNode]) -> Any:
    if node:
      self.visit(node)
    res = super()._resolve_type_node(node)
    if node and res:
      self.node_types[node] = res
    return res

  def error(self, message: str) -> None:
    # Use position from current_node if available
    node = self.current_node
    line = 1
    col = 0
    length = 1
    if node is not None:
      if getattr(node, "start_line", None) is not None:
        line = node.start_line
      if getattr(node, "start_column", None) is not None:
        col = node.start_column
      if getattr(node, "length", None) is not None:
        length = node.length

    diagnostic = {
        "range": {
            "start": {"line": line - 1, "character": col},
            "end": {"line": line - 1, "character": col + length},
        },
        "message": message,
        "severity": 1,  # Error
        "source": "sapphire-semantic",
    }
    self.lsp_errors.append(diagnostic)
    super().error(message)

  def add_token(self, line: Optional[int], col: Optional[int], length: Optional[int], token_type: str, modifiers: int = 0) -> None:
    """Adds a raw semantic token if the positioning info is valid."""
    if line is not None and col is not None and length is not None and length > 0:
      self.raw_tokens.append((line, col, length, token_type, modifiers))

  def visit_ProgramNode(self, node) -> None:
    for imp in getattr(node, "imports", []):
      self.visit(imp)
    if getattr(node, "export_block", None):
      self.visit(node.export_block)
    super().visit_ProgramNode(node)

  def visit_ImportStmtNode(self, node) -> None:
    alias_name = node.alias if node.alias else node.path.split(".")[-1]
    sym = self.symbol_table.lookup(alias_name)
    if sym:
      self.node_types[node] = sym.symbol_type

  def visit_ExportStmtNode(self, node) -> None:
    for spec in node.specifiers:
      if spec.module_prefix:
        mod_sym = self.symbol_table.lookup(spec.module_prefix)
        if isinstance(mod_sym, ModuleSymbol):
          exp_sym = mod_sym.lookup_export(spec.symbol)
          if exp_sym is not None:
            val_type = getattr(exp_sym, "symbol_type", exp_sym)
            self.node_types[spec] = val_type
      else:
        sym = self.symbol_table.lookup(spec.symbol) or self.symbol_table.lookup_type(spec.symbol)
        if sym is not None:
          val_type = getattr(sym, "symbol_type", sym)
          self.node_types[spec] = val_type

  def visit_StructDeclNode(self, node) -> None:
    # Struct name declaration
    self.add_token(node.name_line, node.name_column, node.name_length, "struct", 1)  # declaration
    if node.parent_name:
      self.add_token(node.parent_name_line, node.parent_name_column, node.parent_name_length, "struct")
    
    struct_type = self.symbol_table.lookup_type(node.name)
    old_struct = self.current_struct
    self.current_struct = struct_type
    try:
      for field in node.fields:
        self.visit(field)
    finally:
      self.current_struct = old_struct

    super().visit_StructDeclNode(node)
    if struct_type and self.doc_text:
      comments = extract_comments_above(self.doc_text, getattr(node, "start_line", None))
      if comments:
        struct_type.comments = comments

  def visit_StructFieldNode(self, node) -> None:
    # Field declaration
    mods = 1  # declaration
    if not node.is_mutable:
      mods |= 4  # readonly
    self.add_token(node.name_line, node.name_column, node.name_length, "property", mods)
    if self.current_struct and node.name in self.current_struct.fields:
      field = self.current_struct.fields[node.name]
      if self.doc_text:
        comments = extract_comments_above(self.doc_text, getattr(node, "start_line", None))
        if comments:
          field.comments = comments
      self.node_types[node] = field.field_type

  def visit_TraitDeclNode(self, node) -> None:
    # Trait name declaration
    self.add_token(node.name_line, node.name_column, node.name_length, "interface", 1)
    
    trait_type = self.symbol_table.lookup_type(node.name)
    old_trait = self.current_trait
    self.current_trait = trait_type
    try:
      for member in node.members:
        self.visit(member)
    finally:
      self.current_trait = old_trait

    super().visit_TraitDeclNode(node)
    if trait_type and self.doc_text:
      comments = extract_comments_above(self.doc_text, getattr(node, "start_line", None))
      if comments:
        trait_type.comments = comments

  def visit_TraitMemberNode(self, node) -> None:
    # Trait method declaration
    self.add_token(node.name_line, node.name_column, node.name_length, "method", 1)
    if self.current_trait and node.name in self.current_trait.methods:
      method_type = self.current_trait.methods[node.name]
      if self.doc_text:
        comments = extract_comments_above(self.doc_text, getattr(node, "start_line", None))
        if comments:
          method_type.comments = comments
      self.node_types[node] = method_type

  def visit_EnumDeclNode(self, node) -> None:
    # Enum name declaration
    self.add_token(node.name_line, node.name_column, node.name_length, "enum", 1)
    enum_type = self.symbol_table.lookup_type(node.name)
    old_enum = getattr(self, "current_enum", None)
    self.current_enum = enum_type
    try:
      for member in node.members:
        self.visit(member)
    finally:
      self.current_enum = old_enum

    super().visit_EnumDeclNode(node)
    if enum_type and self.doc_text:
      comments = extract_comments_above(self.doc_text, getattr(node, "start_line", None))
      if comments:
        enum_type.comments = comments

  def visit_EnumMemberNode(self, node) -> None:
    # Enum member declaration (readonly)
    self.add_token(node.name_line, node.name_column, node.name_length, "enumMember", 1 | 4)
    if getattr(self, "current_enum", None):
      self.node_types[node] = self.current_enum

  def visit_AnnotationNode(self, node) -> None:
    at_line = getattr(node, "at_line", None)
    at_col = getattr(node, "at_column", None)
    if at_line is not None and at_col is not None:
      self.add_token(at_line, at_col, 1, "decorator")
    line = getattr(node, "line", None)
    col = getattr(node, "column", None)
    length = getattr(node, "length", None)
    if line is not None and col is not None and length is not None:
      self.add_token(line, col, length, "decorator")

  def visit_FuncDeclNode(self, node) -> None:
    for ann in getattr(node, "annotations", []):
      self.visit(ann)
    # Function declaration (only highlight if not a method; methods are handled by ImplMemberNode)
    is_method = self.current_struct is not None
    if not is_method:
      self.add_token(node.name_line, node.name_column, node.name_length, "function", 1)
    for p in node.parameters:
      self.visit(p)
    super().visit_FuncDeclNode(node)
    if not is_method:
      sym = self.symbol_table.lookup(node.name)
      if sym:
        try:
          from semantics.symbol_table import FunctionType
        except ImportError:  # pragma: no cover
          from src.semantics.symbol_table import FunctionType
        if isinstance(sym.symbol_type, FunctionType) and self.doc_text:
          comments = extract_comments_above(self.doc_text, getattr(node, "start_line", None))
          if comments:
            sym.symbol_type.comments = comments
        self.node_types[node] = sym.symbol_type

  def visit_ImplMemberNode(self, node) -> None:
    # Method declaration
    mods = 1  # declaration
    if node.modifier == "static":
      mods |= 2  # static
    self.add_token(node.func_decl.name_line, node.func_decl.name_column, node.func_decl.name_length, "method", mods)
    for p in node.func_decl.parameters:
      self.visit(p)
    super().visit_ImplMemberNode(node)
    if self.current_struct and node.func_decl.name in self.current_struct.methods:
      method_type = self.current_struct.methods[node.func_decl.name].method_type
      try:
        from semantics.symbol_table import FunctionType
      except ImportError:  # pragma: no cover
        from src.semantics.symbol_table import FunctionType
      if isinstance(method_type, FunctionType) and self.doc_text:
        comments = extract_comments_above(self.doc_text, getattr(node.func_decl, "start_line", None))
        if comments:
          method_type.comments = comments
      self.node_types[node.func_decl] = method_type

  def visit_ParameterNode(self, node) -> None:
    mods = 1
    if not node.is_mutable:
      mods |= 4
    self.add_token(node.name_line, node.name_column, node.name_length, "parameter", mods)
    # No parent visitor exists for parameters

  def visit_VarDeclNode(self, node) -> None:
    for ann in getattr(node, "annotations", []):
      self.visit(ann)
    mods = 1
    if not node.is_mutable:
      mods |= 4
    self.add_token(node.name_line, node.name_column, node.name_length, "variable", mods)
    super().visit_VarDeclNode(node)
    sym = self.symbol_table.lookup(node.name)
    if sym:
      self.node_types[node] = sym.symbol_type

  def visit_AssignmentNode(self, node) -> None:
    self.visit(node.target)
    super().visit_AssignmentNode(node)

  def visit_IfNode(self, node) -> None:
    if node.init_binding:
      # Add semantic token for let_name
      mods = 1 | 4  # declaration | readonly
      self.add_token(node.init_binding.let_name_line, node.init_binding.let_name_column, node.init_binding.let_name_length, "variable", mods)
      # Calculate unwrapped type for hover info
      expr_type = self.visit(node.init_binding.expr)
      try:
        from semantics.symbol_table import OptionalType
      except ImportError:  # pragma: no cover
        from src.semantics.symbol_table import OptionalType
      if node.init_binding.is_unwrap and isinstance(expr_type, OptionalType):
        unwrapped_type = expr_type.base_type
      else:
        unwrapped_type = expr_type
      self.node_types[node.init_binding] = unwrapped_type

    super().visit_IfNode(node)

  def visit_WhileNode(self, node) -> None:
    if node.init_binding:
      # Add semantic token for let_name
      mods = 1 | 4  # declaration | readonly
      self.add_token(node.init_binding.let_name_line, node.init_binding.let_name_column, node.init_binding.let_name_length, "variable", mods)
      # Calculate unwrapped type for hover info
      expr_type = self.visit(node.init_binding.expr)
      try:
        from semantics.symbol_table import OptionalType
      except ImportError:  # pragma: no cover
        from src.semantics.symbol_table import OptionalType
      if node.init_binding.is_unwrap and isinstance(expr_type, OptionalType):
        unwrapped_type = expr_type.base_type
      else:
        unwrapped_type = expr_type
      self.node_types[node.init_binding] = unwrapped_type

    super().visit_WhileNode(node)

  def visit_ForNode(self, node) -> None:
    # Add semantic token for loop_var
    mods = 1  # declaration
    if not node.is_mutable:
      mods |= 4  # readonly
    self.add_token(node.loop_var_line, node.loop_var_column, node.loop_var_length, "variable", mods)
    # Calculate loop var element type for hover info
    iter_type = self.visit(node.iterable)
    try:
      from semantics.symbol_table import ArrayType, PrimitiveType
    except ImportError:  # pragma: no cover
      from src.semantics.symbol_table import ArrayType, PrimitiveType
    if isinstance(iter_type, ArrayType):
      elem_type = iter_type.element_type
    else:
      elem_type = PrimitiveType("none")
    self.node_types[node] = elem_type

    super().visit_ForNode(node)

  def visit_IdentifierNode(self, node) -> None:
    # Variable or symbol reference
    sym = self.symbol_table.lookup(node.name)
    if sym:
      if isinstance(sym, StructSymbol):
        self.add_token(node.name_line, node.name_column, node.name_length, "struct")
      elif isinstance(sym, TraitSymbol):
        self.add_token(node.name_line, node.name_column, node.name_length, "interface")
      elif isinstance(sym, FunctionSymbol):
        self.add_token(node.name_line, node.name_column, node.name_length, "function")
      elif isinstance(sym, VariableSymbol):
        mods = 0
        if not sym.is_mutable:
          mods |= 4
        token_type = "parameter" if sym.is_parameter else "variable"
        self.add_token(node.name_line, node.name_column, node.name_length, token_type, mods)
    return super().visit_IdentifierNode(node)

  def visit_MemberAccessNode(self, node):
    # Member lookup
    receiver_type = self.visit(node.receiver)
    token_type = "property"
    mods = 0
    if receiver_type:
      if hasattr(receiver_type, "methods") and node.member in receiver_type.methods:
        token_type = "method"
      elif hasattr(receiver_type, "fields") and node.member in receiver_type.fields:
        token_type = "property"
        field = receiver_type.fields[node.member]
        if not getattr(field, "is_mutable", True):
          mods |= 4
    self.add_token(node.member_line, node.member_column, node.member_length, token_type, mods)
    return super().visit_MemberAccessNode(node)

  def visit_StructInitializerNode(self, node):
    # Struct initializer constructor name
    self.add_token(node.name_line, node.name_column, node.name_length, "struct")
    return super().visit_StructInitializerNode(node)

  def visit_BasicTypeNode(self, node):
    # Type reference
    if node.name not in ("int", "float", "bool", "string", "none", "void"):
      from semantics.symbol_table import TraitType
      resolved = self.symbol_table.lookup_type(node.name)
      if resolved and isinstance(resolved, TraitType):
        self.add_token(node.name_line, node.name_column, node.name_length, "interface")
      else:
        self.add_token(node.name_line, node.name_column, node.name_length, "struct")
    else:
      self.add_token(node.name_line, node.name_column, node.name_length, "type")
    return None


def encode_semantic_tokens(raw_tokens: List[Tuple[int, int, int, str, int]]) -> List[int]:
  """Converts absolute token coordinate tuples into delta-encoded LSP format."""
  # 1. Map absolute ANTLR coordinates (1-based lines, 0-based columns) to LSP (0-based lines)
  valid_tokens = []
  for line, col, length, type_str, mods in raw_tokens:
    if line is not None and col is not None and length is not None:
      valid_tokens.append((line - 1, col, length, type_str, mods))

  # 2. Sort tokens: primary key = line, secondary key = column
  valid_tokens.sort(key=lambda t: (t[0], t[1]))

  # 3. Deduplicate tokens sharing the same start position
  unique_tokens = []
  last_pos = None
  for t in valid_tokens:
    pos = (t[0], t[1])
    if pos != last_pos:
      unique_tokens.append(t)
      last_pos = pos

  # 4. Generate delta-encoded array
  delta_tokens: List[int] = []
  last_line = 0
  last_col = 0

  for line, col, length, type_str, mods in unique_tokens:
    type_idx = TOKEN_TYPES.index(type_str) if type_str in TOKEN_TYPES else 0
    if line == last_line:
      delta_line = 0
      delta_start = col - last_col
    else:
      delta_line = line - last_line
      delta_start = col

    delta_tokens.extend([delta_line, delta_start, length, type_idx, mods])
    last_line = line
    last_col = col

  return delta_tokens


def find_node_at_position(node: ASTNode, line: int, col: int) -> Optional[ASTNode]:
  """Recursively finds the most specific AST node containing (line, col).

  Line is 1-based, col is 0-based.
  """
  if getattr(node, "start_line", None) is None or getattr(node, "end_line", None) is None:
    return None

  # Check if line is within the node's line boundaries
  if node.start_line <= line <= node.end_line:
    # Check column boundary on start line
    if line == node.start_line and col < node.start_column:
      return None
    # Check column boundary on end line
    if line == node.end_line and col > node.end_column:
      return None

    # Recursively check children for a tighter match
    for key, value in node.__dict__.items():
      if key in ("current_node", "lsp_errors", "raw_tokens", "node_types"):
        continue
      if isinstance(value, ASTNode):
        found = find_node_at_position(value, line, col)
        if found:
          return found
      elif isinstance(value, list):
        for item in value:
          if isinstance(item, ASTNode):
            found = find_node_at_position(item, line, col)
            if found:
              return found

    return node
  return None
