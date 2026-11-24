"""Code generator to transpile Sapphire AST into executable Python code.

This module implements an AST visitor that formats and outputs Python code
corresponding to the semantic behavior of Sapphire, including a runtime header
for prototypal inheritance delegation.
"""

from typing import Any

from src.code_gen.base_transpiler import (
  BaseTranspiler,
  get_default_value_for_type_node,
  is_coroutine_func,
)
from src.code_gen.python_expr_emitter import PythonExprMixin
from src.code_gen.python_runtime import (
  PYTHON_RESERVED_WORDS,
  PYTHON_RUNTIME_MODULE_IMPORT,
  PYTHON_RUNTIME_PREAMBLE,
)
from src.code_gen.python_runtime import (
  RUNTIME_PREAMBLE as RUNTIME_PREAMBLE,
)
from src.code_gen.python_stmt_emitter import PythonStmtMixin
from src.code_gen.transpiler_registry import TranspilerRegistry
from src.parser.ast import (
  AssignmentNode,
  ASTNode,
  BlockNode,
  EnumDeclNode,
  ExportStmtNode,
  ForNode,
  FuncDeclNode,
  GuardStmtNode,
  IdentifierNode,
  IfNode,
  ImplBlockNode,
  ImplMemberNode,
  ImportStmtNode,
  LambdaNode,
  LiteralNode,
  ProgramNode,
  ReturnNode,
  StmtNode,
  StructDeclNode,
  StructFieldNode,
  TraitDeclNode,
  UnaryOpNode,
  VarDeclNode,
  WhileNode,
)


