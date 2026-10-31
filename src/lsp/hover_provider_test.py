"""Unit tests for HoverProvider in src/lsp/hover_provider.py."""

import unittest
from unittest.mock import MagicMock
from lsprotocol.types import (
    HoverParams,
    Position,
    TextDocumentIdentifier,
)

from src.parser.ast import (
    BasicTypeNode,
    BinaryOpNode,
    CallNode,
    IdentifierNode,
    LiteralNode,
    MemberAccessNode,
    UnaryOpNode,
)
from src.lsp.hover_provider import HoverProvider, format_ast_expr
from src.lsp.server import SapphireLanguageServer, validate_source


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
    ls = SapphireLanguageServer("test-lsp", "0.1.0")
    ls.text_document_publish_diagnostics = MagicMock()
    ls.protocol._workspace = MagicMock()
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


if __name__ == "__main__":
  unittest.main()
