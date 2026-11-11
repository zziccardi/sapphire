"""Unit tests for annotation security and injection hardening."""

import unittest

from antlr4 import InputStream, CommonTokenStream
from src.parser.gen.SapphireLexer import SapphireLexer
from src.parser.gen.SapphireParser import SapphireParser
from src.parser.ast_builder import ASTBuilder
from src.semantics.type_checker import TypeChecker, SemanticError


class AnnotationSecurityTest(unittest.TestCase):
  """Verifies that @extern and @export annotation arguments are strictly validated."""

  def _check(self, source: str):
    lexer = SapphireLexer(InputStream(source))
    tokens = CommonTokenStream(lexer)
    parser = SapphireParser(tokens)
    tree = parser.program()
    ast = ASTBuilder().visit(tree)
    checker = TypeChecker()
    checker.check(ast)

  def test_valid_annotations(self):
    """Verifies that legitimate identifier paths in annotations are accepted."""
    valid_source = """
    @extern("love")
    var love_engine: int;

    @extern("wsgiref.simple_server")
    var server: int;

    @extern
    var bare_extern: int;

    trait Window {
      @export("love.graphics.setColor")
      func set_color(r: float, g: float, b: float);
    }

    struct Game {}

    impl Window for Game {
      @export("love.graphics.setColor")
      func set_color(r: float, g: float, b: float) {}
    }

    trait StaticGraphics {
      @export("setColor")
      static func setColorRgba(r: float, g: float, b: float, a: float = 1.0);
    }

    impl StaticGraphics for Game {
      @export("setColor")
      static func setColorRgba(r: float, g: float, b: float, a: float = 1.0) {}
    }

    @export("my_game.update")
    func game_update(dt: float) {}
    """
    # Should not raise any SemanticError
    self._check(valid_source)

  def test_reject_extern_injection_newlines(self):
    """Verifies that code injection payloads with newlines in @extern are rejected."""
    bad_source = """
    @extern("os\\nimport subprocess\\n#")
    var hijacked: int;
    """
    with self.assertRaises(SemanticError) as ctx:
      self._check(bad_source)
    self.assertIn("Invalid identifier path in '@extern' annotation", str(ctx.exception))

  def test_reject_export_injection_semicolons(self):
    """Verifies that commands and semicolons in @export are rejected."""
    bad_source = """
    @export("love.update; os.system('calc')")
    func update() {}
    """
    with self.assertRaises(SemanticError) as ctx:
      self._check(bad_source)
    self.assertIn("Invalid identifier path in '@export' annotation", str(ctx.exception))

  def test_reject_empty_annotation_argument(self):
    """Verifies that empty string argument in @extern or @export is rejected."""
    bad_source = """
    @extern("")
    var bad: int;
    """
    with self.assertRaises(SemanticError) as ctx:
      self._check(bad_source)
    self.assertIn("Invalid identifier path in '@extern' annotation", str(ctx.exception))

  def test_reject_spaces_in_annotation_argument(self):
    """Verifies that spaces in @export arguments are rejected."""
    bad_source = """
    @export("hello world")
    func greet() {}
    """
    with self.assertRaises(SemanticError) as ctx:
      self._check(bad_source)
    self.assertIn("Invalid identifier path in '@export' annotation", str(ctx.exception))

  def test_reject_consecutive_dots(self):
    """Verifies that malformed paths with consecutive dots are rejected."""
    bad_source = """
    @extern("foo..bar")
    var bad: int;
    """
    with self.assertRaises(SemanticError) as ctx:
      self._check(bad_source)
    self.assertIn("Invalid identifier path in '@extern' annotation", str(ctx.exception))


if __name__ == "__main__":
  unittest.main()
