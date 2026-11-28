"""Code generator to transpile Sapphire AST into executable Lua 5.1 code.

This module implements an AST visitor that formats and outputs Lua 5.1 code
corresponding to the semantic behavior of Sapphire, including a runtime header
for prototypal inheritance delegation and Arena memory management.
"""

from typing import Any

from sapphire.code_gen.base_transpiler import (
  BaseTranspiler,
  get_default_value_for_type_node,
  is_coroutine_func,
)
from sapphire.code_gen.lua_expr_emitter import LuaExprMixin
from sapphire.code_gen.lua_runtime import (
  LUA_DEV_RELOAD_WATCHER,
  LUA_RUNTIME_PREAMBLE,
  LUA_SOURCEMAP_DEMANGLER,
)
from sapphire.code_gen.lua_stmt_emitter import LuaStmtMixin
from sapphire.code_gen.source_map import SourceMapBuilder
from sapphire.code_gen.transpiler_registry import TranspilerRegistry
from sapphire.parser.ast import (
  ASTNode,
  EnumDeclNode,
  ExportStmtNode,
  FuncDeclNode,
  ImplBlockNode,
  ImplMemberNode,
  ImportStmtNode,
  LiteralNode,
  OptionalTypeNode,
  ProgramNode,
  StructDeclNode,
  StructFieldNode,
  TraitDeclNode,
  VarDeclNode,
)

LUA_RUNTIME_MODULE_IMPORT = """-- Sapphire Lua 5.1 Runtime Module Import
local function _sp_load_runtime()
  local ok, rt = pcall(require, "_sapphire_runtime")
  if ok and type(rt) == "table" then return rt end
  local info = debug and debug.getinfo and debug.getinfo(2, "S")
  if info and info.source and info.source:sub(1, 1) == "@" then
    local curr_dir = info.source:sub(2):match("^(.*[/\\\\])") or "./"
    local chunk = loadfile(curr_dir .. "_sapphire_runtime.lua")
    if chunk then return chunk() end
  end
  error("Could not load _sapphire_runtime.lua")
end
local _SP_RT = _sp_load_runtime()
local Arena, Ref = _SP_RT.Arena, _SP_RT.Ref
local SharedRef, WeakRef = _SP_RT.SharedRef, _SP_RT.WeakRef
"""

LUA_RUNTIME_MODULE_EXPORTS = """
return _SP_RT
"""


LUA_RESERVED_WORDS = {
  "and",
  "break",
  "do",
  "else",
  "elseif",
  "end",
  "false",
  "for",
  "function",
  "goto",
  "if",
  "in",
  "local",
  "nil",
  "not",
  "or",
  "repeat",
  "return",
  "then",
  "true",
  "until",
  "while",
}


