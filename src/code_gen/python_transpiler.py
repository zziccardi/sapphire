"""Code generator to transpile Sapphire AST into executable Python code.

This module implements an AST visitor that formats and outputs Python code
corresponding to the semantic behavior of Sapphire, including a runtime header
for prototypal inheritance delegation.
"""

import os
import sys
from typing import Any, Dict, List, Optional

try:
  from parser.ast import *
except ModuleNotFoundError:  # pragma: no cover
  from src.parser.ast import *


# ==========================================
# Sapphire Python Runtime Preamble
# ==========================================

PYTHON_RUNTIME_PREAMBLE = """# Sapphire Runtime Header
import copy
from enum import Enum, IntEnum

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

class _LazyCoWProxy:
  def __init__(self, parent, name, target):
    super().__setattr__('_parent', parent)
    super().__setattr__('_name', name)
    super().__setattr__('_target', target)

  def _get_parent_obj(self):
    p = super().__getattribute__('_parent')
    if isinstance(p, _LazyCoWProxy):
      return p._get_active()
    return p

  def _get_active(self):
    parent = self._get_parent_obj()
    name = super().__getattribute__('_name')
    if isinstance(parent, dict):
      return parent[name] if name in parent else super().__getattribute__('_target')
    if hasattr(parent, '__shadow__') and name in parent.__shadow__:
      return parent.__shadow__[name]
    return super().__getattribute__('_target')

  def _ensure_cow(self):
    p = super().__getattribute__('_parent')
    attr_name = super().__getattribute__('_name')
    if isinstance(p, _LazyCoWProxy):
      parent_obj = p._ensure_cow()
    else:
      parent_obj = p

    if isinstance(parent_obj, dict):
      return parent_obj
    if hasattr(parent_obj, '__shadow__'):
      if attr_name not in parent_obj.__shadow__:
        target = super().__getattribute__('_target')
        if hasattr(target, 'clone'):
          cow_val = target.clone()
        else:
          cow_val = copy.deepcopy(target)
        parent_obj.__shadow__[attr_name] = cow_val
        return cow_val
      return parent_obj.__shadow__[attr_name]
    return parent_obj

  def __getattr__(self, name):
    if name.startswith('_'):
      return super().__getattribute__(name)
    val = getattr(self._get_active(), name)
    if not isinstance(val, (int, float, bool, str, type(None))):
      return _LazyCoWProxy(self, name, val)
    return val

  def __setattr__(self, name, value):
    if name.startswith('_'):
      super().__setattr__(name, value)
      return
    target_obj = self._ensure_cow()
    setattr(target_obj, name, value)

  def __getitem__(self, key):
    active = self._get_active()
    val = active[key]
    if not isinstance(val, (int, float, bool, str, type(None))):
      return _LazyCoWProxy(self, key, val)
    return val

  def __setitem__(self, key, value):
    target_obj = self._ensure_cow()
    target_obj[key] = value

  def __len__(self):
    return len(self._get_active())

  def __iter__(self):
    return iter(self._get_active())

  def __repr__(self):
    return repr(self._get_active())

  def __str__(self):
    return str(self._get_active())

  def __bool__(self):
    return bool(self._get_active())

  def __call__(self, *args, **kwargs):
    return self._get_active()(*args, **kwargs)

  def __contains__(self, item):
    return item in self._get_active()

  def __eq__(self, other):
    return self._get_active() == (other._get_active() if isinstance(other, _LazyCoWProxy) else other)

  def __ne__(self, other):
    return not (self == other)

  def __lt__(self, other):
    return self._get_active() < (other._get_active() if isinstance(other, _LazyCoWProxy) else other)

  def __le__(self, other):
    return self._get_active() <= (other._get_active() if isinstance(other, _LazyCoWProxy) else other)

  def __gt__(self, other):
    return self._get_active() > (other._get_active() if isinstance(other, _LazyCoWProxy) else other)

  def __ge__(self, other):
    return self._get_active() >= (other._get_active() if isinstance(other, _LazyCoWProxy) else other)

  def __add__(self, other):
    return self._get_active() + (other._get_active() if isinstance(other, _LazyCoWProxy) else other)

  def __radd__(self, other):
    return (other._get_active() if isinstance(other, _LazyCoWProxy) else other) + self._get_active()

  def __iadd__(self, other):
    target_obj = self._ensure_cow()
    val = (other._get_active() if isinstance(other, _LazyCoWProxy) else other)
    target_obj += val
    return self

  def __sub__(self, other):
    return self._get_active() - (other._get_active() if isinstance(other, _LazyCoWProxy) else other)

  def __rsub__(self, other):
    return (other._get_active() if isinstance(other, _LazyCoWProxy) else other) - self._get_active()

  def __isub__(self, other):
    target_obj = self._ensure_cow()
    val = (other._get_active() if isinstance(other, _LazyCoWProxy) else other)
    target_obj -= val
    return self

  def __mul__(self, other):
    return self._get_active() * (other._get_active() if isinstance(other, _LazyCoWProxy) else other)

  def __rmul__(self, other):
    return (other._get_active() if isinstance(other, _LazyCoWProxy) else other) * self._get_active()

  def __imul__(self, other):
    target_obj = self._ensure_cow()
    val = (other._get_active() if isinstance(other, _LazyCoWProxy) else other)
    target_obj *= val
    return self

  def __truediv__(self, other):
    return self._get_active() / (other._get_active() if isinstance(other, _LazyCoWProxy) else other)

  def __itruediv__(self, other):
    target_obj = self._ensure_cow()
    val = (other._get_active() if isinstance(other, _LazyCoWProxy) else other)
    target_obj /= val
    return self

  def __floordiv__(self, other):
    return self._get_active() // (other._get_active() if isinstance(other, _LazyCoWProxy) else other)

  def __mod__(self, other):
    return self._get_active() % (other._get_active() if isinstance(other, _LazyCoWProxy) else other)

  def __imod__(self, other):
    target_obj = self._ensure_cow()
    val = (other._get_active() if isinstance(other, _LazyCoWProxy) else other)
    target_obj %= val
    return self

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
        return _LazyCoWProxy(self, name, val)
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

def _sapphire_string_split(s, sep=None):
  if s is None:
    return []
  if sep == "":
    return list(s)
  return s.split(sep)

def _sapphire_string_find(s, sub, start=0, reverse=False):
  if s is None or sub is None:
    return None
  if reverse:
    res = s.rfind(sub, start)
  else:
    res = s.find(sub, start)
  return None if res == -1 else res

def _sapphire_string_to_int(s, radix=10):
  if s is None:
    return None
  try:
    return int(s, radix)
  except (ValueError, TypeError):
    return None

def _sapphire_string_to_float(s):
  if s is None:
    return None
  try:
    return float(s)
  except (ValueError, TypeError):
    return None

def _sapphire_string_to_bool(s):
  if not isinstance(s, str):
    return None
  val = s.strip().lower()
  if val == "true":
    return True
  if val == "false":
    return False
  return None

def _sapphire_string_from(val):
  if val is True:
    return "true"
  if val is False:
    return "false"
  return str(val)

def _sapphire_enum_from(enum_cls, val):
  if val is None:
    return None
  try:
    return enum_cls(val)
  except ValueError:
    if isinstance(val, str):
      try:
        return enum_cls[val]
      except KeyError:
        return None
    return None
"""

