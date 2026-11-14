"""Code generator to transpile Sapphire AST into executable Python code.

This module implements an AST visitor that formats and outputs Python code
corresponding to the semantic behavior of Sapphire, including a runtime header
for prototypal inheritance delegation.
"""

from typing import Any, Dict, List, Optional, Set

from src.parser.ast import *
from src.code_gen.base_transpiler import BaseTranspiler, extract_type_name, get_default_value_for_type_node, is_coroutine_func
from src.code_gen.intrinsics import IntrinsicRegistry
from src.code_gen.transpiler_registry import TranspilerRegistry

from src.code_gen.python_runtime import (
    PYTHON_RUNTIME_PREAMBLE,
    RUNTIME_PREAMBLE,
    PYTHON_RUNTIME_MODULE_IMPORT,
    PYTHON_RESERVED_WORDS,
)
from src.code_gen.python_stmt_emitter import PythonStmtMixin
from src.code_gen.python_expr_emitter import PythonExprMixin


@TranspilerRegistry.register(aliases=["python", "py"], display_name="Python", default_extension=".py")
class PythonTranspiler(PythonStmtMixin, PythonExprMixin, BaseTranspiler):

  """AST visitor to transpile Sapphire code to Python."""

  def _mangle_name(self, name: str) -> str:
    """Mangles Sapphire identifiers that collide with Python reserved keywords."""
    if not name:
      return name
    if name in ("self", "__init__", "__del__", "main"):
      return name
    if name in PYTHON_RESERVED_WORDS:
      return f"{name}_"
    return name

  def __init__(self, test_mode: bool = False, use_runtime_module: bool = False):
    self.code: List[str] = []
    self.indent_level = 0
    self.test_mode = test_mode
    self.use_runtime_module = use_runtime_module
    # Map struct names to their collected method AST nodes from impl blocks
    self.struct_methods: Dict[str, List[Any]] = {}
    self.struct_traits: Dict[str, Set[str]] = {}
    self.destructor_stack: List[List[str]] = []
    self.loop_destructor_depth: List[int] = []
    self.structs_with_destructor: Set[str] = {"Arena"}
    self.proto_structs: Set[str] = set()
    self.struct_destructible_fields: Dict[str, List[str]] = {}
    self.struct_parent_names: Dict[str, List[str]] = {}
    self._current_struct_name: Optional[str] = None
    self.moved_vars: Set[str] = set()
    self._branch_depth: int = 0
    self._var_branch_depth: Dict[str, int] = {}
    self._pending_null_vars: List[str] = []
    self.func_return_types: Dict[str, str] = {}
    self.method_return_types: Dict[str, str] = {}
    self.variable_types: Dict[str, str] = {}
    self.clone_helper_counter = 0
    self._identifier_map: Dict[str, str] = {}
    self.extern_vars: Dict[str, str] = {}
    self.global_vars: Set[str] = set()
    # Source line map: Python output line -> Sapphire source line
    self._py_lineno = 1
    self._line_map: Dict[int, int] = {}

  def newline(self) -> None:
    """Starts a new line with the current level of indentation."""
    self._py_lineno += 1
    self.code.append("\n" + "  " * self.indent_level)

  def record_line(self, sp_line: int) -> None:
    """Records a mapping from the current Python output line to a Sapphire source line."""
    if sp_line and sp_line > 0:
      self._line_map[self._py_lineno] = sp_line

  def _format_param(self, p) -> str:
    pname = self._mangle_name(p.name)
    if p.default_expr:
      temp = PythonTranspiler()
      temp.visit(p.default_expr)
      return f"{pname}={temp.get_output()}"
    return pname

  def transpile(self, program: ProgramNode) -> str:
    """Entry point to transpile a ProgramNode AST into Python source code string."""
    self.code = []
    self._py_lineno = 1
    self._line_map = {}

    # 1. Output runtime preamble or shared runtime module import
    preamble = PYTHON_RUNTIME_MODULE_IMPORT if self.use_runtime_module else PYTHON_RUNTIME_PREAMBLE
    self.emit(preamble)
    self._py_lineno += preamble.count("\n")
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
    self._collect_struct_metadata(program, track_known_structs=False)

    top_level_decls = []
    has_main = False

    self.global_vars = set()
    for decl in program.declarations:
      if isinstance(decl, VarDeclNode):
        for name in decl.names:
          self.global_vars.add(self._mangle_name(name))

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

    # 3. Transpile all top-level declarations (types, functions, global variables)
    for decl in top_level_decls:
      self.visit(decl)
      self.newline()

    # 4. Transpile main call
    if has_main:
      self.newline()
      self.emit('if __name__ == "__main__":')
      self.indent()
      self.newline()
      self.emit("main()")
      self.dedent()
      self.newline()

    # 5. Transpile export manifest to __all__
    if getattr(program, "export_block", None):
      self.visit(program.export_block)

    # 6. Emit source line map for test runner demangling
    if self._line_map:
      self.newline()
      self.emit("_SP_LINE_MAP = {")
      for py_line, sp_line in sorted(self._line_map.items()):
        self.emit(f"{py_line}: {sp_line}, ")
      self.emit("}")
      self.newline()

    return self.get_output()

  # ==========================================
  # Visitor Dispatcher
  # ==========================================

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
    raw_alias = node.alias if node.alias else node.path.split(".")[-1]
    alias = self._mangle_name(raw_alias)
    if node.alias or "." in node.path or alias != raw_alias:
      self.emit(f"import {node.path} as {alias}")
    else:
      self.emit(f"import {node.path}")
    self.newline()

  def visit_ExportStmtNode(self, node: ExportStmtNode) -> None:
    exported_names = [f'"{self._mangle_name(spec.exported_name)}"' for spec in node.specifiers]
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
        default_expr = f.default_expr or get_default_value_for_type_node(f.field_type)
        if default_expr:
          self.newline()
          temp = PythonTranspiler()
          temp.visit(default_expr)
          self.emit(f"self.{self._mangle_name(f.name)} = {temp.get_output()}")
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
        default_expr = f.default_expr or get_default_value_for_type_node(f.field_type)
        if default_expr:
          self.newline()
          temp = PythonTranspiler()
          temp.visit(default_expr)
          self.emit(f"self.{self._mangle_name(f.name)} = {temp.get_output()}")
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

    has_explicit_del = any(
        getattr(m, "func_decl", None) and m.func_decl.name == "__del__"
        for m in methods
    )
    destructible_parents = [
        p for p in (node.parent_names or []) if p in self.structs_with_destructor
    ]
    needs_synth_del = (
        not is_proto
        and not has_explicit_del
        and node.name in self.structs_with_destructor
        and bool(
            self.struct_destructible_fields.get(node.name)
            or len(destructible_parents) > 1
        )
    )

    old_struct_name = getattr(self, "_current_struct_name", None)
    self._current_struct_name = node.name
    try:
      # Output impl methods
      if not methods and not needs_synth_del:
        self.newline()
        self.emit("pass")
      else:
        for m in methods:
          self.visit(m)
        if needs_synth_del:
          self.newline()
          self.emit("def __del__(self):")
          self.indent()
          self.newline()
          self.emit("if getattr(self, '__dict__', {}).get('_sapphire_disposed_', False):")
          self.indent()
          self.newline()
          self.emit("return")
          self.dedent()
          self.newline()
          self.emit("object.__setattr__(self, '_sapphire_disposed_', True)")
          self._emit_struct_auto_teardown(node.name, call_parents=True)
          self.dedent()
    finally:
      self._current_struct_name = old_struct_name

    self.dedent()
    self.newline()

  def _emit_struct_auto_teardown(
      self, struct_name: str, call_parents: bool = True
  ) -> None:
    """Emits LIFO `_sapphire_del` calls for destructible fields and parents."""
    for f_name in reversed(self.struct_destructible_fields.get(struct_name, [])):
      self.newline()
      self.emit(f"_sapphire_del(getattr(self, '{self._mangle_name(f_name)}', None))")
    if call_parents:
      for p_name in reversed(self.struct_parent_names.get(struct_name, [])):
        if p_name in self.structs_with_destructor:
          self.newline()
          self.emit("object.__setattr__(self, '_sapphire_disposed_', False)")
          self.newline()
          self.emit(f"{p_name}.__del__(self)")
          self.newline()
          self.emit("object.__setattr__(self, '_sapphire_disposed_', True)")

  def visit_StructFieldNode(self, node: StructFieldNode) -> None:
    # Fields are dynamically initialized in __init__, so we do not declare them at class level.
    pass

  def visit_ImplMemberNode(self, node: ImplMemberNode) -> None:
    func = node.func_decl
    is_test_func = any(
        getattr(a, "name", "") == "test"
        for a in getattr(func, "annotations", [])
    )
    if is_test_func and not self.test_mode:
      return

    self.newline()

    if node.modifier == "static":
      self.emit("@staticmethod")
      self.newline()

    # Rename __init__ constructor to _init_sapphire to separate from boilerplate __init__
    func_name = "_init_sapphire" if func.name == "__init__" else self._mangle_name(func.name)

    # Python parameter formatting
    params = []
    raw_params = []
    if node.modifier != "static":
      params.append("self")
      raw_params.append("self")
    for p in func.parameters:
      if p.name != "self":
        params.append(self._format_param(p))
        raw_params.append(self._mangle_name(p.name))

    if is_coroutine_func(func):
      self.emit(f"def {func_name}({', '.join(params)}):")
      self.indent()
      self.newline()
      self.emit(f"def _gen_{func_name}({', '.join(raw_params)}):")
      self.indent()
      assigned_globals = self._find_assigned_globals(func.body, local_params=set(raw_params))
      if assigned_globals:
        self.newline()
        self.emit(f"global {', '.join(sorted(assigned_globals))}")
      self.visit(func.body)
      self.dedent()
      self.newline()
      if raw_params:
        self.emit(f"return _SapphireCoroutine(_gen_{func_name}, {', '.join(raw_params)})")
      else:
        self.emit(f"return _SapphireCoroutine(_gen_{func_name})")
      self.dedent()
    else:
      self.emit(f"def {func_name}({', '.join(params)}):")
      self.indent()
      if func.name == "__del__":
        self.newline()
        self.emit("if getattr(self, '__dict__', {}).get('_sapphire_disposed_', False):")
        self.indent()
        self.newline()
        self.emit("return")
        self.dedent()
        self.newline()
        self.emit("object.__setattr__(self, '_sapphire_disposed_', True)")
      assigned_globals = self._find_assigned_globals(func.body, local_params=set(raw_params))
      if assigned_globals:
        self.newline()
        self.emit(f"global {', '.join(sorted(assigned_globals))}")
      if func.name == "__init__" and getattr(func, "base_initializers", None):
        for base_init in func.base_initializers:
          self.newline()
          args_list = ["self"]
          for arg in base_init.arguments:
            temp = PythonTranspiler()
            temp.visit(arg.expr)
            val = temp.get_output()
            if arg.name:
              args_list.append(f"{arg.name}={val}")
            else:
              args_list.append(val)
          self.emit(f"{base_init.callee.name}._init_sapphire({', '.join(args_list)})")
      cur_struct = getattr(self, "_current_struct_name", None)
      has_auto_teardown = (
          func.name == "__del__"
          and cur_struct
          and cur_struct not in self.proto_structs
          and bool(
              self.struct_destructible_fields.get(cur_struct)
              or any(
                  p in self.structs_with_destructor
                  for p in self.struct_parent_names.get(cur_struct, [])
              )
          )
      )
      if has_auto_teardown:
        self.newline()
        self.emit("try:")
        self.indent()
        self.visit(func.body)
        self.dedent()
        self.newline()
        self.emit("finally:")
        self.indent()
        self._emit_struct_auto_teardown(cur_struct, call_parents=True)
        self.dedent()
      else:
        self.visit(func.body)
      self.dedent()

  def _find_assigned_globals(
      self, node: Any, local_params: Optional[Set[str]] = None
  ) -> Set[str]:
    """Finds all global variables that are assigned to within node without local shadowing."""
    if not self.global_vars:
      return set()

    local_vars = set(local_params) if local_params else set()
    assigned = set()

    def _collect_locals_and_assignments(n: Any, current_locals: Set[str]) -> None:
      if n is None:
        return
      if isinstance(n, (FuncDeclNode, LambdaNode)):
        return

      if isinstance(n, VarDeclNode):
        for name in n.names:
          current_locals.add(name)
      elif isinstance(n, ForNode):
        if n.val_var:
          current_locals.add(n.val_var)
        if getattr(n, "key_var", None):
          current_locals.add(n.key_var)
      elif isinstance(n, HeaderBindingNode):
        if getattr(n, "let_names", None):
          for name in n.let_names:
            current_locals.add(name)
        elif getattr(n, "let_name", None):
          current_locals.add(n.let_name)
      elif isinstance(n, GuardClauseNode):
        if n.binding:
          if getattr(n.binding, "let_names", None):
            for name in n.binding.let_names:
              current_locals.add(name)
          elif getattr(n.binding, "let_name", None):
            current_locals.add(n.binding.let_name)
      elif isinstance(n, AssignmentNode):
        targets = getattr(n, "targets", [])
        if not targets and getattr(n, "target", None):
          targets = [n.target]
        for t in targets:
          if isinstance(t, IdentifierNode):
            m_name = self._mangle_name(t.name)
            if m_name in self.global_vars and m_name not in current_locals and t.name not in current_locals:
              assigned.add(m_name)

      if isinstance(n, ASTNode):
        for k, v in n.__dict__.items():
          if k.startswith("_"):
            continue
          if isinstance(v, list):
            for item in v:
              _collect_locals_and_assignments(item, current_locals)
          elif isinstance(v, ASTNode):
            _collect_locals_and_assignments(v, current_locals)

    _collect_locals_and_assignments(node, set(local_vars))
    return assigned

  def visit_TraitDeclNode(self, node: TraitDeclNode) -> None:
    # Traits are compile-time monomorphic contracts and are not needed at Python runtime.
    pass

  def visit_FuncDeclNode(self, node: FuncDeclNode) -> None:
    is_test_func = any(getattr(a, "name", "") == "test" for a in getattr(node, "annotations", []))
    if is_test_func and not self.test_mode:
      return

    self.newline()
    fn_name = self._mangle_name(node.name)
    params = [self._format_param(p) for p in node.parameters]
    raw_params = [self._mangle_name(p.name) for p in node.parameters]
    if is_coroutine_func(node):
      self.emit(f"def {fn_name}({', '.join(params)}):")
      self.indent()
      self.newline()
      self.emit(f"def _gen_{fn_name}({', '.join(raw_params)}):")
      self.indent()
      assigned_globals = self._find_assigned_globals(node.body, local_params=set(raw_params))
      if assigned_globals:
        self.newline()
        self.emit(f"global {', '.join(sorted(assigned_globals))}")
      self.visit(node.body)
      self.dedent()
      self.newline()
      if raw_params:
        self.emit(f"return _SapphireCoroutine(_gen_{fn_name}, {', '.join(raw_params)})")
      else:
        self.emit(f"return _SapphireCoroutine(_gen_{fn_name})")
      self.dedent()
    else:
      self.emit(f"def {fn_name}({', '.join(params)}):")
      self.indent()
      assigned_globals = self._find_assigned_globals(node.body, local_params=set(raw_params))
      if assigned_globals:
        self.newline()
        self.emit(f"global {', '.join(sorted(assigned_globals))}")
      self.visit(node.body)
      self.dedent()

    export_ann = next((a for a in getattr(node, "annotations", []) if a.name == "export"), None)
    if export_ann:
      target_path = export_ann.arg if export_ann.arg else fn_name
      if "." in target_path:
        self.newline()
        self.emit("try:")
        self.indent()
        self.newline()
        self.emit(f"{target_path} = {fn_name}")
        self.dedent()
        self.newline()
        self.emit("except (NameError, AttributeError):")
        self.indent()
        self.newline()
        self.emit("pass")
        self.dedent()
      elif target_path != fn_name:
        self.newline()
        self.emit(f"{target_path} = {fn_name}")

  def _visit_statements(self, statements: List[StmtNode]) -> None:
    for stmt in statements:
      self.visit(stmt)
      if not isinstance(stmt, ReturnNode):
        self._drain_pending_null_vars("None")



Transpiler = PythonTranspiler
