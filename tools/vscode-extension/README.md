# Sapphire VS Code extension

This directory contains the Visual Studio Code extension client for the **Sapphire** programming language. It interfaces with the Sapphire language server to provide rich, editor-level IDE support.

## Features

- **Semantic highlighting**: High-accuracy semantic coloring provided by the compiler frontend (resolving struct definitions, trait names, function calls, methods, parameters, and variable mutability/scopes).
- **Hover support**: Hovering over variables, fields, methods, or parameters displays their declared type signature and category in a detailed Markdown format.
- **Member auto-completion (dot trigger)**: Auto-suggests available fields and methods of a struct when typing a dot `.` on a struct instance.
- **Syntax highlighting**: Fast regex-based fallback coloring for structural keywords, types, strings, comments, and numbers.
- **Diagnostics**: Real-time syntax and type-checking error reporting.
- **Structural configuration**: Bracket matching and auto-closing pairs for parentheses, braces, brackets, and quotes.

## Directory structure

- `src/extension.ts`: Client code that launches the background Python LSP process and connects it to VS Code.
- `syntaxes/sapphire.tmLanguage.json`: Static TextMate syntax highlighter (generated from `grammar/Sapphire.g4`).
- `scripts/generate_grammar.py`: Python tool to rebuild the TextMate grammar file automatically when the compiler's ANTLR-based grammar changes.
- `language-configuration.json`: Language behavior rules (brackets, comments).
- `package.json`: Extension settings, requirements, and configurations.

## Development & testing

### 1. Requirements
Ensure you have the following installed in your development environment:
- Node.js (v14.15+) and `npm`
- Python 3.14+ (with `pygls` installed in the Sapphire workspace virtualenv)

### 2. Compile the Extension
From this directory (`tools/vscode-extension`), run:

```bash
npm install
npm run compile
```

### 3. Launching in debug mode
1. Open this directory (`tools/vscode-extension`) in VS Code.
2. Go to **Run and Debug** in the sidebar and select **Launch Extension**.
3. A new **Extension Development Host** window will open.
4. Open any Sapphire file (`.sp`) in this host window to test highlighting and compiler diagnostics.

## Packaging & installing locally

To install the extension permanently in your local VS Code instance:

1. **Package the extension** into a `.vsix` file:

   ```bash
   npx @vscode/vsce package
   ```

   This compiles the files and creates `sapphire-0.1.0.vsix` in this directory.

2. **Install the package**:
   * **Via CLI**:

     ```bash
     code --install-extension sapphire-0.1.0.vsix
     ```

   * **Via VS Code GUI**: Open the Command Palette (`Cmd+Shift+P`), select `Extensions: Install from VSIX...`, and choose the generated `.vsix` file.

## Extension settings

You can customize the extension behavior in your user or workspace settings (`settings.json`):

* `sapphire.lsp.pythonPath` (Default: `"pipenv"`): The path or command to run Python (e.g. `"python3"` or `"pipenv"`). If set to `"pipenv"`, it automatically boots using the project virtualenv.
* `sapphire.lsp.serverPath` (Default: `"src/lsp/server.py"`): The relative path to the Python Language Server file within the workspace.
