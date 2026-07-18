# Sapphire language server

This directory contains the Python-based Language Server Protocol (LSP) server implementation for the Sapphire programming language.

## Architecture

The Sapphire LSP server is built on top of the `pygls` library and runs as a background process communicating with the VS Code extension over standard input/output (`stdio`).

```
 +------------------+                +------------------------------+
 |                  |     stdio      |                              |
 |  VS Code Client  | <============> |  Sapphire LSP Server         |
 |                  |     (LSP)      |  (pygls background process)  |
 +------------------+                +------------------------------+
                                                  |
                                                  v
                                     +-------------------------+
                                     |  Compiler Frontend      |
                                     |  (ANTLR -> AST -> Sema) |
                                     +-------------------------+
```

It leverages the compiler's lexer, parser, and `TypeChecker` to inspect document changes in real time, serving the following primary features:
1. **Diagnostics**: Real-time syntax and semantic validation. Whenever a file is opened, edited, or saved, the compiler frontend checks the source code. Errors are mapped to editor locations and pushed back to the client as diagnostics.
2. **Semantic tokens**: Rich syntax highlighting. An AST-walking semantic subclass of `TypeChecker` maps identifiers and definitions to semantic types (e.g. `struct`, `interface`, `parameter`, `variable`, `function`, `method`, `property`) and modifier states (e.g. `declaration`, `static`, `readonly`), delta-encoding them for the editor.
3. **Hover**: Displays type signatures, parameter scopes, and declaration kind metadata when hovering over variables, functions, structs, fields, parameters, or traits.
4. **Member auto-completion**: Auto-suggests fields and methods of a struct when the user types a dot `.` on a variable or inside `self` methods.

## Requirements

- Python 3.14+
- `pygls` package (installed via Pipfile)

## Files

- [server.py](src/lsp/server.py): The main LSP server entrypoint that runs the server on `stdio` and manages the event hooks.
- [semantic_tokens.py](src/lsp/semantic_tokens.py): Implements position tracking and LSP relative delta-encoding for Sapphire symbols.
- [semantic_tokens_test.py](src/lsp/semantic_tokens_test.py): Unit tests for token generation and relative offset calculations.

## Diagnostics

To ensure a smooth editor experience, when a syntax error is introduced temporarily during active typing:
- The server will report the syntax error diagnostics immediately.
- The server caches the last successfully resolved semantic token highlights and keeps displaying them, preventing the entire editor's syntax coloring from flashing or collapsing.
