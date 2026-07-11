# Instructions

To use ANTLR to generate Python parser files for the grammar, run the following
from the project root:

```
antlr -Dlanguage=Python3 -visitor -o src/parser/gen -Xexact-output-dir \
    grammar/Sapphire.g4
```

This will create SapphireLexer.py, SapphireParser.py, SapphireListener.py, and
SapphireVisitor.py in the workspace.

From there, create a Python runner script that loads the Sapphire source code,
hooks up custom error listeners, and parses the program.

For a script called e.g. `run_parser.py`:

```
pipenv run python src/run_parser.py
```
