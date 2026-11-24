"""Unit tests for HoverProvider in src/lsp/hover_provider.py."""

import unittest
from unittest.mock import MagicMock

from lsprotocol.types import (
  HoverParams,
  Position,
  TextDocumentIdentifier,
)

from src.lsp.hover_provider import HoverProvider, format_ast_expr
from src.lsp.server import SapphireLanguageServer, validate_source
from src.parser.ast import (
  BasicTypeNode,
  BinaryOpNode,
  CallNode,
  IdentifierNode,
  LiteralNode,
  MemberAccessNode,
  UnaryOpNode,
)


class TestHoverProvider(unittest.TestCase):
  """Unit tests for hover expression formatting and hover tooltips."""

  def test_format_ast_expr(self):
    self.assertEqual(format_ast_expr(None), "")
    self.assertEqual(format_ast_expr(LiteralNode(lit_type="string", value="hello")), '"hello"')
    self.assertEqual(format_ast_expr(LiteralNode(lit_type="bool", value=True)), "true")
    self.assertEqual(format_ast_expr(LiteralNode(lit_type="none", value=None)), "none")
    self.assertEqual(format_ast_expr(LiteralNode(lit_type="int", value=42)), "42")
    self.assertEqual(format_ast_expr(IdentifierNode("x")), "x")
    self.assertEqual(format_ast_expr(BasicTypeNode("float")), "float")

    member = MemberAccessNode(IdentifierNode("player"), "health", False)
    self.assertEqual(format_ast_expr(member), "player.health")

    member_opt = MemberAccessNode(IdentifierNode("opt_player"), "name", True)
    self.assertEqual(format_ast_expr(member_opt), "opt_player?.name")

    unary = UnaryOpNode("-", IdentifierNode("count"))
    self.assertEqual(format_ast_expr(unary), "-count")

    binary = BinaryOpNode(IdentifierNode("a"), "+", IdentifierNode("b"))
    self.assertEqual(format_ast_expr(binary), "a + b")

    call = CallNode(IdentifierNode("attack"), [])
    self.assertEqual(format_ast_expr(call), "attack()")

  def test_hover_missing_cache(self):
    mock_ls = MagicMock()
    mock_ls.ast_cache = {}
    mock_ls.node_types_cache = {}

    params = HoverParams(
        text_document=TextDocumentIdentifier(uri="file:///missing.sp"),
        position=Position(line=0, character=0),
    )
    result = HoverProvider.provide_hover(mock_ls, params)
    self.assertIsNone(result)

  def test_hover_integration(self):
    from testing.test_utils import FakeWorkspace

    ls = SapphireLanguageServer("test-lsp", "0.1.0", workspace=FakeWorkspace())
    ls.text_document_publish_diagnostics = MagicMock()
    doc_uri = "file:///hover_test.sp"
    code = """
    // Represents a game weapon.
    struct Weapon {
      var power: int;
    }

    func equip(w: Weapon) {
      let current = w.power;
    }
    """
    validate_source(ls, doc_uri, code)
    self.assertIn(doc_uri, ls.ast_cache)

    # Hover over struct Weapon (line 3, col 12)
    params = HoverParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=2, character=11),
    )
    res = HoverProvider.provide_hover(ls, params)
    self.assertIsNotNone(res)
    self.assertIn("struct", res.contents.value)
    self.assertIn("Weapon", res.contents.value)

  def test_hover_qualified_ancestor_dispatch(self):
    """Verifies hover info on qualified ancestor method calls."""
    from testing.test_utils import FakeWorkspace

    ls = SapphireLanguageServer("test-lsp", "0.1.0", workspace=FakeWorkspace())
    ls.text_document_publish_diagnostics = MagicMock()
    doc_uri = "file:///hover_ancestor.sp"
    code = (
        "struct Base {\n"
        "  var hp: int;\n"
        "}\n"
        "impl Base {\n"
        "  func draw(): int {\n"
        "    return self.hp;\n"
        "  }\n"
        "}\n"
        "struct Child: Base {\n"
        "  var extra: int;\n"
        "}\n"
        "impl Child {\n"
        "  func draw(): int {\n"
        "    return Base.draw(self) + self.extra;\n"
        "  }\n"
        "}\n"
    )
    validate_source(ls, doc_uri, code)
    lines = code.splitlines()
    call_line = 13
    draw_col = lines[call_line].index("draw(self)")
    res = HoverProvider.provide_hover(
        ls,
        HoverParams(
            text_document=TextDocumentIdentifier(uri=doc_uri),
            position=Position(line=call_line, character=draw_col),
        ),
    )
    self.assertIsNotNone(res)
    self.assertIn("method", res.contents.value)
    self.assertIn("draw", res.contents.value)

  def test_hover_method_call_unwraps_struct_method_and_shadows_global(self):
    """Verifies CallNode(MemberAccessNode) unwraps StructMethod and local hover beats global."""
    from testing.test_utils import FakeWorkspace

    ls = SapphireLanguageServer("test-lsp", "0.1.0", workspace=FakeWorkspace())
    ls.text_document_publish_diagnostics = MagicMock()
    doc_uri = "file:///hover_bugfixes.sp"
    code = (
        "struct Base {\n"
        "  var val: int;\n"
        "}\n"
        "impl Base {\n"
        "  func compute(x: int): int { return self.val + x; }\n"
        "}\n"
        "func helper(): int { return 1; }\n"
        "func demo(helper: int) {\n"
        "  let b = Base { val = 10 };\n"
        "  let r = b.compute(helper);\n"
        "  let a, msg = 1, \"hi\";\n"
        "}\n"
    )
    ls.workspace.put_document(doc_uri, code)
    validate_source(ls, doc_uri, code)
    lines = code.splitlines()

    # Hover on parameter declaration `helper` (line 7) shows parameter: int, not global function.
    res_param = HoverProvider.provide_hover(
        ls,
        HoverParams(
            text_document=TextDocumentIdentifier(uri=doc_uri),
            position=Position(line=7, character=lines[7].index("helper")),
        ),
    )
    self.assertIsNotNone(res_param)
    self.assertIn("(parameter)", res_param.contents.value)
    self.assertIn("int", res_param.contents.value)

    # Hover on `helper` identifier inside demo() (line 9) shows parameter, NOT function.
    res_use = HoverProvider.provide_hover(
        ls,
        HoverParams(
            text_document=TextDocumentIdentifier(uri=doc_uri),
            position=Position(line=9, character=lines[9].index("helper")),
        ),
    )
    self.assertIsNotNone(res_use)
    self.assertIn("(parameter)", res_use.contents.value)
    self.assertNotIn("(function)", res_use.contents.value)

    # Hover on `compute` in `b.compute(helper)` renders clean method signature, never StructMethod repr.
    res_call = HoverProvider.provide_hover(
        ls,
        HoverParams(
            text_document=TextDocumentIdentifier(uri=doc_uri),
            position=Position(line=9, character=lines[9].index("compute")),
        ),
    )
    self.assertIsNotNone(res_call)
    self.assertNotIn("StructMethod", res_call.contents.value)
    self.assertIn("compute", res_call.contents.value)
    self.assertIn("Returns: `int`", res_call.contents.value)

    # Hover on `msg` in multi-var `let a, msg = 1, "hi";` shows `msg: String`, not `a: int`.
    res_mv = HoverProvider.provide_hover(
        ls,
        HoverParams(
            text_document=TextDocumentIdentifier(uri=doc_uri),
            position=Position(line=10, character=lines[10].index("msg")),
        ),
    )
    self.assertIsNotNone(res_mv)
    self.assertIn("`msg`", res_mv.contents.value)
    self.assertIn("`String`", res_mv.contents.value)


if __name__ == "__main__":
  unittest.main()
