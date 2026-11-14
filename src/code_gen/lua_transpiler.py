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
local _Coroutine, Arena, _clone_helper, _create_cow_proxy, _create_proto_object = _SP_RT._Coroutine, _SP_RT.Arena, _SP_RT._clone_helper, _SP_RT._create_cow_proxy, _SP_RT._create_proto_object
local _sapphire_string_strip, _sapphire_string_split, _sapphire_string_find, _sapphire_string_to_int, _sapphire_string_to_float, _sapphire_string_to_bool, _sapphire_cast_int, _sapphire_enum_from = _SP_RT._sapphire_string_strip, _SP_RT._sapphire_string_split, _SP_RT._sapphire_string_find, _SP_RT._sapphire_string_to_int, _SP_RT._sapphire_string_to_float, _SP_RT._sapphire_string_to_bool, _SP_RT._sapphire_cast_int, _SP_RT._sapphire_enum_from
local _sapphire_array_map, _sapphire_array_filter, _sapphire_array_reduce, _sapphire_array_contains, _sapphire_array_reverse, _sapphire_array_sort, _sapphire_array_join, _sapphire_array_push, _sapphire_array_pop, _sapphire_array_insert, _sapphire_array_remove, _sapphire_array_clear, _sapphire_array_swap, _sapphire_array_get, _sapphire_array_idx = _SP_RT._sapphire_array_map, _SP_RT._sapphire_array_filter, _SP_RT._sapphire_array_reduce, _SP_RT._sapphire_array_contains, _SP_RT._sapphire_array_reverse, _SP_RT._sapphire_array_sort, _SP_RT._sapphire_array_join, _SP_RT._sapphire_array_push, _SP_RT._sapphire_array_pop, _SP_RT._sapphire_array_insert, _SP_RT._sapphire_array_remove, _SP_RT._sapphire_array_clear, _SP_RT._sapphire_array_swap, _SP_RT._sapphire_array_get, _SP_RT._sapphire_array_idx
local _sapphire_map_size, _sapphire_map_empty, _sapphire_map_contains, _sapphire_map_get, _sapphire_map_keys, _sapphire_map_values, _sapphire_map_insert, _sapphire_map_remove, _sapphire_map_clear = _SP_RT._sapphire_map_size, _SP_RT._sapphire_map_empty, _SP_RT._sapphire_map_contains, _SP_RT._sapphire_map_get, _SP_RT._sapphire_map_keys, _SP_RT._sapphire_map_values, _SP_RT._sapphire_map_insert, _SP_RT._sapphire_map_remove, _SP_RT._sapphire_map_clear
local _sapphire_iter_array, _sapphire_range, _sapphire_del, _Ref, Ref, _SharedRef, _WeakRef, SharedRef, WeakRef = _SP_RT._sapphire_iter_array, _SP_RT._sapphire_range, _SP_RT._sapphire_del, _SP_RT._Ref, _SP_RT.Ref, _SP_RT._SharedRef, _SP_RT._WeakRef, _SP_RT.SharedRef, _SP_RT.WeakRef
"""

LUA_RUNTIME_MODULE_EXPORTS = """
return {
  _Coroutine = _Coroutine,
  Arena = Arena,
  _clone_helper = _clone_helper,
  _create_cow_proxy = _create_cow_proxy,
  _create_proto_object = _create_proto_object,
  _sapphire_string_strip = _sapphire_string_strip,
  _sapphire_string_split = _sapphire_string_split,
  _sapphire_string_find = _sapphire_string_find,
  _sapphire_string_to_int = _sapphire_string_to_int,
  _sapphire_string_to_float = _sapphire_string_to_float,
  _sapphire_string_to_bool = _sapphire_string_to_bool,
  _sapphire_cast_int = _sapphire_cast_int,
  _sapphire_enum_from = _sapphire_enum_from,
  _sapphire_array_map = _sapphire_array_map,
  _sapphire_array_filter = _sapphire_array_filter,
  _sapphire_array_reduce = _sapphire_array_reduce,
  _sapphire_array_contains = _sapphire_array_contains,
  _sapphire_array_reverse = _sapphire_array_reverse,
  _sapphire_array_sort = _sapphire_array_sort,
  _sapphire_array_join = _sapphire_array_join,
  _sapphire_array_push = _sapphire_array_push,
  _sapphire_array_pop = _sapphire_array_pop,
  _sapphire_array_insert = _sapphire_array_insert,
  _sapphire_array_remove = _sapphire_array_remove,
  _sapphire_array_clear = _sapphire_array_clear,
  _sapphire_array_swap = _sapphire_array_swap,
  _sapphire_array_get = _sapphire_array_get,
  _sapphire_array_idx = _sapphire_array_idx,
  _sapphire_map_size = _sapphire_map_size,
  _sapphire_map_empty = _sapphire_map_empty,
  _sapphire_map_contains = _sapphire_map_contains,
  _sapphire_map_get = _sapphire_map_get,
  _sapphire_map_keys = _sapphire_map_keys,
  _sapphire_map_values = _sapphire_map_values,
  _sapphire_map_insert = _sapphire_map_insert,
  _sapphire_map_remove = _sapphire_map_remove,
  _sapphire_map_clear = _sapphire_map_clear,
  _sapphire_iter_array = _sapphire_iter_array,
  _sapphire_range = _sapphire_range,
  _sapphire_del = _sapphire_del,
  _Ref = _Ref,
  Ref = Ref,
  _SharedRef = _SharedRef,
  _WeakRef = _WeakRef,
  SharedRef = SharedRef,
  WeakRef = WeakRef,
}
"""


LUA_RESERVED_WORDS = {
    "and", "break", "do", "else", "elseif", "end", "false", "for",
    "function", "goto", "if", "in", "local", "nil", "not", "or",
    "repeat", "return", "then", "true", "until", "while",
}


@TranspilerRegistry.register(aliases=["lua", "lua5.1", "love2d", "love"], display_name="Lua 5.1", default_extension=".lua")
@TranspilerRegistry.register(aliases=["lua", "lua5.1", "love2d", "love"], display_name="Lua 5.1", default_extension=".lua")
class LuaTranspiler(LuaStmtMixin, LuaExprMixin, BaseTranspiler):

  """AST visitor to transpile Sapphire code to Lua 5.1."""

  def _mangle_name(self, name: str) -> str:
    """Mangles Sapphire identifiers that collide with Lua reserved keywords."""
    if not name:
      return name
    if name in ("self", "__init__", "__del__", "_init_sapphire"):
      return name
    if name in LUA_RESERVED_WORDS:
      return f"{name}_"
    return name

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
    self.structs_with_destructor: Set[str] = {"Arena"}
    self.proto_structs: Set[str] = set()
    self.struct_destructible_fields: Dict[str, List[str]] = {}
    self.struct_parent_names: Dict[str, List[str]] = {}
    self.moved_vars: Set[str] = set()
    self._branch_depth: int = 0
    self._var_branch_depth: Dict[str, int] = {}
    self._pending_null_vars: List[str] = []
    self.func_return_types: Dict[str, str] = {}
    self.method_return_types: Dict[str, str] = {}
    self.variable_types: Dict[str, str] = {}
    self._identifier_map: Dict[str, str] = {}
    self._loop_stack: List[bool] = []

  def emit(self, text: str) -> None:
    """Emits text on the current line and updates line/column numbers."""
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
        self.newline()
        self.emit(f"_M.{sym} = {sym}")
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
        self.source_map_builder.add_mapping(
            gen_line=self.current_line,
            gen_col=self.current_column,
            source_file=src,
            orig_line=node.start_line,
            orig_col=node.start_column or 0,
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
    raw_alias = node.alias if node.alias else node.path.split(".")[-1]
    alias_name = self._mangle_name(raw_alias)
    self.imported_modules.add(alias_name)
    self.emit(f"local {alias_name} = require(\"{node.path}\")")
    if self.dev_mode:
      file_path = node.path.replace(".", "/") + ".lua"
      self.newline()
      self.emit(f"if _SP_DEV_WATCHER and _SP_DEV_WATCHER.register_file then _SP_DEV_WATCHER.register_file(\"{file_path}\") end")
    self.newline()

  def visit_ExportStmtNode(self, node: ExportStmtNode) -> None:
    self.newline()
    default_spec = next(
        (
            s
            for s in node.specifiers
            if (s.alias == "default" or s.exported_name == "default")
            and not s.module_prefix
        ),
        None,
    )
    if default_spec is None and len(node.specifiers) == 1 and not node.specifiers[0].module_prefix:
      if node.specifiers[0].symbol in self.known_structs:
        default_spec = node.specifiers[0]

    if default_spec is not None:
      primary_sym = default_spec.symbol
      self.emit(f"{primary_sym}.{primary_sym} = {primary_sym}")
      self.newline()
      self.emit(f"{primary_sym}.default = {primary_sym}")
      self.newline()
      for spec in node.specifiers:
        if spec is default_spec and (spec.alias == "default" or spec.exported_name == "default"):
          continue
        exp_name = spec.exported_name
        sym = self._mangle_name(spec.symbol)
        if exp_name == primary_sym and not spec.module_prefix:
          continue
        prop_access = f'["{exp_name}"]' if exp_name in LUA_RESERVED_WORDS else f".{exp_name}"
        if spec.module_prefix:
          self.emit(f"{primary_sym}{prop_access} = {spec.module_prefix}.{sym}")
        else:
          self.emit(f"{primary_sym}{prop_access} = {sym}")
        self.newline()
      self.emit(f"return {primary_sym}")
      self.newline()
    else:
      self.emit("local _M = {}")
      self.newline()
      for spec in node.specifiers:
        exp_name = spec.exported_name
        sym = self._mangle_name(spec.symbol)
        prop_access = f'["{exp_name}"]' if exp_name in LUA_RESERVED_WORDS else f".{exp_name}"
        if spec.module_prefix:
          self.emit(f"_M{prop_access} = {spec.module_prefix}.{sym}")
        else:
          self.emit(f"_M{prop_access} = {sym}")
        self.newline()
      self.emit("return _M")
      self.newline()

  def visit_StructDeclNode(self, node: StructDeclNode) -> None:
    # Header definition for struct
    self.known_structs.add(node.name)
    self.declared_symbols.append(node.name)
    is_proto = node.is_prototype
    struct_name = node.name
    methods = self.struct_methods.get(struct_name, [])

    self.newline()
    if self.dev_mode:
      self.emit(f"{struct_name} = {struct_name} or {{}}")
    else:
      self.emit(f"{struct_name} = {{}}")
    self.newline()
    self.emit(f"{struct_name}.__index = {struct_name}")
    self.newline()

    if node.parent_names:
      if len(node.parent_names) == 1:
        self.emit(f"setmetatable({struct_name}, {{ __index = {node.parent_names[0]} }})")
      else:
        chain = " or ".join(f"{p}[k]" for p in node.parent_names)
        self.emit(f"setmetatable({struct_name}, {{ __index = function(t, k) return {chain} end }})")
      self.newline()

    # Define helper `._init_fields(self)`
    self.emit(f"function {struct_name}._init_fields(self)")
    self.indent()
    if node.parent_names:
      for p in node.parent_names:
        self.newline()
        self.emit(f"if {p}._init_fields then {p}._init_fields(self) end")
    for f in node.fields:
      default_expr = f.default_expr or get_default_value_for_type_node(f.field_type)
      if default_expr:
        self.newline()
        temp = LuaTranspiler()
        temp.known_structs = self.known_structs
        temp.visit(default_expr)
        self.emit(f"self.{self._mangle_name(f.name)} = {temp.get_output()}")
    self.dedent()
    self.newline()
    self.emit("end")
    self.newline()

    # Define constructor `.init(...)`
    self.emit(f"function {struct_name}.init(...)")
    self.indent()
    self.newline()
    self.emit("local _n_args = select(\"#\", ...)")
    self.newline()
    self.emit("local self")
    self.newline()
    if is_proto:
      self.emit(f"local proto = (_n_args == 2 and type(select(2, ...)) == \"table\") and select(2, ...) or nil")
      self.newline()
      self.emit(f"self = _create_proto_object(proto, {struct_name})")
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

    init_member = next((m for m in methods if m.func_decl.name == "__init__"), None)
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
      init_params = init_member.func_decl.parameters
      if len(init_params) == 0:
        self.emit(f"{struct_name}._init_sapphire(self)")
      else:
        init_args = []
        for idx, p in enumerate(init_params):
          init_args.append(f"(_arg1['{p.name}'] ~= nil and _arg1['{p.name}'] or _arg1[{idx + 1}])")
        call_args = ["self"] + init_args

        param_checks = " or ".join(f"_arg1['{p.name}'] ~= nil" for p in init_params)
        self.emit(f"if type(_arg1) == \"table\" and ({param_checks} or _arg1[1] ~= nil) then")
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
        self.emit(f"if _args[{idx + 1}] ~= nil then self.{self._mangle_name(f.name)} = _args[{idx + 1}] end")
      self.dedent()
      self.newline()
      self.emit("elseif _n_args == 1 then")
      self.indent()
      self.newline()
      self.emit("local _arg1 = ...")
      self.newline()
      self.emit("if type(_arg1) == \"table\" then")
      self.indent()
      self.newline()
      self.emit("for k, v in pairs(_arg1) do")
      self.indent()
      self.newline()
      self.emit("if type(k) == \"string\" then self[k] = v end")
      self.dedent()
      self.newline()
      self.emit("end")
      for idx, f in enumerate(node.fields):
        self.newline()
        self.emit(f"if _arg1[{idx + 1}] ~= nil and self.{self._mangle_name(f.name)} == nil then self.{self._mangle_name(f.name)} = _arg1[{idx + 1}] end")
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
        and struct_name in self.structs_with_destructor
        and bool(
            self.struct_destructible_fields.get(struct_name)
            or len(destructible_parents) > 1
        )
    )

    # Emit methods from impl block
    for m in methods:
      self._visit_ImplMemberNode_for_struct(m, struct_name)

    if needs_synth_del:
      self.newline()
      self.emit(f"function {struct_name}:__del__()")
      self.indent()
      self._emit_struct_auto_teardown(struct_name, call_parents=True)
      self.dedent()
      self.newline()
      self.emit("end")
      self.newline()

  def _emit_destructor_call(self, var_name: str) -> None:
    """Emits Lua destructor teardown (`destroy()` for Arena, `_sapphire_del` otherwise)."""
    if self.variable_types.get(var_name) == "Arena":
      self.emit(f"if {var_name} ~= nil then {var_name}:destroy() end")
    else:
      self.emit(f"_sapphire_del({var_name})")

  def _emit_struct_auto_teardown(
      self, struct_name: str, call_parents: bool = True
  ) -> None:
    """Emits LIFO `_sapphire_del` calls for destructible fields and parents in Lua."""
    for f_name in reversed(self.struct_destructible_fields.get(struct_name, [])):
      self.newline()
      self.emit(f"_sapphire_del(self.{self._mangle_name(f_name)})")
    if call_parents:
      for p_name in reversed(self.struct_parent_names.get(struct_name, [])):
        if p_name in self.structs_with_destructor:
          self.newline()
          self.emit(f"if {p_name}.__del__ then {p_name}.__del__(self) end")

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

  def _visit_ImplMemberNode_for_struct(self, node: ImplMemberNode,
                                       struct_name: str) -> None:
    func = node.func_decl
    is_test_func = any(
        getattr(a, "name", "") == "test"
        for a in getattr(func, "annotations", [])
    )
    if is_test_func and not self.test_mode:
      return

    func_name = "_init_sapphire" if func.name == "__init__" else self._mangle_name(func.name)
    self.newline()

    if node.modifier == "static":
      params = [self._mangle_name(p.name) for p in func.parameters if p.name != "self"]
      self.emit(f"function {struct_name}.{func_name}({', '.join(params)})")
    else:
      other_params = [self._mangle_name(p.name) for p in func.parameters if p.name != "self"]
      self.emit(f"function {struct_name}:{func_name}({', '.join(other_params)})")

    self.indent()
    for p in func.parameters:
      if p.default_expr:
        self.newline()
        temp = LuaTranspiler()
        temp.known_structs = self.known_structs
        temp.visit(p.default_expr)
        pname = self._mangle_name(p.name)
        self.emit(f"if {pname} == nil then {pname} = {temp.get_output()} end")
    if is_coroutine_func(func):
      self.newline()
      all_params = (["self"] if node.modifier != "static" else []) + [p.name for p in func.parameters if p.name != "self"]
      if all_params:
        self.emit(f"return _Coroutine.create(function({', '.join(all_params)})")
      else:
        self.emit("return _Coroutine.create(function()")
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
          parent_name = base_init.callee.name
          p_members = self.struct_methods.get(parent_name, [])
          p_init = next((m for m in p_members if getattr(m, "func_decl", None) and m.func_decl.name == "__init__"), None)
          param_names = [p.name for p in p_init.func_decl.parameters if p.name != "self"] if p_init else []

          args_strs = ["self"]
          if param_names:
            args_by_name = {}
            for idx, arg in enumerate(base_init.arguments):
              temp = LuaTranspiler()
              temp.known_structs = self.known_structs
              temp.visit(arg.expr)
              val = temp.get_output()
              if arg.name:
                args_by_name[arg.name] = val
              elif idx < len(param_names):
                args_by_name[param_names[idx]] = val
            args_strs.extend(args_by_name.get(p_name, "nil") for p_name in param_names)
          else:
            for arg in base_init.arguments:
              temp = LuaTranspiler()
              temp.known_structs = self.known_structs
              temp.visit(arg.expr)
              args_strs.append(temp.get_output())

          self.newline()
          self.emit(f"{parent_name}._init_sapphire({', '.join(args_strs)})")
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
    self.newline()

  def visit_TraitDeclNode(self, node: TraitDeclNode) -> None:
    # Traits are compile-time contracts erased at runtime
    pass

  def visit_FuncDeclNode(self, node: FuncDeclNode) -> None:
    is_test_func = any(getattr(a, "name", "") == "test" for a in getattr(node, "annotations", []))
    if is_test_func and not self.test_mode:
      return
    if is_test_func:
      self.declared_symbols.append(node.name)

    if any(getattr(a, "name", "") == "on_reload" for a in getattr(node, "annotations", [])):
      self.on_reload_callbacks.append(node.name)

    export_ann = next((a for a in node.annotations if a.name == "export"), None)
    fn_name = self._mangle_name(node.name)
    params = [self._mangle_name(p.name) for p in node.parameters]

    self.newline()
    if export_ann:
      target_path = export_ann.arg if export_ann.arg else fn_name
      self.emit(f"function {target_path}({', '.join(params)})")
    else:
      self.emit(f"function {fn_name}({', '.join(params)})")

    self.indent()
    if self.dev_mode and export_ann and export_ann.arg == "love.update":
      self.newline()
      self.emit("if _SP_DEV_WATCHER then _SP_DEV_WATCHER.check(dt) end")

    # Check default parameters
    for p in node.parameters:
      if p.default_expr:
        self.newline()
        temp = LuaTranspiler()
        temp.known_structs = self.known_structs
        temp.visit(p.default_expr)
        pname = self._mangle_name(p.name)
        self.emit(f"if {pname} == nil then {pname} = {temp.get_output()} end")
    if is_coroutine_func(node):
      self.newline()
      if params:
        self.emit(f"return _Coroutine.create(function({', '.join(params)})")
      else:
        self.emit("return _Coroutine.create(function()")
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

