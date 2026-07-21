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
except ModuleNotFoundError:  # pragma: no cover
  from src.parser.ast import *
  from src.parser.gen.SapphireLexer import SapphireLexer
  from src.parser.gen.SapphireParser import SapphireParser
  from src.parser.ast_builder import ASTBuilder
  from src.semantics.type_checker import TypeChecker, SemanticError


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
          local cow = _clone_helper(val, nil, nil)
          shadow[key] = cow
          return cow
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

    # 2. Collect known struct names and impl block methods
    for decl in program.declarations:
      if isinstance(decl, StructDeclNode):
        self.known_structs.add(decl.name)
      elif isinstance(decl, ImplBlockNode):
        if decl.struct_name not in self.struct_methods:
          self.struct_methods[decl.struct_name] = []
        self.struct_methods[decl.struct_name].extend(decl.members)

    top_level_decls = []
    executable_stmts = []
    has_main = False

    for decl in program.declarations:
      if isinstance(decl, ImplBlockNode):
        continue
      elif isinstance(decl, FuncDeclNode):
        if decl.name == "main":
          has_main = True
        top_level_decls.append(decl)
      elif isinstance(decl, (StructDeclNode, EnumDeclNode, TraitDeclNode,
                             VarDeclNode)):
        top_level_decls.append(decl)
      else:
        executable_stmts.append(decl)

    # 3. Transpile all top-level declarations (types, functions, global variables)
    for decl in top_level_decls:
      self.visit(decl)
      self.newline()

    # 4. Transpile executable top-level statements and main invocation
    for stmt in executable_stmts:
      self.visit(stmt)
      self.newline()

    if has_main:
      self.newline()
      self.emit("main()")
      self.newline()

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
    current_val = 0
    for idx, member in enumerate(node.members):
      if member.value is not None:
        current_val = member.value
      self.newline()
      self.emit(f"{member.name} = {current_val}")
      if idx < len(node.members) - 1:
        self.emit(",")
      current_val += 1
    self.dedent()
    self.newline()
    self.emit("}")
    self.newline()

  def visit_StructDeclNode(self, node: StructDeclNode) -> None:
    is_proto = node.is_prototype
    struct_name = node.name
    methods = self.struct_methods.get(struct_name, [])

    self.newline()
    self.emit(f"local {struct_name} = {{}}")
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
    self.newline()
    params = [p.name for p in node.parameters]
    self.emit(f"local function {node.name}({', '.join(params)})")
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
    is_arena = (
        isinstance(node.expr, CallNode)
        and isinstance(node.expr.callee, IdentifierNode)
        and node.expr.callee.name == "Arena"
    )
    if is_arena and self.arena_stack:
      self.arena_stack[-1].append(node.name)

    self.newline()
    self.emit(f"local {node.name} = ")
    self.visit(node.expr)

  def visit_AssignmentNode(self, node: AssignmentNode) -> None:
    self.newline()
    if node.op == "=":
      self.visit(node.target)
      self.emit(" = ")
      self.visit(node.expr)
    else:
      # Expand compound assignment (e.g. +=, -=, *=, /=) into binary operation
      raw_op = node.op[:-1]
      self.visit(node.target)
      self.emit(" = ")
      self.visit(node.target)
      self.emit(f" {raw_op} ")
      self.visit(node.expr)

  def visit_ExprStmtNode(self, node: ExprStmtNode) -> None:
    self.newline()
    self.visit(node.expr)

  def visit_ReturnNode(self, node: ReturnNode) -> None:
    all_active_arenas = [
        a for frame in reversed(self.arena_stack) for a in reversed(frame)
    ]
    for arena_name in all_active_arenas:
      self.newline()
      self.emit(f"{arena_name}:destroy()")

    self.newline()
    if node.expr:
      self.emit("return ")
      self.visit(node.expr)
    else:
      self.emit("return")

  def visit_IfNode(self, node: IfNode) -> None:
    self.newline()
    if node.is_if_let:
      val_var = f"_val_{node.let_name}"
      self.emit(f"local {val_var} = ")
      self.visit(node.condition_or_expr)
      self.newline()
      self.emit(f"if {val_var} ~= nil then")
      self.indent()
      self.newline()
      self.emit(f"local {node.let_name} = {val_var}")
      self.visit(node.then_block)
      self.dedent()
    else:
      self.emit("if ")
      self.visit(node.condition_or_expr)
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
      self.emit(node.name)

  def visit_BinaryOpNode(self, node: BinaryOpNode) -> None:
    op_map = {"&&": "and", "||": "or", "!=": "~="}
    op = op_map.get(node.op, node.op)

    # Convert '+' for strings to '..' string concatenation in Lua
    if op == "+":
      if isinstance(node.left, LiteralNode) and node.left.lit_type == "string":
        op = ".."
      elif isinstance(node.right, LiteralNode) and node.right.lit_type == "string":
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
      receiver_name = getattr(node.callee.receiver, "name", None)
      if receiver_name and receiver_name in self.known_structs:
        # Static method call on Struct name: StructName.static_func(...)
        self.visit(node.callee.receiver)
        self.emit(f".{node.callee.member}(")
      else:
        # Instance method call: receiver:method(...)
        self.visit(node.callee.receiver)
        self.emit(f":{node.callee.member}(")
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

  def visit_IndexExprNode(self, node: IndexExprNode) -> None:
    self.visit(node.array)
    self.emit("[")
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
