"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
const vitest_1 = require("vitest");
// Mock vscode module
let mockWorkspaceFolders = undefined;
let mockConfig = {
    'lsp.pythonPath': 'pipenv',
    'lsp.serverPath': 'src/lsp/server.py'
};
let lastErrorMessage = '';
vitest_1.vi.mock('vscode', () => {
    return {
        workspace: {
            getConfiguration: () => ({
                get: (key, defaultValue) => mockConfig[key] !== undefined ? mockConfig[key] : defaultValue
            }),
            createFileSystemWatcher: () => ({}),
            get workspaceFolders() {
                return mockWorkspaceFolders;
            }
        },
        window: {
            showErrorMessage: (msg) => { lastErrorMessage = msg; }
        }
    };
});
// Mock LanguageClient
let clientInstance = null;
let startCalled = false;
let stopCalled = false;
let startShouldFail = false;
vitest_1.vi.mock('vscode-languageclient/node', () => {
    class MockLanguageClient {
        constructor(id, name, serverOptions, clientOptions) {
            this.id = id;
            this.name = name;
            this.serverOptions = serverOptions;
            this.clientOptions = clientOptions;
            clientInstance = this;
        }
        start() {
            startCalled = true;
            if (startShouldFail) {
                return Promise.reject("Start failed mock");
            }
            return Promise.resolve();
        }
        stop() {
            stopCalled = true;
            return Promise.resolve();
        }
    }
    return {
        LanguageClient: MockLanguageClient
    };
});
// Import the extension code
const extension_1 = require("./extension");
(0, vitest_1.describe)('extension.ts', () => {
    (0, vitest_1.beforeEach)(() => {
        mockWorkspaceFolders = undefined;
        mockConfig = {
            'lsp.pythonPath': 'pipenv',
            'lsp.serverPath': 'src/lsp/server.py'
        };
        lastErrorMessage = '';
        clientInstance = null;
        startCalled = false;
        stopCalled = false;
        startShouldFail = false;
    });
    (0, vitest_1.it)('should handle deactivate with no active client', () => {
        const res = (0, extension_1.deactivate)();
        (0, vitest_1.expect)(res).toBeUndefined();
    });
    (0, vitest_1.it)('should handle activation with no workspace folders', () => {
        (0, extension_1.activate)({});
        (0, vitest_1.expect)(lastErrorMessage).toBe('Sapphire LSP requires an open workspace.');
        (0, vitest_1.expect)(clientInstance).toBeNull();
    });
    (0, vitest_1.it)('should activate successfully with default pipenv settings', () => {
        mockWorkspaceFolders = [{ uri: { fsPath: '/mock/workspace' } }];
        (0, extension_1.activate)({});
        (0, vitest_1.expect)(clientInstance).not.toBeNull();
        (0, vitest_1.expect)(clientInstance.serverOptions.command).toBe('pipenv');
        (0, vitest_1.expect)(clientInstance.serverOptions.args).toEqual(['run', 'python', '/mock/workspace/src/lsp/server.py']);
        (0, vitest_1.expect)(startCalled).toBe(true);
    });
    (0, vitest_1.it)('should activate successfully with custom Python interpreter and absolute path', () => {
        mockWorkspaceFolders = [{ uri: { fsPath: '/mock/workspace' } }];
        mockConfig['lsp.pythonPath'] = '/usr/bin/python3';
        mockConfig['lsp.serverPath'] = '/absolute/server.py';
        (0, extension_1.activate)({});
        (0, vitest_1.expect)(clientInstance).not.toBeNull();
        (0, vitest_1.expect)(clientInstance.serverOptions.command).toBe('/usr/bin/python3');
        (0, vitest_1.expect)(clientInstance.serverOptions.args).toEqual(['/absolute/server.py']);
    });
    (0, vitest_1.it)('should show error message if LanguageClient fails to start', async () => {
        mockWorkspaceFolders = [{ uri: { fsPath: '/mock/workspace' } }];
        startShouldFail = true;
        (0, extension_1.activate)({});
        // Wait for the start promise rejection to handle
        await new Promise(resolve => setTimeout(resolve, 15));
        (0, vitest_1.expect)(lastErrorMessage).toBe('Failed to start Sapphire Language Server: Start failed mock');
    });
    (0, vitest_1.it)('should handle deactivate with active client', async () => {
        mockWorkspaceFolders = [{ uri: { fsPath: '/mock/workspace' } }];
        (0, extension_1.activate)({});
        const res = (0, extension_1.deactivate)();
        (0, vitest_1.expect)(res).toBeDefined();
        await res;
        (0, vitest_1.expect)(stopCalled).toBe(true);
    });
});
//# sourceMappingURL=extension.test.js.map