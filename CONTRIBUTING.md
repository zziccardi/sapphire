# Contributing to Sapphire

Thank you for your interest in contributing to Sapphire! For detailed
environment setup and compiler architecture notes, see
[docs/development.md](docs/development.md) and
[docs/compiler.md](docs/compiler.md).

## Getting started

1. Fork and clone the repository.
2. Install Python dependencies (Python 3.10+ and `pipenv`):

```bash
pipenv install --dev
```

3. Verify your environment by running the unit and native test suites:

```bash
pipenv run test
pipenv run sapphire test
pipenv run sapphire test -t lua
```

## Making changes

* **Grammar edits**: If you modify `grammar/Sapphire.g4`, regenerate the
  committed ANTLR4 parser files before committing:
  ```bash
  pipenv run antlr
  ```
* **Syntax highlighting**: If you add keywords or change tokens, regenerate the
  TextMate grammar:
  ```bash
  python3 tools/vscode-extension/scripts/generate_grammar.py
  ```
* **Language semantics**: Update [docs/SPEC.md](docs/SPEC.md) (and
  [docs/builtins.md](docs/builtins.md) or [docs/stdlib.md](docs/stdlib.md) when
  relevant) whenever language behavior changes.
* **Markdown style**: Keep lines at or under 80 characters (except URLs), use
  sentence case for headings, and avoid horizontal rules.
* **Sapphire style**: Follow [docs/style_guide.md](docs/style_guide.md) (2-space
  indentation, max 80-character lines, explicit semicolons).

## Pre-PR checklist

Run these checks locally before opening a pull request:

```bash
pipenv run lint
pipenv run test          # or `pipenv run test-fast` for parallel local runs
pipenv run coverage      # statement + branch coverage gate
pipenv run coverage-lua  # Lua 5.1 stdlib coverage report
pipenv run sapphire test
pipenv run sapphire test -t lua
pipenv run check-samples
```

If you modified the VS Code extension (`tools/vscode-extension/`) or website
(`web/`), also run `npm test` (and `npm run build` for `web/`) in that
directory.
