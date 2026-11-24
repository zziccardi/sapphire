# Language server

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
5. **Go-to-definition**: Jump directly to variable, function, struct, trait, enum, field, or inheritance declaration locations (`F12` / `Cmd+Click`).
6. **Signature help**: Parameter hints, docstrings, and active parameter tracking when invoking functions, constructors, or methods.
7. **Document symbols & outline**: Hierarchical symbols for VS Code's Outline view, Breadcrumbs, and Go to Symbol in File (`Cmd+Shift+O`). Extracts structs, prototypes, enums, traits, impl blocks, methods, functions, and top-level variables/constants.

## Requirements

- Python 3.12+
- `pygls` package (installed via Pipfile)

## Files

- [server.py](server.py): Main LSP server entrypoint running over `stdio` and wiring LSP request/notification handlers.
- [completion_provider.py](completion_provider.py): Dot-access (`obj.`, `self.`) and scope-level identifier completions.
- [definition_provider.py](definition_provider.py): Go-to-definition resolution across local scopes, structs, traits, enums, and imported modules.
- [hover_provider.py](hover_provider.py): Hover tooltip formatting with type signatures and doc comments.
- [signature_provider.py](signature_provider.py): Call signature help, parameter hints, and active parameter tracking.
- [document_symbols.py](document_symbols.py): Translates AST declarations into hierarchical LSP `DocumentSymbol` trees.
- [semantic_tokens.py](semantic_tokens.py): Implements UTF-16 position tracking and LSP relative delta-encoding for Sapphire symbols.

## Diagnostics

To ensure a smooth editor experience, when a syntax error is introduced temporarily during active typing:
- The server will report the syntax error diagnostics immediately.
- The server caches the last successfully resolved semantic token highlights and keeps displaying them, preventing the entire editor's syntax coloring from flashing or collapsing.

## Development

When making changes to the language server, assuming the VS Code extension is
already installed, you can quickly test them by opening the command palette
(`Cmd+Shift+P`) and selecting `Developer: Reload Window`.

When changing any of the extension's (client-side) files, however, it will be
necessary to repackage and reinstall the `.vsix` file.
