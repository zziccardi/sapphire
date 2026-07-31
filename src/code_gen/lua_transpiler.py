"""Code generator to transpile Sapphire AST into executable Lua 5.1 code.

This module implements an AST visitor that formats and outputs Lua 5.1 code
corresponding to the semantic behavior of Sapphire, including a runtime header
for prototypal inheritance delegation and Arena memory management.
"""

import os
import sys
from typing import Any, Dict, List, Optional, Set

from antlr4 import FileStream, CommonTokenStream
from antlr4.error.ErrorListener import ErrorListener

try:
  from parser.ast import *
  from parser.gen.SapphireLexer import SapphireLexer
  from parser.gen.SapphireParser import SapphireParser
  from parser.ast_builder import ASTBuilder
  from semantics.type_checker import TypeChecker, SemanticError
  from semantics.symbol_table import MapType
except ModuleNotFoundError:  # pragma: no cover
  from src.parser.ast import *
  from src.parser.gen.SapphireLexer import SapphireLexer
  from src.parser.gen.SapphireParser import SapphireParser
  from src.parser.ast_builder import ASTBuilder
  from src.semantics.type_checker import TypeChecker, SemanticError
  from src.semantics.symbol_table import MapType


# ==========================================
# Sapphire Lua 5.1 Runtime Preamble
# ==========================================

LUA_RUNTIME_PREAMBLE = """-- Sapphire Lua 5.1 Runtime Header

local Arena = {}
Arena.__index = Arena

function Arena.init()
  local self = setmetatable({}, Arena)
  self.objects = {}
  return self
end

function Arena:register(obj)
  if type(obj) == "table" then
    local meta = getmetatable(obj)
    if meta and meta.__arena and meta.__arena ~= self then
      for i, o in ipairs(meta.__arena.objects) do
        if o == obj then
          table.remove(meta.__arena.objects, i)
          break
        end
      end
    end
    table.insert(self.objects, obj)
    if meta then
      meta.__arena = self
    end
  end
  return obj
end

function Arena:destroy()
  for _, obj in ipairs(self.objects) do
    local meta = getmetatable(obj)
    if meta and meta.__shadow then
      for k in pairs(meta.__shadow) do
        meta.__shadow[k] = nil
      end
    end
  end
  self.objects = {}
end

local _DEFAULT_ARENA = Arena.init()

local _clone_helper

local _create_cow_proxy
_create_cow_proxy = function(parent_shadow, parent_proto, key)
  local proxy_meta = {}
  proxy_meta.__index = function(tbl, sub_key)
    if parent_shadow[key] ~= nil then
      return parent_shadow[key][sub_key]
    end
    if parent_proto and parent_proto[key] ~= nil then
      local val = parent_proto[key][sub_key]
      if type(val) == "table" then
        return _create_cow_proxy(parent_shadow, parent_proto[key], sub_key)
      end
      return val
    end
    return nil
  end
  proxy_meta.__newindex = function(tbl, sub_key, value)
    if parent_shadow[key] == nil then
      local target = parent_proto[key]
      parent_shadow[key] = _clone_helper(target, nil, nil)
    end
    parent_shadow[key][sub_key] = value
  end
  return setmetatable({}, proxy_meta)
end

local function _create_proto_object(proto, class_tbl)
  local shadow = {}
  local meta = {}
  meta.__shadow = shadow
  meta.__proto = proto
  meta.__class = class_tbl
  meta.__index = function(tbl, key)
    if key == "__proto__" then return meta.__proto end
    if key == "__shadow__" then return meta.__shadow end
    if shadow[key] ~= nil then return shadow[key] end
    if proto ~= nil then
      local val = proto[key]
      if val ~= nil then
        if type(val) == "table" then
          return _create_cow_proxy(shadow, proto, key)
        end
        return val
      end
    end
    if class_tbl and class_tbl[key] ~= nil then
      return class_tbl[key]
    end
    return nil
  end
  meta.__newindex = function(tbl, key, val)
    if key == "__proto__" or key == "__shadow__" then return end
    if proto ~= nil then
      shadow[key] = val
    else
      rawset(tbl, key, val)
    end
  end
  local obj = setmetatable({}, meta)
  if proto == nil then
    _DEFAULT_ARENA:register(obj)
  end
  return obj
end

_clone_helper = function(obj, init_fn, arena)
  if obj == nil then return nil end
  local clone_obj
  if type(obj) == "table" then
    local meta = getmetatable(obj)
    if obj.clone and type(obj.clone) == "function" then
      clone_obj = obj:clone()
    elseif meta and meta.__class then
      clone_obj = _create_proto_object(obj, meta.__class)
    else
      clone_obj = _create_proto_object(obj, nil)
    end
  else
    clone_obj = obj
  end
  if arena ~= nil and type(clone_obj) == "table" then
    arena:register(clone_obj)
  end
  if init_fn then
    init_fn(clone_obj)
  end
  return clone_obj
end
"""


