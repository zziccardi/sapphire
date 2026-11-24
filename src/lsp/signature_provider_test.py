"""Unit and integration tests for SignatureProvider in src/lsp/signature_provider.py."""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from lsprotocol.types import (
    Position,
    SignatureHelpParams,
    TextDocumentIdentifier,
)

from src.lsp.server import SapphireLanguageServer, validate_source
from src.lsp.signature_provider import (
    SignatureProvider,
    _strip_trailing_type_args,
    _struct_constructor_signature,
)
from src.semantics.symbol_table import (
    FunctionSymbol,
    FunctionType,
    ModuleSymbol,
    PrimitiveType,
    StructSymbol,
    StructType,
    SymbolTable,
    VariableSymbol,
)
from src.semantics.types import (
    OptionalType,
    RefType,
    SharedRefType,
    StructField,
    StructMethod,
)


class TestSignatureProviderHelpers(unittest.TestCase):
  """Unit tests for signature_provider.py helper functions."""

  def test_strip_trailing_type_args(self):
    self.assertEqual(_strip_trailing_type_args("foo"), "foo")
    self.assertEqual(_strip_trailing_type_args("foo<int>"), "foo")
    self.assertEqual(_strip_trailing_type_args("foo<Map<String, int>>"), "foo")
    # Unbalanced '>' returns original trimmed text
    self.assertEqual(_strip_trailing_type_args("foo> "), "foo>")

  def test_struct_constructor_signature_with_self_and_fallback(self):
    st = StructType("Hero")
    init_ft = FunctionType(
        [st, PrimitiveType("int"), PrimitiveType("String")],
        PrimitiveType("void"),
        param_mutabilities=[True, False, False],
        param_names=["self", "hp", "name"],
        num_defaults=1,
        param_defaults=[None, None, "anon"],
    )
    init_ft.comments = "Creates a Hero."
    st.methods["__init__"] = StructMethod("__init__", init_ft, None)

    sig = _struct_constructor_signature(st)
    self.assertIsNotNone(sig)
    self.assertEqual(sig.param_names, ["hp", "name"])
    self.assertEqual(len(sig.param_types), 2)
    self.assertEqual(sig.param_mutabilities, [False, False])
    self.assertEqual(sig.param_defaults, [None, "anon"])
    self.assertEqual(sig.comments, "Creates a Hero.")

    # Fallback to struct fields when no __init__
    plain = StructType("Point")
    plain.fields["x"] = StructField("x", PrimitiveType("int"), False)
    plain.fields["y"] = StructField("y", PrimitiveType("int"), False)
    plain_sig = _struct_constructor_signature(plain)
    self.assertIsNotNone(plain_sig)
    self.assertEqual(plain_sig.param_names, ["x", "y"])

    # Object with neither __init__ nor fields returns None
    self.assertIsNone(_struct_constructor_signature(object()))

  def test_parse_active_call_comments_strings_and_nesting(self):
    # Line comment with fake parens/commas
    code_line = "foo(1, // ignored(a, b, c)\n 2, "
    self.assertEqual(SignatureProvider._parse_active_call(code_line), ("foo", 2))

    # Block comment with fake parens/commas
    code_block = "bar(/* ignored(x, y) */ a, "
    self.assertEqual(SignatureProvider._parse_active_call(code_block), ("bar", 1))

    # Escaped quotes and commas inside string literals
    code_str = 'baz("a, \\"b\\", c", '
    self.assertEqual(SignatureProvider._parse_active_call(code_str), ("baz", 1))

    # Nested brackets and generic type args
    code_nested = "mod.make<int>([1, 2], {k: v}, "
    self.assertEqual(
        SignatureProvider._parse_active_call(code_nested), ("mod.make", 2)
    )

    # No active call
    self.assertIsNone(SignatureProvider._parse_active_call("let x = 1;"))
    self.assertIsNone(SignatureProvider._parse_active_call("(1, 2"))

  def test_resolve_module_export_callable(self):
    ft = FunctionType([PrimitiveType("int")], PrimitiveType("int"), param_names=["x"])
    st = StructType("Box")
    st.fields["v"] = StructField("v", PrimitiveType("int"), False)

    exports = {
        "fn_sym": FunctionSymbol("fn_sym", ft),
        "fn_type": ft,
        "st_sym": StructSymbol("st_sym", st),
        "st_raw": st,
        "var_fn": VariableSymbol("var_fn", ft, False),
        "var_int": VariableSymbol("var_int", PrimitiveType("int"), False),
    }

    mod = MagicMock(spec=ModuleSymbol)
    mod.lookup_export.side_effect = lambda name: exports.get(name)

    self.assertIsNone(SignatureProvider._resolve_module_export_callable(mod, "missing"))
    self.assertIs(SignatureProvider._resolve_module_export_callable(mod, "fn_sym"), ft)
    self.assertIs(SignatureProvider._resolve_module_export_callable(mod, "fn_type"), ft)
    self.assertEqual(
        SignatureProvider._resolve_module_export_callable(mod, "st_sym").param_names,
        ["v"],
    )
    self.assertEqual(
        SignatureProvider._resolve_module_export_callable(mod, "st_raw").param_names,
        ["v"],
    )
    self.assertIs(SignatureProvider._resolve_module_export_callable(mod, "var_fn"), ft)
    self.assertIsNone(SignatureProvider._resolve_module_export_callable(mod, "var_int"))

  def test_resolve_direct_callee_non_callable_symbol(self):
    st = SymbolTable()
    st.define("count", VariableSymbol("count", PrimitiveType("int"), False))
    self.assertIsNone(SignatureProvider._resolve_direct_callee("count", st))
    self.assertIsNone(SignatureProvider._resolve_direct_callee("unknown", st))

  def test_resolve_member_callee_optional_ref_and_binding_types(self):
    ft = FunctionType(
        [PrimitiveType("int")],
        PrimitiveType("void"),
        param_names=["dmg"],
    )
    target_st = StructType("Enemy")
    target_st.methods["hit"] = StructMethod("hit", ft, None)

    sym_table = SymbolTable()
    sym_table.define(
        "opt_enemy", VariableSymbol("opt_enemy", OptionalType(target_st), False)
    )
    sym_table.define(
        "ref_enemy", VariableSymbol("ref_enemy", RefType(target_st), False)
    )
    sym_table.define(
        "shared_enemy",
        VariableSymbol("shared_enemy", SharedRefType(target_st), False),
    )

    mock_ls = SimpleNamespace(ast_cache={})
    uri = "file:///mem.sp"

    # Unknown receiver returns (None, method_name)
    self.assertEqual(
        SignatureProvider._resolve_member_callee(
            mock_ls, uri, "ghost.hit", 1, sym_table, {}
        ),
        (None, "hit"),
    )

    # OptionalType unwrapping
    resolved, name = SignatureProvider._resolve_member_callee(
        mock_ls, uri, "opt_enemy.hit", 1, sym_table, {}
    )
    self.assertIs(resolved, ft)
    self.assertEqual(name, "hit")

    # RefType unwrapping
    resolved, _ = SignatureProvider._resolve_member_callee(
        mock_ls, uri, "ref_enemy.hit", 1, sym_table, {}
    )
    self.assertIs(resolved, ft)

    # SharedRefType unwrapping for inner method
    resolved, _ = SignatureProvider._resolve_member_callee(
        mock_ls, uri, "shared_enemy.hit", 1, sym_table, {}
    )
    self.assertIs(resolved, ft)

    # Fallback scan over node_types with binding_types dict
    class _BindingNode:
      binding_types = {"bound_e": target_st}
      start_line = 3

    binding_node = _BindingNode()
    resolved, _ = SignatureProvider._resolve_member_callee(
        mock_ls, uri, "bound_e.hit", 4, sym_table, {binding_node: target_st}
    )
    self.assertIs(resolved, ft)


