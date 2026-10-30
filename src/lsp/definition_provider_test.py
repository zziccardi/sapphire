"""Unit tests for DefinitionProvider in src/lsp/definition_provider.py."""

import unittest
from unittest.mock import MagicMock
from lsprotocol.types import (
    DefinitionParams,
    Position,
    TextDocumentIdentifier,
)

from src.lsp.definition_provider import (
    DefinitionProvider,
    find_local_decl,
    resolve_module_path,
)
from src.lsp.server import SapphireLanguageServer, validate_source


class TestDefinitionProvider(unittest.TestCase):
  """Unit tests for go-to-definition and local declaration lookup."""

  def test_resolve_module_path_nonexistent(self):
    self.assertIsNone(resolve_module_path("file:///main.sp", "nonexistent.mod"))
    self.assertIsNone(resolve_module_path("invalid_uri", "nonexistent.mod"))

  def test_find_local_decl_none(self):
    mock_ast = MagicMock()
    mock_ast.declarations = []
    self.assertIsNone(find_local_decl(mock_ast, "x", 10))

  def test_definition_missing_cache(self):
    mock_ls = MagicMock()
    mock_ls.ast_cache = {}
    mock_ls.symbol_table_cache = {}

    params = DefinitionParams(
        text_document=TextDocumentIdentifier(uri="file:///missing.sp"),
        position=Position(line=0, character=0),
    )
    result = DefinitionProvider.provide_definition(mock_ls, params)
    self.assertIsNone(result)

  def test_definition_integration(self):
    ls = SapphireLanguageServer("test-lsp", "0.1.0")
    ls.text_document_publish_diagnostics = MagicMock()
    ls.protocol._workspace = MagicMock()
    doc_uri = "file:///def_test.sp"
    code = """
    struct Item {
      var id: int;
    }

    func use_item(item: Item) {
      let x = item.id;
    }
    """
    validate_source(ls, doc_uri, code)
    self.assertIn(doc_uri, ls.ast_cache)

    # Go to definition on 'Item' in 'use_item(item: Item)' (line 6, col 25)
    params = DefinitionParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=5, character=25),
    )
    res = DefinitionProvider.provide_definition(ls, params)
    self.assertIsNotNone(res)
    self.assertEqual(res.uri, doc_uri)
    # Definition should point to line 2 (line index 1 in 0-based LSP)
    self.assertEqual(res.range.start.line, 1)


if __name__ == "__main__":
  unittest.main()
