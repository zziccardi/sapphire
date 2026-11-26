"""Declaration pass for Sapphire semantic analyzer.

Handles Pass 0 (imported module declarations) and Pass 1 (global declarations
for structs, enums, traits, externs, and functions).
"""

import os
import re
from typing import Any

from antlr4 import CommonTokenStream, InputStream

try:
  from pygls.uris import from_fs_path
except ImportError:
  from pathlib import Path

  def from_fs_path(path: str) -> str:
    return Path(path).resolve().as_uri()


from sapphire.code_gen.intrinsics import is_builtin_module
from sapphire.common.diagnostics import format_diagnostic
from sapphire.common.errors import SapphireSyntaxError, SemanticError
from sapphire.parser.ast import (
  ASTNode,
  EnumDeclNode,
  FuncDeclNode,
  IdentifierNode,
  ImplBlockNode,
  MemberAccessNode,
  ParameterNode,
  ProgramNode,
  StructDeclNode,
  TraitDeclNode,
  VarDeclNode,
)
from sapphire.parser.ast_builder import ASTBuilder
from sapphire.parser.error_listener import CustomErrorListener
from sapphire.parser.gen.SapphireLexer import SapphireLexer
from sapphire.parser.gen.SapphireParser import SapphireParser
from sapphire.semantics.module_resolver import resolve_module_path
from sapphire.semantics.symbol_table import (
  EnumSymbol,
  EnumType,
  FunctionSymbol,
  FunctionType,
  GenericTypeParameter,
  ModuleSymbol,
  ModuleType,
  PrimitiveType,
  StructSymbol,
  StructType,
  TraitSymbol,
  TraitType,
  Type,
  VariableSymbol,
)


