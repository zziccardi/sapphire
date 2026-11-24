"""Test utilities for output suppression and common test helpers."""

import contextlib
import io
import sys
from typing import Any


@contextlib.contextmanager
def suppress_output():
  """Suppresses stdout and stderr for the duration of the context."""
  new_stdout, new_stderr = io.StringIO(), io.StringIO()
  old_stdout, old_stderr = sys.stdout, sys.stderr
  try:
    sys.stdout, sys.stderr = new_stdout, new_stderr
    yield new_stdout, new_stderr
  finally:
    sys.stdout, sys.stderr = old_stdout, old_stderr


class FakeDocument:
  """Lightweight in-memory text document for LSP unit tests."""

  def __init__(self, uri: str, source: str, version: int = 1) -> None:
    self.uri = uri
    self.source = source
    self.version = version

  @property
  def lines(self) -> list[str]:
    return self.source.splitlines(keepends=True)


class FakeWorkspace:
  """In-memory workspace test double replacing `ls.protocol._workspace` mocks.
  """

  def __init__(
    self,
    documents: dict[str, str | FakeDocument] | None = None,
    *,
    root_path: str | None = None,
    root_uri: str | None = None,
  ) -> None:
    self.root_path = root_path
    self.root_uri = root_uri
    self.text_documents: dict[str, FakeDocument] = {}
    if documents:
      for uri, doc in documents.items():
        if isinstance(doc, FakeDocument):
          self.text_documents[uri] = doc
        else:
          self.text_documents[uri] = FakeDocument(uri, doc)

  def put_document(self, uri: str, source: str) -> FakeDocument:
    """Adds or updates an in-memory document."""
    doc = FakeDocument(uri, source)
    self.text_documents[uri] = doc
    return doc

  def get_text_document(self, uri: str) -> FakeDocument:
    """Returns the document for *uri*, or an empty FakeDocument if absent."""
    if uri in self.text_documents:
      return self.text_documents[uri]
    return FakeDocument(uri, "")


def parse_source(
  source: str,
  *,
  file_path: str | None = None,
  quiet: bool = True,
) -> Any:
  """Parses a Sapphire source string into an AST ProgramNode."""
  from antlr4 import CommonTokenStream, InputStream

  from src.common.errors import SapphireSyntaxError
  from src.parser.ast_builder import ASTBuilder
  from src.parser.error_listener import CustomErrorListener
  from src.parser.gen.SapphireLexer import SapphireLexer
  from src.parser.gen.SapphireParser import SapphireParser

  input_stream = InputStream(source)
  error_listener = CustomErrorListener(
    file_path=file_path, source_content=source, quiet=quiet
  )
  lexer = SapphireLexer(input_stream)
  lexer.removeErrorListeners()
  lexer.addErrorListener(error_listener)
  stream = CommonTokenStream(lexer)
  parser = SapphireParser(stream)
  parser.removeErrorListeners()
  parser.addErrorListener(error_listener)
  tree = parser.program()
  if error_listener.errors > 0:
    err_text = (
      "\n".join(error_listener.error_messages)
      if error_listener.error_messages
      else f"Parsing failed with {error_listener.errors} syntax error(s)."
    )
    raise SapphireSyntaxError(err_text, file_path=file_path)
  return ASTBuilder().visit(tree)


def parse_and_check(
  source: str,
  *,
  file_path: str | None = None,
  target: str | None = None,
) -> tuple[Any, Any]:
  """Parses and type-checks Sapphire source, returning (ast, checker)."""
  from src.semantics.type_checker import TypeChecker

  ast = parse_source(source, file_path=file_path)
  checker = TypeChecker(
    source_file_path=file_path,
    source_content=source,
    target=target,
  )
  checker.check(ast)
  return ast, checker


def check_source(
  source: str,
  *,
  file_path: str | None = None,
  target: str | None = None,
) -> Any:
  """Parses and type-checks Sapphire source, returning the TypeChecker."""
  _, checker = parse_and_check(source, file_path=file_path, target=target)
  return checker


class TypeCheckerTestBase:
  """Shared mixin providing `_check()` and diagnostic-code assertions."""

  def _check(self, code: str, source_file_path: str | None = None) -> Any:
    """Parses and runs the semantic checker on a Sapphire source string."""
    from src.common.errors import SapphireSyntaxError
    from src.semantics.type_checker import TypeChecker

    try:
      ast = parse_source(code, file_path=source_file_path, quiet=True)
    except SapphireSyntaxError as err:
      raise SyntaxError(
        f"Syntax error while parsing code string for type checking:\n{code}"
      ) from err
    checker = TypeChecker(source_file_path=source_file_path)
    checker.check(ast)
    return checker
