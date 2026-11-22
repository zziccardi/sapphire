"""Code generator to transpile Sapphire AST into executable Lua 5.1 code.

This module implements an AST visitor that formats and outputs Lua 5.1 code
corresponding to the semantic behavior of Sapphire, including a runtime header
for prototypal inheritance delegation and Arena memory management.
"""

from typing import Any, Dict, List, Optional, Set

from src.parser.ast import *
from src.semantics.symbol_table import ArrayType, MapType, RangeType
from src.code_gen.source_map import SourceMapBuilder
from src.code_gen.base_transpiler import BaseTranspiler, extract_type_name, get_default_value_for_type_node, is_coroutine_func
from src.code_gen.transpiler_registry import TranspilerRegistry
from src.code_gen.intrinsics import IntrinsicRegistry

from src.code_gen.lua_runtime import (
    LUA_DEV_RELOAD_WATCHER,
    LUA_RUNTIME_PREAMBLE,
    LUA_SOURCEMAP_DEMANGLER,
)
from src.code_gen.lua_stmt_emitter import LuaStmtMixin, _has_continue_node
from src.code_gen.lua_expr_emitter import LuaExprMixin


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
local Arena, Ref, SharedRef, WeakRef = _SP_RT.Arena, _SP_RT.Ref, _SP_RT.SharedRef, _SP_RT.WeakRef
"""

LUA_RUNTIME_MODULE_EXPORTS = """
return _SP_RT
"""


LUA_RESERVED_WORDS = {
    "and", "break", "do", "else", "elseif", "end", "false", "for",
    "function", "goto", "if", "in", "local", "nil", "not", "or",
    "repeat", "return", "then", "true", "until", "while",
}


@TranspilerRegistry.register(aliases=["lua", "lua5.1", "love2d", "love"], display_name="Lua 5.1", default_extension=".lua")
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

  def _mangle_dotted(self, name: str) -> str:
    """Mangles each segment of a dotted identifier path."""
    if not name:
      return name
    return ".".join(self._mangle_name(part) for part in name.split("."))

  def __init__(
      self,
      source_file: Optional[str] = None,
      source_map_builder: Optional[SourceMapBuilder] = None,
      test_mode: bool = False,
      dev_mode: bool = False,
      use_runtime_module: bool = False,
  ):
    self.code: List[str] = []
    self.indent_level = 0
    self.current_line = 1
    self.current_column = 0
    self.source_file = source_file
    self.source_map_builder = source_map_builder
    self._pending_source_mapping: Optional[Tuple[str, int, int]] = None
    self.test_mode = test_mode
    self.dev_mode = dev_mode
    self.use_runtime_module = use_runtime_module
    self.on_reload_callbacks: List[str] = []
    self.declared_symbols: List[str] = []
    # Map struct names to their collected method AST nodes from impl blocks
    self.struct_methods: Dict[str, List[Any]] = {}
    self.known_structs: Set[str] = set()
    self.imported_modules: Set[str] = set()
    self.destructor_stack: List[List[str]] = []
    self.loop_destructor_depth: List[int] = []
    self.structs_with_destructor: Set[str] = {"Arena", "Ref", "SharedRef"}
    self.proto_structs: Set[str] = set()
    self.struct_destructible_fields: Dict[str, List[str]] = {}
    self.struct_parent_names: Dict[str, List[str]] = {}
    self.moved_vars: Set[str] = set()
    self._branch_depth: int = 0
    self._var_branch_depth: Dict[str, int] = {}
    self._pending_null_vars: List[str] = []
    self._pending_unconditional_null_vars: List[str] = []
    self._pending_destroy_moved_vars: List[str] = []
    self.func_return_types: Dict[str, List[str]] = {}
    self.method_return_types: Dict[Any, List[str]] = {}
    self.variable_types: Dict[str, str] = {}
    self._identifier_map: Dict[str, str] = {}
    self._loop_stack: List[bool] = []
    self._lifted_matches: Dict[int, str] = {}
    self._lifted_match_arity: Dict[int, int] = {}
    self._lifted_short_circuits: Dict[int, str] = {}
    self._temp_name_counters: Dict[str, int] = {}
    self._current_match_target: Optional[str] = None
    self._current_match_done_flag: Optional[str] = None
    self._match_loop_depth: int = 0

  def _make_expr_transpiler(self) -> "LuaTranspiler":
    """Creates a sub-transpiler inheriting module, struct, and rename state."""
    temp = type(self)(
        test_mode=self.test_mode,
        dev_mode=self.dev_mode,
        use_runtime_module=self.use_runtime_module,
    )
    temp.known_structs = self.known_structs
    temp.imported_modules = self.imported_modules
    temp._identifier_map = self._identifier_map
    temp.proto_structs = self.proto_structs
    temp.structs_with_destructor = self.structs_with_destructor
    temp.struct_methods = self.struct_methods
    temp.struct_parent_names = self.struct_parent_names
    temp.struct_destructible_fields = self.struct_destructible_fields
    temp.func_return_types = self.func_return_types
    temp.method_return_types = self.method_return_types
    temp.variable_types = self.variable_types
    temp.moved_vars = self.moved_vars
    temp.destructor_stack = self.destructor_stack
    temp._branch_depth = self._branch_depth
    temp._var_branch_depth = self._var_branch_depth
    temp._pending_null_vars = self._pending_null_vars
    temp._pending_unconditional_null_vars = self._pending_unconditional_null_vars
    temp._pending_destroy_moved_vars = self._pending_destroy_moved_vars
    temp._lifted_matches = self._lifted_matches
    temp._lifted_match_arity = self._lifted_match_arity
    temp._lifted_short_circuits = self._lifted_short_circuits
    temp._temp_name_counters = self._temp_name_counters
    return temp

  def emit(self, text: str) -> None:
    """Emits text on the current line and updates line/column numbers."""
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
    self.code.append(text)

  def newline(self) -> None:
    """Starts a new line with the current level of indentation."""
    indent_str = "  " * self.indent_level
    self.code.append("\n" + indent_str)
    self.current_line += 1
    self.current_column = len(indent_str)

  def transpile(
      self,
      program: ProgramNode,
      source_file: Optional[str] = None,
      source_map_builder: Optional[SourceMapBuilder] = None,
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

    # 1. Output runtime preamble or shared runtime module import
    preamble = LUA_RUNTIME_MODULE_IMPORT if self.use_runtime_module else LUA_RUNTIME_PREAMBLE
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
      elif isinstance(decl, (StructDeclNode, EnumDeclNode, TraitDeclNode,
                             VarDeclNode)):
        struct_decls.append(decl)

    forward_names = []
    if not self.dev_mode:
      for decl in struct_decls:
        if isinstance(decl, StructDeclNode):
          forward_names.append(self._mangle_name(decl.name))
        elif isinstance(decl, TraitDeclNode) and any(
            getattr(m, "body", None) is not None for m in decl.members
        ):
          forward_names.append(self._mangle_name(decl.name))
      for decl in func_decls:
        anns = getattr(decl, "annotations", [])
        if any(a.name == "export" for a in anns):
          continue
        if not self.test_mode and any(a.name == "test" for a in anns):
          continue
        forward_names.append(self._mangle_name(decl.name))

    if forward_names:
      self.emit(f"local {', '.join(forward_names)}")
      self.newline()

    top_level_decls = struct_decls + func_decls

    # 3. Transpile all top-level declarations (types, functions, global variables)
    for decl in top_level_decls:
      self.visit(decl)
      self.newline()

    # 3b. Bind default trait methods onto implementing structs
    for struct_name, bindings in self.struct_default_trait_methods.items():
      m_struct = self._mangle_name(struct_name)
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

    # 4. Transpile main invocation if present
    if has_main:
      self.emit("main()")
      self.newline()

    for cb in self.on_reload_callbacks:
      self.newline()
      self.emit(f"if {cb} then {cb}() end")

    # 6. Append inline source map table and Love2D error demangler if sourcemap builder present
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
        self.newline()
        self.emit(f"_M.{m_sym} = {m_sym}")
        if sym in LUA_RESERVED_WORDS:
          self.newline()
          self.emit(f'_M["{sym}"] = {m_sym}')
      self.newline()
      self.emit("return _M")

    return self.get_output()

  # ==========================================
  # Visitor Dispatcher
  # ==========================================

  def visit(self, node: ASTNode) -> None:
    """Visit an AST node and emit its corresponding Lua code."""
    if self.source_map_builder and getattr(node, "start_line", None) is not None:
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
      f" is not implemented.")

  # ==========================================
  # Declarations Visitor
  # ==========================================

  def visit_EnumDeclNode(self, node: EnumDeclNode) -> None:
    self.newline()
    enum_name = self._mangle_name(node.name)
    self.emit(f"local {enum_name} = {{")
    self.indent()
    current_val: Union[int, str] = 0
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
    self.emit(f"local {alias_name} = require(\"{node.path}\")")
    if self.dev_mode:
      file_path = node.path.replace(".", "/") + ".lua"
      self.newline()
      self.emit(f"if _SP_DEV_WATCHER and _SP_DEV_WATCHER.register_file then _SP_DEV_WATCHER.register_file(\"{file_path}\") end")
    self.newline()

  def _emit_export_prop(
      self, target_tbl: str, exp_name: str, value_expr: str
  ) -> None:
    """Emits an export property assignment using consistent Sapphire mangling."""
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
    if default_spec is None and len(node.specifiers) == 1 and not node.specifiers[0].module_prefix:
      if node.specifiers[0].symbol in self.known_structs:
        default_spec = node.specifiers[0]

    if default_spec is not None:
      primary_raw = default_spec.symbol
      primary_sym = self._mangle_name(primary_raw)
      self._emit_export_prop(primary_sym, primary_raw, primary_sym)
      self.emit(f"{primary_sym}.default = {primary_sym}")
      self.newline()
      for spec in node.specifiers:
        if spec is default_spec and (spec.alias == "default" or spec.exported_name == "default"):
          continue
        exp_name = spec.exported_name
        sym = self._mangle_name(spec.symbol)
        if exp_name == primary_raw and not spec.module_prefix:
          continue
        if spec.module_prefix:
          mod_prefix = self._mangle_dotted(spec.module_prefix)
          val_expr = f"{mod_prefix}.{sym}"
        else:
          val_expr = sym
        self._emit_export_prop(primary_sym, exp_name, val_expr)
      self.emit(f"return {primary_sym}")
      self.newline()
    else:
      self.emit("local _M = {}")
      self.newline()
      for spec in node.specifiers:
        exp_name = spec.exported_name
        sym = self._mangle_name(spec.symbol)
        if spec.module_prefix:
          mod_prefix = self._mangle_dotted(spec.module_prefix)
          val_expr = f"{mod_prefix}.{sym}"
        else:
          val_expr = sym
        self._emit_export_prop("_M", exp_name, val_expr)
      self.emit("return _M")
      self.newline()

  def _emit_struct_init_fields(self, node: StructDeclNode) -> None:
    """Emits `Struct._init_fields(self)` to apply parent and field defaults."""
    struct_name = self._mangle_name(node.name)
    self.emit(f"function {struct_name}._init_fields(self)")
    self.indent()
    if node.parent_names:
      for p in node.parent_names:
        mp = self._mangle_dotted(p)
        self.newline()
        self.emit(f"if {mp}._init_fields then {mp}._init_fields(self) end")
    for f in node.fields:
      default_expr = f.default_expr or get_default_value_for_type_node(
          f.field_type
      )
      if default_expr:
        self.newline()
        temp = self._make_expr_transpiler()
        temp.visit(default_expr)
        self.emit(f"self.{self._mangle_name(f.name)} = {temp.get_output()}")
    self.dedent()
    self.newline()
    self.emit("end")
    self.newline()

  def _emit_struct_init_constructor(
      self, node: StructDeclNode, methods: List[Any]
  ) -> None:
    """Emits `Struct.init(...)` handling proto delegation, `__init__`, and kwargs."""
    struct_name = self._mangle_name(node.name)
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
          'local proto = (_n_args == 2 and type(select(2, ...)) == "table") and select(2, ...) or nil'
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
      self.newline()
      self.emit(f"if {struct_name}._init_sapphire then")
      self.indent()
      self.newline()
      self.emit("if _n_args > 1 then")
      self.indent()
      self.newline()
      self.emit(f"{struct_name}._init_sapphire(self, ...)")
      self.dedent()
      self.newline()
      self.emit("elseif _n_args == 1 then")
      self.indent()
      self.newline()
      self.emit("local _arg1 = ...")
      self.newline()
      init_params = [
          p for p in init_member.func_decl.parameters if p.name != "self"
      ]
      if len(init_params) == 0:
        self.emit(f"{struct_name}._init_sapphire(self)")
      else:
        init_args = []
        for idx, p in enumerate(init_params):
          pname = self._mangle_name(p.name)
          unset_val = (
              "_SP_RT._SP_UNSET"
              if isinstance(p.param_type, OptionalTypeNode)
              else "nil"
          )
          init_args.append(
              f"(function() if _arg1['{pname}'] ~= nil then "
              f"return _SP_RT._unwrap_opt(_arg1['{pname}']) "
              f"elseif _arg1[{idx + 1}] ~= nil then "
              f"return _SP_RT._unwrap_opt(_arg1[{idx + 1}]) "
              f"else return {unset_val} end end)()"
          )
        call_args = ["self"] + init_args
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
        self.newline()
        self.emit(f"{struct_name}._init_sapphire({', '.join(call_args)})")
        self.dedent()
        self.newline()
        self.emit("else")
        self.indent()
        self.newline()
        self.emit(f"{struct_name}._init_sapphire(self, _arg1)")
        self.dedent()
        self.newline()
        self.emit("end")
      self.dedent()
      self.newline()
      self.emit("else")
      self.indent()
      self.newline()
      self.emit(f"{struct_name}._init_sapphire(self)")
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
      for idx, f in enumerate(node.fields):
        self.newline()
        self.emit(
            f"if _args[{idx + 1}] ~= nil then self.{self._mangle_name(f.name)} = _args[{idx + 1}] end"
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
      self.emit('if type(k) == "string" then self[k] = _SP_RT._unwrap_opt(v) end')
      self.dedent()
      self.newline()
      self.emit("end")
      for idx, f in enumerate(node.fields):
        fname = self._mangle_name(f.name)
        self.newline()
        self.emit(
            f"if _arg1[{idx + 1}] ~= nil and _arg1['{fname}'] == nil then self.{fname} = _SP_RT._unwrap_opt(_arg1[{idx + 1}]) end"
        )
      self.dedent()
      self.newline()
      self.emit("else")
      self.indent()
      if node.fields:
        self.newline()
        self.emit(f"self.{self._mangle_name(node.fields[0].name)} = _arg1")
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

  def _emit_diamond_del_guard(self, raw_struct_name: str) -> None:
    """Emits per-class destruction tracking so diamond bases run `__del__` once."""
    self.newline()
    self.emit('local _sp_d = rawget(self, "_sapphire_destroyed_classes_")')
    self.newline()
    self.emit('if not _sp_d then _sp_d = {}; rawset(self, "_sapphire_destroyed_classes_", _sp_d) end')
    self.newline()
    self.emit(f'if _sp_d["{raw_struct_name}"] then return end')
    self.newline()
    self.emit(f'_sp_d["{raw_struct_name}"] = true')

  def visit_StructDeclNode(self, node: StructDeclNode) -> None:
    """Emits Lua table, metatable inheritance, constructor, methods, and `__del__`."""
    self.known_structs.add(node.name)
    self.declared_symbols.append(node.name)
    is_proto = node.is_prototype
    raw_name = node.name
    struct_name = self._mangle_name(raw_name)
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
      else:
        chain = " or ".join(f"{p}[k]" for p in mangled_parents)
        self.emit(
            f"setmetatable({struct_name}, {{ __index = function(t, k) return {chain} end }})"
        )
      self.newline()

    self._emit_struct_init_fields(node)
    self._emit_struct_init_constructor(node, methods)

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
      self._emit_diamond_del_guard(raw_name)
      self._emit_struct_auto_teardown(raw_name, call_parents=True)
      self.dedent()
      self.newline()
      self.emit("end")
      self.newline()

  def _emit_destructor_call(self, var_name: str) -> None:
    """Emits Lua destructor teardown (`destroy()` for Arena, `_SP_RT._sapphire_del` otherwise)."""
    if self.variable_types.get(var_name) == "Arena":
      self.emit(f"if {var_name} ~= nil then {var_name}:destroy() end")
    else:
      self.emit(f"_SP_RT._sapphire_del({var_name})")

  def _emit_struct_auto_teardown(
      self, struct_name: str, call_parents: bool = True
  ) -> None:
    """Emits LIFO `_SP_RT._sapphire_del` calls for destructible fields and parents in Lua."""
    for f_name in reversed(self.struct_destructible_fields.get(struct_name, [])):
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

  def _has_optional_default_param(self, params: List[Any]) -> bool:
    """Returns True if any parameter has both an optional type and a default value."""
    return any(
        p.default_expr is not None and isinstance(p.param_type, OptionalTypeNode)
        for p in params
    )

  def _emit_default_params(
      self, params: List[Any], has_opt_default: bool
  ) -> None:
    """Emits parameter unpacking (for optional defaults) and default assignments."""
    if has_opt_default:
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
        cond = f"_n_args < {idx + 1} or {pname} == _SP_RT._SP_UNSET"
      elif has_opt_default:
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
        temp = self._make_expr_transpiler()
        temp.visit(p.default_expr)
        self.emit(f"if {cond} then {pname} = {temp.get_output()} end")

  def _visit_ImplMemberNode_for_struct(self, node: ImplMemberNode,
                                       struct_name: str) -> None:
    func = node.func_decl
    is_test_func = any(
        getattr(a, "name", "") == "test"
        for a in getattr(func, "annotations", [])
    )
    if is_test_func and not self.test_mode:
      return

    m_struct = self._mangle_name(struct_name)
    func_name = "_init_sapphire" if func.name == "__init__" else self._mangle_name(func.name)
    non_self_params = [p for p in func.parameters if p.name != "self"]
    has_opt_default = self._has_optional_default_param(non_self_params)
    params = [self._mangle_name(p.name) for p in non_self_params]
    sig_params = "..." if has_opt_default else ", ".join(params)

    self.newline()
    if node.modifier == "static":
      self.emit(f"function {m_struct}.{func_name}({sig_params})")
    else:
      self.emit(f"function {m_struct}:{func_name}({sig_params})")

    self.indent()
    self._emit_default_params(non_self_params, has_opt_default)

    if is_coroutine_func(func):
      self.newline()
      all_params = (["self"] if node.modifier != "static" else []) + params
      if all_params:
        self.emit(f"return _SP_RT._Coroutine.create(function({', '.join(all_params)})")
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
                  if getattr(m, "func_decl", None) and m.func_decl.name == "__init__"
              ),
              None,
          )
          p_init_params = (
              [p for p in p_init.func_decl.parameters if p.name != "self"]
              if p_init
              else []
          )
          if resolved is not None:
            if getattr(base_init, "_requires_eval_order_temps", False):
              temp_binds = []
              for arg_idx, arg in enumerate(base_init.arguments):
                temp = self._make_expr_transpiler()
                temp.visit(arg.expr)
                temp_binds.append(f"local _a{arg_idx} = {temp.get_output()}")
              slot_to_temp = {
                  slot: f"_a{arg_idx}"
                  for arg_idx, slot in enumerate(
                      getattr(base_init, "_eval_order_slots", [])
                  )
              }
              call_args = ["self"]
              for i in range(len(resolved)):
                if i in slot_to_temp:
                  call_args.append(slot_to_temp[i])
                elif i < len(p_init_params) and isinstance(
                    p_init_params[i].param_type, OptionalTypeNode
                ):
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
              for idx, expr in enumerate(resolved):
                if (
                    idx in omitted_slots
                    and idx < len(p_init_params)
                    and isinstance(p_init_params[idx].param_type, OptionalTypeNode)
                ):
                  args_strs.append("_SP_RT._SP_UNSET")
                else:
                  temp = self._make_expr_transpiler()
                  temp.visit(expr)
                  args_strs.append(temp.get_output())
              self.newline()
              self.emit(f"{parent_name}._init_sapphire({', '.join(args_strs)})")
            continue

          param_names = [p.name for p in p_init_params]

          args_strs = ["self"]
          if param_names:
            args_by_name = {}
            for idx, arg in enumerate(base_init.arguments):
              temp = self._make_expr_transpiler()
              temp.visit(arg.expr)
              val = temp.get_output()
              if arg.name:
                args_by_name[arg.name] = val
              elif idx < len(param_names):
                args_by_name[param_names[idx]] = val
            for idx, p_name in enumerate(param_names):
              if p_name in args_by_name:
                args_strs.append(args_by_name[p_name])
              elif isinstance(p_init_params[idx].param_type, OptionalTypeNode):
                args_strs.append("_SP_RT._SP_UNSET")
              else:
                args_strs.append("nil")
          else:
            for arg in base_init.arguments:
              temp = self._make_expr_transpiler()
              temp.visit(arg.expr)
              args_strs.append(temp.get_output())

          self.newline()
          self.emit(f"{parent_name}._init_sapphire({', '.join(args_strs)})")

      if func.name == "__del__":
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
    self.dedent()
    self.newline()
    self.emit("end")
    export_ann = next(
        (a for a in getattr(func, "annotations", []) if a.name == "export"),
        None,
    )
    if export_ann and export_ann.arg:
      alias_name = self._mangle_name(export_ann.arg)
      if alias_name != func_name:
        self.newline()
        self.emit(f"{m_struct}.{alias_name} = {m_struct}.{func_name}")
    self.newline()

  def visit_TraitDeclNode(self, node: TraitDeclNode) -> None:
    default_members = [m for m in node.members if getattr(m, "body", None) is not None]
    if not default_members:
      # Pure abstract traits are compile-time contracts erased at runtime
      return
    m_trait = self._mangle_name(node.name)
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
    is_test_func = any(getattr(a, "name", "") == "test" for a in getattr(node, "annotations", []))
    if is_test_func and not self.test_mode:
      return
    if is_test_func:
      self.declared_symbols.append(node.name)

    fn_name = self._mangle_name(node.name)
    if any(getattr(a, "name", "") == "on_reload" for a in getattr(node, "annotations", [])):
      self.on_reload_callbacks.append(fn_name)

    export_ann = next((a for a in node.annotations if a.name == "export"), None)
    has_opt_default = self._has_optional_default_param(node.parameters)
    params = [self._mangle_name(p.name) for p in node.parameters]
    sig_params = "..." if has_opt_default else ", ".join(params)

    self.newline()
    if export_ann:
      target_path = export_ann.arg if export_ann.arg else fn_name
      self.emit(f"function {target_path}({sig_params})")
    else:
      self.emit(f"function {fn_name}({sig_params})")

    self.indent()
    if self.dev_mode and export_ann and export_ann.arg == "love.update":
      self.newline()
      self.emit("if _SP_DEV_WATCHER then _SP_DEV_WATCHER.check(dt) end")

    self._emit_default_params(node.parameters, has_opt_default)

    if is_coroutine_func(node):
      self.newline()
      if params:
        self.emit(f"return _SP_RT._Coroutine.create(function({', '.join(params)})")
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
    self.dedent()
    self.newline()
    self.emit("end")
    self.newline()

  # ==========================================
  # Statements Visitor
  # ==========================================

