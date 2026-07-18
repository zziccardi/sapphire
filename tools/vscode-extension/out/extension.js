"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.activate = activate;
exports.deactivate = deactivate;
const path = __importStar(require("path"));
const vscode = __importStar(require("vscode"));
const node_1 = require("vscode-languageclient/node");
let client;
function activate(context) {
    const config = vscode.workspace.getConfiguration('sapphire');
    const pythonPath = config.get('lsp.pythonPath', 'pipenv');
    const serverRelativePath = config.get('lsp.serverPath', 'src/lsp/server.py');
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
    let serverOptions;
    if (pythonPath === 'pipenv') {
        serverOptions = {
            command: 'pipenv',
            args: ['run', 'python', serverPath],
            options: { cwd: workspaceRoot }
        };
    }
    else {
        serverOptions = {
            command: pythonPath,
            args: [serverPath],
            options: { cwd: workspaceRoot }
        };
    }
    // Configure options for the language client
    const clientOptions = {
        documentSelector: [{ scheme: 'file', language: 'sapphire' }],
        synchronize: {
            // Synchronize the setting section 'sapphire' to the server
            fileEvents: vscode.workspace.createFileSystemWatcher('**/*.sp')
        }
    };
    // Create and start the Language Client
    client = new node_1.LanguageClient('sapphireLanguageServer', 'Sapphire Language Server', serverOptions, clientOptions);
    client.start().catch(error => {
        vscode.window.showErrorMessage(`Failed to start Sapphire Language Server: ${error.message || error}`);
    });
    console.log('Sapphire Language Support extension is now active!');
}
function deactivate() {
    if (!client) {
        return undefined;
    }
    return client.stop();
}
//# sourceMappingURL=extension.js.map