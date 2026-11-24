"""Unit tests for the Sapphire LSP CompletionProvider and SignatureProvider."""

import os
import tempfile
import unittest
from unittest.mock import MagicMock

from lsprotocol.types import (
    CompletionParams,
    Position,
    SignatureHelpParams,
    TextDocumentIdentifier,
)
from pygls.uris import from_fs_path

from src.lsp.completion_provider import CompletionProvider
from src.lsp.server import SapphireLanguageServer, validate_source
from src.lsp.signature_provider import SignatureProvider


def _make_ls(doc_uri: str, code: str) -> SapphireLanguageServer:
  ls = SapphireLanguageServer("sapphire-test", "v0")
  ls.text_document_publish_diagnostics = MagicMock()
  ls.protocol._workspace = MagicMock()
  doc = MagicMock()
  doc.uri = doc_uri
  doc.source = code
  ls.workspace.get_text_document.return_value = doc
  validate_source(ls, doc_uri, code)
  return ls


class TestCompletionProvider(unittest.TestCase):
  """Tests dot-completions, scope isolation, multi-var, and inheritance."""

  def test_self_dot_completion_resolves_enclosing_impl_struct(self):
    code = "\n".join([
        "struct Foo { var foo_field: int; }",
        "impl Foo {",
        "  func a(): int { return self.foo_field; }",
        "}",
        "struct Bar { var bar_field: int; }",
        "impl Bar {",
        "  func b() {",
        "    self.",
        "  }",
        "}",
    ])
    uri = "file:///self_completion.sp"
    ls = _make_ls(uri, code)
    res = CompletionProvider.provide_completion(
        ls,
        CompletionParams(
            text_document=TextDocumentIdentifier(uri=uri),
            position=Position(line=7, character=9),
        ),
    )
    labels = {item.label for item in res.items}
    self.assertIn("bar_field", labels)
    self.assertNotIn("foo_field", labels)

  def test_inherited_struct_dot_completions_and_multivar(self):
    code = "\n".join([
        "struct Base { var base_x: int; }",
        "impl Base { func base_fn(): int { return self.base_x; } }",
        "struct Child: Base { var child_y: int; }",
        "func demo() {",
        '  let c, msg = Child { base_x = 1, child_y = 2 }, "hello";',
        "  c.",
        "  msg.",
        "}",
    ])
    uri = "file:///inherited_completion.sp"
    ls = _make_ls(uri, code)

    res_child = CompletionProvider.provide_completion(
        ls,
        CompletionParams(
            text_document=TextDocumentIdentifier(uri=uri),
            position=Position(line=5, character=4),
        ),
    )
    child_labels = {item.label for item in res_child.items}
    self.assertIn("child_y", child_labels)
    self.assertIn("base_x", child_labels)
    self.assertIn("base_fn", child_labels)

    res_msg = CompletionProvider.provide_completion(
        ls,
        CompletionParams(
            text_document=TextDocumentIdentifier(uri=uri),
            position=Position(line=6, character=6),
        ),
    )
    msg_labels = {item.label for item in res_msg.items}
    self.assertIn("size", msg_labels)

  def test_scope_completion_no_function_leak_and_includes_nested_block(self):
    code = "\n".join([
        "func first() {",
        "  let first_only = 1;",
        "}",
        "func second() {",
        "  if true {",
        "    let nested_var = 2;",
        "    ",
        "  }",
        "  ",
        "}",
    ])
    uri = "file:///scope_completion.sp"
    ls = _make_ls(uri, code)

    # Inside nested if-block (line 6): nested_var is visible, first_only is NOT a variable item.
    res_inner = CompletionProvider.provide_completion(
        ls,
        CompletionParams(
            text_document=TextDocumentIdentifier(uri=uri),
            position=Position(line=6, character=4),
        ),
    )
    inner_var_labels = {
        item.label for item in res_inner.items if item.kind == 6
    }
    self.assertIn("nested_var", inner_var_labels)
    self.assertNotIn("first_only", inner_var_labels)

    # Outside nested if-block (line 8): nested_var is NOT visible as a variable.
    res_outer = CompletionProvider.provide_completion(
        ls,
        CompletionParams(
            text_document=TextDocumentIdentifier(uri=uri),
            position=Position(line=8, character=2),
        ),
    )
    outer_var_labels = {
        item.label for item in res_outer.items if item.kind == 6
    }
    self.assertNotIn("nested_var", outer_var_labels)
    self.assertNotIn("first_only", outer_var_labels)


