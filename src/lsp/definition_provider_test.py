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
    ls = SapphireLanguageServer("test-lsp", "0.1.0", workspace=MagicMock())
    ls.text_document_publish_diagnostics = MagicMock()
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
    ls = SapphireLanguageServer("test-lsp", "0.1.0", workspace=MagicMock())
    ls.text_document_publish_diagnostics = MagicMock()
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

  def test_local_decl_inside_control_flow_blocks(self):
    code = "\n".join([
        "func demo(flag: bool): void {",
        "  if flag {",
        "    let a: int = 1;",
        "    let x: int = a;",
        "  } else if !flag {",
        "    let b: int = 2;",
        "    let y: int = b;",
        "  } else {",
        "    let c: int = 3;",
        "    let z: int = c;",
        "  }",
        "  for i in 0..3 {",
        "    let d: int = 4;",
        "    let w: int = d;",
        "  }",
        "  while false {",
        "    let e: int = 5;",
        "    let u: int = e;",
        "  }",
        "  {",
        "    let f: int = 6;",
        "    let v: int = f;",
        "  }",
        "}",
    ])
    ls = SapphireLanguageServer("sapphire", "v0", workspace=MagicMock())
    ls.text_document_publish_diagnostics = MagicMock()
    doc_uri = "file:///tmp/test_cf_def.sp"
    doc = MagicMock()
    doc.source = code
    doc.uri = doc_uri
    ls.workspace.get_text_document.return_value = doc
    validate_source(ls, doc_uri, code)

    lines = code.splitlines()
    checks = [
        (3, "a;", 2, "a:"),
        (6, "b;", 5, "b:"),
        (9, "c;", 8, "c:"),
        (13, "d;", 12, "d:"),
        (17, "e;", 16, "e:"),
        (21, "f;", 20, "f:"),
    ]
    for use_line, use_tok, decl_line, decl_tok in checks:
      res = DefinitionProvider.provide_definition(
          ls,
          DefinitionParams(
              text_document=TextDocumentIdentifier(uri=doc_uri),
              position=Position(
                  line=use_line, character=lines[use_line].index(use_tok)
              ),
          ),
      )
      self.assertIsNotNone(res)
      self.assertEqual(res.range.start.line, decl_line)
      self.assertEqual(
          res.range.start.character, lines[decl_line].index(decl_tok)
      )

  def test_definition_qualified_ancestor_dispatch(self):
    """Verifies go-to-definition resolves Parent.method and inherited ancestor methods."""
    code = "\n".join([
        "struct Grand {",
        "  var x: int;",
        "}",
        "impl Grand {",
        "  func ping(): int { return self.x; }",
        "}",
        "struct Parent: Grand {",
        "  var y: int;",
        "}",
        "struct Child: Parent {",
        "  var z: int;",
        "}",
        "impl Child {",
        "  func ping(): int {",
        "    return Parent.ping(self) + self.z;",
        "  }",
        "}",
    ])
    ls = SapphireLanguageServer("sapphire", "v0", workspace=MagicMock())
    ls.text_document_publish_diagnostics = MagicMock()
    doc_uri = "file:///tmp/test_ancestor_def.sp"
    doc = MagicMock()
    doc.source = code
    doc.uri = doc_uri
    ls.workspace.get_text_document.return_value = doc
    validate_source(ls, doc_uri, code)

    lines = code.splitlines()
    use_line = 14
    use_col = lines[use_line].index("ping(self)")
    res = DefinitionProvider.provide_definition(
        ls,
        DefinitionParams(
            text_document=TextDocumentIdentifier(uri=doc_uri),
            position=Position(line=use_line, character=use_col),
        ),
    )
    self.assertIsNotNone(res)
    self.assertEqual(res.range.start.line, 4)

  def test_definition_local_shadows_global_and_no_scope_leak(self):
    """Verifies locals resolve before globals and do not leak across functions or blocks."""
    code = "\n".join([
        "func helper(): int { return 1; }",
        "func first() {",
        "  let helper = 42;",
        "  let a = helper;",
        "  if true {",
        "    let inner_only = 7;",
        "  }",
        "  let b = 0;",
        "}",
        "func second() {",
        "  let c = helper();",
        "  let d = inner_only;",
        "}",
    ])
    ls = SapphireLanguageServer("sapphire", "v0", workspace=MagicMock())
    ls.text_document_publish_diagnostics = MagicMock()
    doc_uri = "file:///tmp/test_scope_def.sp"
    doc = MagicMock()
    doc.source = code
    doc.uri = doc_uri
    ls.workspace.get_text_document.return_value = doc
    validate_source(ls, doc_uri, code)

    lines = code.splitlines()
    # Inside first(), `helper` on line 3 jumps to local `let helper = 42` on line 2.
    res_shadow = DefinitionProvider.provide_definition(
        ls,
        DefinitionParams(
            text_document=TextDocumentIdentifier(uri=doc_uri),
            position=Position(line=3, character=lines[3].index("helper")),
        ),
    )
    self.assertIsNotNone(res_shadow)
    self.assertEqual(res_shadow.range.start.line, 2)

    # Inside second(), `helper()` on line 10 jumps to global `func helper` on line 0 (no +10 leak!).
    res_global = DefinitionProvider.provide_definition(
        ls,
        DefinitionParams(
            text_document=TextDocumentIdentifier(uri=doc_uri),
            position=Position(line=10, character=lines[10].index("helper")),
        ),
    )
    self.assertIsNotNone(res_global)
    self.assertEqual(res_global.range.start.line, 0)

    # `inner_only` declared inside first()'s if-block must not leak to second().
    res_leak = DefinitionProvider.provide_definition(
        ls,
        DefinitionParams(
            text_document=TextDocumentIdentifier(uri=doc_uri),
            position=Position(line=11, character=lines[11].index("inner_only")),
        ),
    )
    self.assertIsNone(res_leak)

  def test_definition_struct_init_move_multivar_and_same_field_name(self):
    """Verifies go-to-def for StructInitializerNode, MoveNode, multi-var, and same-named fields."""
    code = "\n".join([
        "struct Foo {",
        "  var x: int;",
        "}",
        "struct Bar {",
        "  var x: int;",
        "}",
        "func take(f: Foo) {}",
        "func main() {",
        "  let f = Foo { x = 1 };",
        "  let b = Bar { x = 2 };",
        "  let bx = b.x;",
        "  let a, second_val = 10, 20;",
        "  let use_second = second_val;",
        "  take(move f);",
        "}",
    ])
    ls = SapphireLanguageServer("sapphire", "v0", workspace=MagicMock())
    ls.text_document_publish_diagnostics = MagicMock()
    doc_uri = "file:///tmp/test_extra_def.sp"
    doc = MagicMock()
    doc.source = code
    doc.uri = doc_uri
    ls.workspace.get_text_document.return_value = doc
    validate_source(ls, doc_uri, code)

    lines = code.splitlines()
    # StructInitializerNode: `Foo` in `Foo { x = 1 }` jumps to `struct Foo` (line 0).
    res_init = DefinitionProvider.provide_definition(
        ls,
        DefinitionParams(
            text_document=TextDocumentIdentifier(uri=doc_uri),
            position=Position(line=8, character=lines[8].index("Foo")),
        ),
    )
    self.assertIsNotNone(res_init)
    self.assertEqual(res_init.range.start.line, 0)

    # `b.x` jumps to `Bar.x` (line 4), NOT `Foo.x` (line 1).
    res_bx = DefinitionProvider.provide_definition(
        ls,
        DefinitionParams(
            text_document=TextDocumentIdentifier(uri=doc_uri),
            position=Position(line=10, character=lines[10].index(".x") + 1),
        ),
    )
    self.assertIsNotNone(res_bx)
    self.assertEqual(res_bx.range.start.line, 4)

    # Multi-var: `second_val` jumps to `second_val`'s column on line 11, not `a`.
    res_mv = DefinitionProvider.provide_definition(
        ls,
        DefinitionParams(
            text_document=TextDocumentIdentifier(uri=doc_uri),
            position=Position(line=12, character=lines[12].index("second_val")),
        ),
    )
    self.assertIsNotNone(res_mv)
    self.assertEqual(res_mv.range.start.line, 11)
    self.assertEqual(
        res_mv.range.start.character, lines[11].index("second_val")
    )

    # MoveNode: `move f` jumps to `let f = ...` (line 8).
    res_move = DefinitionProvider.provide_definition(
        ls,
        DefinitionParams(
            text_document=TextDocumentIdentifier(uri=doc_uri),
            position=Position(line=13, character=lines[13].index("f)")),
        ),
    )
    self.assertIsNotNone(res_move)
    self.assertEqual(res_move.range.start.line, 8)

  def test_definition_utf16_columns_with_emoji(self):
    """Verifies UTF-16 LSP columns map accurately across non-BMP characters."""
    code = 'func main() {\n  let s = "🚀"; let target = 1;\n  let r = target;\n}\n'
    ls = SapphireLanguageServer("sapphire", "v0", workspace=MagicMock())
    ls.text_document_publish_diagnostics = MagicMock()
    doc_uri = "file:///tmp/test_utf16_def.sp"
    doc = MagicMock()
    doc.source = code
    doc.uri = doc_uri
    ls.workspace.get_text_document.return_value = doc
    validate_source(ls, doc_uri, code)

    lines = code.splitlines()
    # In UTF-16, "🚀" takes 2 code units instead of 1 Python code point.
    expected_u16_col = (
        len(lines[1][: lines[1].index("target")].encode("utf-16-le")) // 2
    )
    res = DefinitionProvider.provide_definition(
        ls,
        DefinitionParams(
            text_document=TextDocumentIdentifier(uri=doc_uri),
            position=Position(line=2, character=lines[2].index("target")),
        ),
    )
    self.assertIsNotNone(res)
    self.assertEqual(res.range.start.line, 1)
    self.assertEqual(res.range.start.character, expected_u16_col)

  def test_preload_does_not_overwrite_open_dirty_buffer(self):
    """Verifies _preload_module_dependencies skips disk reload for open workspace buffers."""
    import os
    import tempfile

    from pygls.uris import from_fs_path

    with tempfile.TemporaryDirectory() as tmp_dir:
      dep_path = os.path.join(tmp_dir, "dep.sp")
      main_path = os.path.join(tmp_dir, "main.sp")
      with open(dep_path, "w", encoding="utf-8") as f:
        f.write("func from_disk(): int { return 1; }\nexport { from_disk, }\n")
      main_code = "import dep;\nfunc main() { let x = dep.from_disk(); }\n"
      with open(main_path, "w", encoding="utf-8") as f:
        f.write(main_code)

      dep_uri = from_fs_path(os.path.abspath(dep_path))
      main_uri = from_fs_path(os.path.abspath(main_path))

      from testing.test_utils import FakeWorkspace

      dirty_dep = "func unsaved_fn(): int { return 2; }\nexport { unsaved_fn, }\n"
      ls = SapphireLanguageServer(
          "sapphire", "v0", workspace=FakeWorkspace({dep_uri: dirty_dep})
      )
      ls.text_document_publish_diagnostics = MagicMock()
      validate_source(ls, dep_uri, dirty_dep)
      cached_ast_before = ls.ast_cache[dep_uri]

      validate_source(ls, main_uri, main_code)
      # The open unsaved buffer's AST cache must NOT be replaced by disk content.
      self.assertIs(ls.ast_cache[dep_uri], cached_ast_before)

  def test_extract_node_range_fallbacks(self):
    """Verifies HeaderBindingNode let_name_* and start_line/end_line fallback ranges."""
    from types import SimpleNamespace

    from src.parser.ast import HeaderBindingNode, IdentifierNode, LiteralNode

    hb = HeaderBindingNode(False, "x", None, LiteralNode(1, "int"), True)
    hb.let_name_line = 4
    hb.let_name_column = 6
    hb.let_name_length = 1
    r1 = DefinitionProvider._extract_node_range(hb, IdentifierNode("x"))
    self.assertIsNotNone(r1)
    self.assertEqual(r1.start.line, 3)
    self.assertEqual(r1.start.character, 6)
    self.assertEqual(r1.end.character, 7)

    # Fallback to start_line/start_column/end_line/end_column when name_* absent
    plain = SimpleNamespace(
        start_line=2, start_column=3, end_line=2, end_column=8
    )
    r2 = DefinitionProvider._extract_node_range(plain, IdentifierNode("y"))
    self.assertIsNotNone(r2)
    self.assertEqual(r2.start.line, 1)
    self.assertEqual(r2.start.character, 3)
    self.assertEqual(r2.end.character, 8)

  def test_locate_in_ast_cache_identity_and_name_fallback(self):
    """Verifies _locate_in_ast_cache across enum/struct/impl members and name fallback."""
    from types import SimpleNamespace

    from src.parser.ast import (
      BasicTypeNode,
      BlockNode,
      EnumDeclNode,
      EnumMemberNode,
      FuncDeclNode,
      ImplBlockNode,
      ImplMemberNode,
      ProgramNode,
      StructDeclNode,
      StructFieldNode,
    )

    enum_mem = EnumMemberNode("Active", None)
    enum_mem.name_line = 2
    enum_mem.name_column = 2
    enum_mem.name_length = 6
    enum_decl = EnumDeclNode("Status", [enum_mem])

    field_decl = StructFieldNode(True, "hp", BasicTypeNode("int"), None)
    field_decl.name_line = 5
    field_decl.name_column = 4
    field_decl.name_length = 2
    struct_decl = StructDeclNode("Hero", fields=[field_decl])

    method_fn = FuncDeclNode("heal", [], [], BlockNode([]))
    method_fn.name_line = 9
    method_fn.name_column = 7
    method_fn.name_length = 4
    impl_decl = ImplBlockNode("Hero", None, [ImplMemberNode(None, method_fn)])

    prog = ProgramNode([enum_decl, struct_decl, impl_decl])
    uri = "file:///cache_loc.sp"
    prog.file_uri = uri
    mock_ls = SimpleNamespace(ast_cache={uri: prog})

    # Pass 1: exact identity on enum member and struct field
    res_enum = DefinitionProvider._locate_in_ast_cache(mock_ls, enum_mem)
    self.assertIsNotNone(res_enum)
    self.assertEqual(res_enum[0], uri)
    self.assertEqual(res_enum[1].start.line, 1)

    res_field = DefinitionProvider._locate_in_ast_cache(mock_ls, field_decl)
    self.assertIsNotNone(res_field)
    self.assertEqual(res_field[1].start.line, 4)

    # Pass 2: name fallback with a distinct EnumMemberNode / StructFieldNode instance
    enum_copy = EnumMemberNode("Active", None)
    res_copy = DefinitionProvider._locate_in_ast_cache(mock_ls, enum_copy)
    self.assertIsNotNone(res_copy)
    self.assertEqual(res_copy[1].start.line, 1)

    field_copy = StructFieldNode(True, "hp", BasicTypeNode("int"), None)
    res_fcopy = DefinitionProvider._locate_in_ast_cache(mock_ls, field_copy)
    self.assertIsNotNone(res_fcopy)
    self.assertEqual(res_fcopy[1].start.line, 4)

    # Unnamed target returns None
    self.assertIsNone(
        DefinitionProvider._locate_in_ast_cache(mock_ls, SimpleNamespace())
    )


if __name__ == "__main__":
  unittest.main()
