import * as path from 'path';
import * as vscode from 'vscode';
import {
  LanguageClient,
  LanguageClientOptions,
  ServerOptions,
  TransportKind
} from 'vscode-languageclient/node';

let client: LanguageClient;

export function activate(context: vscode.ExtensionContext) {
  const config = vscode.workspace.getConfiguration('sapphire');
  const pythonPath = config.get<string>('lsp.pythonPath', 'pipenv');
  const serverRelativePath = config.get<string>('lsp.serverPath', 'src/lsp/server.py');

  const workspaceFolders = vscode.workspace.workspaceFolders;
  if (!workspaceFolders) {
    vscode.window.showErrorMessage('Sapphire LSP requires an open workspace.');
    return;
  }

  const workspaceRoot = workspaceFolders[0].uri.fsPath;
  const serverPath = path.isAbsolute(serverRelativePath)
    ? serverRelativePath
    : path.join(workspaceRoot, serverRelativePath);

  // Setup options for executing the Python background server
  let serverOptions: ServerOptions;

  if (pythonPath === 'pipenv') {
    serverOptions = {
      command: 'pipenv',
      args: ['run', 'python', serverPath],
      options: { cwd: workspaceRoot }
    };
  } else {
    serverOptions = {
      command: pythonPath,
      args: [serverPath],
      options: { cwd: workspaceRoot }
    };
  }

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

  client.start().catch(error => {
    vscode.window.showErrorMessage(
      `Failed to start Sapphire Language Server: ${error.message || error}`
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
