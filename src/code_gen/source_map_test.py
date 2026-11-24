"""Unit tests for Source Map generation and Base64 VLQ encoding."""

import json
import unittest

from src.code_gen.source_map import SourceMapBuilder, encode_vlq


class TestSourceMap(unittest.TestCase):

  def test_encode_vlq(self):
    """Tests Base64 VLQ encoding against standard specification examples."""
    # 0 -> 'A'
    self.assertEqual(encode_vlq(0), "A")
    # 1 -> 'C'
    self.assertEqual(encode_vlq(1), "C")
    # -1 -> 'D'
    self.assertEqual(encode_vlq(-1), "D")
    # 16 -> 'gB'
    self.assertEqual(encode_vlq(16), "gB")

  def test_source_map_builder_v3_json(self):
    """Tests generating a standard V3 Source Map JSON structure."""
    source_code = "let x = 10;\nlet y = 20;\nlet z = x + y;"
    builder = SourceMapBuilder("test.sp", source_code)

    builder.add_mapping(
        gen_line=1, gen_col=0, source_file="test.sp", orig_line=1, orig_col=0
    )
    builder.add_mapping(
        gen_line=2, gen_col=0, source_file="test.sp", orig_line=2, orig_col=0
    )
    builder.add_mapping(
        gen_line=3, gen_col=0, source_file="test.sp", orig_line=3, orig_col=0
    )

    v3_json_str = builder.to_v3_json("test.lua")
    v3_dict = json.loads(v3_json_str)

    self.assertEqual(v3_dict["version"], 3)
    self.assertEqual(v3_dict["file"], "test.lua")
    self.assertEqual(v3_dict["sources"], ["test.sp"])
    self.assertEqual(v3_dict["sourcesContent"], [source_code])
    self.assertTrue(isinstance(v3_dict["mappings"], str))

  def test_to_lua_line_map_table(self):
    """Tests generating the Lua inline lookup table with code snippets."""
    source_code = "let x = 10;\nlet y = 20;\nlet z = x + y;"
    builder = SourceMapBuilder("main.sp", source_code)

    builder.add_mapping(
        gen_line=10, gen_col=0, source_file="main.sp", orig_line=1, orig_col=0
    )
    builder.add_mapping(
        gen_line=11, gen_col=0, source_file="main.sp", orig_line=2, orig_col=0
    )

    lua_table = builder.to_lua_line_map_table()
    self.assertIn('_SP_LINE_MAP = {', lua_table)
    self.assertIn('[10] = { file = "main.sp", line = 1, col = 0, text = "let x = 10;" }', lua_table)
    self.assertIn('[11] = { file = "main.sp", line = 2, col = 0, text = "let y = 20;" }', lua_table)

  def test_symbol_name_mapping(self):
    """Tests mappings containing symbol names."""
    builder = SourceMapBuilder("main.sp", "func foo() {}")
    builder.add_mapping(
        gen_line=1, gen_col=0, source_file="main.sp", orig_line=1, orig_col=0, symbol_name="foo"
    )
    v3_dict = builder.to_v3_dict("main.lua")
    self.assertEqual(v3_dict["names"], ["foo"])
    self.assertTrue(len(v3_dict["mappings"]) > 0)

  def test_add_source_and_content(self):
    """Tests adding additional source files and contents dynamically."""
    builder = SourceMapBuilder("main.sp", "let x = 1;")
    idx = builder.add_source("helper.sp", "let y = 2;")
    self.assertEqual(idx, 1)
    self.assertEqual(builder.sources, ["main.sp", "helper.sp"])
    self.assertEqual(builder.sources_content["helper.sp"], "let y = 2;")

  def test_non_positive_gen_line_ignored_and_missing_content_is_none(self):
    """Verifies gen_line <= 0 does not corrupt VLQ lines and missing content emits None."""
    builder = SourceMapBuilder("main.sp")
    builder.add_mapping(
        gen_line=0, gen_col=0, source_file="main.sp", orig_line=1, orig_col=0
    )
    builder.add_mapping(
        gen_line=-3, gen_col=0, source_file="main.sp", orig_line=1, orig_col=0
    )
    builder.add_mapping(
        gen_line=2, gen_col=0, source_file="main.sp", orig_line=1, orig_col=0
    )
    v3_dict = builder.to_v3_dict("main.lua")
    self.assertEqual(v3_dict["sourcesContent"], [None])
    # Line 1 has no mappings, line 2 has one mapping => starts with ';'
    self.assertTrue(v3_dict["mappings"].startswith(";"))
    self.assertEqual(v3_dict["mappings"].count(";"), 1)


if __name__ == "__main__":
  unittest.main()
