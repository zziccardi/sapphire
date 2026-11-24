import * as vscode from 'vscode';
import {
  LanguageClient,
  LanguageClientOptions,
  ServerOptions,
  Executable
} from 'vscode-languageclient/node';

let client: LanguageClient | undefined;

export function activate(context: vscode.ExtensionContext) {
  const config = vscode.workspace.getConfiguration('sapphire');
  const lspPath = config.get<string>('lsp.path', 'sapphire');

  const workspaceFolders = vscode.workspace.workspaceFolders;
  if (!workspaceFolders || workspaceFolders.length === 0) {
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

  const watcher = vscode.workspace.createFileSystemWatcher('**/*.sp');
  if (context && Array.isArray(context.subscriptions)) {
    context.subscriptions.push(watcher);
  }

  // Configure options for the language client
  const clientOptions: LanguageClientOptions = {
    documentSelector: [{ scheme: 'file', language: 'sapphire' }],
    synchronize: {
      // Synchronize the setting section 'sapphire' to the server
      fileEvents: watcher
    }
  };

  // Create and start the Language Client
  client = new LanguageClient(
    'sapphireLanguageServer',
    'Sapphire Language Server',
    serverOptions,
    clientOptions
  );

  const outputChannel = vscode.window.createOutputChannel(
    'Sapphire Language Server'
  );
  if (context && Array.isArray(context.subscriptions)) {
    context.subscriptions.push(outputChannel);
  }

  client.start().catch((error: unknown) => {
    const msg = error instanceof Error ? error.message : String(error);
    vscode.window.showErrorMessage(
      `Failed to start Sapphire Language Server ('${lspPath} lsp'): ${msg}. Please ensure '${lspPath}' is installed on your system PATH or configure 'sapphire.lsp.path' in VS Code settings.`
    );
  });

  outputChannel.appendLine(
    'Sapphire Language Support extension is now active!'
  );
}

export function deactivate(): Thenable<void> | undefined {
  if (!client) {
    return undefined;
  }
  const activeClient = client;
  client = undefined;
  return activeClient.stop();
}
