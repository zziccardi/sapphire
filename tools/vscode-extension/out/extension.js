import * as vscode from 'vscode';
import { LanguageClient } from 'vscode-languageclient/node';
let client;
export function activate(context) {
    const config = vscode.workspace.getConfiguration('sapphire');
    const lspPath = config.get('lsp.path', 'sapphire');
    const workspaceFolders = vscode.workspace.workspaceFolders;
    if (!workspaceFolders) {
        vscode.window.showErrorMessage('Sapphire LSP requires an open workspace.');
        return;
    }
    const workspaceRoot = workspaceFolders[0].uri.fsPath;
    // Setup options for executing the Sapphire LSP CLI server
    const executable = {
        command: lspPath,
        args: ['lsp'],
        options: { cwd: workspaceRoot }
    };
    const serverOptions = {
        run: executable,
        debug: executable
    };
    // Configure options for the language client
    const clientOptions = {
        documentSelector: [{ scheme: 'file', language: 'sapphire' }],
        synchronize: {
            // Synchronize the setting section 'sapphire' to the server
            fileEvents: vscode.workspace.createFileSystemWatcher('**/*.sp')
        }
    };
    // Create and start the Language Client
    client = new LanguageClient('sapphireLanguageServer', 'Sapphire Language Server', serverOptions, clientOptions);
    client.start().catch((error) => {
        vscode.window.showErrorMessage(`Failed to start Sapphire Language Server: ${error.message || error}`);
    });
    console.log('Sapphire Language Support extension is now active!');
}
export function deactivate() {
    if (!client) {
        return undefined;
    }
    return client.stop();
}
//# sourceMappingURL=extension.js.map