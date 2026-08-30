"""Script for generating Highlight.js grammar & updating head_custom.html."""

import argparse
import json
import re
from pathlib import Path


def extract_grammar_tokens(grammar_text: str) -> dict[str, list[str]]:
  """Extracts categorized keywords and tokens from ANTLR4 lexer rules."""

  rules = re.findall(r"^([A-Z0-9_]+)\s*:\s*'([^']+)'\s*;", grammar_text,
                     flags=re.MULTILINE)

  categories = {
      "keyword": [],
      "type": [],
      "literal": [],
      "built_in": []
  }

  for rule_name, rule_val in rules:
    if rule_name.endswith("_TYPE"):
      categories["type"].append(rule_val)
    elif rule_name in {"TRUE", "FALSE", "NONE", "SELF"}:
      categories["literal"].append(rule_val)
    elif rule_name in {"INIT", "PROTO"}:
      categories["built_in"].append(rule_val)
    elif rule_val.isalpha() or rule_val.startswith("__"):
      categories["keyword"].append(rule_val)

  return categories


def generate_head_custom_html(grammar_path: Path, theme: str = "github") -> str:
  """Generates head_custom.html with Highlight.js & Sapphire grammar."""

  content = grammar_path.read_text(encoding="utf-8")
  tokens = extract_grammar_tokens(content)

  keywords_json = json.dumps(tokens, indent=4)

  return f"""<!-- Auto-generated from {grammar_path.name} by tools/gen_highlightjs.py -->
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/{theme}.min.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"></script>
<script>
  hljs.registerLanguage('sapphire', function(hljs) {{
    const KEYWORDS = {keywords_json};

    const ANNOTATION = {{
      className: 'meta',
      begin: /@[a-zA-Z_][a-zA-Z0-9_]*/
    }};

    const INTERPOLATED_STRING = {{
      className: 'string',
      begin: /f"/,
      end: /"/,
      illegal: /\\n/,
      contains: [
        hljs.BACKSLASH_ESCAPE,
        {{
          className: 'subst',
          begin: /\\{{/,
          end: /\\}}/,
          keywords: KEYWORDS
        }}
      ]
    }};

    return {{
      name: 'Sapphire',
      aliases: ['sapphire'],
      keywords: KEYWORDS,
      contains: [
        hljs.C_LINE_COMMENT_MODE,
        hljs.C_BLOCK_COMMENT_MODE,
        hljs.C_NUMBER_MODE,
        hljs.QUOTE_STRING_MODE,
        INTERPOLATED_STRING,
        ANNOTATION,
        {{
          className: 'function',
          beginKeywords: 'func',
          end: /[{{;]/,
          excludeEnd: true,
          contains: [
            hljs.inherit(hljs.TITLE_MODE, {{ begin: /[a-zA-Z_][a-zA-Z0-9_]*/ }}),
            {{
              className: 'params',
              begin: /\\(/,
              end: /\\)/,
              keywords: KEYWORDS,
              contains: [
                hljs.C_LINE_COMMENT_MODE,
                hljs.C_BLOCK_COMMENT_MODE
              ]
            }}
          ]
        }},
        {{
          className: 'class',
          beginKeywords: 'struct trait enum impl proto',
          end: /[{{;]/,
          excludeEnd: true,
          contains: [hljs.TITLE_MODE]
        }}
      ]
    }};
  }});

  document.addEventListener('DOMContentLoaded', () => {{
    // Select code blocks inside Kramdown's language-sapphire containers.
    const targets = document.querySelectorAll(
      '.language-sapphire code, pre code.language-sapphire'
    );
    targets.forEach((el) => {{
      hljs.highlightElement(el);
    }});
  }});
</script>
"""


def main():
  parser = argparse.ArgumentParser(
      description=("Generate head_custom.html with Highlight.js grammar from "
                   "ANTLR4 file."))

  parser.add_argument(
      "--grammar",
      type=Path,
      default=Path("grammar/Sapphire.g4"),
      help="Path to Sapphire.g4 (default: grammar/Sapphire.g4)")
  parser.add_argument(
      "--output",
      type=Path,
      default=Path("_includes/head_custom.html"),
      help="Output HTML file path (default: _includes/head_custom.html)")
  parser.add_argument(
      "--theme",
      type=str,
      default="github",
      help="Highlight.js theme name from CDN (default: github)")

  args = parser.parse_args()

  if not args.grammar.exists():
    raise FileNotFoundError(f"Grammar file not found at {args.grammar}")

  html_content = generate_head_custom_html(args.grammar, theme=args.theme)

  # Ensure parent directory exists
  args.output.parent.mkdir(parents=True, exist_ok=True)
  args.output.write_text(html_content, encoding="utf-8")

  print(f"Successfully generated {args.output} from {args.grammar}")


if __name__ == "__main__":
    main()
