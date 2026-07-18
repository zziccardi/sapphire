import unittest
from unittest.mock import MagicMock, patch
from lsprotocol.types import SemanticTokensParams

# Import server components
try:
  from lsp.server import (
      SapphireLanguageServer,
      ANTLRDiagnosticListener,
      validate_source,
      did_open,
      did_change,
      did_save,
      semantic_tokens_full,
      main,
  )
except ImportError:
  from src.lsp.server import (
      SapphireLanguageServer,
      ANTLRDiagnosticListener,
      validate_source,
      did_open,
      did_change,
      did_save,
      semantic_tokens_full,
      main,
  )


class TestLSPServer(unittest.TestCase):

  def setUp(self):
    self.ls = SapphireLanguageServer("test-lsp", "0.1.0")
    # Mock publish_diagnostics
    self.ls.publish_diagnostics = MagicMock()
    # Mock workspace lookup method by setting protocol._workspace
    self.ls.protocol._workspace = MagicMock()

  def test_validate_source_valid(self):
    doc_uri = "file:///test.sp"
    doc_text = "let x: int = 42;"
    validate_source(self.ls, doc_uri, doc_text)

    # Check diagnostics published (should be empty list)
    self.ls.publish_diagnostics.assert_called_once_with(doc_uri, [])
    # Check cache contains encoded tokens
    self.assertIn(doc_uri, self.ls.tokens_cache)
    self.assertTrue(len(self.ls.tokens_cache[doc_uri]) > 0)

  def test_validate_source_syntax_error(self):
    doc_uri = "file:///test.sp"
    doc_text = "let x int 42;"  # Syntax error: missing colon and assignment
    validate_source(self.ls, doc_uri, doc_text)

    # Check diagnostics published
    self.ls.publish_diagnostics.assert_called_once()
    args = self.ls.publish_diagnostics.call_args[0]
    self.assertEqual(args[0], doc_uri)
    self.assertTrue(len(args[1]) > 0)
    self.assertEqual(args[1][0].source, "sapphire-parser")

  def test_validate_source_ast_builder_failure(self):
    doc_uri = "file:///test.sp"
    doc_text = "let x: int = 42;"

    # Mock ASTBuilder.visit to throw an exception to simulate compiler error
    # Try importing either local or global path for mock
    try:
      patch_path = "lsp.server.ASTBuilder.visit"
      with patch(patch_path, side_effect=ValueError("Mock AST generation error")):
        validate_source(self.ls, doc_uri, doc_text)
    except (ImportError, ModuleNotFoundError, AttributeError):  # pragma: no cover
      patch_path = "src.lsp.server.ASTBuilder.visit"
      with patch(patch_path, side_effect=ValueError("Mock AST generation error")):
        validate_source(self.ls, doc_uri, doc_text)

    self.ls.publish_diagnostics.assert_called_once()
    args = self.ls.publish_diagnostics.call_args[0]
    self.assertEqual(args[0], doc_uri)
    self.assertEqual(args[1][0].source, "sapphire-compiler")
    self.assertIn("Internal AST generation failure", args[1][0].message)

  def test_validate_source_semantic_error(self):
    doc_uri = "file:///test.sp"
    doc_text = 'let x: int = "string";'  # Type mismatch
    validate_source(self.ls, doc_uri, doc_text)

    # Check diagnostics published
    self.ls.publish_diagnostics.assert_called_once()
    args = self.ls.publish_diagnostics.call_args[0]
    self.assertEqual(args[0], doc_uri)
    self.assertTrue(len(args[1]) > 0)
    self.assertEqual(args[1][0].source, "sapphire-semantics")

  def test_did_open_change_save(self):
    doc_uri = "file:///test.sp"
    doc_text = "let x: int = 42;"

    mock_doc = MagicMock()
    mock_doc.uri = doc_uri
    mock_doc.source = doc_text
    self.ls.workspace.get_text_document.return_value = mock_doc

    # Mock params
    params = MagicMock()
    params.text_document.uri = doc_uri

    # 1. did_open
    did_open(self.ls, params)
    self.ls.publish_diagnostics.assert_called_with(doc_uri, [])
    self.ls.publish_diagnostics.reset_mock()

    # 2. did_change
    did_change(self.ls, params)
    self.ls.publish_diagnostics.assert_called_with(doc_uri, [])
    self.ls.publish_diagnostics.reset_mock()

    # 3. did_save
    did_save(self.ls, params)
    self.ls.publish_diagnostics.assert_called_with(doc_uri, [])

  def test_semantic_tokens_full(self):
    doc_uri = "file:///test.sp"
    doc_text = "let x: int = 42;"

    # Mock params
    params = MagicMock()
    params.text_document.uri = doc_uri

    # Mock document lookup
    mock_doc = MagicMock()
    mock_doc.uri = doc_uri
    mock_doc.source = doc_text
    self.ls.workspace.get_text_document.return_value = mock_doc

    # 1. First retrieval when not cached (triggers validation)
    tokens = semantic_tokens_full(self.ls, params)
    self.assertTrue(len(tokens.data) > 0)
    self.assertEqual(self.ls.tokens_cache[doc_uri], tokens.data)

    # 2. Subsequent retrieval from cache
    self.ls.publish_diagnostics.reset_mock()
    self.ls.workspace.get_text_document.reset_mock()
    tokens2 = semantic_tokens_full(self.ls, params)
    self.assertEqual(tokens2.data, tokens.data)
    # Shouldn't require document lookup or validate again
    self.ls.workspace.get_text_document.assert_not_called()

  def test_main(self):
    try:
      patch_path = "lsp.server.server.start_io"
      with patch(patch_path) as mock_start_io:
        main()
        mock_start_io.assert_called_once()
    except (ImportError, ModuleNotFoundError, AttributeError):  # pragma: no cover
      patch_path = "src.lsp.server.server.start_io"
      with patch(patch_path) as mock_start_io:
        main()
        mock_start_io.assert_called_once()


if __name__ == "__main__":
  unittest.main()
