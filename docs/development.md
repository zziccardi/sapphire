# Development

## Prerequisites

Make sure you have [Pipenv](https://pipenv.pypa.io/) installed. Install
dependencies by running:

```bash
pipenv install
```

## ANTLR

To use ANTLR to generate Python parser files for the grammar, run the following
from the project root:

```bash
pipenv run antlr
```

Which executes:

```bash
antlr -Dlanguage=Python3 -visitor -o src/parser/gen -Xexact-output-dir \
    grammar/Sapphire.g4
```

This will create `SapphireLexer.py`, `SapphireParser.py`, `SapphireListener.py`,
and `SapphireVisitor.py` in `src/parser/gen/`. These generated files are
tracked in Git and verified to be in sync with `grammar/Sapphire.g4` by CI.

## Installing the CLI as a package

You can install the `sapphire` CLI directly into your Python environment so it
can be executed from anywhere without prefixing `pipenv run`:

### Option A: Editable installation via Pipenv virtual environment

Inside `pipenv shell` (or with an active virtualenv):

```bash
pip install -e .
```

After installation, invoke the command directly:

```bash
sapphire run samples/overview.sp
sapphire build samples/overview.sp
```

### Option B: System-wide global CLI via pipx

To install `sapphire` as a global executable isolated from system Python:

```bash
pipx install -e .

# Now executable anywhere in your terminal:
sapphire samples/overview.sp
```

## Compilation and execution

The `sapphire` CLI tool provides convenient commands for compiling and
executing Sapphire programs across supported targets (`python`, `lua`).

To compile and immediately run a Sapphire source file in one step (Python by
default, or Lua 5.1 via `-t lua`):

```bash
# Python target (default)
sapphire samples/overview.sp

# Lua 5.1 target (requires lua, luajit, or lua5.1 in PATH)
sapphire samples/overview.sp -t lua

# Or via Pipenv:
pipenv run sapphire samples/overview.sp -t lua
```

To transpile a Sapphire source file to Python (`.py`) or Lua (`.lua`) without
running it:

```bash
# Transpile to Python (.py)
sapphire build samples/overview.sp [-o custom_output.py]

# Transpile to Lua 5.1 (.lua)
sapphire build samples/overview.sp -t lua [-o custom_output.lua]
```

Note: The high-level compilation driver function `transpile_file()` is
exported by `src/code_gen/transpiler.py`. Additional CLI inspection
commands include:

```bash
# Parse source and print concrete parse tree
pipenv run sapphire parse samples/overview.sp

# Parse source and dump AST in JSON format
pipenv run sapphire dump-ast samples/overview.sp

# Run semantic analysis and type checking without code generation
pipenv run sapphire check samples/overview.sp
```

## Testing and verification

### Running unit and integration tests

Run the following to execute all unit tests under `src/` (which automatically
includes all samples compilation tests):

```bash
pipenv run test
```

### Verifying sample programs compilation

To exclusively verify that all 25+ demo programs in `samples/` compile cleanly
across both Python and Lua 5.1 target backends without writing artifacts to
disk:

```bash
pipenv run check-samples
```

## Test coverage

Run the following to execute all unit tests under `src/` & track code coverage:

```bash
pipenv run coverage
```

Note that this requires each directory to include an `__init__.py` file.

This will also create an HTML version of the coverage report.

## Packaging and distribution

### Building distribution packages

To build the source distribution (`.tar.gz`) and binary wheel (`.whl`) locally:

```bash
pip install build
python -m build
```

This generates distribution artifacts under `dist/`:
* `dist/sapphire_lang-0.1.0-py3-none-any.whl`
* `dist/sapphire_lang-0.1.0.tar.gz`

Both packages bundle all standard library modules (`lib/std/`), Love2D engine
bindings (`lib/love2d/`), and runtime resources.

### Packaging the VS Code extension

The Sapphire VS Code extension resides in `tools/vscode-extension`. To package
it into a `.vsix` archive locally:

```bash
cd tools/vscode-extension
npm ci
npm run compile
npx @vscode/vsce package --no-dependencies
```

This creates `tools/vscode-extension/sapphire-0.1.0.vsix`. Install the extension
into VS Code via:

```bash
code --install-extension tools/vscode-extension/sapphire-0.1.0.vsix
```

## Release workflow

Sapphire uses automated GitHub Actions workflows for continuous integration and
releases.

### Versioning convention

Releases adhere to [semantic versioning](https://semver.org/)
(`vMAJOR.MINOR.PATCH`). When releasing a new version:

1. Update the version string in `pyproject.toml` under `[project] version`.
2. Update the version string in `tools/vscode-extension/package.json`.
3. Commit the version bump:
   ```bash
   git commit -am "chore: bump version to v0.1.0"
   ```
4. Create and push an annotated Git tag:
   ```bash
   git tag -a v0.1.0 -m "Release v0.1.0"
   git push origin v0.1.0
   ```

### Release CI automation

Pushing a `v*` tag triggers `.github/workflows/release.yml`, which:
1. Runs the complete test suite: Python unit tests, coverage verification,
   Sapphire native E2E test suites on both Python and Lua backends, and sample
   compilations.
2. Builds the source distribution and wheel packages via `python -m build`.
3. Compiles and packages the VS Code extension into a `.vsix` archive.
4. Publishes a GitHub Release with auto-generated release notes and attaches the
   `.whl`, `.tar.gz`, and `.vsix` release artifacts.