class DeclarationPass:
  """Executes preliminary module imports and top-level global symbol
  registration.
  """

  # Cache of clean, cycle-free parsed and typechecked modules on disk:
  # abs_file_path -> (mtime, file_size, exports_dict, dep_stats)
  _module_cache: dict[str, Any] = {}

  @classmethod
  def clear_cache(cls) -> None:
    """Clears the cached imported module declarations."""
    cls._module_cache.clear()

  VALID_ANNOTATION_PATH_RE = re.compile(
    r"^[a-zA-Z_][a-zA-Z0-9_]*(\.[a-zA-Z_][a-zA-Z0-9_]*)*$"
  )

  @staticmethod
  def validate_annotations(
    checker: Any, annotations: list[Any], node: Any | None = None
  ) -> None:
    """Validates that @extern and @export string arguments are well-formed
    identifier paths.
    """
    for ann in annotations or []:
      if ann.name in ("extern", "export") and ann.arg is not None:
        if not DeclarationPass.VALID_ANNOTATION_PATH_RE.match(ann.arg):
          checker.error(
            f"Invalid identifier path in '@{ann.name}' annotation: "
            f"'{ann.arg}'.",
            node=node,
          )

  @staticmethod
  def validate_parameter_defaults(
    checker: Any, parameters: list[ParameterNode]
  ) -> None:
    """Validates that parameters without default values do not follow parameters
    with default values.
    """
    seen_default = False
    for p in parameters:
      if getattr(p, "default_expr", None) is not None:
        seen_default = True
      elif seen_default:
        checker.error(
          f"Parameter without a default value '{p.name}' cannot follow a "
          "parameter with a default value.",
          node=p,
        )

  @staticmethod
  def _is_cache_entry_valid(
    cached_entry: Any, mtime: int | None, fsize: int | None
  ) -> bool:
    """Returns True if a cached module and all transitive deps match disk."""
    if (
      cached_entry is None
      or mtime is None
      or fsize is None
      or cached_entry[0] != mtime
      or cached_entry[1] != fsize
    ):
      return False
    dep_stats = cached_entry[3] if len(cached_entry) > 3 else {}
    for dep_path, (dep_mtime, dep_fsize) in dep_stats.items():
      try:
        dep_stat = os.stat(dep_path)
      except OSError:
        return False
      if dep_stat.st_mtime_ns != dep_mtime or dep_stat.st_size != dep_fsize:
        return False
    return True

  @staticmethod
  def _propagate_import_errors(
    checker: Any, imp: Any, mod_errors: list[str], reported_errors: set[str]
  ) -> None:
    """Propagates imported module diagnostics to the importing checker."""
    if not mod_errors:
      return
    if hasattr(checker, "lsp_errors"):
      reported_sites = getattr(checker, "_reported_lsp_import_sites", None)
      if reported_sites is None:
        reported_sites = set()
        checker._reported_lsp_import_sites = reported_sites
      site_key = (
        imp.path,
        getattr(imp, "start_line", None),
        getattr(imp, "start_column", None),
      )
      if site_key not in reported_sites:
        reported_sites.add(site_key)
        checker.error(
          f"Imported module '{imp.path}' contains syntax or semantic errors.",
          node=imp,
        )
      return

    for err in mod_errors:
      if err not in reported_errors:
        reported_errors.add(err)
        checker.errors.append(err)

  @staticmethod
  def _mark_file_uri(node: Any, mod_file_uri: str) -> None:
    """Tags AST nodes recursively with their defining file URI."""
    if not isinstance(node, ASTNode):
      return
    node.file_uri = mod_file_uri
    for val in node.__dict__.values():
      if isinstance(val, list):
        for item in val:
          if isinstance(item, ASTNode):
            DeclarationPass._mark_file_uri(item, mod_file_uri)
      elif isinstance(val, ASTNode):
        DeclarationPass._mark_file_uri(val, mod_file_uri)

  @staticmethod
  def _extract_module_exports(
    sub_checker: Any, sub_ast: Any, mod_sym: ModuleSymbol
  ) -> dict[str, Any]:
    """Collects exported symbols and types from a checked imported module."""
    computed_exports: dict[str, Any] = {}
    defining_mod = mod_sym.file_path or mod_sym.module_path
    if getattr(sub_ast, "export_block", None):
      for spec in sub_ast.export_block.specifiers:
        export_name = spec.alias or spec.symbol
        if spec.module_prefix:
          prefix_sym = sub_checker.symbol_table.lookup(spec.module_prefix)
          if isinstance(prefix_sym, ModuleSymbol):
            exp = prefix_sym.lookup_export(spec.symbol)
            if exp:
              computed_exports[export_name] = exp
        else:
          exp = sub_checker.symbol_table.lookup(
            spec.symbol
          ) or sub_checker.symbol_table.lookup_type(spec.symbol)
          if exp:
            if isinstance(exp, StructType):
              exp.is_imported = True
              exp.defining_module = defining_mod
            elif isinstance(exp, (TraitType, EnumType)):
              exp.defining_module = defining_mod
            elif hasattr(exp, "struct_type"):
              exp.struct_type.is_imported = True
              exp.struct_type.defining_module = defining_mod
            elif isinstance(getattr(exp, "symbol_type", None), StructType):
              exp.symbol_type.is_imported = True
              exp.symbol_type.defining_module = defining_mod
            elif isinstance(
              getattr(exp, "symbol_type", None), (TraitType, EnumType)
            ):
              exp.symbol_type.defining_module = defining_mod
            computed_exports[export_name] = exp
    else:
      sub_root = sub_checker.symbol_table.current_scope
      while sub_root.parent:
        sub_root = sub_root.parent
      for name, sym in sub_root.symbols.items():
        if hasattr(sym, "struct_type"):
          sym.struct_type.is_imported = True
          sym.struct_type.defining_module = defining_mod
        elif isinstance(getattr(sym, "symbol_type", None), StructType):
          sym.symbol_type.is_imported = True
          sym.symbol_type.defining_module = defining_mod
        elif isinstance(
          getattr(sym, "symbol_type", None), (TraitType, EnumType)
        ):
          sym.symbol_type.defining_module = defining_mod
        computed_exports[name] = sym
      for name, t in sub_root.types.items():
        if name not in ("int", "float", "bool", "String", "none", "Arena"):
          if isinstance(t, StructType):
            t.is_imported = True
            t.defining_module = defining_mod
          elif isinstance(t, (TraitType, EnumType)):
            t.defining_module = defining_mod
          computed_exports[name] = t
    return computed_exports

  @staticmethod
  def _parse_and_check_imported_module(
    target_file: str,
    mod_file_path: str,
    sub_code: str,
    mod_sym: ModuleSymbol,
    checked_results: dict[str, Any],
    active_stack: set[str],
  ) -> tuple[dict[str, Any], list[str], dict[str, tuple[int, int]], bool]:
    """Parses and type-checks *target_file*, returning exports, errors, deps,
    and
    cycle flag.
    """
    err_listener = CustomErrorListener(
      file_path=target_file, source_content=sub_code, quiet=True
    )
    sub_lexer = SapphireLexer(InputStream(sub_code))
    sub_lexer.removeErrorListeners()
    sub_lexer.addErrorListener(err_listener)
    sub_parser = SapphireParser(CommonTokenStream(sub_lexer))
    sub_parser.removeErrorListeners()
    sub_parser.addErrorListener(err_listener)
    sub_tree = sub_parser.program()

    mod_errors: list[str] = list(err_listener.error_messages)
    computed_exports: dict[str, Any] = {}
    sub_deps: dict[str, tuple[int, int]] = {}
    sub_hit_cycle = False

    if err_listener.errors == 0:
      sub_ast = None
      try:
        sub_ast = ASTBuilder().visit(sub_tree)
      except (SapphireSyntaxError, SyntaxError) as syn_err:
        mod_errors.append(
          format_diagnostic(
            error_type="Syntax Error",
            message=getattr(syn_err, "message", str(syn_err)),
            file_path=target_file,
            line=getattr(syn_err, "line", None),
            column=getattr(syn_err, "column", None),
            source_content=sub_code,
          )
        )

      if sub_ast is not None:
        DeclarationPass._mark_file_uri(sub_ast, from_fs_path(mod_file_path))

        from sapphire.semantics.type_checker import TypeChecker

        sub_checker = TypeChecker(
          source_file_path=target_file, source_content=sub_code
        )
        sub_checker._checked_import_results = checked_results
        sub_checker._active_import_stack = active_stack

        active_stack.add(mod_file_path)
        try:
          sub_checker.check(sub_ast)
        except SemanticError as sem_err:
          if not sub_checker.errors and str(sem_err):
            mod_errors.append(str(sem_err))
        finally:
          active_stack.discard(mod_file_path)

        for err in sub_checker.errors:
          if err not in mod_errors:
            mod_errors.append(err)
        sub_deps = dict(sub_checker._resolved_dep_stats)
        sub_hit_cycle = bool(getattr(sub_checker, "_hit_import_cycle", False))
        computed_exports = DeclarationPass._extract_module_exports(
          sub_checker, sub_ast, mod_sym
        )

    return computed_exports, mod_errors, sub_deps, sub_hit_cycle

  @staticmethod
  def _check_imported_file(
    checker: Any,
    imp: Any,
    target_file: str,
    mod_sym: ModuleSymbol,
    is_builtin: bool,
    checked_results: dict[str, Any],
    active_stack: set[str],
    reported_errors: set[str],
    resolved_dep_stats: dict[str, tuple[int, int]],
  ) -> None:
    """Parses, typechecks, caches, and extracts exports for *target_file*."""
    mod_file_path = os.path.abspath(target_file)
    mod_sym.file_path = mod_file_path
    try:
      stat_res = os.stat(mod_file_path)
      mtime: int | None = stat_res.st_mtime_ns
      fsize: int | None = stat_res.st_size
    except OSError:
      mtime = None
      fsize = None

    # 1. Reuse global cross-file module cache when mtime/size and deps match.
    cached_entry = DeclarationPass._module_cache.get(mod_file_path)
    if DeclarationPass._is_cache_entry_valid(cached_entry, mtime, fsize):
      mod_sym.exports.update(cached_entry[2])
      resolved_dep_stats[mod_file_path] = (mtime, fsize)
      if len(cached_entry) > 3:
        resolved_dep_stats.update(cached_entry[3])
      if imp.path == "std.testing" or imp.path.startswith("std.testing"):
        mod_sym.exports["TestCase"] = checker.symbol_table.testcase_trait
      return
    if cached_entry is not None:
      DeclarationPass._module_cache.pop(mod_file_path, None)

    # 2. Reuse per-compilation result if already checked in this session.
    is_std_testing = imp.path == "std.testing" or imp.path.startswith(
      "std.testing"
    )
    if mod_file_path in checked_results:
      cached_exports, mod_errors, sub_deps, sub_cycle = checked_results[
        mod_file_path
      ]
      mod_sym.exports.update(cached_exports)
      if is_std_testing:
        mod_sym.exports["TestCase"] = checker.symbol_table.testcase_trait
      if mtime is not None and fsize is not None:
        resolved_dep_stats[mod_file_path] = (mtime, fsize)
        resolved_dep_stats.update(sub_deps)
      if sub_cycle:
        checker._hit_import_cycle = True
      DeclarationPass._propagate_import_errors(
        checker, imp, mod_errors, reported_errors
      )
      return

    # 3. Break recursive import cycles without caching partial exports.
    if mod_file_path in active_stack:
      checker._hit_import_cycle = True
      if is_std_testing:
        mod_sym.exports["TestCase"] = checker.symbol_table.testcase_trait
      return

    try:
      with open(target_file, encoding="utf-8") as f:
        sub_code = f.read()
    except OSError as os_err:
      checker.error(
        f"Failed to read imported module '{imp.path}': {os_err}",
        node=imp,
      )
      return

    computed_exports, mod_errors, sub_deps, sub_hit_cycle = (
      DeclarationPass._parse_and_check_imported_module(
        target_file,
        mod_file_path,
        sub_code,
        mod_sym,
        checked_results,
        active_stack,
      )
    )

    checked_results[mod_file_path] = (
      dict(computed_exports),
      list(mod_errors),
      dict(sub_deps),
      sub_hit_cycle,
    )
    if sub_hit_cycle:
      checker._hit_import_cycle = True
    if mtime is not None and fsize is not None:
      resolved_dep_stats[mod_file_path] = (mtime, fsize)
      resolved_dep_stats.update(sub_deps)
      # Only cache clean, cycle-free modules across compilations.
      if not mod_errors and not sub_hit_cycle:
        DeclarationPass._module_cache[mod_file_path] = (
          mtime,
          fsize,
          dict(computed_exports),
          dict(sub_deps),
        )

    mod_sym.exports.update(computed_exports)
    if is_std_testing:
      mod_sym.exports["TestCase"] = checker.symbol_table.testcase_trait
    DeclarationPass._propagate_import_errors(
      checker, imp, mod_errors, reported_errors
    )

  @staticmethod
  def declare_imports(checker: Any, program: ProgramNode) -> None:
    """Pass 0: Register imported module symbols."""
    checked_results = getattr(checker, "_checked_import_results", None)
    if checked_results is None:
      checked_results = {}
      checker._checked_import_results = checked_results
    active_stack = getattr(checker, "_active_import_stack", None)
    if active_stack is None:
      active_stack = set()
      checker._active_import_stack = active_stack
    reported_errors = getattr(checker, "_reported_import_errors", None)
    if reported_errors is None:
      reported_errors = set()
      checker._reported_import_errors = reported_errors
    resolved_dep_stats = getattr(checker, "_resolved_dep_stats", None)
    if resolved_dep_stats is None:
      resolved_dep_stats = {}
      checker._resolved_dep_stats = resolved_dep_stats
    if not hasattr(checker, "_hit_import_cycle"):
      checker._hit_import_cycle = False

    src_path = getattr(checker, "source_file_path", None)
    abs_src_path = os.path.abspath(src_path) if src_path else None
    added_self = False
    if abs_src_path and abs_src_path not in active_stack:
      active_stack.add(abs_src_path)
      added_self = True

    seen_import_names: dict[str, str] = {}
    try:
      for imp in getattr(program, "imports", []):
        module_name = imp.alias if imp.alias else imp.path.split(".")[-1]

        # Resolve imported module file path on disk
        target_file = resolve_module_path(
          imp.path, source_file_path=getattr(checker, "source_file_path", None)
        )
        is_builtin = is_builtin_module(imp.path)

        if module_name in seen_import_names:
          if seen_import_names[module_name] != imp.path:
            checker.error(
              f"Duplicate imported module name '{module_name}' "
              f"(already imported from '{seen_import_names[module_name]}'); "
              f"use an 'as' alias for '{imp.path}'.",
              node=imp,
            )
            if not target_file and not is_builtin:
              checker.error(
                f"Cannot resolve imported module '{imp.path}'. "
                "Module file not found.",
                node=imp,
              )
          continue
        seen_import_names[module_name] = imp.path

        existing = checker.symbol_table.lookup_current_scope(module_name)
        is_predefined = existing is not None and isinstance(
          existing, ModuleSymbol
        )
        if not is_predefined:
          mod_sym = ModuleSymbol(module_name, imp.path)
          checker.symbol_table.define(module_name, mod_sym)
          checker.symbol_table.define_type(module_name, ModuleType(imp.path))
        else:
          mod_sym = existing

        if imp.path == "std.testing" or imp.path.startswith("std.testing"):
          mod_sym.exports["TestCase"] = checker.symbol_table.testcase_trait

        if not target_file and not is_builtin and not is_predefined:
          checker.error(
            f"Cannot resolve imported module '{imp.path}'. Module file not "
            "found.",
            node=imp,
          )

        if target_file:
          DeclarationPass._check_imported_file(
            checker,
            imp,
            target_file,
            mod_sym,
            is_builtin,
            checked_results,
            active_stack,
            reported_errors,
            resolved_dep_stats,
          )
    finally:
      if added_self and abs_src_path:
        active_stack.discard(abs_src_path)

  @staticmethod
  def _validate_decl_annotations(checker: Any, decl: ASTNode) -> None:
    """Validates annotations on a top-level declaration and its members."""
    if hasattr(decl, "annotations") and decl.annotations:
      DeclarationPass.validate_annotations(checker, decl.annotations, node=decl)
    if isinstance(decl, TraitDeclNode):
      for member in decl.members:
        if hasattr(member, "annotations") and member.annotations:
          DeclarationPass.validate_annotations(
            checker, member.annotations, node=member
          )
    elif hasattr(decl, "members") and isinstance(decl.members, list):
      for member in decl.members:
        if hasattr(member, "annotations") and member.annotations:
          DeclarationPass.validate_annotations(
            checker, member.annotations, node=member
          )
        if (
          hasattr(member, "func_decl")
          and hasattr(member.func_decl, "annotations")
          and member.func_decl.annotations
        ):
          DeclarationPass.validate_annotations(
            checker, member.func_decl.annotations, node=member.func_decl
          )

  @staticmethod
  def _declare_enum_global(checker: Any, decl: EnumDeclNode) -> None:
    if checker.symbol_table.lookup_current_scope(
      decl.name
    ) or checker.symbol_table.lookup_type(decl.name):
      checker.error(f"Redefinition of identifier '{decl.name}'.")
      return
    has_int_val = any(isinstance(m.value, int) for m in decl.members)
    has_str_val = any(isinstance(m.value, str) for m in decl.members)
    if has_int_val and has_str_val:
      checker.error(
        f"Enum '{decl.name}' cannot mix integer and string variant values.",
        node=decl,
      )
    current_val: int | str = "" if has_str_val else 0
    is_string_enum = has_str_val
    variants: dict[str, int | str] = {}
    seen_members: set[str] = set()
    for member in decl.members:
      if member.name in seen_members:
        checker.error(
          f"Duplicate member '{member.name}' in enum '{decl.name}'."
        )
        continue
      seen_members.add(member.name)
      if member.value is not None:
        current_val = member.value
      elif is_string_enum:
        current_val = member.name
      variants[member.name] = current_val
      if isinstance(current_val, int):
        current_val += 1
    enum_type = EnumType(
      decl.name,
      variants,
      defining_module=checker.source_file_path or "__main__",
    )
    enum_type.ast_decl = decl
    checker.symbol_table.define_type(decl.name, enum_type)
    checker.symbol_table.define(decl.name, EnumSymbol(decl.name, enum_type))

  @staticmethod
  def _declare_trait_global(checker: Any, decl: TraitDeclNode) -> None:
    if checker.symbol_table.lookup_current_scope(
      decl.name
    ) or checker.symbol_table.lookup_type(decl.name):
      checker.error(f"Redefinition of identifier '{decl.name}'.")
      return
    trait_type = TraitType(
      decl.name,
      type_params=decl.type_params,
      ast_decl=decl,
      defining_module=checker.source_file_path or "__main__",
    )
    # Forward-register trait before resolving member signatures so
    # self-referencing
    # traits (e.g. `trait Mergeable { func merge(other: Mergeable); }`) resolve.
    checker.symbol_table.define_type(decl.name, trait_type)
    checker.symbol_table.define(decl.name, TraitSymbol(decl.name, trait_type))
    if decl.type_params:
      checker.symbol_table.enter_scope()
      for tp in decl.type_params:
        checker.symbol_table.define_type(tp, GenericTypeParameter(tp))
    for member in decl.members:
      if member.name in trait_type.methods:
        checker.error(
          f"Duplicate method '{member.name}' in trait '{decl.name}'.",
          node=member,
        )
        continue
      DeclarationPass.validate_parameter_defaults(checker, member.parameters)
      p_types = []
      for p in member.parameters:
        if p.name == "self" and p.param_type is None:
          p_types.append(trait_type)
        else:
          p_types.append(checker._resolve_type_node(p.param_type))
      ret_t = checker._resolve_return_types(member)
      p_mutabilities = [p.is_mutable for p in member.parameters]
      param_names = [p.name for p in member.parameters]
      has_self = bool(param_names) and param_names[0] == "self"
      extern_name = None
      for ann in getattr(member, "annotations", []):
        if ann.name == "export" and ann.arg:
          extern_name = ann.arg
          break
      num_defaults = sum(
        1
        for p in member.parameters
        if getattr(p, "default_expr", None) is not None
      )
      param_defaults = [
        getattr(p, "default_expr", None) for p in member.parameters
      ]
      trait_type.methods[member.name] = FunctionType(
        p_types,
        ret_t,
        p_mutabilities,
        param_names=param_names,
        has_self=has_self,
        extern_name=extern_name,
        num_defaults=num_defaults,
        param_defaults=param_defaults,
        ast_decl=member,
      )
      if getattr(member, "body", None) is not None:
        trait_type.default_methods[member.name] = member
    if decl.type_params:
      checker.symbol_table.exit_scope()

  @staticmethod
  def _declare_var_global(checker: Any, decl: VarDeclNode) -> None:
    """Pre-registers @extern globals and type-alias module bindings."""
    for i, name in enumerate(decl.names):
      if checker.symbol_table.lookup_current_scope(name):
        checker.error(f"Redefinition of identifier '{name}'.", node=decl)
        continue
      if any(a.name == "extern" for a in decl.annotations):
        if decl.exprs:
          checker.error(
            "An '@extern' variable declaration cannot have an initializer "
            "expression.",
            node=decl,
          )
        v_type = (
          checker._resolve_type_node(decl.val_types[i])
          if (decl.val_types and i < len(decl.val_types) and decl.val_types[i])
          else PrimitiveType("none")
        )
        if not decl.val_types or not decl.val_types[i]:
          checker.error(
            f"An '@extern' variable declaration for '{name}' requires an "
            "explicit type annotation.",
            node=decl,
          )
        sym = VariableSymbol(name, v_type, decl.is_mutable)
        # Mark so Pass 2 (`visit_VarDeclNode`) knows this global was
        # pre-declared.
        sym._from_declare_globals = True
        sym.is_extern = True
        checker.symbol_table.define(name, sym)
      elif decl.exprs and i < len(decl.exprs):
        expr_node = decl.exprs[i]
        val_t = None
        is_type_alias = False
        if isinstance(expr_node, MemberAccessNode) and isinstance(
          expr_node.receiver, IdentifierNode
        ):
          mod_sym = checker.symbol_table.lookup(expr_node.receiver.name)
          if isinstance(mod_sym, ModuleSymbol):
            exp = mod_sym.lookup_export(expr_node.member)
            if isinstance(exp, Type):
              val_t = exp
              is_type_alias = True
            elif isinstance(
              exp, (StructSymbol, EnumSymbol, TraitSymbol)
            ) or getattr(exp, "is_type_alias", False):
              val_t = exp.symbol_type
              is_type_alias = True
            elif hasattr(exp, "symbol_type") and isinstance(
              exp.symbol_type, Type
            ):
              val_t = exp.symbol_type
        elif isinstance(expr_node, IdentifierNode):
          exp_sym = checker.symbol_table.lookup(expr_node.name)
          if isinstance(
            exp_sym, (StructSymbol, EnumSymbol, TraitSymbol)
          ) or getattr(exp_sym, "is_type_alias", False):
            val_t = exp_sym.symbol_type
            is_type_alias = True
          else:
            exp = checker.symbol_table.lookup_type(expr_node.name)
            if isinstance(exp, Type):
              val_t = exp
              is_type_alias = True
        if val_t:
          sym = VariableSymbol(name, val_t, decl.is_mutable)
          sym._from_declare_globals = True
          if is_type_alias and not decl.is_mutable:
            sym.is_type_alias = True
            checker.symbol_table.define_type(name, val_t)
          checker.symbol_table.define(name, sym)

  @staticmethod
  def _declare_func_global(checker: Any, decl: FuncDeclNode) -> None:
    if checker.symbol_table.lookup_current_scope(decl.name):
      checker.error(f"Redefinition of identifier '{decl.name}'.")
      return
    DeclarationPass.validate_parameter_defaults(checker, decl.parameters)
    if decl.type_params:
      checker.symbol_table.enter_scope()
      for tp in decl.type_params:
        checker.symbol_table.define_type(tp, GenericTypeParameter(tp))
    param_types = []
    param_mutabilities = []
    for p in decl.parameters:
      param_types.append(checker._resolve_type_node(p.param_type))
      param_mutabilities.append(p.is_mutable)
    ret_type = checker._resolve_return_types(decl)
    if decl.type_params:
      checker.symbol_table.exit_scope()
    num_defaults = sum(
      1 for p in decl.parameters if getattr(p, "default_expr", None) is not None
    )
    param_defaults = [getattr(p, "default_expr", None) for p in decl.parameters]
    signature = FunctionType(
      param_types,
      ret_type,
      param_mutabilities,
      param_names=[p.name for p in decl.parameters],
      num_defaults=num_defaults,
      param_defaults=param_defaults,
    )
    checker.symbol_table.define(
      decl.name,
      FunctionSymbol(
        decl.name, signature, type_params=decl.type_params, ast_decl=decl
      ),
    )

  @staticmethod
  def declare_globals(checker: Any, program: ProgramNode) -> None:
    """Pass 1: Collect struct, enum, and function declarations into global
    scope.
    """
    for decl in program.declarations:
      if not isinstance(
        decl,
        (
          StructDeclNode,
          EnumDeclNode,
          TraitDeclNode,
          VarDeclNode,
          FuncDeclNode,
          ImplBlockNode,
        ),
      ):
        checker.error(
          "Executable statements are not permitted at module scope. All "
          "executable logic must reside inside 'func main()' or a function.",
          node=decl,
        )
        continue

      DeclarationPass._validate_decl_annotations(checker, decl)

      if isinstance(decl, StructDeclNode):
        if checker.symbol_table.lookup_current_scope(
          decl.name
        ) or checker.symbol_table.lookup_type(decl.name):
          checker.error(f"Redefinition of identifier '{decl.name}'.")
          continue
        struct_type = StructType(
          decl.name,
          parent_names=decl.parent_names,
          is_prototype=decl.is_prototype,
          type_params=decl.type_params,
          ast_decl=decl,
          defining_module=checker.source_file_path or "__main__",
          is_imported=False,
        )
        checker.symbol_table.define_type(decl.name, struct_type)
        checker.symbol_table.define(
          decl.name, StructSymbol(decl.name, struct_type)
        )
      elif isinstance(decl, EnumDeclNode):
        DeclarationPass._declare_enum_global(checker, decl)
      elif isinstance(decl, TraitDeclNode):
        DeclarationPass._declare_trait_global(checker, decl)
      elif isinstance(decl, VarDeclNode):
        DeclarationPass._declare_var_global(checker, decl)
      elif isinstance(decl, FuncDeclNode):
        DeclarationPass._declare_func_global(checker, decl)