class LuaTranspiler:
  """AST visitor to transpile Sapphire code to Lua 5.1."""

  def __init__(self):
    self.code: List[str] = []
    self.indent_level = 0
    # Map struct names to their collected method AST nodes from impl blocks
    self.struct_methods: Dict[str, List[Any]] = {}
    self.known_structs: Set[str] = set()
    self.arena_stack: List[List[str]] = []
    self._identifier_map: Dict[str, str] = {}

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

  def get_output(self) -> str:
    """Returns the final generated Lua 5.1 source code string."""
    return "".join(self.code)

  def transpile(self, program: ProgramNode) -> str:
    """Main entry point to transpile a Sapphire ProgramNode to Lua 5.1."""
    # 1. Output runtime preamble
    self.emit(LUA_RUNTIME_PREAMBLE)
    self.newline()

    # 1b. Transpile module imports
    for imp in getattr(program, "imports", []):
      self.visit(imp)

    # 2. Collect known struct names and impl block methods
    for decl in program.declarations:
      if getattr(decl, "type_params", None):
        continue
      if isinstance(decl, StructDeclNode):
        self.known_structs.add(decl.name)
      elif isinstance(decl, ImplBlockNode):
        if decl.struct_name not in self.struct_methods:
          self.struct_methods[decl.struct_name] = []
        self.struct_methods[decl.struct_name].extend(decl.members)

    struct_decls = []
    func_decls = []
    executable_stmts = []
    has_main = False

    for decl in program.declarations:
      if getattr(decl, "type_params", None):
        continue
      if isinstance(decl, ImplBlockNode):
        continue
      elif isinstance(decl, FuncDeclNode):
        if decl.name == "main":
          has_main = True
        func_decls.append(decl)
      elif isinstance(decl, (StructDeclNode, EnumDeclNode, TraitDeclNode,
                             VarDeclNode)):
        struct_decls.append(decl)
      else:
        executable_stmts.append(decl)

    forward_names = []
    for decl in struct_decls:
      if isinstance(decl, StructDeclNode):
        forward_names.append(decl.name)
    for decl in func_decls:
      if not any(a.name == "export" for a in getattr(decl, "annotations", [])):
        forward_names.append(decl.name)

    if forward_names:
      self.emit(f"local {', '.join(forward_names)}")
      self.newline()

    top_level_decls = struct_decls + func_decls

    # 3. Transpile all top-level declarations (types, functions, global variables)
    for decl in top_level_decls:
      self.visit(decl)
      self.newline()

    # 4. Transpile executable top-level statements and main invocation
    for stmt in executable_stmts:
      self.visit(stmt)
      self.newline()

    if has_main:
      self.emit("main()")
      self.newline()

    # 5. Transpile export manifest module return table _M
    if getattr(program, "export_block", None):
      self.visit(program.export_block)

    return self.get_output()

  # ==========================================
  # Visitor Dispatcher
  # ==========================================

  def visit(self, node: ASTNode) -> None:
    """Visit an AST node and emit its corresponding Lua code."""
    method_name = f"visit_{node.__class__.__name__}"
    visitor = getattr(self, method_name, self.generic_visit)
    visitor(node)

  def generic_visit(self, node: ASTNode) -> None:
    raise NotImplementedError(
      f"Lua Transpilation for visitor visit_{node.__class__.__name__}"
      f" is not implemented.")

  # ==========================================
  # Declarations Visitor
  # ==========================================

  def visit_EnumDeclNode(self, node: EnumDeclNode) -> None:
    self.newline()
    self.emit(f"local {node.name} = {{")
    self.indent()
    current_val: Union[int, str] = 0
    is_string_enum = any(isinstance(m.value, str) for m in node.members)
    for idx, member in enumerate(node.members):
      if member.value is not None:
        current_val = member.value
      elif is_string_enum and isinstance(current_val, str):
        current_val = member.name
      self.newline()
      if isinstance(current_val, str):
        self.emit(f'{member.name} = "{current_val}"')
      else:
        self.emit(f"{member.name} = {current_val}")
        current_val += 1
      if idx < len(node.members) - 1:
        self.emit(",")
    self.dedent()
    self.newline()
    self.emit("}")
    self.newline()

  def visit_ImportStmtNode(self, node: ImportStmtNode) -> None:
    alias_name = node.alias if node.alias else node.path.split(".")[-1]
    self.emit(f"local {alias_name} = require(\"{node.path}\")")
    self.newline()

  def visit_ExportStmtNode(self, node: ExportStmtNode) -> None:
    self.newline()
    self.emit("local _M = {}")
    self.newline()
    for spec in node.specifiers:
      exp_name = spec.exported_name
      if spec.module_prefix:
        self.emit(f"_M.{exp_name} = {spec.module_prefix}.{spec.symbol}")
      else:
        self.emit(f"_M.{exp_name} = {spec.symbol}")
      self.newline()
    self.emit("return _M")
    self.newline()

  def visit_StructDeclNode(self, node: StructDeclNode) -> None:
    # Header definition for struct
    self.known_structs.add(node.name)
    is_proto = node.is_prototype
    struct_name = node.name
    methods = self.struct_methods.get(struct_name, [])

    self.newline()
    self.emit(f"{struct_name} = {{}}")
    self.newline()
    self.emit(f"{struct_name}.__index = {struct_name}")
    self.newline()

    # Define constructor `.init(...)`
    self.emit(f"function {struct_name}.init(kwargs, proto)")
    self.indent()
    self.newline()
    self.emit("kwargs = kwargs or {}")
    self.newline()
    self.emit("local self")
    self.newline()
    if is_proto:
      self.emit(f"self = _create_proto_object(proto, {struct_name})")
    else:
      self.emit(f"self = setmetatable({{}}, {struct_name})")

    self.newline()
    self.emit("if proto == nil then")
    self.indent()
    for f in node.fields:
      if f.default_expr:
        self.newline()
        temp = LuaTranspiler()
        temp.known_structs = self.known_structs
        temp.visit(f.default_expr)
        self.emit(f"self.{f.name} = {temp.get_output()}")
    self.dedent()
    self.newline()
    self.emit("end")
    self.newline()

    self.emit("for k, v in pairs(kwargs) do")
    self.indent()
    self.newline()
    self.emit("self[k] = v")
    self.dedent()
    self.newline()
    self.emit("end")

    init_member = next((m for m in methods if m.func_decl.name == "__init__"), None)
    if init_member:
      init_args = []
      for idx, p in enumerate(init_member.func_decl.parameters):
        init_args.append(f"(kwargs['{p.name}'] ~= nil and kwargs['{p.name}'] or kwargs[{idx + 1}])")
      call_args = ["self"] + init_args
      self.newline()
      self.emit(f"if {struct_name}._init_sapphire then")
      self.indent()
      self.newline()
      self.emit(f"{struct_name}._init_sapphire({', '.join(call_args)})")
      self.dedent()
      self.newline()
      self.emit("end")

    self.newline()
    self.emit("return self")
    self.dedent()
    self.newline()
    self.emit("end")
    self.newline()

    # Emit methods from impl block
    for m in methods:
      self._visit_ImplMemberNode_for_struct(m, struct_name)

  def visit_StructFieldNode(self, node: StructFieldNode) -> None:
    pass

  def _visit_ImplMemberNode_for_struct(self, node: ImplMemberNode,
                                       struct_name: str) -> None:
    func = node.func_decl
    func_name = "_init_sapphire" if func.name == "__init__" else func.name
    self.newline()

    if node.modifier == "static":
      params = [p.name for p in func.parameters]
      self.emit(f"function {struct_name}.{func_name}({', '.join(params)})")
    else:
      params = ["self"] + [p.name for p in func.parameters]
      self.emit(f"function {struct_name}:{func_name}({', '.join(params[1:])})")

    self.indent()
    for p in func.parameters:
      if p.default_expr:
        self.newline()
        temp = LuaTranspiler()
        temp.known_structs = self.known_structs
        temp.visit(p.default_expr)
        self.emit(f"if {p.name} == nil then {p.name} = {temp.get_output()} end")
    self.visit(func.body)
    self.dedent()
    self.newline()
    self.emit("end")
    self.newline()

  def visit_TraitDeclNode(self, node: TraitDeclNode) -> None:
    # Traits are compile-time contracts erased at runtime
    pass

  def visit_FuncDeclNode(self, node: FuncDeclNode) -> None:
    export_ann = next((a for a in node.annotations if a.name == "export"), None)
    params = [p.name for p in node.parameters]

    self.newline()
    if export_ann:
      target_path = export_ann.arg if export_ann.arg else node.name
      self.emit(f"function {target_path}({', '.join(params)})")
    else:
      self.emit(f"function {node.name}({', '.join(params)})")

    self.indent()
    # Check default parameters
    for p in node.parameters:
      if p.default_expr:
        self.newline()
        temp = LuaTranspiler()
        temp.known_structs = self.known_structs
        temp.visit(p.default_expr)
        self.emit(f"if {p.name} == nil then {p.name} = {temp.get_output()} end")
    self.visit(node.body)
    self.dedent()
    self.newline()
    self.emit("end")
    self.newline()

  # ==========================================
  # Statements Visitor
  # ==========================================

  def visit_BlockNode(self, node: BlockNode) -> None:
    self.arena_stack.append([])
    if not node.statements:
      self.newline()
      self.emit("-- pass")
    else:
      for stmt in node.statements:
        self.visit(stmt)

    current_arenas = self.arena_stack.pop()
    has_returned = bool(node.statements and isinstance(node.statements[-1], ReturnNode))
    if not has_returned:
      for arena_name in reversed(current_arenas):
        self.newline()
        self.emit(f"{arena_name}:destroy()")

  def visit_VarDeclNode(self, node: VarDeclNode) -> None:
    if any(a.name == "extern" for a in node.annotations):
      return

    if len(node.names) == 1 and node.expr:
      is_arena = (
          isinstance(node.expr, CallNode)
          and isinstance(node.expr.callee, IdentifierNode)
          and node.expr.callee.name == "Arena"
      )
      if is_arena and self.arena_stack:
        self.arena_stack[-1].append(node.names[0])

    expr_vars = []
    for expr in node.exprs:
      if isinstance(expr, MatchExprNode):
        expr_vars.append(self._emit_match_statement(expr))
      else:
        expr_vars.append(None)

    self.newline()
    names_str = ", ".join(node.names)
    self.emit(f"local {names_str}")
    if node.exprs:
      self.emit(" = ")
      for idx, expr in enumerate(node.exprs):
        if idx > 0:
          self.emit(", ")
        if expr_vars[idx]:
          self.emit(expr_vars[idx])
        else:
          self.visit(expr)

  def visit_AssignmentNode(self, node: AssignmentNode) -> None:
    expr_vars = []
    for expr in node.exprs:
      if isinstance(expr, MatchExprNode):
        expr_vars.append(self._emit_match_statement(expr))
      else:
        expr_vars.append(None)

    self.newline()
    if node.op == "=":
      for idx, target in enumerate(node.targets):
        if idx > 0:
          self.emit(", ")
        self.visit(target)
      self.emit(" = ")
      for idx, expr in enumerate(node.exprs):
        if idx > 0:
          self.emit(", ")
        if expr_vars[idx]:
          self.emit(expr_vars[idx])
        else:
          self.visit(expr)
    else:
      raw_op = node.op[:-1]
      self.visit(node.target)
      self.emit(" = ")
      self.visit(node.target)
      self.emit(f" {raw_op} ")
      if expr_vars[0]:
        self.emit(expr_vars[0])
      else:
        self.visit(node.expr)

  def visit_ExprStmtNode(self, node: ExprStmtNode) -> None:
    if isinstance(node.expr, MatchExprNode):
      self._emit_match_statement(node.expr, target_var=None)
      return
    self.newline()
    self.visit(node.expr)

  def visit_ReturnNode(self, node: ReturnNode) -> None:
    all_active_arenas = [
        a for frame in reversed(self.arena_stack) for a in reversed(frame)
    ]
    expr_vars = []
    for expr in node.expressions:
      if isinstance(expr, MatchExprNode):
        expr_vars.append(self._emit_match_statement(expr))
      else:
        expr_vars.append(None)

    for arena_name in all_active_arenas:
      self.newline()
      self.emit(f"{arena_name}:destroy()")

    self.newline()
    if node.expressions:
      self.emit("return ")
      for idx, expr in enumerate(node.expressions):
        if idx > 0:
          self.emit(", ")
        if expr_vars[idx]:
          self.emit(expr_vars[idx])
        else:
          self.visit(expr)
    else:
      self.emit("return")

  def _emit_match_statement(self, node: MatchExprNode, target_var: Optional[str] = "") -> str:
    if target_var == "":
      self._temp_match_count = getattr(self, "_temp_match_count", 0) + 1
      target_var = f"_match_res_{self._temp_match_count}"
      self.newline()
      self.emit(f"local {target_var} = nil")

    self._temp_subj_count = getattr(self, "_temp_subj_count", 0) + 1
    subj_var = f"_subj_{self._temp_subj_count}"
    self.newline()
    self.emit(f"local {subj_var} = ")
    self.visit(node.subject)

    prev_target = getattr(self, "_current_match_target", None)
    self._current_match_target = target_var

    for idx, case in enumerate(node.cases):
      self.newline()
      if isinstance(case.pattern, EllipsisPatternNode) or (isinstance(case.pattern, IdentifierNode) and case.pattern.name == "_"):
        if idx == 0:
          self.emit("if true then")
        else:
          self.emit("else")
      else:
        if idx == 0:
          self.emit(f"if {subj_var} == ")
          self.visit(case.pattern)
          self.emit(" then")
        else:
          self.emit(f"elseif {subj_var} == ")
          self.visit(case.pattern)
          self.emit(" then")

      self.indent()
      if isinstance(case.body, BlockNode):
        self.visit(case.body)
      else:
        self.newline()
        if target_var:
          self.emit(f"{target_var} = ")
          self.visit(case.body)
        else:
          self.visit(case.body)  # pragma: no cover
      self.dedent()

    self.newline()
    self.emit("end")
    self._current_match_target = prev_target
    return target_var or ""

  def visit_YieldNode(self, node: YieldNode) -> None:
    target = getattr(self, "_current_match_target", None)
    self.newline()
    if target:
      self.emit(f"{target} = ")
    self.visit(node.expr)

  def visit_MatchExprNode(self, node: MatchExprNode) -> None:
    temp_var = self._emit_match_statement(node)
    if temp_var:
      self.emit(temp_var)

  def visit_EllipsisPatternNode(self, node: EllipsisPatternNode) -> None:
    pass

  def visit_IfNode(self, node: IfNode) -> None:
    self.newline()
    if node.init_binding:
      let_name = node.init_binding.let_name
      if node.init_binding.is_unwrap:
        val_var = f"_val_{let_name}"
        self.emit(f"local {val_var} = ")
        self.visit(node.init_binding.expr)
        self.newline()

        # Map identifier to temporary variable during condition check
        old_map = self._identifier_map.copy()
        self._identifier_map[let_name] = val_var

        self.emit(f"if {val_var} ~= nil")
        if node.condition:
          self.emit(" and ")
          self.visit(node.condition)
        self.emit(" then")

        # Restore identifier map
        self._identifier_map = old_map

        self.indent()
        self.newline()
        self.emit(f"local {let_name} = {val_var}")
        self.visit(node.then_block)
        self.dedent()
      else:
        # Standard bind + condition
        self.emit(f"local {let_name} = ")
        self.visit(node.init_binding.expr)
        self.newline()
        self.emit("if ")
        self.visit(node.condition)
        self.emit(" then")
        self.indent()
        self.visit(node.then_block)
        self.dedent()
    else:
      self.emit("if ")
      self.visit(node.condition)
      self.emit(" then")
      self.indent()
      self.visit(node.then_block)
      self.dedent()

    if node.else_block:
      self.newline()
      self.emit("else")
      self.indent()
      self.visit(node.else_block)
      self.dedent()

    self.newline()
    self.emit("end")

  def visit_WhileNode(self, node: WhileNode) -> None:
    self.newline()
    if node.init_binding:
      let_name = node.init_binding.let_name
      if node.init_binding.is_unwrap:
        self.emit("while true do")
        self.indent()
        self.newline()
        val_var = f"_val_{let_name}"
        self.emit(f"local {val_var} = ")
        self.visit(node.init_binding.expr)
        self.newline()

        # Map identifier to temporary variable during condition check
        old_map = self._identifier_map.copy()
        self._identifier_map[let_name] = val_var

        self.emit(f"if not ({val_var} ~= nil")
        if node.condition:
          self.emit(" and ")
          self.visit(node.condition)
        self.emit(") then")

        # Restore map
        self._identifier_map = old_map

        self.indent()
        self.newline()
        self.emit("break")
        self.dedent()
        self.newline()
        self.emit("end")
        self.newline()
        self.emit(f"local {let_name} = {val_var}")
        self.visit(node.block)
        self.dedent()
        self.newline()
        self.emit("end")
      else:
        # Standard init-statement: execute once before loop begins
        self.emit(f"local {let_name} = ")
        self.visit(node.init_binding.expr)
        self.newline()
        self.emit("while ")
        self.visit(node.condition)
        self.emit(" do")
        self.indent()
        self.visit(node.block)
        self.dedent()
        self.newline()
        self.emit("end")
    else:
      self.emit("while ")
      self.visit(node.condition)
      self.emit(" do")
      self.indent()
      self.visit(node.block)
      self.dedent()
      self.newline()
      self.emit("end")

  def visit_ForNode(self, node: ForNode) -> None:
    self.newline()
    self.emit(f"for _, {node.loop_var} in ipairs(")
    self.visit(node.iterable)
    self.emit(") do")
    self.indent()
    self.visit(node.block)
    self.dedent()
    self.newline()
    self.emit("end")

  # ==========================================
  # Expressions Visitor
  # ==========================================

  def visit_LiteralNode(self, node: LiteralNode) -> None:
    if node.lit_type == "bool":
      self.emit("true" if node.value else "false")
    elif node.lit_type == "none":
      self.emit("nil")
    elif node.lit_type == "string":
      self.emit(f'"{node.value}"')
    else:
      self.emit(str(node.value))

  def visit_IdentifierNode(self, node: IdentifierNode) -> None:
    if node.name == "Arena":
      self.emit("Arena.init")
    else:
      name = self._identifier_map.get(node.name, node.name)
      self.emit(name)

  def visit_BinaryOpNode(self, node: BinaryOpNode) -> None:
    if node.op == "??":
      self.emit("((function() local _v = ")
      self.visit(node.left)
      self.emit("; if _v ~= nil then return _v else return ")
      self.visit(node.right)
      self.emit(" end end)())")
      return

    op_map = {"&&": "and", "||": "or", "!=": "~="}
    op = op_map.get(node.op, node.op)

    # Convert '+' for strings to '..' string concatenation in Lua
    if op == "+":
      if getattr(node, "is_string_concat", False) or (isinstance(node.left, LiteralNode) and node.left.lit_type == "string") or (isinstance(node.right, LiteralNode) and node.right.lit_type == "string"):
        op = ".."

    self.emit("(")
    self.visit(node.left)
    self.emit(f" {op} ")
    self.visit(node.right)
    self.emit(")")

  def visit_UnaryOpNode(self, node: UnaryOpNode) -> None:
    if node.op == "+":
      self.emit("(")
      self.visit(node.expr)
      self.emit(")")
      return
    op_map = {"!": "not "}
    op = op_map.get(node.op, node.op)
    self.emit(f"({op}")
    self.visit(node.expr)
    self.emit(")")

  def visit_CallNode(self, node: CallNode) -> None:
    # Check if this call is calling a struct constructor, e.g. Weapon(...)
    if (isinstance(node.callee, IdentifierNode) and
        node.callee.name in self.known_structs):
      struct_name = node.callee.name
      self.emit(f"{struct_name}.init({{")
      for idx, arg in enumerate(node.arguments):
        if idx > 0:
          self.emit(", ")
        if arg.name:
          self.emit(f"{arg.name} = ")
        else:
          self.emit(f"[{idx + 1}] = ")
        self.visit(arg.expr)
      self.emit("})")
      return

    # Method call optimization for instance methods (e.g. obj.method()) vs
    # static calls
    if isinstance(node.callee, MemberAccessNode):
      member_name = getattr(node.callee, "target_name", None) or node.callee.member
      receiver_name = getattr(node.callee.receiver, "name", None)
      if (receiver_name and receiver_name in self.known_structs) or isinstance(node.callee.receiver, MemberAccessNode):
        # Static method or chained module call (e.g. StructName.func(...) or love.graphics.rectangle(...))
        self.visit(node.callee.receiver)
        self.emit(f".{member_name}(")
      else:
        # Instance method call: receiver:method(...)
        self.visit(node.callee.receiver)
        self.emit(f":{member_name}(")
    else:
      self.visit(node.callee)
      self.emit("(")

    for idx, arg in enumerate(node.arguments):
      if idx > 0:
        self.emit(", ")
      self.visit(arg.expr)
    self.emit(")")

  def visit_MemberAccessNode(self, node: MemberAccessNode) -> None:
    if node.is_optional:
      self.emit("(")
      self.visit(node.receiver)
      self.emit(" ~= nil and ")
      self.visit(node.receiver)
      self.emit(f".{node.member} or nil)")
    else:
      self.visit(node.receiver)
      self.emit(f".{node.member}")

  def visit_CloneNode(self, node: CloneNode) -> None:
    self.emit("_clone_helper(")
    self.visit(node.expr)

    if node.initializer_block:
      self.emit(", function(self)")
      self.indent()
      for stmt in node.initializer_block:
        self.visit(stmt)
      self.dedent()
      self.newline()
      self.emit("end")
    else:
      if node.arena_expr:
        self.emit(", nil")

    if node.arena_expr:
      self.emit(", ")
      self.visit(node.arena_expr)

    self.emit(")")

  def visit_LambdaNode(self, node: LambdaNode) -> None:
    params = [p.name for p in node.parameters]
    self.emit(f"(function({', '.join(params)})")
    self.indent()
    if isinstance(node.body, BlockNode):
      self.visit(node.body)
    else:
      self.newline()
      self.emit("return ")
      self.visit(node.body)
    self.dedent()
    self.newline()
    self.emit("end)")

  def visit_ArrayLiteralNode(self, node: ArrayLiteralNode) -> None:
    self.emit("{")
    for idx, elem in enumerate(node.elements):
      if idx > 0:
        self.emit(", ")
      self.visit(elem)
    self.emit("}")

  def visit_MapLiteralNode(self, node: MapLiteralNode) -> None:
    self.emit("{")
    for idx, entry in enumerate(node.entries):
      if idx > 0:
        self.emit(", ")
      self.emit("[")
      self.visit(entry.key)
      self.emit("] = ")
      self.visit(entry.value)
    self.emit("}")

  def visit_IndexExprNode(self, node: IndexExprNode) -> None:
    self.visit(node.array)
    self.emit("[")
    is_map = isinstance(getattr(node.array, 'inferred_type', None), MapType)
    if is_map:
      self.visit(node.index)
    else:
      if isinstance(node.index, LiteralNode) and node.index.lit_type == "int":
        self.emit(str(node.index.value + 1))
      else:
        self.visit(node.index)
        self.emit(" + 1")
    self.emit("]")

  def visit_StructInitializerNode(self, node: StructInitializerNode) -> None:
    if node.arena_expr:
      self.visit(node.arena_expr)
      self.emit(":register(")
    self.emit(f"{node.struct_name}.init({{")
    for idx, arg in enumerate(node.fields):
      if idx > 0:
        self.emit(", ")
      if arg.name:
        self.emit(f"{arg.name} = ")
      else:
        self.emit(f"[{idx + 1}] = ")
      self.visit(arg.expr)
    self.emit("})")
    if node.arena_expr:
      self.emit(")")