@TranspilerRegistry.register(
  aliases=["lua", "lua5.1", "love2d", "love"],
  display_name="Lua 5.1",
  default_extension=".lua",
)
class LuaTranspiler(LuaStmtMixin, LuaExprMixin, BaseTranspiler):
  """AST visitor to transpile Sapphire code to Lua 5.1."""

  def _mangle_name(self, name: str) -> str:
    """Mangles Sapphire identifiers that collide with Lua reserved keywords."""
    if not name:
      return name
    if name in ("self", "__init__", "__del__", "_init_sapphire"):
      return name
    if name.rstrip("_") in LUA_RESERVED_WORDS:
      return f"{name}_"
    return name

  def _lua_mod_sym(self, raw_name: str) -> str:
    """Resolves a top-level Lua module symbol (using `_MOD.<name>` on spill)."""
    m = self._mangle_name(raw_name)
    if raw_name in getattr(self, "_module_ns_names", ()):
      return f"_MOD.{m}"
    return m

  def _mangle_dotted(self, name: str) -> str:
    """Mangles each segment of a dotted identifier path."""
    if not name:
      return name
    if "." not in name:
      return self._lua_mod_sym(name)
    return ".".join(self._mangle_name(part) for part in name.split("."))

  def __init__(
    self,
    source_file: str | None = None,
    source_map_builder: SourceMapBuilder | None = None,
    test_mode: bool = False,
    dev_mode: bool = False,
    use_runtime_module: bool = False,
    semantic_context: Any = None,
  ):
    super().__init__(
      test_mode=test_mode,
      use_runtime_module=use_runtime_module,
      semantic_context=semantic_context,
    )
    # Lua-specific source-map and module metadata
    self.current_line = 1
    self.current_column = 0
    self.source_file = source_file
    self.source_map_builder = source_map_builder
    self._pending_source_mapping: tuple[str, int, int] | None = None
    self.dev_mode = dev_mode
    self.on_reload_callbacks: list[str] = []
    self.declared_symbols: list[str] = []
    self.known_structs: set[str] = set()
    self.imported_modules: set[str] = set()
    self._loop_stack: list[bool] = []
    self._lifted_match_arity: dict[int, int] = {}
    self._module_ns_names: set[str] = set()

  def emit(self, text: str) -> None:
    """Emits text on the current line and updates line/column numbers."""
    if self.is_root_buffer:
      if self._pending_source_mapping is not None and text.strip():
        src, orig_line, orig_col = self._pending_source_mapping
        self._pending_source_mapping = None
        if self.source_map_builder:
          self.source_map_builder.add_mapping(
            gen_line=self.current_line,
            gen_col=self.current_column,
            source_file=src,
            orig_line=orig_line,
            orig_col=orig_col,
          )
      lines = text.split("\n")
      if len(lines) == 1:
        self.current_column += len(text)
      else:
        self.current_line += len(lines) - 1
        self.current_column = len(lines[-1])
    super().emit(text)

  def newline(self) -> None:
    """Starts a new line with the current level of indentation."""
    indent_str = "  " * self.indent_level
    super().emit("\n" + indent_str)
    if self.is_root_buffer:
      self.current_line += 1
      self.current_column = len(indent_str)

  def transpile(
    self,
    program: ProgramNode,
    source_file: str | None = None,
    source_map_builder: SourceMapBuilder | None = None,
  ) -> str:
    """Main entry point to transpile a Sapphire ProgramNode to Lua 5.1."""
    if source_file:
      self.source_file = source_file
    if source_map_builder:
      self.source_map_builder = source_map_builder

    self._lifted_matches = {}
    self._lifted_match_arity = {}
    self._lifted_short_circuits = {}
    self._temp_name_counters = {}
    self._pending_null_vars = []
    self._pending_unconditional_null_vars = []
    self._module_ns_names = set()
    self._identifier_map = {}

    # 1. Output runtime preamble or shared runtime module import
    preamble = (
      LUA_RUNTIME_MODULE_IMPORT
      if self.use_runtime_module
      else LUA_RUNTIME_PREAMBLE
    )
    self.emit(preamble)
    self.newline()

    if self.dev_mode:
      self.emit(LUA_DEV_RELOAD_WATCHER)
      self.newline()

    # 1b. Transpile module imports
    for imp in getattr(program, "imports", []):
      self.visit(imp)

    # 2. Collect known struct names and impl block methods
    self._collect_struct_metadata(program, track_known_structs=True)

    struct_decls = []
    func_decls = []
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
      elif isinstance(
        decl, (StructDeclNode, EnumDeclNode, TraitDeclNode, VarDeclNode)
      ):
        struct_decls.append(decl)

    forward_raw_names: list[str] = []
    extra_top_raw_names: list[str] = []
    if not self.dev_mode:
      for decl in struct_decls:
        if isinstance(decl, StructDeclNode):
          forward_raw_names.append(decl.name)
        elif isinstance(decl, TraitDeclNode) and any(
          getattr(m, "body", None) is not None for m in decl.members
        ):
          forward_raw_names.append(decl.name)
        elif isinstance(decl, EnumDeclNode):
          extra_top_raw_names.append(decl.name)
        elif isinstance(decl, VarDeclNode):
          is_extern = any(
            getattr(a, "name", "") == "extern"
            for a in getattr(decl, "annotations", [])
          )
          if not is_extern:
            extra_top_raw_names.extend(decl.names)
      for decl in func_decls:
        anns = getattr(decl, "annotations", [])
        if any(a.name == "export" for a in anns):
          continue
        if not self.test_mode and any(a.name == "test" for a in anns):
          continue
        forward_raw_names.append(decl.name)

    if len(forward_raw_names) + len(extra_top_raw_names) > 120:
      self._module_ns_names = set(forward_raw_names) | set(extra_top_raw_names)
      for raw in self._module_ns_names:
        self._identifier_map[raw] = f"_MOD.{self._mangle_name(raw)}"
      self.emit("local _MOD = {}")
      self.newline()
    elif forward_raw_names:
      forward_names = [self._mangle_name(n) for n in forward_raw_names]
      self.emit(f"local {', '.join(forward_names)}")
      self.newline()

    top_level_decls = struct_decls + func_decls
    self._multi_parent_structs: list[tuple[str, list[str]]] = []

    # 3. Transpile all top-level declarations (types, functions, global
    # variables)
    for decl in top_level_decls:
      self.visit(decl)
      self.newline()

    # 3b. Bind default trait methods onto implementing structs
    for struct_name, bindings in self.struct_default_trait_methods.items():
      m_struct = self._lua_mod_sym(struct_name)
      for trait_ref, m_name, _modifier, member in bindings:
        m_trait = self._mangle_dotted(trait_ref)
        m_method = self._mangle_name(m_name)
        self.emit(f"{m_struct}.{m_method} = {m_trait}.{m_method}")
        self.newline()
        export_ann = next(
          (a for a in getattr(member, "annotations", []) if a.name == "export"),
          None,
        )
        if export_ann and export_ann.arg:
          alias_name = self._mangle_name(export_ann.arg)
          if alias_name != m_method:
            self.emit(f"{m_struct}.{alias_name} = {m_struct}.{m_method}")
            self.newline()

    # 3c. Flatten multi-parent struct methods directly onto child struct tables
    if self._multi_parent_structs:
      pending = dict(self._multi_parent_structs)
      emitted_multi: set[str] = set()

      def _emit_multi_chain(raw_name: str) -> None:
        if raw_name in emitted_multi or raw_name not in pending:
          return
        emitted_multi.add(raw_name)
        for p in pending[raw_name]:
          _emit_multi_chain(p)
        m_child = self._lua_mod_sym(raw_name)
        m_parents = ", ".join(self._mangle_dotted(p) for p in pending[raw_name])
        self.emit(f"_SP_RT._inherit_multi({m_child}, {m_parents})")
        self.newline()

      for raw_name, _ in self._multi_parent_structs:
        _emit_multi_chain(raw_name)

    # 4. Transpile main invocation if present
    if has_main:
      self.emit(f"{self._lua_mod_sym('main')}()")
      self.newline()

    for cb in self.on_reload_callbacks:
      self.newline()
      self.emit(f"if {cb} then {cb}() end")

    # 6. Append inline source map table and Love2D error demangler if sourcemap
    # builder present
    if self.source_map_builder and self.source_map_builder.mappings:
      self.newline()
      self.emit(self.source_map_builder.to_lua_line_map_table())
      self.newline()
      self.emit(LUA_SOURCEMAP_DEMANGLER)
      self.newline()

    if getattr(program, "export_block", None):
      self.visit(program.export_block)
    elif self.test_mode and self.declared_symbols:
      self.newline()
      self.emit("local _M = {}")
      for sym in self.declared_symbols:
        m_sym = self._mangle_name(sym)
        sym_ref = self._lua_mod_sym(sym)
        self.newline()
        self.emit(f"_M.{m_sym} = {sym_ref}")
        if sym in LUA_RESERVED_WORDS:
          self.newline()
          self.emit(f'_M["{sym}"] = {sym_ref}')
      self.newline()
      self.emit("return _M")

    return self.get_output()

  # ==========================================
  # Visitor Dispatcher
  # ==========================================

  def visit(self, node: ASTNode) -> None:
    """Visit an AST node and emit its corresponding Lua code."""
    if (
      self.source_map_builder and getattr(node, "start_line", None) is not None
    ):
      src = getattr(node, "source_file", None) or self.source_file
      if src:
        self._pending_source_mapping = (
          src,
          node.start_line,
          node.start_column or 0,
        )
    method_name = f"visit_{node.__class__.__name__}"
    visitor = getattr(self, method_name, self.generic_visit)
    visitor(node)

  def generic_visit(self, node: ASTNode) -> None:
    raise NotImplementedError(
      f"Lua Transpilation for visitor visit_{node.__class__.__name__}"
      f" is not implemented."
    )

  # ==========================================
  # Declarations Visitor
  # ==========================================

  def visit_EnumDeclNode(self, node: EnumDeclNode) -> None:
    self.newline()
    if node.name in self._module_ns_names:
      self.emit(f"{self._lua_mod_sym(node.name)} = {{")
    else:
      enum_name = self._mangle_name(node.name)
      self.emit(f"local {enum_name} = {{")
    self.indent()
    current_val: int | str = 0
    is_string_enum = any(isinstance(m.value, str) for m in node.members)
    for idx, member in enumerate(node.members):
      if member.value is not None:
        current_val = member.value
      elif is_string_enum:
        current_val = member.name
      self.newline()
      m_name = self._mangle_name(member.name)
      if isinstance(current_val, str):
        escaped = (
          current_val.replace("\\", "\\\\")
          .replace('"', '\\"')
          .replace("\r", "\\r")
          .replace("\n", "\\n")
        )
        self.emit(f'{m_name} = "{escaped}"')
      else:
        self.emit(f"{m_name} = {current_val}")
        current_val += 1
      if idx < len(node.members) - 1:
        self.emit(",")
    self.dedent()
    self.newline()
    self.emit("}")
    self.newline()

  def visit_ImportStmtNode(self, node: ImportStmtNode) -> None:
    raw_alias = node.alias if node.alias else node.path.split(".")[-1]
    alias_name = self._mangle_name(raw_alias)
    self.imported_modules.add(alias_name)
    self.emit(f'local {alias_name} = require("{node.path}")')
    if self.dev_mode:
      file_path = node.path.replace(".", "/") + ".lua"
      self.newline()
      self.emit(
        "if _SP_DEV_WATCHER and _SP_DEV_WATCHER.register_file then "
        f'_SP_DEV_WATCHER.register_file("{file_path}") end'
      )
    self.newline()

  def _emit_export_prop(
    self, target_tbl: str, exp_name: str, value_expr: str
  ) -> None:
    """Emits an export property assignment using consistent Sapphire mangling.
    """
    mangled_exp = self._mangle_name(exp_name)
    self.emit(f"{target_tbl}.{mangled_exp} = {value_expr}")
    self.newline()
    if exp_name in LUA_RESERVED_WORDS:
      self.emit(f'{target_tbl}["{exp_name}"] = {value_expr}')
      self.newline()

  def visit_ExportStmtNode(self, node: ExportStmtNode) -> None:
    self.newline()
    default_spec = next(
      (
        s
        for s in node.specifiers
        if (s.alias == "default" or s.exported_name == "default")
        and not s.module_prefix
        and s.symbol in self.known_structs
      ),
      None,
    )
    if (
      default_spec is None
      and len(node.specifiers) == 1
      and not node.specifiers[0].module_prefix
    ):
      if node.specifiers[0].symbol in self.known_structs:
        default_spec = node.specifiers[0]

    if default_spec is not None:
      primary_raw = default_spec.symbol
      primary_sym = self._lua_mod_sym(primary_raw)
      self._emit_export_prop(primary_sym, primary_raw, primary_sym)
      self.emit(f"{primary_sym}.default = {primary_sym}")
      self.newline()
      for spec in node.specifiers:
        if spec is default_spec and (
          spec.alias == "default" or spec.exported_name == "default"
        ):
          continue
        exp_name = spec.exported_name
        if exp_name == primary_raw and not spec.module_prefix:
          continue
        if spec.module_prefix:
          mod_prefix = self._mangle_dotted(spec.module_prefix)
          val_expr = f"{mod_prefix}.{self._mangle_name(spec.symbol)}"
        else:
          val_expr = self._lua_mod_sym(spec.symbol)
        self._emit_export_prop(primary_sym, exp_name, val_expr)
      self.emit(f"return {primary_sym}")
      self.newline()
    else:
      self.emit("local _M = {}")
      self.newline()
      for spec in node.specifiers:
        exp_name = spec.exported_name
        if spec.module_prefix:
          mod_prefix = self._mangle_dotted(spec.module_prefix)
          val_expr = f"{mod_prefix}.{self._mangle_name(spec.symbol)}"
        else:
          val_expr = self._lua_mod_sym(spec.symbol)
        self._emit_export_prop("_M", exp_name, val_expr)
      self.emit("return _M")
      self.newline()

  def _emit_struct_init_fields(self, node: StructDeclNode) -> None:
    """Emits `Struct._init_fields(self)` to apply parent and field defaults."""
    struct_name = self._lua_mod_sym(node.name)
    self.emit(f"function {struct_name}._init_fields(self)")
    self.indent()
    if node.parent_names:
      for p in node.parent_names:
        mp = self._mangle_dotted(p)
        self.newline()
        self.emit(f"if {mp}._init_fields then {mp}._init_fields(self) end")
    for f in node.fields:
      if getattr(f, "is_static", False):
        continue
      default_expr = f.default_expr or get_default_value_for_type_node(
        f.field_type
      )
      if default_expr:
        if self._contains_liftable_expr(default_expr, include_moves=True):
          self._lift_match_expressions(default_expr)
          self.newline()
          self.emit(f"self.{self._mangle_name(f.name)} = ")
          self.visit(default_expr)
        else:
          self.newline()
          default_code = self.capture_expr(default_expr)
          self.emit(f"self.{self._mangle_name(f.name)} = {default_code}")
    self.dedent()
    self.newline()
    self.emit("end")
    self.newline()

  def _emit_struct_init_constructor(
    self, node: StructDeclNode, methods: list[Any]
  ) -> None:
    """Emits `Struct.init(...)` handling proto delegation, `__init__`, and
    kwargs.
    """
    struct_name = self._lua_mod_sym(node.name)
    is_proto = node.is_prototype
    self.emit(f"function {struct_name}.init(...)")
    self.indent()
    self.newline()
    self.emit('local _n_args = select("#", ...)')
    self.newline()
    self.emit("local self")
    self.newline()
    if is_proto:
      self.emit(
        'local proto = (_n_args == 2 and type(select(2, ...)) == "table") '
        "and select(2, ...) or nil"
      )
      self.newline()
      self.emit(f"self = _SP_RT._create_proto_object(proto, {struct_name})")
      self.newline()
      self.emit("if proto == nil then")
      self.indent()
      self.newline()
      self.emit(f"{struct_name}._init_fields(self)")
      self.dedent()
      self.newline()
      self.emit("end")
    else:
      self.emit(f"self = setmetatable({{}}, {struct_name})")
      self.newline()
      self.emit(f"{struct_name}._init_fields(self)")

    init_member = next(
      (m for m in methods if m.func_decl.name == "__init__"), None
    )
    if init_member:
      init_params = [
        p for p in init_member.func_decl.parameters if p.name != "self"
      ]
      opt_def_indices = {
        i for i, p in enumerate(init_params) if self._is_opt_non_none_default(p)
      }
      max_opt_len = max(opt_def_indices) + 1 if opt_def_indices else 0

      def _pad_init_args(prefix: list[str], provided: int) -> str:
        args = list(prefix)
        for i in range(provided, max_opt_len):
          args.append("_SP_RT._SP_UNSET" if i in opt_def_indices else "nil")
        return ", ".join(args)

      self.newline()
      self.emit(f"if {struct_name}._init_sapphire then")
      self.indent()
      self.newline()
      self.emit("if _n_args > 1 then")
      self.indent()
      if opt_def_indices:
        pvars = [f"_a{i + 1}" for i in range(len(init_params))]
        self.newline()
        self.emit(f"local {', '.join(pvars)} = ...")
        for i in sorted(opt_def_indices):
          self.newline()
          self.emit(
            f"if _n_args < {i + 1} then {pvars[i]} = _SP_RT._SP_UNSET end"
          )
        self.newline()
        self.emit(
          f"{struct_name}._init_sapphire(self, {', '.join(pvars)})"
        )
      else:
        self.newline()
        self.emit(f"{struct_name}._init_sapphire(self, ...)")
      self.dedent()
      self.newline()
      self.emit("elseif _n_args == 1 then")
      self.indent()
      self.newline()
      self.emit("local _arg1 = ...")
      self.newline()
      if len(init_params) == 0:
        self.emit(f"{struct_name}._init_sapphire(self)")
      else:
        param_checks = " or ".join(
          f"_arg1['{self._mangle_name(p.name)}'] ~= nil" for p in init_params
        )
        pos_checks = " or ".join(
          f"_arg1[{idx + 1}] ~= nil" for idx in range(len(init_params))
        )
        self.emit(
          f'if type(_arg1) == "table" and '
          f"({param_checks} or {pos_checks} or next(_arg1) == nil) then"
        )
        self.indent()
        call_args = ["self"]
        for idx, p in enumerate(init_params):
          pname = self._mangle_name(p.name)
          unset_val = (
            "_SP_RT._SP_UNSET" if idx in opt_def_indices else "nil"
          )
          tmp = f"_p{idx + 1}"
          call_args.append(tmp)
          self.newline()
          self.emit(
            f"local {tmp}; if _arg1['{pname}'] ~= nil then "
            f"{tmp} = _SP_RT._unwrap_opt(_arg1['{pname}']) "
            f"elseif _arg1[{idx + 1}] ~= nil then "
            f"{tmp} = _SP_RT._unwrap_opt(_arg1[{idx + 1}]) "
            f"else {tmp} = {unset_val} end"
          )
        self.newline()
        self.emit(f"{struct_name}._init_sapphire({', '.join(call_args)})")
        self.dedent()
        self.newline()
        self.emit("else")
        self.indent()
        self.newline()
        padded = _pad_init_args(["self", "_arg1"], 1)
        self.emit(f"{struct_name}._init_sapphire({padded})")
        self.dedent()
        self.newline()
        self.emit("end")
      self.dedent()
      self.newline()
      self.emit("else")
      self.indent()
      self.newline()
      self.emit(f"{struct_name}._init_sapphire({_pad_init_args(['self'], 0)})")
      self.dedent()
      self.newline()
      self.emit("end")
      self.dedent()
      self.newline()
      self.emit("end")
    else:
      self.newline()
      self.emit("if _n_args > 1 then")
      self.indent()
      self.newline()
      self.emit("local _args = { ... }")
      instance_fields = [
        f for f in node.fields if not getattr(f, "is_static", False)
      ]
      for idx, f in enumerate(instance_fields):
        self.newline()
        mangled_f = self._mangle_name(f.name)
        self.emit(
          f"if _args[{idx + 1}] ~= nil then "
          f"self.{mangled_f} = _args[{idx + 1}] end"
        )
      self.dedent()
      self.newline()
      self.emit("elseif _n_args == 1 then")
      self.indent()
      self.newline()
      self.emit("local _arg1 = ...")
      self.newline()
      self.emit('if type(_arg1) == "table" then')
      self.indent()
      self.newline()
      self.emit("for k, v in pairs(_arg1) do")
      self.indent()
      self.newline()
      self.emit(
        'if type(k) == "string" then self[k] = _SP_RT._unwrap_opt(v) end'
      )
      self.dedent()
      self.newline()
      self.emit("end")
      for idx, f in enumerate(instance_fields):
        fname = self._mangle_name(f.name)
        self.newline()
        self.emit(
          f"if _arg1[{idx + 1}] ~= nil and _arg1['{fname}'] == nil then "
          f"self.{fname} = _SP_RT._unwrap_opt(_arg1[{idx + 1}]) end"
        )
      self.dedent()
      self.newline()
      self.emit("else")
      self.indent()
      if instance_fields:
        self.newline()
        self.emit(
          f"self.{self._mangle_name(instance_fields[0].name)} = _arg1"
        )
      self.dedent()
      self.newline()
      self.emit("end")
      self.dedent()
      self.newline()
      self.emit("end")

    self.newline()
    self.emit("return self")
    self.dedent()
    self.newline()
    self.emit("end")
    self.newline()

  def _emit_struct_new_constructor(
    self, node: StructDeclNode, methods: list[Any]
  ) -> None:
    """Emits fixed-arity `Struct._new(...)` used by compiled Sapphire calls."""
    from sapphire.semantics.types import OptionalType, StructType

    struct_name = self._lua_mod_sym(node.name)
    is_proto = node.is_prototype
    init_member = next(
      (m for m in methods if m.func_decl.name == "__init__"), None
    )
    flat_fields, all_parents_local = self._get_flattened_struct_fields(node)
    can_inline_defaults = all_parents_local and all(
      f.default_expr is None
      or not self._contains_liftable_expr(f.default_expr, include_moves=True)
      for f in flat_fields
    )

    if init_member:
      init_params = [
        p for p in init_member.func_decl.parameters if p.name != "self"
      ]
      mangled_params = [self._mangle_name(p.name) for p in init_params]
      self.emit(f"function {struct_name}._new({', '.join(mangled_params)})")
      self.indent()
      self.newline()
      if can_inline_defaults:
        entries: list[str] = []
        for f in flat_fields:
          d_expr = f.default_expr or get_default_value_for_type_node(
            f.field_type
          )
          if d_expr is not None and not (
            isinstance(d_expr, LiteralNode) and d_expr.lit_type == "none"
          ):
            entries.append(
              f"{self._mangle_name(f.name)} = {self.capture_expr(d_expr)}"
            )
        tbl_lit = "{ " + ", ".join(entries) + " }" if entries else "{}"
        if is_proto:
          self.emit(
            f"local self = _SP_RT._create_proto_object(nil, {struct_name}, "
            f"{tbl_lit})"
          )
        else:
          self.emit(f"local self = setmetatable({tbl_lit}, {struct_name})")
      else:
        if is_proto:
          self.emit(
            f"local self = _SP_RT._create_proto_object(nil, {struct_name})"
          )
        else:
          self.emit(f"local self = setmetatable({{}}, {struct_name})")
        self.newline()
        self.emit(f"{struct_name}._init_fields(self)")
      self.newline()
      if mangled_params:
        self.emit(
          f"{struct_name}._init_sapphire(self, {', '.join(mangled_params)})"
        )
      else:
        self.emit(f"{struct_name}._init_sapphire(self)")
      self.newline()
      self.emit("return self")
      self.dedent()
      self.newline()
      self.emit("end")
      self.newline()
      return

    if can_inline_defaults:
      param_names = [self._mangle_name(f.name) for f in flat_fields]
      self.emit(f"function {struct_name}._new({', '.join(param_names)})")
      self.indent()
      for f, m_f in zip(flat_fields, param_names, strict=True):
        if isinstance(f.field_type, OptionalTypeNode):
          if f.default_expr is not None:
            d_code = self.capture_expr(f.default_expr)
            self.newline()
            self.emit(f"if {m_f} == _SP_RT._SP_UNSET then {m_f} = {d_code} end")
        else:
          d_expr = f.default_expr or get_default_value_for_type_node(
            f.field_type
          )
          if d_expr is not None:
            d_code = self.capture_expr(d_expr)
            self.newline()
            self.emit(f"if {m_f} == nil then {m_f} = {d_code} end")
      entries = [f"{m_f} = {m_f}" for m_f in param_names]
      tbl_lit = "{ " + ", ".join(entries) + " }" if entries else "{}"
      self.newline()
      if is_proto:
        self.emit(
          f"return _SP_RT._create_proto_object(nil, {struct_name}, {tbl_lit})"
        )
      else:
        self.emit(f"return setmetatable({tbl_lit}, {struct_name})")
      self.dedent()
      self.newline()
      self.emit("end")
      self.newline()
      return

    canonical_fields = getattr(node, "_canonical_fields", None)
    if canonical_fields is None and self.semantic_context is not None:
      struct_type = self.semantic_context.symbol_table.lookup_type(node.name)
      if isinstance(struct_type, StructType):
        canonical_fields = [
          (
            fn,
            isinstance(f_obj.field_type, OptionalType)
            and f_obj.has_explicit_default,
          )
          for fn, f_obj in struct_type.fields.items()
        ]
    if canonical_fields is not None:
      param_names = [self._mangle_name(fn) for fn, _ in canonical_fields]
      self.emit(f"function {struct_name}._new({', '.join(param_names)})")
      self.indent()
      self.newline()
      if is_proto:
        self.emit(
          f"local self = _SP_RT._create_proto_object(nil, {struct_name})"
        )
      else:
        self.emit(f"local self = setmetatable({{}}, {struct_name})")
      self.newline()
      self.emit(f"{struct_name}._init_fields(self)")
      for (_fn, is_opt_default), m_f in zip(
        canonical_fields, param_names, strict=True
      ):
        self.newline()
        if is_opt_default:
          self.emit(f"if {m_f} ~= _SP_RT._SP_UNSET then self.{m_f} = {m_f} end")
        else:
          self.emit(f"if {m_f} ~= nil then self.{m_f} = {m_f} end")
      self.newline()
      self.emit("return self")
      self.dedent()
      self.newline()
      self.emit("end")
      self.newline()
      return

    self.emit(
      f"function {struct_name}._new(...) return {struct_name}.init(...) end"
    )
    self.newline()

  def _emit_diamond_del_guard(self, raw_struct_name: str) -> None:
    """Emits per-class destruction tracking so diamond bases run `__del__` once.
    """
    self.newline()
    self.emit('local _sp_d = rawget(self, "_sapphire_destroyed_classes_")')
    self.newline()
    self.emit(
      "if not _sp_d then _sp_d = {}; "
      'rawset(self, "_sapphire_destroyed_classes_", _sp_d) end'
    )
    self.newline()
    self.emit(f'if _sp_d["{raw_struct_name}"] then return end')
    self.newline()
    self.emit(f'_sp_d["{raw_struct_name}"] = true')

  def visit_StructDeclNode(self, node: StructDeclNode) -> None:
    """Emits Lua table, metatable inheritance, constructor, methods, and
    `__del__`.
    """
    self.known_structs.add(node.name)
    self.declared_symbols.append(node.name)
    is_proto = node.is_prototype
    raw_name = node.name
    struct_name = self._lua_mod_sym(raw_name)
    methods = self.struct_methods.get(raw_name, [])

    self.newline()
    if self.dev_mode:
      self.emit(f"{struct_name} = {struct_name} or {{}}")
    else:
      self.emit(f"{struct_name} = {{}}")
    self.newline()
    self.emit(f"{struct_name}.__index = {struct_name}")
    self.newline()

    if node.parent_names:
      mangled_parents = [self._mangle_dotted(p) for p in node.parent_names]
      if len(mangled_parents) == 1:
        self.emit(
          f"setmetatable({struct_name}, {{ __index = {mangled_parents[0]} }})"
        )
        self.newline()
      else:
        if not hasattr(self, "_multi_parent_structs"):
          self._multi_parent_structs = []
        self._multi_parent_structs.append((raw_name, list(node.parent_names)))

    for f in node.fields:
      if getattr(f, "is_static", False) and f.default_expr is not None:
        default_code = self.capture_expr(f.default_expr)
        self.emit(
          f"{struct_name}.{self._mangle_name(f.name)} = {default_code}"
        )
        self.newline()

    self._emit_struct_init_fields(node)
    self._emit_struct_init_constructor(node, methods)
    self._emit_struct_new_constructor(node, methods)
    if raw_name in self._flat_value_structs:
      flat_fields, _ = self._get_flattened_struct_fields(node)
      entries = [
        f"{self._mangle_name(f.name)} = v.{self._mangle_name(f.name)}"
        for f in flat_fields
      ]
      tbl_lit = "{ " + ", ".join(entries) + " }" if entries else "{}"
      self.emit(f"function {struct_name}._copy(v)")
      self.indent()
      self.newline()
      self.emit(f"if v == {struct_name} then return v end")
      self.newline()
      self.emit("v = _SP_RT._unwrap_read(v)")
      self.newline()
      self.emit(f"return setmetatable({tbl_lit}, {struct_name})")
      self.dedent()
      self.newline()
      self.emit("end")
      self.newline()

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
      and raw_name in self.structs_with_destructor
      and bool(
        self.struct_destructible_fields.get(raw_name)
        or len(destructible_parents) > 1
      )
    )

    for m in methods:
      self._visit_ImplMemberNode_for_struct(m, raw_name)

    if needs_synth_del:
      self.newline()
      self.emit(f"function {struct_name}:__del__()")
      self.indent()
      if raw_name in self._diamond_destructible_structs:
        self._emit_diamond_del_guard(raw_name)
      self._emit_struct_auto_teardown(raw_name, call_parents=True)
      self.dedent()
      self.newline()
      self.emit("end")
      self.newline()

  def _emit_destructor_call(self, var_name: str) -> None:
    """Emits Lua destructor teardown (`destroy()` for Arena,
    `_SP_RT._sapphire_del`
    otherwise).
    """
    if self.variable_types.get(var_name) == "Arena":
      self.emit(f"if {var_name} ~= nil then {var_name}:destroy() end")
    else:
      self.emit(f"_SP_RT._sapphire_del({var_name})")

  def _emit_struct_auto_teardown(
    self, struct_name: str, call_parents: bool = True
  ) -> None:
    """Emits LIFO `_SP_RT._sapphire_del` calls for destructible fields and
    parents
    in Lua.
    """
    for f_name in reversed(
      self.struct_destructible_fields.get(struct_name, [])
    ):
      self.newline()
      self.emit(f"_SP_RT._sapphire_del(self.{self._mangle_name(f_name)})")
    if call_parents:
      for p_name in reversed(self.struct_parent_names.get(struct_name, [])):
        if p_name in self.structs_with_destructor:
          mp = self._mangle_dotted(p_name)
          self.newline()
          self.emit(f"if {mp}.__del__ then {mp}.__del__(self) end")

  def visit_StructFieldNode(self, node: StructFieldNode) -> None:
    pass

  def visit_ImplMemberNode(self, node: ImplMemberNode) -> None:
    """Public visitor satisfying the BaseTranspiler contract.

    Impl members are not visited standalone in the Lua backend -- they are
    emitted as part of `visit_StructDeclNode` via the private helper. This
    method exists solely to fulfil the abstract-method contract so that the
    class hierarchy remains structurally symmetric with `PythonTranspiler`.
    """
    # Struct name is unavailable at this call site; callers that need to emit
    # a specific impl member should use _visit_ImplMemberNode_for_struct.
    raise NotImplementedError(
      "visit_ImplMemberNode must be called via visit_StructDeclNode in the "
      "Lua backend, not directly on a standalone ImplMemberNode."
    )

  @staticmethod
  def _is_opt_non_none_default(p: Any) -> bool:
    """Returns True if *p* is an OptionalTypeNode with a non-none default."""
    return (
      p.default_expr is not None
      and isinstance(p.param_type, OptionalTypeNode)
      and not (
        isinstance(p.default_expr, LiteralNode)
        and p.default_expr.lit_type == "none"
      )
    )

  def _has_optional_default_param(self, params: list[Any]) -> bool:
    """Returns True if any parameter has both an optional type and a non-none
    default value.
    """
    return any(self._is_opt_non_none_default(p) for p in params)

  def _emit_default_params(
    self,
    params: list[Any],
    has_opt_default: bool,
    use_varargs: bool = False,
  ) -> None:
    """Emits parameter unpacking (for exported vararg optional defaults) and
    default assignments.
    """
    if use_varargs:
      self.newline()
      self.emit('local _n_args = select("#", ...)')
      if params:
        pnames = ", ".join(self._mangle_name(p.name) for p in params)
        self.newline()
        self.emit(f"local {pnames} = ...")

    for idx, p in enumerate(params):
      if p.default_expr is None:
        continue
      pname = self._mangle_name(p.name)
      is_opt = isinstance(p.param_type, OptionalTypeNode)
      if is_opt:
        if (
          isinstance(p.default_expr, LiteralNode)
          and p.default_expr.lit_type == "none"
        ):
          continue
        cond = (
          f"_n_args < {idx + 1} or {pname} == _SP_RT._SP_UNSET"
          if use_varargs
          else f"{pname} == _SP_RT._SP_UNSET"
        )
      elif use_varargs:
        cond = f"{pname} == nil or {pname} == _SP_RT._SP_UNSET"
      else:
        cond = f"{pname} == nil"

      if self._contains_liftable_expr(p.default_expr, include_moves=True):
        self.newline()
        self.emit(f"if {cond} then")
        self.indent()
        self._lift_match_expressions(p.default_expr)
        self.newline()
        self.emit(f"{pname} = ")
        self.visit(p.default_expr)
        self.dedent()
        self.newline()
        self.emit("end")
      else:
        self.newline()
        default_code = self.capture_expr(p.default_expr)
        self.emit(f"if {cond} then {pname} = {default_code} end")

  def _visit_ImplMemberNode_for_struct(
    self, node: ImplMemberNode, struct_name: str
  ) -> None:
    func = node.func_decl
    is_test_func = any(
      getattr(a, "name", "") == "test" for a in getattr(func, "annotations", [])
    )
    if is_test_func and not self.test_mode:
      return

    m_struct = self._lua_mod_sym(struct_name)
    func_name = (
      "_init_sapphire"
      if func.name == "__init__"
      else self._mangle_name(func.name)
    )
    export_ann = next(
      (a for a in getattr(func, "annotations", []) if a.name == "export"),
      None,
    )
    non_self_params = [p for p in func.parameters if p.name != "self"]
    has_opt_default = self._has_optional_default_param(non_self_params)
    use_varargs = has_opt_default and export_ann is not None
    params = [self._mangle_name(p.name) for p in non_self_params]
    sig_params = "..." if use_varargs else ", ".join(params)

    self.newline()
    if node.modifier == "static":
      self.emit(f"function {m_struct}.{func_name}({sig_params})")
    else:
      self.emit(f"function {m_struct}:{func_name}({sig_params})")

    self.indent()
    prev_plain = self._plain_local_containers
    prev_id_map = (
      self._identifier_map.copy() if self._module_ns_names else None
    )
    self._plain_local_containers = set()
    if prev_id_map is not None:
      for p in non_self_params:
        self._identifier_map.pop(p.name, None)
    try:
      self._emit_default_params(
        non_self_params, has_opt_default, use_varargs=use_varargs
      )
      self._emit_impl_member_body(node, func, struct_name, params)
    finally:
      self._plain_local_containers = prev_plain
      if prev_id_map is not None:
        self._identifier_map = prev_id_map
    self.dedent()
    self.newline()
    self.emit("end")
    if export_ann and export_ann.arg:
      alias_name = self._mangle_name(export_ann.arg)
      if alias_name != func_name:
        self.newline()
        self.emit(f"{m_struct}.{alias_name} = {m_struct}.{func_name}")
    self.newline()

  def _emit_impl_member_body(
    self,
    node: ImplMemberNode,
    func: FuncDeclNode,
    struct_name: str,
    params: list[str],
  ) -> None:
    """Emits the body of a struct method (coroutine, __init__, __del__, or
    regular method).
    """
    if is_coroutine_func(func):
      self.newline()
      all_params = (["self"] if node.modifier != "static" else []) + params
      if all_params:
        self.emit(
          f"return _SP_RT._Coroutine.create(function({', '.join(all_params)})"
        )
      else:
        self.emit("return _SP_RT._Coroutine.create(function()")
      self.indent()
      self.visit(func.body)
      self.dedent()
      self.newline()
      if all_params:
        self.emit(f"end, {', '.join(all_params)})")
      else:
        self.emit("end)")
    else:
      if func.name == "__init__" and getattr(func, "base_initializers", None):
        for base_init in func.base_initializers:
          raw_parent = base_init.callee.name
          parent_name = self._mangle_dotted(raw_parent)
          resolved = getattr(base_init, "_resolved_arguments", None)
          omitted_slots = getattr(base_init, "_omitted_arg_slots", set())
          p_members = self.struct_methods.get(raw_parent, [])
          p_init = next(
            (
              m
              for m in p_members
              if getattr(m, "func_decl", None)
              and m.func_decl.name == "__init__"
            ),
            None,
          )
          p_init_params = (
            [p for p in p_init.func_decl.parameters if p.name != "self"]
            if p_init
            else []
          )
          p_opt_def_slots = {
            i
            for i, p in enumerate(p_init_params)
            if self._is_opt_non_none_default(p)
          }
          if resolved is not None:
            total_base_slots = len(resolved)
            if p_opt_def_slots and max(p_opt_def_slots) + 1 > total_base_slots:
              total_base_slots = max(p_opt_def_slots) + 1
            if getattr(base_init, "_requires_eval_order_temps", False):
              temp_binds = []
              for arg_idx, arg in enumerate(base_init.arguments):
                val = self.capture_expr(arg.expr)
                temp_binds.append(f"local _a{arg_idx} = {val}")
              slot_to_temp = {
                slot: f"_a{arg_idx}"
                for arg_idx, slot in enumerate(
                  getattr(base_init, "_eval_order_slots", [])
                )
              }
              call_args = ["self"]
              for i in range(total_base_slots):
                if i in slot_to_temp:
                  call_args.append(slot_to_temp[i])
                elif i in p_opt_def_slots:
                  call_args.append("_SP_RT._SP_UNSET")
                else:
                  call_args.append("nil")
              self.newline()
              self.emit(
                f"do {'; '.join(temp_binds)}; "
                f"{parent_name}._init_sapphire({', '.join(call_args)}) end"
              )
            else:
              args_strs = ["self"]
              for idx in range(total_base_slots):
                if idx < len(resolved):
                  if idx in omitted_slots and idx in p_opt_def_slots:
                    args_strs.append("_SP_RT._SP_UNSET")
                  else:
                    args_strs.append(self.capture_expr(resolved[idx]))
                elif idx in p_opt_def_slots:
                  args_strs.append("_SP_RT._SP_UNSET")
                else:
                  args_strs.append("nil")
              self.newline()
              self.emit(f"{parent_name}._init_sapphire({', '.join(args_strs)})")
            continue

          param_names = [p.name for p in p_init_params]

          args_strs = ["self"]
          if param_names:
            args_by_name = {}
            for idx, arg in enumerate(base_init.arguments):
              val = self.capture_expr(arg.expr)
              if arg.name:
                args_by_name[arg.name] = val
              elif idx < len(param_names):
                args_by_name[param_names[idx]] = val
            for idx, p_name in enumerate(param_names):
              if p_name in args_by_name:
                args_strs.append(args_by_name[p_name])
              elif idx in p_opt_def_slots:
                args_strs.append("_SP_RT._SP_UNSET")
              else:
                args_strs.append("nil")
          else:
            for arg in base_init.arguments:
              args_strs.append(self.capture_expr(arg.expr))

          self.newline()
          self.emit(f"{parent_name}._init_sapphire({', '.join(args_strs)})")

      if func.name == "__del__" and (
        struct_name in self._diamond_destructible_structs
      ):
        self._emit_diamond_del_guard(struct_name)

      has_auto_teardown = (
        func.name == "__del__"
        and struct_name not in self.proto_structs
        and bool(
          self.struct_destructible_fields.get(struct_name)
          or any(
            p in self.structs_with_destructor
            for p in self.struct_parent_names.get(struct_name, [])
          )
        )
      )
      if has_auto_teardown:
        from sapphire.parser.ast import (
          ForNode,
          LambdaNode,
          ReturnNode,
          WhileNode,
        )

        def _scan_returns(n: Any, in_loop: bool = False) -> tuple[bool, bool]:
          if isinstance(n, ReturnNode):
            return True, in_loop
          if isinstance(n, (LambdaNode, FuncDeclNode)):
            return False, False
          next_loop = in_loop or isinstance(n, (WhileNode, ForNode))
          any_ret = False
          in_l_ret = False
          for k, v in getattr(n, "__dict__", {}).items():
            if k.startswith("_"):
              continue
            if isinstance(v, ASTNode):
              r, lr = _scan_returns(v, next_loop)
              any_ret = any_ret or r
              in_l_ret = in_l_ret or lr
            elif isinstance(v, list):
              for item in v:
                if isinstance(item, ASTNode):
                  r, lr = _scan_returns(item, next_loop)
                  any_ret = any_ret or r
                  in_l_ret = in_l_ret or lr
          return any_ret, in_l_ret

        has_ret, has_loop_ret = _scan_returns(func.body)
        if not has_ret:
          self.visit(func.body)
        elif not has_loop_ret:
          self.newline()
          self.emit("repeat")
          self.indent()
          prev_in_del = getattr(self, "_in_del_repeat", False)
          self._in_del_repeat = True
          try:
            self.visit(func.body)
          finally:
            self._in_del_repeat = prev_in_del
          self.dedent()
          self.newline()
          self.emit("until true")
        else:
          self.newline()
          self.emit("(function()")
          self.indent()
          self.visit(func.body)
          self.dedent()
          self.newline()
          self.emit("end)()")
        self._emit_struct_auto_teardown(struct_name, call_parents=True)
      else:
        self.visit(func.body)

  def visit_TraitDeclNode(self, node: TraitDeclNode) -> None:
    default_members = [
      m for m in node.members if getattr(m, "body", None) is not None
    ]
    if not default_members:
      # Pure abstract traits are compile-time contracts erased at runtime
      return
    m_trait = self._lua_mod_sym(node.name)
    self.newline()
    if self.dev_mode:
      self.emit(f"{m_trait} = {m_trait} or {{}}")
    else:
      self.emit(f"{m_trait} = {{}}")
    self.newline()
    for member in default_members:
      synth_func = FuncDeclNode(
        member.name,
        member.parameters,
        member.return_types,
        member.body,
        annotations=member.annotations,
      )
      synth_member = ImplMemberNode(member.modifier, synth_func)
      self._visit_ImplMemberNode_for_struct(synth_member, node.name)

  def visit_FuncDeclNode(self, node: FuncDeclNode) -> None:
    is_test_func = any(
      getattr(a, "name", "") == "test" for a in getattr(node, "annotations", [])
    )
    if is_test_func and not self.test_mode:
      return
    if is_test_func:
      self.declared_symbols.append(node.name)

    fn_name = self._mangle_name(node.name)
    fn_sym = self._lua_mod_sym(node.name)
    if any(
      getattr(a, "name", "") == "on_reload"
      for a in getattr(node, "annotations", [])
    ):
      self.on_reload_callbacks.append(fn_sym)

    export_ann = next((a for a in node.annotations if a.name == "export"), None)
    has_opt_default = self._has_optional_default_param(node.parameters)
    use_varargs = has_opt_default and export_ann is not None
    params = [self._mangle_name(p.name) for p in node.parameters]
    sig_params = "..." if use_varargs else ", ".join(params)

    self.newline()
    if export_ann:
      target_path = export_ann.arg if export_ann.arg else fn_name
      self.emit(f"function {target_path}({sig_params})")
    else:
      self.emit(f"function {fn_sym}({sig_params})")

    self.indent()
    prev_plain = self._plain_local_containers
    prev_id_map = (
      self._identifier_map.copy() if self._module_ns_names else None
    )
    self._plain_local_containers = set()
    if prev_id_map is not None:
      for p in node.parameters:
        self._identifier_map.pop(p.name, None)
    try:
      if self.dev_mode and export_ann and export_ann.arg == "love.update":
        self.newline()
        self.emit("if _SP_DEV_WATCHER then _SP_DEV_WATCHER.check(dt) end")

      self._emit_default_params(
        node.parameters, has_opt_default, use_varargs=use_varargs
      )

      if is_coroutine_func(node):
        self.newline()
        if params:
          self.emit(
            f"return _SP_RT._Coroutine.create(function({', '.join(params)})"
          )
        else:
          self.emit("return _SP_RT._Coroutine.create(function()")
        self.indent()
        self.visit(node.body)
        self.dedent()
        self.newline()
        if params:
          self.emit(f"end, {', '.join(params)})")
        else:
          self.emit("end)")
      else:
        self.visit(node.body)
    finally:
      self._plain_local_containers = prev_plain
      if prev_id_map is not None:
        self._identifier_map = prev_id_map
    self.dedent()
    self.newline()
    self.emit("end")
    self.newline()

  # ==========================================
  # Statements Visitor
  # ==========================================
