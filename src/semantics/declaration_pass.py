"""Declaration pass for Sapphire semantic analyzer.

Handles Pass 0 (imported module declarations) and Pass 1 (global declarations
for structs, enums, traits, externs, and functions).
"""

import os
from typing import Any, Dict, List, Optional, Union
from antlr4 import InputStream, CommonTokenStream
from pygls.uris import from_fs_path

from src.parser.ast import (
    ASTNode,
    EnumDeclNode,
    FuncDeclNode,
    IdentifierNode,
    MemberAccessNode,
    ParameterNode,
    ProgramNode,
    StructDeclNode,
    TraitDeclNode,
    VarDeclNode,
)
from src.parser.ast_builder import ASTBuilder
from src.parser.gen.SapphireLexer import SapphireLexer
from src.parser.gen.SapphireParser import SapphireParser
from src.semantics.module_resolver import resolve_module_path
from src.semantics.symbol_table import (
    EnumType,
    EnumSymbol,
    FunctionType,
    FunctionSymbol,
    GenericTypeParameter,
    ModuleSymbol,
    ModuleType,
    PrimitiveType,
    StructType,
    StructSymbol,
    TraitType,
    TraitSymbol,
    Type,
    VariableSymbol,
)


class DeclarationPass:
  """Executes preliminary module imports and top-level global symbol registration."""

  @staticmethod
  def validate_parameter_defaults(checker: Any, parameters: List[ParameterNode]) -> None:
    """Validates that parameters without default values do not follow parameters with default values."""
    seen_default = False
    for p in parameters:
      if getattr(p, "default_expr", None) is not None:
        seen_default = True
      elif seen_default:
        checker.error(
            f"Parameter without a default value '{p.name}' cannot follow a parameter with a default value.",
            node=p,
        )

  @staticmethod
  def declare_imports(checker: Any, program: ProgramNode) -> None:
    """Pass 0: Register imported module symbols."""
    for imp in getattr(program, "imports", []):
      module_name = imp.alias if imp.alias else imp.path.split(".")[-1]
      existing = checker.symbol_table.lookup_current_scope(module_name)
      is_predefined = existing is not None and isinstance(existing, ModuleSymbol)
      if not is_predefined:
        mod_sym = ModuleSymbol(module_name, imp.path)
        checker.symbol_table.define(module_name, mod_sym)
        checker.symbol_table.define_type(module_name, ModuleType(imp.path))
      else:
        mod_sym = existing

      if imp.path == "std.testing" or imp.path.startswith("std.testing"):
        mod_sym.exports["TestCase"] = checker.symbol_table.testcase_trait

      # Resolve imported module file path on disk
      target_file = resolve_module_path(imp.path, source_file_path=getattr(checker, "source_file_path", None))

      is_builtin = (
          imp.path in ("std.testing", "std.math")
          or imp.path.startswith("std.testing")
          or imp.path.startswith("std.math")
      )
      if not target_file and not is_builtin and not is_predefined:
        checker.error(f"Cannot resolve imported module '{imp.path}'. Module file not found.", node=imp)

      if target_file:
        try:
          with open(target_file, "r", encoding="utf-8") as f:
            sub_code = f.read()

          try:
            sub_lexer = SapphireLexer(InputStream(sub_code))
            sub_lexer.removeErrorListeners()
            sub_parser = SapphireParser(CommonTokenStream(sub_lexer))
            sub_parser.removeErrorListeners()
            sub_ast = ASTBuilder().visit(sub_parser.program())
            mod_file_path = os.path.abspath(target_file)
            mod_file_uri = from_fs_path(mod_file_path)

            def _mark_file_uri(node):
              if isinstance(node, ASTNode):
                node.file_uri = mod_file_uri
                for v in node.__dict__.values():
                  if isinstance(v, list):
                    for item in v:
                      if isinstance(item, ASTNode):
                        _mark_file_uri(item)
                  elif isinstance(v, ASTNode):
                    _mark_file_uri(v)

            if sub_ast:
              _mark_file_uri(sub_ast)

            sub_checker = checker.__class__(source_file_path=target_file)
            try:
              sub_checker.check(sub_ast)
            except Exception:
              pass

            mod_sym.file_path = os.path.abspath(target_file)
            # Populate mod_sym exports from sub_checker
            if getattr(sub_ast, "export_block", None):
              for spec in sub_ast.export_block.specifiers:
                export_name = spec.alias or spec.symbol
                if spec.module_prefix:
                  prefix_sym = sub_checker.symbol_table.lookup(spec.module_prefix)
                  if isinstance(prefix_sym, ModuleSymbol):
                    exp = prefix_sym.lookup_export(spec.symbol)
                    if exp:
                      mod_sym.exports[export_name] = exp
                else:
                  exp = sub_checker.symbol_table.lookup_type(spec.symbol) or sub_checker.symbol_table.lookup(spec.symbol)
                  if exp:
                    if isinstance(exp, StructType):
                      exp.is_imported = True
                      exp.defining_module = mod_sym.file_path or mod_sym.module_path
                    elif hasattr(exp, "struct_type"):
                      exp.struct_type.is_imported = True
                      exp.struct_type.defining_module = mod_sym.file_path or mod_sym.module_path
                    mod_sym.exports[export_name] = exp
            else:
              sub_root = sub_checker.symbol_table.current_scope
              while sub_root.parent:
                sub_root = sub_root.parent
              for name, sym in sub_root.symbols.items():
                if hasattr(sym, "struct_type"):
                  sym.struct_type.is_imported = True
                  sym.struct_type.defining_module = mod_sym.file_path or mod_sym.module_path
                mod_sym.exports[name] = sym
              for name, t in sub_root.types.items():
                if name not in ("int", "float", "bool", "String", "none", "Arena"):
                  if isinstance(t, StructType):
                    t.is_imported = True
                    t.defining_module = mod_sym.file_path or mod_sym.module_path
                  mod_sym.exports[name] = t
            if is_builtin:
              mod_sym.exports["TestCase"] = checker.symbol_table.testcase_trait
          except Exception:  # pragma: no cover
            pass
        except Exception:  # pragma: no cover
          pass

  @staticmethod
  def declare_globals(checker: Any, program: ProgramNode) -> None:
    """Pass 1: Collect struct, enum, and function declarations into global scope."""
    for decl in program.declarations:
      if isinstance(decl, StructDeclNode):
        if checker.symbol_table.lookup_current_scope(decl.name) or checker.symbol_table.lookup_type(decl.name):
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
        checker.symbol_table.define(decl.name, StructSymbol(decl.name, struct_type))

      elif isinstance(decl, EnumDeclNode):
        if checker.symbol_table.lookup_current_scope(decl.name) or checker.symbol_table.lookup_type(decl.name):
          checker.error(f"Redefinition of identifier '{decl.name}'.")
          continue
        current_val: Union[int, str] = 0
        is_string_enum = any(isinstance(m.value, str) for m in decl.members)
        variants: Dict[str, Union[int, str]] = {}
        seen_members = set()
        for member in decl.members:
          if member.name in seen_members:
            checker.error(f"Duplicate member '{member.name}' in enum '{decl.name}'.")
            continue
          seen_members.add(member.name)
          if member.value is not None:
            current_val = member.value
          elif is_string_enum and isinstance(current_val, str):
            current_val = member.name
          variants[member.name] = current_val
          if isinstance(current_val, int):
            current_val += 1
        enum_type = EnumType(decl.name, variants)
        enum_type.ast_decl = decl
        checker.symbol_table.define_type(decl.name, enum_type)
        checker.symbol_table.define(decl.name, EnumSymbol(decl.name, enum_type))

      elif isinstance(decl, TraitDeclNode):
        if checker.symbol_table.lookup_current_scope(decl.name) or checker.symbol_table.lookup_type(decl.name):
          checker.error(f"Redefinition of identifier '{decl.name}'.")
          continue
        trait_type = TraitType(decl.name, type_params=decl.type_params, ast_decl=decl)
        # Populate trait method signatures
        if decl.type_params:
          checker.symbol_table.enter_scope()
          for tp in decl.type_params:
            checker.symbol_table.define_type(tp, GenericTypeParameter(tp))
        for member in decl.members:
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
          num_defaults = sum(1 for p in member.parameters if getattr(p, "default_expr", None) is not None)
          param_defaults = [getattr(p, "default_expr", None) for p in member.parameters]
          fn_type = FunctionType(
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
          trait_type.methods[member.name] = fn_type
        if decl.type_params:
          checker.symbol_table.exit_scope()
        checker.symbol_table.define_type(decl.name, trait_type)
        checker.symbol_table.define(decl.name, TraitSymbol(decl.name, trait_type))

      elif isinstance(decl, VarDeclNode):
        for i, name in enumerate(decl.names):
          if checker.symbol_table.lookup_current_scope(name):
            checker.error(f"Redefinition of identifier '{name}'.", node=decl)
            continue
          if any(a.name == "extern" for a in decl.annotations):
            if decl.exprs:
              checker.error("An '@extern' variable declaration cannot have an initializer expression.", node=decl)
            v_type = (
                checker._resolve_type_node(decl.val_types[i])
                if (decl.val_types and i < len(decl.val_types) and decl.val_types[i])
                else PrimitiveType("none")
            )
            if not decl.val_types or not decl.val_types[i]:
              checker.error(f"An '@extern' variable declaration for '{name}' requires an explicit type annotation.", node=decl)
            sym = VariableSymbol(name, v_type, decl.is_mutable)
            sym._from_declare_globals = True
            checker.symbol_table.define(name, sym)
          elif decl.exprs and i < len(decl.exprs):
            expr_node = decl.exprs[i]
            val_t = None
            if isinstance(expr_node, MemberAccessNode) and isinstance(expr_node.receiver, IdentifierNode):
              mod_sym = checker.symbol_table.lookup(expr_node.receiver.name)
              if isinstance(mod_sym, ModuleSymbol):
                exp = mod_sym.lookup_export(expr_node.member)
                if isinstance(exp, Type):
                  val_t = exp
                elif hasattr(exp, "symbol_type") and isinstance(exp.symbol_type, Type):
                  val_t = exp.symbol_type
            elif isinstance(expr_node, IdentifierNode):
              exp = checker.symbol_table.lookup_type(expr_node.name)
              if isinstance(exp, Type):
                val_t = exp
            if val_t:
              sym = VariableSymbol(name, val_t, decl.is_mutable)
              sym._from_declare_globals = True
              checker.symbol_table.define(name, sym)
              checker.symbol_table.define_type(name, val_t)

      elif isinstance(decl, FuncDeclNode):
        if checker.symbol_table.lookup_current_scope(decl.name):
          checker.error(f"Redefinition of identifier '{decl.name}'.")
          continue
        DeclarationPass.validate_parameter_defaults(checker, decl.parameters)
        if decl.type_params:
          checker.symbol_table.enter_scope()
          for tp in decl.type_params:
            checker.symbol_table.define_type(tp, GenericTypeParameter(tp))
        param_types = []
        param_mutabilities = []
        for p in decl.parameters:
          ptype = checker._resolve_type_node(p.param_type)
          param_types.append(ptype)
          param_mutabilities.append(p.is_mutable)
        ret_type = checker._resolve_return_types(decl)
        if decl.type_params:
          checker.symbol_table.exit_scope()
        num_defaults = sum(1 for p in decl.parameters if getattr(p, "default_expr", None) is not None)
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
            FunctionSymbol(decl.name, signature, type_params=decl.type_params, ast_decl=decl),
        )
