"""Source map builder and V3 JSON generator for Sapphire compiler.

Provides Base64 VLQ encoding and line position mapping for transpiling
Sapphire (.sp) code to target languages (e.g. Lua 5.1).
"""

import json
from typing import Dict, List, Optional, Tuple, Any

# Base64 characters used in V3 Source Maps
BASE64_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"


def encode_vlq(value: int) -> str:
  """Encodes an integer into a Base64 VLQ (Variable-Length Quantity) string.

  Source map V3 specifies Base64 VLQ format for relative offset encoding.
  """
  # Convert sign to least significant bit (sign-magnitude representation)
  if value < 0:
    vlq = ((-value) << 1) | 1
  else:
    vlq = value << 1

  encoded = ""
  while True:
    digit = vlq & 0x1F  # Take 5 bits
    vlq >>= 5
    if vlq > 0:
      digit |= 0x20  # Set continuation bit (bit 6)
    encoded += BASE64_CHARS[digit]
    if vlq == 0:
      break

  return encoded


class MappingEntry:
  """Represents a single position mapping from generated code to original source code."""

  def __init__(
      self,
      gen_line: int,  # 1-indexed
      gen_col: int,   # 0-indexed
      source_file: str,
      orig_line: int, # 1-indexed
      orig_col: int,  # 0-indexed
      symbol_name: Optional[str] = None,
  ):
    self.gen_line = gen_line
    self.gen_col = gen_col
    self.source_file = source_file
    self.orig_line = orig_line
    self.orig_col = orig_col
    self.symbol_name = symbol_name


class SourceMapBuilder:
  """Collects position mappings and generates V3 Source Map JSON and Lua runtime line maps."""

  def __init__(self, source_file: str, source_content: Optional[str] = None):
    self.sources: List[str] = [source_file]
    self.sources_content: Dict[str, str] = {}
    if source_content is not None:
      self.sources_content[source_file] = source_content
    self.names: List[str] = []
    self.mappings: List[MappingEntry] = []

  def add_source(self, source_file: str, source_content: Optional[str] = None) -> int:
    """Ensures a source file is present in sources list and returns its index."""
    if source_file not in self.sources:
      self.sources.append(source_file)
    if source_content is not None:
      self.sources_content[source_file] = source_content
    return self.sources.index(source_file)

  def add_name(self, name: str) -> int:
    """Ensures a symbol name is present in names list and returns its index."""
    if name not in self.names:
      self.names.append(name)
    return self.names.index(name)

  def add_mapping(
      self,
      gen_line: int,
      gen_col: int,
      source_file: str,
      orig_line: int,
      orig_col: int,
      symbol_name: Optional[str] = None,
  ) -> None:
    """Adds a mapping entry from generated position to original source position."""
    self.add_source(source_file)
    if symbol_name:
      self.add_name(symbol_name)
    entry = MappingEntry(
        gen_line=gen_line,
        gen_col=gen_col,
        source_file=source_file,
        orig_line=orig_line,
        orig_col=orig_col,
        symbol_name=symbol_name,
    )
    self.mappings.append(entry)

  def generate_vlq_mappings(self) -> str:
    """Generates the V3 'mappings' string using Base64 VLQ encoding."""
    # Sort mappings by generated line then generated column
    sorted_mappings = sorted(
        self.mappings, key=lambda m: (m.gen_line, m.gen_col)
    )

    lines_mappings: Dict[int, List[MappingEntry]] = {}
    for m in sorted_mappings:
      lines_mappings.setdefault(m.gen_line, []).append(m)

    max_line = max(lines_mappings.keys()) if lines_mappings else 0

    result_lines: List[str] = []

    last_source_idx = 0
    last_orig_line = 0
    last_orig_col = 0
    last_name_idx = 0

    for current_gen_line in range(1, max_line + 1):
      line_entries = lines_mappings.get(current_gen_line, [])
      encoded_entries: List[str] = []
      last_gen_col = 0

      for entry in line_entries:
        source_idx = self.sources.index(entry.source_file)

        # Relative field calculation (V3 delta encoding)
        gen_col_delta = entry.gen_col - last_gen_col
        source_idx_delta = source_idx - last_source_idx
        orig_line_delta = (entry.orig_line - 1) - last_orig_line  # 0-indexed delta
        orig_col_delta = entry.orig_col - last_orig_col

        fields = [
            encode_vlq(gen_col_delta),
            encode_vlq(source_idx_delta),
            encode_vlq(orig_line_delta),
            encode_vlq(orig_col_delta),
        ]

        if entry.symbol_name:
          name_idx = self.names.index(entry.symbol_name)
          name_idx_delta = name_idx - last_name_idx
          fields.append(encode_vlq(name_idx_delta))
          last_name_idx = name_idx

        encoded_entries.append("".join(fields))

        # Update last position trackers
        last_gen_col = entry.gen_col
        last_source_idx = source_idx
        last_orig_line = entry.orig_line - 1
        last_orig_col = entry.orig_col

      result_lines.append(",".join(encoded_entries))

    return ";".join(result_lines)

  def to_v3_dict(self, generated_filename: str) -> Dict[str, Any]:
    """Returns the V3 Source Map as a python dictionary."""
    sources_content_list = [
        self.sources_content.get(src, "") for src in self.sources
    ]
    return {
        "version": 3,
        "file": generated_filename,
        "sources": self.sources,
        "sourcesContent": sources_content_list,
        "names": self.names,
        "mappings": self.generate_vlq_mappings(),
    }

  def to_v3_json(self, generated_filename: str, indent: int = 2) -> str:
    """Returns the V3 Source Map JSON string."""
    return json.dumps(self.to_v3_dict(generated_filename), indent=indent)

  def to_lua_line_map_table(self) -> str:
    """Generates a Lua table string for runtime demangling.

    Example table format:
      _SP_LINE_MAP = {
        [45] = { file = "main.sp", line = 12, col = 0, text = "let x = 10;" },
        ...
      }
    """
    entries: List[str] = []
    # Deduplicate: pick first mapping per generated line
    seen_lines = set()
    sorted_mappings = sorted(
        self.mappings, key=lambda m: (m.gen_line, m.gen_col)
    )

    for m in sorted_mappings:
      if m.gen_line in seen_lines:
        continue
      seen_lines.add(m.gen_line)

      src_code = self.sources_content.get(m.source_file, "")
      src_lines = src_code.splitlines()
      snippet = ""
      if 1 <= m.orig_line <= len(src_lines):
        snippet = src_lines[m.orig_line - 1].strip()

      # Escape quotes/backslashes in Lua string literal
      escaped_file = m.source_file.replace("\\", "\\\\").replace('"', '\\"')
      escaped_text = snippet.replace("\\", "\\\\").replace('"', '\\"')

      entries.append(
          f'  [{m.gen_line}] = {{ file = "{escaped_file}", line = {m.orig_line},'
          f' col = {m.orig_col}, text = "{escaped_text}" }}'
      )

    return "local _SP_LINE_MAP = {\n" + ",\n".join(entries) + "\n}\n"
