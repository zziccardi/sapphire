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
antlr -Dlanguage=Python3 -visitor -o src/parser/gen -Xexact-output-dir \
    grammar/Sapphire.g4
```

This will create `SapphireLexer.py`, `SapphireParser.py`, `SapphireListener.py`,
and `SapphireVisitor.py` in the workspace.

## Compilation & execution

The `sapphire` CLI tool provides convenient commands for compiling and executing Sapphire programs.

To compile and immediately run a Sapphire source file in one step:

```bash
pipenv run sapphire samples/overview.sp
```

To compile a Sapphire source file to Python without running it:

```bash
pipenv run sapphire build samples/overview.sp [-o custom_output.py]
```

Note: You can also call the low-level transpiler script directly via:

```bash
pipenv run python src/run_transpiler.py samples/overview.sp
```

## Test coverage

Run the following to execute all unit tests under `src/` & track code coverage:

```bash
pipenv run coverage
```

Note that this requires each directory to include an `__init__.py` file.

This will also create an HTML version of the coverage report.
