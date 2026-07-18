#!/usr/bin/env python3
"""Generates or updates the TextMate grammar for Sapphire in VS Code.

This script parses the ANTLR grammar specification (grammar/Sapphire.g4) to extract
lexer keywords, literals, and types, keeping the VS Code editor syntax highlighting
in sync with the official language grammar rules.
"""

import json
import os
import re

# Paths relative to the project root
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
GRAMMAR_FILE = os.path.join(ROOT_DIR, "grammar", "Sapphire.g4")
OUTPUT_DIR = os.path.join(ROOT_DIR, "tools", "vscode-extension", "syntaxes")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "sapphire.tmLanguage.json")


def parse_antlr_grammar():
  """Parses Sapphire.g4 to find keyword and literal mappings."""
  if not os.path.exists(GRAMMAR_FILE):
    raise FileNotFoundError(f"ANTLR grammar file not found at: {GRAMMAR_FILE}")

  with open(GRAMMAR_FILE, "r", encoding="utf-8") as f:
    content = f.read()

  # Regular expressions to find keyword lexer rules
  # e.g., STRUCT : 'struct';
  rule_pattern = re.compile(r"^([A-Z_]+)\s*:\s*'([^']+)'\s*;", re.MULTILINE)
  matches = rule_pattern.findall(content)

  keywords = []
  types = ["void"]  # 'void' might not be in lexer rules but standard in types
  constants = []

  control_words = {"if", "else", "while", "for", "in", "return", "clone"}
  modifier_words = {"static", "const", "proto", "struct", "impl", "trait", "func", "let", "var"}

  for name, val in matches:
    if val.isalnum():
      if val in control_words:
        keywords.append(val)
      elif val in modifier_words:
        # These are also added as keywords in VS Code scope but under storage category
        pass
      elif val in {"int", "float", "bool", "string", "none"}:
        if val == "none":
          constants.append(val)
        else:
          types.append(val)
      elif val in {"true", "false", "self"}:
        constants.append(val)

  return {
      "control": sorted(list(control_words)),
      "modifiers": sorted(list(modifier_words)),
      "types": sorted(types),
      "constants": sorted(constants),
  }


def main():
  print("Parsing ANTLR grammar specification...")
  data = parse_antlr_grammar()

  # Define TextMate JSON structure
  tm_grammar = {
      "$schema": "https://raw.githubusercontent.com/martinring/tmlanguage/master/tmlanguage.json",
      "name": "Sapphire",
      "patterns": [
          {"include": "#comments"},
          {"include": "#strings"},
          {"include": "#numbers"},
          {"include": "#keywords"},
          {"include": "#types"},
          {"include": "#identifiers"}
      ],
      "repository": {
          "comments": {
              "patterns": [
                  {
                      "name": "comment.line.double-slash.sapphire",
                      "match": "//.*$"
                  },
                  {
                      "name": "comment.block.sapphire",
                      "begin": "/\\*",
                      "end": "\\*/"
                  }
              ]
          },
          "strings": {
              "patterns": [
                  {
                      "name": "string.quoted.double.sapphire",
                      "begin": "\"",
                      "end": "\"",
                      "patterns": [
                          {
                              "name": "constant.character.escape.sapphire",
                              "match": "\\\\."
                          }
                      ]
                  }
              ]
          },
          "numbers": {
              "patterns": [
                  {
                      "name": "constant.numeric.float.sapphire",
                      "match": "\\b[0-9]+\\.[0-9]+\\b"
                  },
                  {
                      "name": "constant.numeric.integer.sapphire",
                      "match": "\\b[0-9]+\\b"
                  }
              ]
          },
          "keywords": {
              "patterns": [
                  {
                      "name": "keyword.control.sapphire",
                      "match": f"\\b({'|'.join(data['control'])})\\b"
                  },
                  {
                      "name": "storage.modifier.sapphire",
                      "match": f"\\b({'|'.join(data['modifiers'])})\\b"
                  },
                  {
                      "name": "constant.language.sapphire",
                      "match": f"\\b({'|'.join(data['constants'])})\\b"
                  }
              ]
          },
          "types": {
              "patterns": [
                  {
                      "name": "support.type.primitive.sapphire",
                      "match": f"\\b({'|'.join(data['types'])})\\b"
                  }
              ]
          },
          "identifiers": {
              "patterns": [
                  {
                      "name": "variable.other.sapphire",
                      "match": "\\b[a-zA-Z_][a-zA-Z0-9_]*\\b"
                  }
              ]
          }
      },
      "scopeName": "source.sp"
  }

  os.makedirs(OUTPUT_DIR, exist_ok=True)
  with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    json.dump(tm_grammar, f, indent=2)

  print(f"TextMate grammar successfully written to: {OUTPUT_FILE}")


if __name__ == "__main__":  # pragma: no cover
  main()
