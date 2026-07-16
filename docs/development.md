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

This will create SapphireLexer.py, SapphireParser.py, SapphireListener.py, and
SapphireVisitor.py in the workspace.

## Compilation & execution

To compile a Sapphire source file to Python (e.g. `sample.sp` to `sample.py`):

```bash
pipenv run python src/run_transpiler.py sample.sp
```

To execute the transpiled Python file:

```bash
pipenv run python sample.py
```

To run the full semantics demo of the transpiled file:

```bash
pipenv run python -c "import sample; sample.run_demo()"
```

## Test coverage

Run the following to execute all unit tests under `src/` & track code coverage:

```bash
pipenv run coverage
```

Note that this requires each directory to include an `__init__.py` file.

This will also create an HTML version of the coverage report.