RUNTIME_PREAMBLE = PYTHON_RUNTIME_PREAMBLE


class PythonTranspiler:
  """AST visitor to transpile Sapphire code to Python."""

  def __init__(self, test_mode: bool = False):
    self.code: List[str] = []
    self.indent_level = 0
    self.test_mode = test_mode
    # Map struct names to their collected method AST nodes from impl blocks
    self.struct_methods: Dict[str, List[Any]] = {}
    self.struct_traits: Dict[str, Set[str]] = {}
    self.clone_helper_counter = 0
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

  def _format_param(self, p) -> str:
    if p.default_expr:
      temp = PythonTranspiler()
      temp.visit(p.default_expr)
      return f"{p.name}={temp.get_output()}"
    return p.name

  def get_output(self) -> str:
    """Returns the final generated Python source code string."""
    return "".join(self.code)

  def transpile(self, program: ProgramNode) -> str:
    """Entry point to transpile a ProgramNode AST into Python source code string."""
    self.code = []

    # 1. Output runtime preamble
    self.emit(PYTHON_RUNTIME_PREAMBLE)
    self.newline()

    # Detect testing module import alias
    self.testing_alias = "testing"
    for imp in getattr(program, "imports", []):
      if imp.path == "std.testing" or imp.path.startswith("std.testing"):
        self.testing_alias = imp.alias if imp.alias else imp.path.split(".")[-1]

    # 1. Imports
    for imp in getattr(program, "imports", []):
      self.visit(imp)

    # 2. Collect impl block methods to attach to class definitions
    for decl in program.declarations:
      if getattr(decl, "type_params", None):
        continue
      if isinstance(decl, ImplBlockNode):
        if decl.struct_name not in self.struct_methods:
          self.struct_methods[decl.struct_name] = []
        self.struct_methods[decl.struct_name].extend(decl.members)
        if decl.trait_name:
          if decl.struct_name not in self.struct_traits:
            self.struct_traits[decl.struct_name] = set()
          self.struct_traits[decl.struct_name].add(decl.trait_name)

    top_level_decls = []
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
        top_level_decls.append(decl)
      elif isinstance(decl, (StructDeclNode, EnumDeclNode, TraitDeclNode, VarDeclNode)):
        top_level_decls.append(decl)
      else:
        executable_stmts.append(decl)

    # 3. Transpile all top-level declarations (types, functions, global variables)
    for decl in top_level_decls:
      self.visit(decl)
      self.newline()

    # 4. Transpile executable top-level statements and/or main call
    if executable_stmts or has_main:
      self.newline()
      self.emit('if __name__ == "__main__":')
      self.indent()
      for stmt in executable_stmts:
        self.newline()
        self.visit(stmt)
      if has_main:
        self.newline()
        self.emit("main()")
      self.dedent()
      self.newline()

    # 5. Transpile export manifest to __all__
    if getattr(program, "export_block", None):
      self.visit(program.export_block)

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
    raise NotImplementedError(
        f"Transpilation for visitor visit_{node.__class__.__name__} is not"
        " implemented."
    )

  # ==========================================
  # Visitor Implementations
  # ==========================================

  def visit_EnumDeclNode(self, node: EnumDeclNode) -> None:
    self.newline()
    is_string_enum = any(isinstance(m.value, str) for m in node.members)
    base_class = "str, Enum" if is_string_enum else "IntEnum"
    self.emit(f"class {node.name}({base_class}):")
    self.indent()
    if not node.members:
      self.newline()
      self.emit("pass")
    else:
      current_val: Union[int, str] = 0
      for member in node.members:
        self.newline()
        if member.value is not None:
          current_val = member.value
        elif is_string_enum and isinstance(current_val, str):
          current_val = member.name
        if isinstance(current_val, str):
          self.emit(f'{member.name} = "{current_val}"')
        else:
          self.emit(f"{member.name} = {current_val}")
          current_val += 1
    self.dedent()
    self.newline()

  def visit_ImportStmtNode(self, node: ImportStmtNode) -> None:
    if node.alias:
      self.emit(f"import {node.path} as {node.alias}")
    else:
      self.emit(f"import {node.path}")
    self.newline()

  def visit_ExportStmtNode(self, node: ExportStmtNode) -> None:
    exported_names = [f'"{spec.exported_name}"' for spec in node.specifiers]
    self.newline()
    self.emit(f"__all__ = [{', '.join(exported_names)}]")
    self.newline()

  def visit_StructDeclNode(self, node: StructDeclNode) -> None:
    is_proto = node.is_prototype
    traits = self.struct_traits.get(node.name, set())
    is_test_case = any("TestCase" in t for t in traits)
    test_base = f"{getattr(self, 'testing_alias', 'testing')}.TestCase"

    if node.parent_names:
      parents = list(node.parent_names)
      if is_test_case and test_base not in parents:
        parents.append(test_base)
      parent_class = ", ".join(parents)
    else:
      if is_test_case:
        parent_class = test_base
      else:
        parent_class = "SapphireObject" if is_proto else "object"
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
      if node.parent_names:
        for p in node.parent_names:
          self.newline()
          self.emit(f"{p}.__init__(self, *args, **kwargs)")
      for f in node.fields:
        if f.default_expr:
          self.newline()
          temp = PythonTranspiler()
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
      if node.parent_names:
        for p in node.parent_names:
          self.newline()
          self.emit(f"{p}.__init__(self, *args, **kwargs)")
      for f in node.fields:
        if f.default_expr:
          self.newline()
          temp = PythonTranspiler()
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
    is_test_func = any(getattr(a, "name", "") == "test" for a in getattr(node, "annotations", []))
    if is_test_func and not self.test_mode:
      return

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

  def _lift_match_expressions(self, node: Any) -> None:
    """Finds all MatchExprNode in the AST subtree and emits their match statement blocks first."""
    if node is None:
      return
    if isinstance(node, MatchExprNode):
      if not getattr(node, "_is_lifted", False):
        node._is_lifted = True
        for case in node.cases:
          self._lift_match_expressions(case.body)
        node._lifted_var = self._emit_match_statement(node)
      return
    if isinstance(node, list):
      for item in node:
        self._lift_match_expressions(item)
      return
    if isinstance(node, ASTNode):
      for v in node.__dict__.values():
        if isinstance(v, (ASTNode, list)):
          self._lift_match_expressions(v)

  def visit_VarDeclNode(self, node: VarDeclNode) -> None:
    if any(a.name == "extern" for a in node.annotations):
      return

    self._lift_match_expressions(node.exprs)

    self.newline()
    names_str = ", ".join(node.names)
    self.emit(f"{names_str}")
    if node.exprs:
      self.emit(" = ")
      for idx, expr in enumerate(node.exprs):
        if idx > 0:
          self.emit(", ")
        self.visit(expr)

  def visit_AssignmentNode(self, node: AssignmentNode) -> None:
    self._lift_match_expressions(node.targets)
    self._lift_match_expressions(node.exprs)

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
        self.visit(expr)
    else:
      self.visit(node.target)
      self.emit(f" {node.op} ")
      self.visit(node.expr)

  def visit_ExprStmtNode(self, node: ExprStmtNode) -> None:
    if isinstance(node.expr, MatchExprNode):
      self._emit_match_statement(node.expr, target_var=None)
      return
    self._lift_match_expressions(node.expr)
    self.newline()
    self.visit(node.expr)

  def visit_ReturnNode(self, node: ReturnNode) -> None:
    self._lift_match_expressions(node.expressions)
    self.newline()
    if not node.expressions:
      self.emit("return")
    else:
      self.emit("return ")
      for idx, expr in enumerate(node.expressions):
        if idx > 0:
          self.emit(", ")
        self.visit(expr)

  def _emit_match_statement(self, node: MatchExprNode, target_var: Optional[str] = "") -> str:
    if target_var == "":
      self._temp_match_count = getattr(self, "_temp_match_count", 0) + 1
      target_var = f"_match_res_{self._temp_match_count}"
      self.newline()
      self.emit(f"{target_var} = None")

    self.newline()
    self.emit("match ")
    self.visit(node.subject)
    self.emit(":")
    self.indent()

    prev_target = getattr(self, "_current_match_target", None)
    self._current_match_target = target_var

    for case in node.cases:
      self.newline()
      if isinstance(case.pattern, EllipsisPatternNode):
        self.emit("case _:")
      else:
        self.emit("case ")
        self.visit(case.pattern)
        self.emit(":")

      self.indent()
      if isinstance(case.body, BlockNode):
        if not case.body.statements:
          self.newline()
          self.emit("pass")
        else:
          self.visit(case.body)
      else:
        self.newline()
        if target_var:
          self.emit(f"{target_var} = ")
          self.visit(case.body)
        else:
          self.visit(case.body)  # pragma: no cover
      self.dedent()

    self.dedent()
    self._current_match_target = prev_target
    return target_var or ""

  def visit_YieldNode(self, node: YieldNode) -> None:
    self._lift_match_expressions(node.expr)
    target = getattr(self, "_current_match_target", None)
    self.newline()
    if target:
      self.emit(f"{target} = ")
    self.visit(node.expr)

  def visit_MatchExprNode(self, node: MatchExprNode) -> None:
    if not getattr(node, "_is_lifted", False):
      node._is_lifted = True
      node._lifted_var = self._emit_match_statement(node)
    self.emit(node._lifted_var)

  def visit_EllipsisPatternNode(self, node: EllipsisPatternNode) -> None:
    self.emit("_")

  def visit_IfNode(self, node: IfNode) -> None:
    if node.init_binding:
      self._lift_match_expressions(node.init_binding.expr)
    if node.condition:
      self._lift_match_expressions(node.condition)

    self.newline()
    if node.init_binding:
      let_name = node.init_binding.let_name
      if node.init_binding.is_unwrap:
        val_var = f"_val_{let_name}"
        self.emit(f"{val_var} = ")
        self.visit(node.init_binding.expr)
        self.newline()

        # Map identifier to temporary variable during condition check
        old_map = self._identifier_map.copy()
        self._identifier_map[let_name] = val_var

        self.emit(f"if {val_var} is not None")
        if node.condition:
          self.emit(" and ")
          self.visit(node.condition)
        self.emit(":")

        # Restore identifier map
        self._identifier_map = old_map

        self.indent()
        self.newline()
        self.emit(f"{let_name} = {val_var}")
        self.visit(node.then_block)
        self.dedent()
      else:
        # Standard bind + condition
        self.emit(f"{let_name} = ")
        self.visit(node.init_binding.expr)
        self.newline()
        self.emit("if ")
        self.visit(node.condition)
        self.emit(":")
        self.indent()
        self.visit(node.then_block)
        self.dedent()
    else:
      self.emit("if ")
      self.visit(node.condition)
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
    if node.init_binding:
      self._lift_match_expressions(node.init_binding.expr)
    if node.condition:
      self._lift_match_expressions(node.condition)

    self.newline()
    if node.init_binding:
      let_name = node.init_binding.let_name
      if node.init_binding.is_unwrap:
        self.emit("while True:")
        self.indent()
        self.newline()
        val_var = f"_val_{let_name}"
        self.emit(f"{val_var} = ")
        self.visit(node.init_binding.expr)
        self.newline()

        # Map identifier to temporary variable during condition check
        old_map = self._identifier_map.copy()
        self._identifier_map[let_name] = val_var

        self.emit(f"if not ({val_var} is not None")
        if node.condition:
          self.emit(" and ")
          self.visit(node.condition)
        self.emit("):")

        # Restore map
        self._identifier_map = old_map

        self.indent()
        self.newline()
        self.emit("break")
        self.dedent()
        self.newline()
        self.emit(f"{let_name} = {val_var}")
        self.visit(node.block)
        self.dedent()
      else:
        # Standard init-statement: execute once before loop begins
        self.emit(f"{let_name} = ")
        self.visit(node.init_binding.expr)
        self.newline()
        self.emit("while ")
        self.visit(node.condition)
        self.emit(":")
        self.indent()
        self.visit(node.block)
        self.dedent()
    else:
      self.emit("while ")
      self.visit(node.condition)
      self.emit(":")
      self.indent()
      self.visit(node.block)
      self.dedent()

  def visit_ForNode(self, node: ForNode) -> None:
    self._lift_match_expressions(node.iterable)
    self.newline()
    if node.key_var is not None:
      self.emit(f"for {node.key_var}, {node.val_var} in ")
      self.visit(node.iterable)
      self.emit(".items():")
    else:
      self.emit(f"for {node.val_var} in ")
      self.visit(node.iterable)
      self.emit(":")
    self.indent()
    self.visit(node.block)
    self.dedent()

  def visit_BreakNode(self, node: BreakNode) -> None:
    self.newline()
    self.emit("break")

  def visit_ContinueNode(self, node: ContinueNode) -> None:
    self.newline()
    self.emit("continue")

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

  def visit_InterpolatedStringNode(self, node: InterpolatedStringNode) -> None:
    if not node.parts:
      self.emit('""')
      return

    def _emit_part_str(part):
      if isinstance(part, LiteralNode) and part.lit_type == "string":
        escaped_val = part.value.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
        self.emit(f'"{escaped_val}"')
      else:
        self.emit("(lambda x: x.value if hasattr(x, 'value') else str(x))(")
        self.visit(part)
        self.emit(")")

    if len(node.parts) == 1:
      _emit_part_str(node.parts[0])
      return

    self.emit("(")
    for idx, part in enumerate(node.parts):
      if idx > 0:
        self.emit(" + ")
      _emit_part_str(part)
    self.emit(")")

  def visit_IdentifierNode(self, node: IdentifierNode) -> None:
    name = self._identifier_map.get(node.name, node.name)
    self.emit(name)

  def visit_BinaryOpNode(self, node: BinaryOpNode) -> None:
    if node.op == "+" and getattr(node, "is_string_concat", False):
      self.emit("(str(")
      self.visit(node.left)
      self.emit(") + str(")
      self.visit(node.right)
      self.emit("))")
      return

    if node.op == "??":
      self.emit("((lambda _v: _v if _v is not None else ")
      self.visit(node.right)
      self.emit(")(")
      self.visit(node.left)
      self.emit("))")
      return

    op_map = {"&&": "and", "||": "or"}
    op = op_map.get(node.op, node.op)
    self.emit("(")
    self.visit(node.left)
    self.emit(f" {op} ")
    self.visit(node.right)
    self.emit(")")

  def visit_TernaryExprNode(self, node: TernaryExprNode) -> None:
    self.emit("(")
    self.visit(node.true_expr)
    self.emit(" if ")
    self.visit(node.condition)
    self.emit(" else ")
    self.visit(node.false_expr)
    self.emit(")")

  def visit_UnaryOpNode(self, node: UnaryOpNode) -> None:
    op_map = {"!": "not "}
    op = op_map.get(node.op, node.op)
    self.emit(f"({op}")
    self.visit(node.expr)
    self.emit(")")

  def visit_CastExprNode(self, node: CastExprNode) -> None:
    target = node.target_type.name if hasattr(node.target_type, "name") else str(node.target_type)
    if target == "float":
      self.emit("float(")
      self.visit(node.expr)
      self.emit(")")
    elif target == "int":
      self.emit("int(")
      self.visit(node.expr)
      self.emit(")")
    elif target == "bool":
      self.emit("bool(")
      self.visit(node.expr)
      self.emit(")")
    elif target == "String":
      self.emit("str(")
      self.visit(node.expr)
      self.emit(")")
    else:
      self.visit(node.expr)

  def visit_CallNode(self, node: CallNode) -> None:
    if isinstance(node.callee, MemberAccessNode) and getattr(node.callee, "is_string_from", False):
      self.emit("_sapphire_string_from(")
      self.visit(node.arguments[0].expr)
      self.emit(")")
      return

    if isinstance(node.callee, MemberAccessNode) and getattr(node.callee, "is_enum_from", False):
      self.emit("_sapphire_enum_from(")
      self.visit(node.callee.receiver)
      self.emit(", ")
      self.visit(node.arguments[0].expr)
      self.emit(")")
      return

    if isinstance(node.callee, MemberAccessNode) and getattr(node.callee, "is_string_method", False):
      method = node.callee.member
      receiver = node.callee.receiver
      if method == "size":
        self.emit("len(")
        self.visit(receiver)
        self.emit(")")
        return
      elif method == "empty":
        self.emit("(len(")
        self.visit(receiver)
        self.emit(") == 0)")
        return
      elif method == "lower":
        self.visit(receiver)
        self.emit(".lower()")
        return
      elif method == "upper":
        self.visit(receiver)
        self.emit(".upper()")
        return
      elif method == "strip":
        self.visit(receiver)
        self.emit(".strip(")
        if node.arguments:
          self.visit(node.arguments[0].expr)
        self.emit(")")
        return
      elif method == "split":
        self.emit("_sapphire_string_split(")
        self.visit(receiver)
        if node.arguments:
          self.emit(", ")
          self.visit(node.arguments[0].expr)
        self.emit(")")
        return
      elif method == "contains":
        self.emit("(")
        self.visit(node.arguments[0].expr)
        self.emit(" in ")
        self.visit(receiver)
        self.emit(")")
        return
      elif method == "find":
        self.emit("_sapphire_string_find(")
        self.visit(receiver)
        for arg in node.arguments:
          self.emit(", ")
          if arg.name:
            self.emit(f"{arg.name}=")
          self.visit(arg.expr)
        self.emit(")")
        return
      elif method == "to_int":
        self.emit("_sapphire_string_to_int(")
        self.visit(receiver)
        if node.arguments:
          for arg in node.arguments:
            self.emit(", ")
            if arg.name:
              self.emit(f"{arg.name}=")
            self.visit(arg.expr)
        self.emit(")")
        return
      elif method == "to_float":
        self.emit("_sapphire_string_to_float(")
        self.visit(receiver)
        self.emit(")")
        return
      elif method == "to_bool":
        self.emit("_sapphire_string_to_bool(")
        self.visit(receiver)
        self.emit(")")
        return

    self.visit(node.callee)
    self.emit("(")
    args = []
    for arg in node.arguments:
      if arg.name:
        args.append(f"{arg.name}=")
      else:
        args.append("")

    for idx, arg in enumerate(node.arguments):
      if idx > 0:
        self.emit(", ")
      if args[idx]:
        self.emit(args[idx])
      self.visit(arg.expr)
    self.emit(")")

  def visit_MemberAccessNode(self, node: MemberAccessNode) -> None:
    member_name = getattr(node, "target_name", None) or node.member
    if node.is_optional:
      self.emit("(")
      self.visit(node.receiver)
      self.emit(f".{member_name} if ")
      self.visit(node.receiver)
      self.emit(" is not None else None)")
    else:
      self.visit(node.receiver)
      self.emit(f".{member_name}")

  def visit_CloneNode(self, node: CloneNode) -> None:
    self.emit("_clone_helper(")
    self.visit(node.expr)

    if node.initializer_block:
      self.emit(", lambda self: [")
      assignments = []
      for stmt in node.initializer_block:
        if isinstance(stmt, AssignmentNode) and isinstance(
            stmt.target, MemberAccessNode
        ):
          if (
              isinstance(stmt.target.receiver, IdentifierNode)
              and stmt.target.receiver.name == "self"
          ):
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

  def visit_MapLiteralNode(self, node: MapLiteralNode) -> None:
    self.emit("{")
    for idx, entry in enumerate(node.entries):
      if idx > 0:
        self.emit(", ")
      self.visit(entry.key)
      self.emit(": ")
      self.visit(entry.value)
    self.emit("}")

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


Transpiler = PythonTranspiler
