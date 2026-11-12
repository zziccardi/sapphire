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

  def test_definition_multi_binding_if_guard_and_shared_ref(self):
    ls = SapphireLanguageServer("test-lsp", "0.1.0")
    ls.text_document_publish_diagnostics = MagicMock()
    ls.protocol._workspace = MagicMock()
    doc_uri = "file:///multi_bind_def.sp"
    code = "\n".join([
        "struct SharedDagNode {",
        "  let label: String;",
        "  let parent: WeakRef<SharedDagNode>?;",
        "}",
        "func demo() {",
        '  let root = SharedRef(SharedDagNode { label = "R", parent = none });',
        "  let leaf = SharedRef(SharedDagNode {",
        '    label = "L",',
        "    parent = root.downgrade(),",
        "  });",
        "  let shared_alias = leaf.share();",
        "  if let p ?= shared_alias.parent; let up ?= p.upgrade() {",
        "    print(up.label);",
        "  }",
        "  guard let gp ?= shared_alias.parent; let gup ?= gp.upgrade() else {",
        "    return;",
        "  }",
        "  print(gup.label);",
        "}",
    ])
    validate_source(ls, doc_uri, code)
    publish_args = ls.text_document_publish_diagnostics.call_args[0][0]
    self.assertEqual(publish_args.diagnostics, [])

    lines = code.splitlines()
    # 1. Go-to-definition on 'p' in 'p.upgrade()' (line 11, 0-based)
    if_line_idx = 11
    p_use_col = lines[if_line_idx].index("p.upgrade()")
    p_decl_col = lines[if_line_idx].index("p ?=")
    res_p = DefinitionProvider.provide_definition(
        ls,
        DefinitionParams(
            text_document=TextDocumentIdentifier(uri=doc_uri),
            position=Position(line=if_line_idx, character=p_use_col),
        ),
    )
    self.assertIsNotNone(res_p)
    self.assertEqual(res_p.range.start.line, if_line_idx)
    self.assertEqual(res_p.range.start.character, p_decl_col)

    # 2. Go-to-definition on 'gp' in 'gp.upgrade()' (line 14, 0-based)
    guard_line_idx = 14
    gp_use_col = lines[guard_line_idx].index("gp.upgrade()")
    gp_decl_col = lines[guard_line_idx].index("gp ?=")
    res_gp = DefinitionProvider.provide_definition(
        ls,
        DefinitionParams(
            text_document=TextDocumentIdentifier(uri=doc_uri),
            position=Position(line=guard_line_idx, character=gp_use_col),
        ),
    )
    self.assertIsNotNone(res_gp)
    self.assertEqual(res_gp.range.start.line, guard_line_idx)
    self.assertEqual(res_gp.range.start.character, gp_decl_col)

    # 3. Go-to-definition on '.parent' in 'shared_alias.parent'
    parent_use_col = lines[if_line_idx].index(".parent") + 1
    parent_decl_col = lines[2].index("parent")
    res_parent = DefinitionProvider.provide_definition(
        ls,
        DefinitionParams(
            text_document=TextDocumentIdentifier(uri=doc_uri),
            position=Position(line=if_line_idx, character=parent_use_col),
        ),
    )
    self.assertIsNotNone(res_parent)
    self.assertEqual(res_parent.range.start.line, 2)
    self.assertEqual(res_parent.range.start.character, parent_decl_col)


if __name__ == "__main__":
  unittest.main()
