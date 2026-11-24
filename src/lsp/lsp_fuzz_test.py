"""Deterministic fuzz tests for the Sapphire parser and LSP providers.

Mutates real Sapphire source files (prefix truncations, deleted delimiters,
injected completion/signature triggers, and multi-byte UTF-16 characters) and
verifies that `validate_source` and every LSP provider handle malformed buffers
and boundary cursor positions without raising unhandled exceptions.
"""

import os
import random
import unittest
from unittest.mock import MagicMock

from lsprotocol.types import (
  CompletionParams,
  DefinitionParams,
  HoverParams,
  Position,
  SignatureHelpParams,
  TextDocumentIdentifier,
)

from src.lsp.completion_provider import CompletionProvider
from src.lsp.definition_provider import DefinitionProvider
from src.lsp.document_symbols import extract_document_symbols
from src.lsp.hover_provider import HoverProvider
from src.lsp.semantic_tokens import find_node_at_position
from src.lsp.server import SapphireLanguageServer, validate_source
from src.lsp.signature_provider import SignatureProvider

_REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)
_SEED = 20261122
_CORPUS_FILES = [
    "testing/e2e/structs_and_methods_test.sp",
    "testing/e2e/match_expressions_test.sp",
    "testing/e2e/optionals_test.sp",
    "testing/e2e/prototypes_test.sp",
    "testing/e2e/traits_polymorphism_test.sp",
    "testing/e2e/raii_and_cleanup_test.sp",
    "testing/e2e/generics_test.sp",
    "testing/e2e/coroutines_test.sp",
]


def _make_server() -> SapphireLanguageServer:
  ls = SapphireLanguageServer("sapphire-fuzz", "0.1.0")
  ls.text_document_publish_diagnostics = MagicMock()
  ls.protocol._workspace = MagicMock()
  return ls


def _set_doc(ls: SapphireLanguageServer, uri: str, source: str) -> None:
  doc = MagicMock()
  doc.uri = uri
  doc.source = source
  ls.workspace.get_text_document.return_value = doc


def _mutate_source(rng: random.Random, source: str) -> str:
  """Applies a deterministic live-typing mutation to *source*."""
  if not source:
    return source
  op = rng.choice([
      "truncate",
      "delete_slice",
      "insert_trigger",
      "drop_delimiter",
      "inject_unicode",
  ])
  idx = rng.randint(0, max(0, len(source) - 1))

  if op == "truncate":
    return source[:idx]
  if op == "delete_slice":
    end = min(len(source), idx + rng.randint(1, 25))
    return source[:idx] + source[end:]
  if op == "insert_trigger":
    trigger = rng.choice([".", "?.", "(", ", ", "self.", "match ", '"unclosed'])
    return source[:idx] + trigger + source[idx:]
  if op == "drop_delimiter":
    delim = rng.choice([";", "{", "}", "(", ")", "[", "]", '"'])
    pos = source.find(delim, idx)
    if pos == -1:
      pos = source.find(delim)
    if pos != -1:
      return source[:pos] + source[pos + 1 :]
    return source[:idx]
  # inject_unicode: insert surrogate-pair emoji and accented chars in comments/strings
  token = rng.choice(['// 😀 café 日本語\n', '"🚀" ', "/* ✨ */ "])
  return source[:idx] + token + source[idx:]


class TestLspFuzz(unittest.TestCase):
  """Fuzz tests ensuring parser and LSP providers never crash on malformed input."""

  def _load_corpus(self) -> list:
    sources = []
    for rel_path in _CORPUS_FILES:
      full_path = os.path.join(_REPO_ROOT, rel_path)
      if os.path.isfile(full_path):
        with open(full_path, encoding="utf-8") as f:
          sources.append((rel_path, f.read()))
    self.assertGreater(len(sources), 0, "Expected non-empty Sapphire corpus")
    return sources

  def test_mutated_buffers_never_crash_lsp_providers(self):
    """Fuzzes validate_source + all LSP providers across 60 mutated buffers."""
    rng = random.Random(_SEED)
    corpus = self._load_corpus()
    ls = _make_server()
    uri = "file:///fuzz_buffer.sp"

    for i in range(60):
      rel_path, base_src = corpus[i % len(corpus)]
      # First validate clean source to populate caches (realistic live-edit flow)
      _set_doc(ls, uri, base_src)
      validate_source(ls, uri, base_src)

      mutated = _mutate_source(rng, base_src)
      _set_doc(ls, uri, mutated)
      try:
        validate_source(ls, uri, mutated)
      except Exception as exc:
        self.fail(
            f"validate_source crashed on mutation #{i} of {rel_path}: {exc!r}"
        )

      lines = mutated.splitlines() or [""]
      sample_positions = [
          Position(line=0, character=0),
          Position(line=len(lines) + 2, character=10),  # past EOF
      ]
      for _ in range(3):
        ln = rng.randint(0, len(lines) - 1)
        col = rng.randint(0, len(lines[ln]) + 4)
        sample_positions.append(Position(line=ln, character=col))

      doc_id = TextDocumentIdentifier(uri=uri)
      for pos in sample_positions:
        try:
          HoverProvider.provide_hover(
              ls,
              HoverParams(text_document=doc_id, position=pos),
              find_node_fn=find_node_at_position,
          )
          CompletionProvider.provide_completion(
              ls, CompletionParams(text_document=doc_id, position=pos)
          )
          DefinitionProvider.provide_definition(
              ls,
              DefinitionParams(text_document=doc_id, position=pos),
              find_node_fn=find_node_at_position,
          )
          SignatureProvider.provide_signature_help(
              ls, SignatureHelpParams(text_document=doc_id, position=pos)
          )
        except Exception as exc:
          self.fail(
              f"LSP provider crashed on mutation #{i} ({rel_path}) at {pos}: {exc!r}"
          )

      ast = ls.ast_cache.get(uri)
      if ast is not None:
        try:
          extract_document_symbols(ast)
        except Exception as exc:
          self.fail(
              f"extract_document_symbols crashed on mutation #{i} ({rel_path}): {exc!r}"
          )

  def test_transient_syntax_error_preserves_valid_token_cache(self):
    """Verifies broken mid-typing edits do not wipe previously valid semantic tokens."""
    ls = _make_server()
    uri = "file:///preserve_tokens.sp"
    valid = (
        "struct Player {\n"
        "  var hp: int;\n"
        "}\n"
        "func demo(): int {\n"
        "  let p = Player { hp = 10 };\n"
        "  return p.hp;\n"
        "}\n"
    )
    _set_doc(ls, uri, valid)
    validate_source(ls, uri, valid)
    cached_tokens = list(ls.tokens_cache.get(uri, []))
    self.assertGreater(len(cached_tokens), 0)

    # Introduce a mid-typing syntax error (`p.`)
    broken = valid.replace("return p.hp;", "return p.;")
    _set_doc(ls, uri, broken)
    validate_source(ls, uri, broken)
    self.assertEqual(ls.tokens_cache.get(uri), cached_tokens)


if __name__ == "__main__":
  unittest.main()