@TranspilerRegistry.register(
  aliases=["python", "py"], display_name="Python", default_extension=".py"
)
class PythonTranspiler(PythonStmtMixin, PythonExprMixin, BaseTranspiler):
  """AST visitor to transpile Sapphire code to Python."""

  def _mangle_name(self, name: str) -> str:
    """Mangles Sapphire identifiers that collide with Python reserved keywords.

    Uses a strict bijection (`pass` -> `pass_`, `pass_` -> `pass__`, ...) so
    user identifiers ending in `_` never collide with mangled reserved words.
    """
    if not name:
      return name
    if name in ("self", "__init__", "__del__", "main"):
      return name
    stripped = name.rstrip("_")
    if stripped in PYTHON_RESERVED_WORDS:
      return f"{name}_"
    return name

  def _mangle_dotted(self, name: str) -> str:
    """Mangles each segment of a dotted identifier (e.g. `mod.class` ->
    `mod.class_`).
    """
    if not name:
      return name
    if "." in name:
      return ".".join(self._mangle_name(part) for part in name.split("."))
    return self._mangle_name(name)

  def _resolve_var_name(self, raw_name: str) -> str:
    """Resolves a Sapphire variable name through lexical shadowing and keyword
    mangling.
    """
    if raw_name in self._identifier_map:
      return self._identifier_map[raw_name]
    return self._mangle_name(raw_name)

  def _declare_local_var(self, raw_name: str) -> str:
    """Declares a local variable in the current lexical scope, alpha-renaming if
    shadowed.
    """
    mangled = self._mangle_name(raw_name)
    if not self._lexical_scopes:
      return mangled
    enclosing_has = any(
      raw_name in scope for scope in self._lexical_scopes[:-1]
    )
    clashes_func_global = mangled in self._current_func_globals
    if enclosing_has or clashes_func_global:
      py_name = self._next_temp_name(f"_{mangled}_s")
      self._identifier_map[raw_name] = py_name
    else:
      py_name = mangled
      if raw_name in self._identifier_map:
        self._identifier_map.pop(raw_name, None)
    self._lexical_scopes[-1].add(raw_name)
    if self._loop_vars_stack:
      if py_name not in self._loop_vars_stack[-1]:
        self._loop_vars_stack[-1].append(py_name)
    return py_name

  def __init__(
    self,
    test_mode: bool = False,
    use_runtime_module: bool = False,
    semantic_context: Any = None,
  ):
    super().__init__(
      test_mode=test_mode,
      use_runtime_module=use_runtime_module,
      semantic_context=semantic_context,
    )
    # Python-specific metadata & scoping state
    self.struct_traits: dict[str, set[str]] = {}
    self._current_struct_name: str | None = None
    self.clone_helper_counter = 0
    self._lexical_scopes: list[set[str]] = []
    self._current_func_globals: set[str] = set()
    self._loop_vars_stack: list[list[str]] = []
    self._lifted_lambdas: dict[int, str] = {}
    self._lifted_clones: dict[int, str] = {}
    self.extern_vars: dict[str, str] = {}
    self.global_vars: set[str] = set()
    # Source line map: Python output line -> Sapphire source line
    self._py_lineno = 1
    self._line_map: dict[int, int] = {}

  def newline(self) -> None:
    """Starts a new line with the current level of indentation."""
    if self.is_root_buffer:
      self._py_lineno += 1
    self.emit("\n" + "  " * self.indent_level)

  def record_line(self, sp_line: int) -> None:
    """Records a mapping from the current Python output line to a Sapphire
    source
    line.
    """
    if sp_line and sp_line > 0:
      self._line_map[self._py_lineno] = sp_line

  @staticmethod
  def _is_const_default_expr(expr: Any) -> bool:
    """Returns True if *expr* is an immutable literal safe as a Python def
    default.
    """
    if isinstance(expr, LiteralNode):
      return True
    if isinstance(expr, UnaryOpNode) and isinstance(expr.expr, LiteralNode):
      return True
    return False

  def _format_param(self, p) -> str:
    pname = self._mangle_name(p.name)
    if p.default_expr:
      if self._is_const_default_expr(p.default_expr):
        return f"{pname}={self.capture_expr(p.default_expr)}"
      return f"{pname}=_SP_UNSET"
    return pname

  def _emit_deferred_default_inits(self, parameters: list[Any]) -> None:
    """Emits runtime initialization for non-literal default parameters inside
    the
    body.
    """
    for p in parameters:
      if p.name == "self" or not p.default_expr:
        continue
      if self._is_const_default_expr(p.default_expr):
        continue
      pname = self._mangle_name(p.name)
      self.newline()
      self.emit(f"if {pname} is _SP_UNSET:")
      self.indent()
      self._lift_match_expressions(p.default_expr)
      self.newline()
      self.emit(f"{pname} = ")
      self._emit_value_expr(p.default_expr)
      self._drain_pending_null_vars("None")
      self.dedent()

  def transpile(self, program: ProgramNode) -> str:
    """Entry point to transpile a ProgramNode AST into Python source code
    string.
    """
    self.code = []
    self._py_lineno = 1
    self._line_map = {}
    self._lifted_matches = {}
    self._lifted_lambdas = {}
    self._lifted_clones = {}
    self._lifted_short_circuits = {}
    self._temp_name_counters = {}
    self._lexical_scopes = []
    self._identifier_map = {}
    self._current_func_globals = set()
    self._loop_vars_stack = []

    # 1. Output runtime preamble or shared runtime module import
    preamble = (
      PYTHON_RUNTIME_MODULE_IMPORT
      if self.use_runtime_module
      else PYTHON_RUNTIME_PREAMBLE
    )
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
      elif isinstance(
        decl, (StructDeclNode, EnumDeclNode, TraitDeclNode, VarDeclNode)
      ):
        top_level_decls.append(decl)

    # 3. Transpile all top-level declarations (types, functions, global
    # variables)
    for decl in top_level_decls:
      self.visit(decl)
      self.newline()

    # 3b. Bind default trait methods onto implementing structs
    for struct_name, bindings in self.struct_default_trait_methods.items():
      m_struct = self._mangle_name(struct_name)
      for trait_ref, m_name, modifier, _member in bindings:
        m_trait = self._mangle_dotted(trait_ref)
        m_method = self._mangle_name(m_name)
        self.newline()
        if modifier == "static":
          self.emit(
            f"{m_struct}.{m_method} = staticmethod({m_trait}.{m_method})"
          )
        else:
          self.emit(f"{m_struct}.{m_method} = {m_trait}.{m_method}")
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
    self.emit(f"class {self._mangle_name(node.name)}({base_class}):")
    self.indent()
    if not node.members:
      self.newline()
      self.emit("pass")
    else:
      current_val: Any = 0
      for member in node.members:
        self.newline()
        m_name = self._mangle_name(member.name)
        if member.value is not None:
          current_val = member.value
        elif is_string_enum:
          current_val = member.name
        if isinstance(current_val, str):
          escaped = current_val.replace("\\", "\\\\").replace('"', '\\"')
          self.emit(f'{m_name} = "{escaped}"')
        else:
          self.emit(f"{m_name} = {current_val}")
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
    exported_names = []
    for spec in node.specifiers:
      exp_name = self._mangle_name(spec.exported_name)
      exported_names.append(f'"{exp_name}"')
      if spec.module_prefix:
        mod_prefix = self._mangle_dotted(spec.module_prefix)
        sym_name = self._mangle_name(spec.symbol)
        src_expr = f"{mod_prefix}.{sym_name}"
        self.newline()
        self.emit(f"{exp_name} = {src_expr}")
      elif spec.alias:
        orig_name = self._mangle_name(spec.symbol)
        if exp_name != orig_name:
          self.newline()
          self.emit(f"{exp_name} = {orig_name}")
    self.newline()
    self.emit(f"__all__ = [{', '.join(exported_names)}]")
    self.newline()

  def visit_StructDeclNode(self, node: StructDeclNode) -> None:
    is_proto = node.is_prototype
    traits = self.struct_traits.get(node.name, set())
    is_test_case = any("TestCase" in t for t in traits)
    test_base = f"{getattr(self, 'testing_alias', 'testing')}.TestCase"
    cls_name = self._mangle_name(node.name)

    parents: list[str] = [
      self._mangle_dotted(p) for p in (node.parent_names or [])
    ]
    if is_proto and not any(
      p in self.proto_structs for p in (node.parent_names or [])
    ):
      parents.append("SapphireObject")
    if is_test_case and test_base not in parents:
      parents.append(test_base)
    parent_class = (
      ", ".join(parents)
      if parents
      else ("SapphireObject" if is_proto else "object")
    )

    self.newline()
    self.emit(f"class {cls_name}({parent_class}):")
    self.indent()

    methods = self.struct_methods.get(node.name, [])
    has_init = any(m.func_decl.name == "__init__" for m in methods)

    self.newline()
    if is_proto:
      self.emit("def __init__(self, *args, proto=None, **kwargs):")
      self.indent()
      self.newline()
      self.emit("SapphireObject.__init__(self, proto=proto)")
      self.newline()
      self.emit("if proto is None:")
      self.indent()
      if node.parent_names:
        for p in node.parent_names:
          p_m = self._mangle_dotted(p)
          self.newline()
          if has_init:
            self.emit(f"{p_m}.__init__(self)")
          else:
            self.emit(f"{p_m}.__init__(self, *args, **kwargs)")
      for f in node.fields:
        default_expr = f.default_expr or get_default_value_for_type_node(
          f.field_type
        )
        if default_expr:
          self.newline()
          default_code = self.capture_expr(default_expr)
          self.emit(f"self.{self._mangle_name(f.name)} = {default_code}")
      if not has_init:
        self.newline()
        self.emit("for k, v in kwargs.items():")
        self.indent()
        self.newline()
        self.emit("setattr(self, k, v)")
        self.dedent()
      else:
        self.newline()
        self.emit(f"if type(self)._init_sapphire is {cls_name}._init_sapphire:")
        self.indent()
        self.newline()
        self.emit("self._init_sapphire(*args, **kwargs)")
        self.dedent()
      if not node.parent_names and not node.fields and has_init is False:
        # kwargs loop was already emitted above
        pass
      self.dedent()
      self.dedent()
    else:
      self.emit("def __init__(self, *args, **kwargs):")
      self.indent()
      if node.parent_names:
        for p in node.parent_names:
          p_m = self._mangle_dotted(p)
          self.newline()
          if has_init:
            self.emit(f"{p_m}.__init__(self)")
          else:
            self.emit(f"{p_m}.__init__(self, *args, **kwargs)")
      for f in node.fields:
        default_expr = f.default_expr or get_default_value_for_type_node(
          f.field_type
        )
        if default_expr:
          self.newline()
          default_code = self.capture_expr(default_expr)
          self.emit(f"self.{self._mangle_name(f.name)} = {default_code}")
      if not has_init:
        self.newline()
        self.emit("for k, v in kwargs.items():")
        self.indent()
        self.newline()
        self.emit("setattr(self, k, v)")
        self.dedent()
      else:
        self.newline()
        self.emit(f"if type(self)._init_sapphire is {cls_name}._init_sapphire:")
        self.indent()
        self.newline()
        self.emit("self._init_sapphire(*args, **kwargs)")
        self.dedent()
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
          self.emit(
            "_sp_destroyed = object.__getattribute__(self, "
            "'__dict__').setdefault('_sapphire_destroyed_classes_', set())"
          )
          self.newline()
          self.emit(f"if '{cls_name}' in _sp_destroyed:")
          self.indent()
          self.newline()
          self.emit("return")
          self.dedent()
          self.newline()
          self.emit(f"_sp_destroyed.add('{cls_name}')")
          self.newline()
          self.emit("try:")
          self.indent()
          self._emit_struct_auto_teardown(node.name, call_parents=True)
          self.dedent()
          self.newline()
          self.emit("finally:")
          self.indent()
          self.newline()
          self.emit(f"if type(self) is {cls_name}:")
          self.indent()
          self.newline()
          self.emit("object.__setattr__(self, '_sapphire_disposed_', True)")
          self.dedent()
          self.dedent()
          self.dedent()
    finally:
      self._current_struct_name = old_struct_name

    self.dedent()
    self.newline()

  def _emit_struct_auto_teardown(
    self, struct_name: str, call_parents: bool = True
  ) -> None:
    """Emits LIFO `_sapphire_del` calls for destructible fields and parents."""
    emitted = False
    for f_name in reversed(
      self.struct_destructible_fields.get(struct_name, [])
    ):
      self.newline()
      self.emit(
        f"_sapphire_del(getattr(self, '{self._mangle_name(f_name)}', None))"
      )
      emitted = True
    if call_parents:
      for p_name in reversed(self.struct_parent_names.get(struct_name, [])):
        if p_name in self.structs_with_destructor:
          self.newline()
          self.emit(f"{self._mangle_dotted(p_name)}.__del__(self)")
          emitted = True
    if not emitted:
      self.newline()
      self.emit("pass")

  def visit_StructFieldNode(self, node: StructFieldNode) -> None:
    # Fields are dynamically initialized in __init__, so we do not declare them
    # at class level.
    pass

  def visit_ImplMemberNode(self, node: ImplMemberNode) -> None:
    func = node.func_decl
    is_test_func = any(
      getattr(a, "name", "") == "test" for a in getattr(func, "annotations", [])
    )
    if is_test_func and not self.test_mode:
      return

    self.newline()

    if node.modifier == "static":
      self.emit("@staticmethod")
      self.newline()

    # Rename __init__ constructor to _init_sapphire to separate from boilerplate
    # __init__
    func_name = (
      "_init_sapphire"
      if func.name == "__init__"
      else self._mangle_name(func.name)
    )

    # Python parameter formatting
    params = []
    raw_params = []
    param_raw_names: set[str] = set()
    if node.modifier != "static":
      params.append("self")
      raw_params.append("self")
      param_raw_names.add("self")
    for p in func.parameters:
      if p.name != "self":
        params.append(self._format_param(p))
        raw_params.append(self._mangle_name(p.name))
        param_raw_names.add(p.name)

    prev_scopes = self._lexical_scopes
    prev_id_map = self._identifier_map
    prev_func_globals = self._current_func_globals
    prev_loop_vars = self._loop_vars_stack
    assigned_globals = self._find_assigned_globals(
      func.body, local_params=set(raw_params)
    )
    self._lexical_scopes = [set(param_raw_names)]
    self._identifier_map = {}
    self._current_func_globals = set(assigned_globals)
    self._loop_vars_stack = []
    try:
      if is_coroutine_func(func):
        self.emit(f"def {func_name}({', '.join(params)}):")
        self.indent()
        self._emit_deferred_default_inits(func.parameters)
        self.newline()
        self.emit(f"def _gen_{func_name}({', '.join(raw_params)}):")
        self.indent()
        if assigned_globals:
          self.newline()
          self.emit(f"global {', '.join(sorted(assigned_globals))}")
        self.visit(func.body)
        self.newline()
        self.emit("if False: yield")
        self.dedent()
        self.newline()
        if raw_params:
          self.emit(
            f"return _SapphireCoroutine(_gen_{func_name}, "
            f"{', '.join(raw_params)})"
          )
        else:
          self.emit(f"return _SapphireCoroutine(_gen_{func_name})")
        self.dedent()
      else:
        self.emit(f"def {func_name}({', '.join(params)}):")
        self.indent()
        cur_struct = getattr(self, "_current_struct_name", None)
        cur_cls = self._mangle_name(cur_struct) if cur_struct else ""
        if func.name == "__del__":
          self.newline()
          self.emit(
            "_sp_destroyed = object.__getattribute__(self, "
            "'__dict__').setdefault('_sapphire_destroyed_classes_', set())"
          )
          self.newline()
          self.emit(f"if '{cur_cls}' in _sp_destroyed:")
          self.indent()
          self.newline()
          self.emit("return")
          self.dedent()
          self.newline()
          self.emit(f"_sp_destroyed.add('{cur_cls}')")
        if assigned_globals:
          self.newline()
          self.emit(f"global {', '.join(sorted(assigned_globals))}")
        self._emit_deferred_default_inits(func.parameters)
        if func.name == "__init__" and getattr(func, "base_initializers", None):
          for base_init in func.base_initializers:
            self.newline()
            args_list = ["self"]
            for arg in base_init.arguments:
              val = self.capture_expr(arg.expr)
              if arg.name:
                args_list.append(f"{self._mangle_name(arg.name)}={val}")
              else:
                args_list.append(val)
            base_name = self._mangle_dotted(base_init.callee.name)
            args_str = ", ".join(args_list)
            self.emit(f"{base_name}._init_sapphire({args_str})")
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
        if func.name == "__del__":
          self.newline()
          self.emit("try:")
          self.indent()
          self.visit(func.body)
          self.dedent()
          self.newline()
          self.emit("finally:")
          self.indent()
          if has_auto_teardown:
            self._emit_struct_auto_teardown(cur_struct, call_parents=True)
          self.newline()
          if cur_cls:
            self.emit(f"if type(self) is {cur_cls}:")
            self.indent()
            self.newline()
            self.emit("object.__setattr__(self, '_sapphire_disposed_', True)")
            self.dedent()
          else:
            self.emit("object.__setattr__(self, '_sapphire_disposed_', True)")
          self.dedent()
        else:
          self.visit(func.body)
        self.dedent()
    finally:
      self._lexical_scopes = prev_scopes
      self._identifier_map = prev_id_map
      self._current_func_globals = prev_func_globals
      self._loop_vars_stack = prev_loop_vars

    export_ann = next(
      (a for a in getattr(func, "annotations", []) if a.name == "export"),
      None,
    )
    if export_ann and export_ann.arg:
      alias_name = self._mangle_name(export_ann.arg)
      if alias_name != func_name:
        self.newline()
        self.emit(f"{alias_name} = {func_name}")

  def _find_assigned_globals(
    self, node: Any, local_params: set[str] | None = None
  ) -> set[str]:
    """Finds all global variables assigned within *node* without lexical local
    shadowing.
    """
    if not self.global_vars:
      return set()

    local_vars = set(local_params) if local_params else set()
    assigned: set[str] = set()

    def _collect_locals_and_assignments(
      n: Any, current_locals: set[str]
    ) -> None:
      if n is None:
        return
      if isinstance(n, (FuncDeclNode, LambdaNode)):
        return

      if isinstance(n, BlockNode):
        block_locals = set(current_locals)
        for stmt in n.statements:
          _collect_locals_and_assignments(stmt, block_locals)
        return

      if isinstance(n, IfNode):
        bindings = getattr(
          n,
          "bindings",
          [n.init_binding] if getattr(n, "init_binding", None) else [],
        )
        branch_locals = set(current_locals)
        for b in bindings:
          _collect_locals_and_assignments(b.expr, branch_locals)
          for name in getattr(b, "let_names", [b.let_name]):
            if name:
              branch_locals.add(name)
              branch_locals.add(self._mangle_name(name))
        if n.condition:
          _collect_locals_and_assignments(n.condition, branch_locals)
        _collect_locals_and_assignments(n.then_block, set(branch_locals))
        if n.else_block:
          _collect_locals_and_assignments(n.else_block, set(current_locals))
        return

      if isinstance(n, ForNode):
        _collect_locals_and_assignments(n.iterable, current_locals)
        loop_locals = set(current_locals)
        if n.val_var:
          loop_locals.add(n.val_var)
          loop_locals.add(self._mangle_name(n.val_var))
        if getattr(n, "key_var", None):
          loop_locals.add(n.key_var)
          loop_locals.add(self._mangle_name(n.key_var))
        _collect_locals_and_assignments(n.block, loop_locals)
        return

      if isinstance(n, WhileNode):
        _collect_locals_and_assignments(n.condition, current_locals)
        _collect_locals_and_assignments(n.block, set(current_locals))
        return

      if isinstance(n, VarDeclNode):
        for expr in n.exprs or []:
          _collect_locals_and_assignments(expr, current_locals)
        for name in n.names:
          current_locals.add(name)
          current_locals.add(self._mangle_name(name))
        return

      if isinstance(n, GuardStmtNode):
        for clause in n.clauses:
          if clause.binding:
            _collect_locals_and_assignments(clause.binding.expr, current_locals)
            for name in getattr(
              clause.binding, "let_names", [clause.binding.let_name]
            ):
              if name:
                current_locals.add(name)
                current_locals.add(self._mangle_name(name))
          elif clause.condition:
            _collect_locals_and_assignments(clause.condition, current_locals)
        _collect_locals_and_assignments(n.else_block, set(current_locals))
        return

      if isinstance(n, AssignmentNode):
        targets = getattr(n, "targets", [])
        if not targets and getattr(n, "target", None):
          targets = [n.target]
        for t in targets:
          if isinstance(t, IdentifierNode):
            m_name = self._mangle_name(t.name)
            if (
              m_name in self.global_vars
              and m_name not in current_locals
              and t.name not in current_locals
            ):
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
    default_members = [
      m for m in node.members if getattr(m, "body", None) is not None
    ]
    cls_name = self._mangle_name(node.name)
    self.newline()
    self.emit(f"class {cls_name}:")
    self.indent()
    if not default_members:
      # Emit an empty placeholder class even for pure abstract traits so that
      # cross-module trait aliases (`let T = mod.Trait;`), re-exports
      # (`export { mod.Trait }`), and `__all__` entries resolve cleanly at
      # import time instead of raising AttributeError in Python. (In Lua,
      # indexing a missing table key yields nil, whereas Python raises
      # AttributeError.)
      self.newline()
      self.emit("pass")
    else:
      for member in default_members:
        synth_func = FuncDeclNode(
          member.name,
          member.parameters,
          member.return_types,
          member.body,
          annotations=member.annotations,
        )
        synth_member = ImplMemberNode(member.modifier, synth_func)
        self.visit_ImplMemberNode(synth_member)
    self.dedent()
    self.newline()

  def visit_FuncDeclNode(self, node: FuncDeclNode) -> None:
    is_test_func = any(
      getattr(a, "name", "") == "test" for a in getattr(node, "annotations", [])
    )
    if is_test_func and not self.test_mode:
      return

    self.newline()
    fn_name = self._mangle_name(node.name)
    params = [self._format_param(p) for p in node.parameters]
    raw_params = [self._mangle_name(p.name) for p in node.parameters]
    param_raw_names = {p.name for p in node.parameters}

    prev_scopes = self._lexical_scopes
    prev_id_map = self._identifier_map
    prev_func_globals = self._current_func_globals
    prev_loop_vars = self._loop_vars_stack
    assigned_globals = self._find_assigned_globals(
      node.body, local_params=set(raw_params)
    )
    self._lexical_scopes = [set(param_raw_names)]
    self._identifier_map = {}
    self._current_func_globals = set(assigned_globals)
    self._loop_vars_stack = []
    try:
      if is_coroutine_func(node):
        self.emit(f"def {fn_name}({', '.join(params)}):")
        self.indent()
        self._emit_deferred_default_inits(node.parameters)
        self.newline()
        self.emit(f"def _gen_{fn_name}({', '.join(raw_params)}):")
        self.indent()
        if assigned_globals:
          self.newline()
          self.emit(f"global {', '.join(sorted(assigned_globals))}")
        self.visit(node.body)
        self.newline()
        self.emit("if False: yield")
        self.dedent()
        self.newline()
        if raw_params:
          self.emit(
            f"return _SapphireCoroutine(_gen_{fn_name}, "
            f"{', '.join(raw_params)})"
          )
        else:
          self.emit(f"return _SapphireCoroutine(_gen_{fn_name})")
        self.dedent()
      else:
        self.emit(f"def {fn_name}({', '.join(params)}):")
        self.indent()
        if assigned_globals:
          self.newline()
          self.emit(f"global {', '.join(sorted(assigned_globals))}")
        self._emit_deferred_default_inits(node.parameters)
        self.visit(node.body)
        self.dedent()
    finally:
      self._lexical_scopes = prev_scopes
      self._identifier_map = prev_id_map
      self._current_func_globals = prev_func_globals
      self._loop_vars_stack = prev_loop_vars

    export_ann = next(
      (a for a in getattr(node, "annotations", []) if a.name == "export"), None
    )
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

  def _visit_statements(self, statements: list[StmtNode]) -> None:
    done_flag = self._current_match_done_flag
    guarded_depth = 0
    for idx, stmt in enumerate(statements):
      self.visit(stmt)
      if not isinstance(stmt, ReturnNode):
        self._drain_pending_null_vars("None")
      if (
        done_flag
        and idx < len(statements) - 1
        and self._stmt_contains_match_yield(stmt)
      ):
        self.newline()
        self.emit(f"if not {done_flag}:")
        self.indent()
        guarded_depth += 1
    for _ in range(guarded_depth):
      self.dedent()


Transpiler = PythonTranspiler
