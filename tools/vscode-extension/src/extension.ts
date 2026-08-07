import * as vscode from 'vscode';
import {
  LanguageClient,
  LanguageClientOptions,
  ServerOptions,
  Executable
} from 'vscode-languageclient/node';

let client: LanguageClient;

export function activate(context: vscode.ExtensionContext) {
  const config = vscode.workspace.getConfiguration('sapphire');
  const lspPath = config.get<string>('lsp.path', 'sapphire');

  const workspaceFolders = vscode.workspace.workspaceFolders;
  if (!workspaceFolders) {
    vscode.window.showErrorMessage('Sapphire LSP requires an open workspace.');
    return;
  }

  const workspaceRoot = workspaceFolders[0].uri.fsPath;

  // Setup options for executing the Sapphire LSP CLI server
  const executable: Executable = {
    command: lspPath,
    args: ['lsp'],
    options: { cwd: workspaceRoot }
  };

  const serverOptions: ServerOptions = {
    run: executable,
    debug: executable
  };

  // Configure options for the language client
  const clientOptions: LanguageClientOptions = {
    documentSelector: [{ scheme: 'file', language: 'sapphire' }],
    synchronize: {
      // Synchronize the setting section 'sapphire' to the server
      fileEvents: vscode.workspace.createFileSystemWatcher('**/*.sp')
    }
  };

  // Create and start the Language Client
  client = new LanguageClient(
    'sapphireLanguageServer',
    'Sapphire Language Server',
    serverOptions,
    clientOptions
  );

  client.start().catch((error: any) => {
    const msg = error.message || String(error);
    vscode.window.showErrorMessage(
      `Failed to start Sapphire Language Server ('${lspPath} lsp'): ${msg}. Please ensure '${lspPath}' is installed on your system PATH or configure 'sapphire.lsp.path' in VS Code settings.`
    );
  });

  console.log('Sapphire Language Support extension is now active!');
}

export function deactivate(): Thenable<void> | undefined {
  if (!client) {
    return undefined;
  }
  return client.stop();
}