class TestSignatureProviderIntegration(unittest.TestCase):
  """Integration tests using SapphireLanguageServer and real Sapphire source."""

  def _make_server_with_doc(self, uri: str, code: str) -> SapphireLanguageServer:
    from testing.test_utils import FakeWorkspace

    ls = SapphireLanguageServer(
        "test-lsp", "0.1.0", workspace=FakeWorkspace({uri: code})
    )
    ls.text_document_publish_diagnostics = MagicMock()
    validate_source(ls, uri, code)
    return ls

  def test_self_method_and_local_var_signature_help(self):
    code = (
        "struct Counter {\n"
        "  var value: int;\n"
        "}\n"
        "impl Counter {\n"
        "  var func add(delta: int, label: String): int {\n"
        "    return self.value + delta;\n"
        "  }\n"
        "  var func bump() {\n"
        "    self.add(1, \"ok\");\n"
        "  }\n"
        "}\n"
        "func run() {\n"
        "  var c = Counter { value = 0 };\n"
        "  c.add(5, \"hi\");\n"
        "}\n"
    )
    uri = "file:///sig_self.sp"
    ls = self._make_server_with_doc(uri, code)

    # Inside self.add(1, |) -> line 8 (0-indexed), col 16
    res_self = SignatureProvider.provide_signature_help(
        ls,
        SignatureHelpParams(
            text_document=TextDocumentIdentifier(uri=uri),
            position=Position(line=8, character=16),
        ),
    )
    self.assertIsNotNone(res_self)
    self.assertEqual(res_self.active_parameter, 1)
    self.assertIn("add(delta: int, label: String)", res_self.signatures[0].label)

    # Inside c.add(5, |) -> line 13 (0-indexed), col 11
    res_local = SignatureProvider.provide_signature_help(
        ls,
        SignatureHelpParams(
            text_document=TextDocumentIdentifier(uri=uri),
            position=Position(line=13, character=11),
        ),
    )
    self.assertIsNotNone(res_local)
    self.assertEqual(res_local.active_parameter, 1)
    self.assertIn("add(delta: int, label: String)", res_local.signatures[0].label)

  def test_cursor_past_eof_uses_full_source(self):
    code = "func greet(name: String): int { return 1; }\nfunc main() { greet("
    uri = "file:///sig_eof.sp"
    ls = self._make_server_with_doc(uri, code)
    # Manually ensure symbol_table_cache has greet even if parse had incomplete call
    if uri not in ls.symbol_table_cache:
      st = SymbolTable()
      st.define(
          "greet",
          FunctionSymbol(
              "greet",
              FunctionType(
                  [PrimitiveType("String")],
                  PrimitiveType("int"),
                  param_names=["name"],
              ),
          ),
      )
      ls.symbol_table_cache[uri] = st
      ls.node_types_cache[uri] = {}

    res = SignatureProvider.provide_signature_help(
        ls,
        SignatureHelpParams(
            text_document=TextDocumentIdentifier(uri=uri),
            position=Position(line=99, character=0),
        ),
    )
    self.assertIsNotNone(res)
    self.assertIn("greet(name: String)", res.signatures[0].label)


if __name__ == "__main__":
  unittest.main()