def _edit_doc(ls: SapphireLanguageServer, uri: str, code: str) -> None:
  doc = MagicMock()
  doc.uri = uri
  doc.source = code
  ls.workspace.get_text_document.return_value = doc
  validate_source(ls, uri, code)


class TestSignatureProvider(unittest.TestCase):
  """Tests unclosed strings, multi-line calls, generics, modules, and __init__."""

  def test_unclosed_string_multiline_and_generic_calls(self):
    header = (
        "func greet(name: String, count: int): String { return name; }\n"
        "func identity<T>(val: T): T { return val; }\n"
    )
    uri = "file:///sig_live.sp"
    ls = _make_ls(uri, header + "func demo() {}\n")

    # 1. Unclosed string on first arg -> param 0
    code0 = header + 'func demo() {\n  greet("hello\n}\n'
    _edit_doc(ls, uri, code0)
    s0 = SignatureProvider.provide_signature_help(
        ls,
        SignatureHelpParams(
            text_document=TextDocumentIdentifier(uri=uri),
            position=Position(line=3, character=len(code0.splitlines()[3])),
        ),
    )
    self.assertIsNotNone(s0)
    self.assertIn("greet(", s0.signatures[0].label)
    self.assertEqual(s0.active_parameter, 0)

    # 2. Unclosed string on second arg after comma inside first string -> param 1
    code1 = header + 'func demo() {\n  greet("a, b", "c\n}\n'
    _edit_doc(ls, uri, code1)
    s1 = SignatureProvider.provide_signature_help(
        ls,
        SignatureHelpParams(
            text_document=TextDocumentIdentifier(uri=uri),
            position=Position(line=3, character=len(code1.splitlines()[3])),
        ),
    )
    self.assertIsNotNone(s1)
    self.assertEqual(s1.active_parameter, 1)

    # 3. Multi-line call -> param 1
    code_ml = header + 'func demo() {\n  greet(\n    "world",\n    \n  );\n}\n'
    _edit_doc(ls, uri, code_ml)
    s_ml = SignatureProvider.provide_signature_help(
        ls,
        SignatureHelpParams(
            text_document=TextDocumentIdentifier(uri=uri),
            position=Position(line=5, character=4),
        ),
    )
    self.assertIsNotNone(s_ml)
    self.assertIn("greet(", s_ml.signatures[0].label)
    self.assertEqual(s_ml.active_parameter, 1)

    # 4. Generic call `identity<int>(` -> resolves `identity`
    code_gen = header + "func demo() {\n  identity<int>(\n}\n"
    _edit_doc(ls, uri, code_gen)
    s_gen = SignatureProvider.provide_signature_help(
        ls,
        SignatureHelpParams(
            text_document=TextDocumentIdentifier(uri=uri),
            position=Position(line=3, character=len(code_gen.splitlines()[3])),
        ),
    )
    self.assertIsNotNone(s_gen)
    self.assertIn("identity(", s_gen.signatures[0].label)

  def test_struct_explicit_init_and_imported_module_calls(self):
    with tempfile.TemporaryDirectory() as tmp_dir:
      mod_path = os.path.join(tmp_dir, "helpers.sp")
      with open(mod_path, "w", encoding="utf-8") as f:
        f.write(
            "func scale(x: float, factor: float): float { return x * factor; }\n"
            "export { scale, }\n"
        )
      main_path = os.path.join(tmp_dir, "main.sp")
      header = "\n".join([
          "import helpers;",
          "struct Box {",
          "  var raw_val: int;",
          "}",
          "impl Box {",
          "  func __init__(initial: int, bonus: int) {",
          "    self.raw_val = initial + bonus;",
          "  }",
          "}",
      ])
      base_code = header + "\nfunc demo() {}\n"
      with open(main_path, "w", encoding="utf-8") as f:
        f.write(base_code)
      uri = from_fs_path(os.path.abspath(main_path))
      ls = _make_ls(uri, base_code)

      # Struct with explicit __init__ uses __init__ params, not raw_val field.
      code_box = header + "\nfunc demo() {\n  let b = Box(\n}\n"
      _edit_doc(ls, uri, code_box)
      s_box = SignatureProvider.provide_signature_help(
          ls,
          SignatureHelpParams(
              text_document=TextDocumentIdentifier(uri=uri),
              position=Position(line=10, character=len(code_box.splitlines()[10])),
          ),
      )
      self.assertIsNotNone(s_box)
      self.assertIn("initial: int", s_box.signatures[0].label)
      self.assertIn("bonus: int", s_box.signatures[0].label)
      self.assertNotIn("raw_val", s_box.signatures[0].label)

      # Imported module function call `helpers.scale(1.0, ` resolves at param 1.
      code_mod = header + "\nfunc demo() {\n  let s = helpers.scale(1.0, \n}\n"
      _edit_doc(ls, uri, code_mod)
      s_mod = SignatureProvider.provide_signature_help(
          ls,
          SignatureHelpParams(
              text_document=TextDocumentIdentifier(uri=uri),
              position=Position(line=10, character=len(code_mod.splitlines()[10])),
          ),
      )
      self.assertIsNotNone(s_mod)
      self.assertIn("scale(", s_mod.signatures[0].label)
      self.assertEqual(s_mod.active_parameter, 1)

  def test_scope_completions_guard_else_while_and_for(self):
    """Verifies scope completions inside guard/else/else-if/while and after for."""
    code = "\n".join([
        "func demo(opt: int?) {",
        "  for item in [1, 2] {",
        "    let in_for = item;",
        "  }",
        "  guard let g_val ?= opt else {",
        "    let in_guard_else = 1;",
        "    ",
        "  }",
        "  if false {",
        "    let in_then = 1;",
        "  } else if true {",
        "    let in_elif = 2;",
        "    ",
        "  } else {",
        "    let in_else = 3;",
        "    ",
        "  }",
        "  while false {",
        "    let in_while = 4;",
        "    ",
        "  }",
        "  ",
        "}",
    ])
    uri = "file:///scope_branches.sp"
    ls = _make_ls(uri, code)

    def _var_labels(line_idx: int) -> set:
      res = CompletionProvider.provide_completion(
          ls,
          CompletionParams(
              text_document=TextDocumentIdentifier(uri=uri),
              position=Position(line=line_idx, character=4),
          ),
      )
      return {item.label for item in res.items}

    # Inside guard else (line 6): sees in_guard_else
    self.assertIn("in_guard_else", _var_labels(6))
    # Inside else-if (line 12): sees in_elif
    self.assertIn("in_elif", _var_labels(12))
    # Inside else (line 15): sees in_else
    self.assertIn("in_else", _var_labels(15))
    # Inside while (line 19): sees in_while
    self.assertIn("in_while", _var_labels(19))
    # After guard (line 21): sees g_val
    self.assertIn("g_val", _var_labels(21))

  def test_enclosing_impl_and_binding_types_dot_fallback(self):
    """Verifies _find_enclosing_impl_struct None paths and binding_types fallback."""
    from types import SimpleNamespace

    from src.lsp.completion_provider import _find_enclosing_impl_struct
    from src.semantics.symbol_table import (
      PrimitiveType,
      StructType,
      SymbolTable,
    )
    from src.semantics.types import StructField

    self.assertIsNone(_find_enclosing_impl_struct(None, None, 1))
    self.assertIsNone(
        _find_enclosing_impl_struct(SimpleNamespace(declarations=[]), SymbolTable(), 1)
    )

    st = StructType("Vec2")
    st.fields["x"] = StructField("x", PrimitiveType("int"), True)

    class _BindingNode:
      binding_types = {"v": st}
      start_line = 2

    node = _BindingNode()
    uri = "file:///bt_dot.sp"
    mock_ls = SimpleNamespace(
        ast_cache={uri: SimpleNamespace(declarations=[])},
        symbol_table_cache={uri: SymbolTable()},
    )
    res = CompletionProvider._get_dot_completions(
        mock_ls, uri, "v", 3, {node: st}
    )
    self.assertIsNotNone(res)
    self.assertIn("x", {item.label for item in res.items})


if __name__ == "__main__":
  unittest.main()
