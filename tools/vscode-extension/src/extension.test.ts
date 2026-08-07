import { describe, it, expect, vi, beforeEach } from 'vitest';
import * as path from 'path';

// Mock vscode module
let mockWorkspaceFolders: any = undefined;
let mockConfig: Record<string, any> = {
  'lsp.path': 'sapphire'
};
let lastErrorMessage = '';

vi.mock('vscode', () => {
  return {
    workspace: {
      getConfiguration: () => ({
        get: (key: string, defaultValue: any) => mockConfig[key] !== undefined ? mockConfig[key] : defaultValue
      }),
      createFileSystemWatcher: () => ({}),
      get workspaceFolders() {
        return mockWorkspaceFolders;
      }
    },
    window: {
      showErrorMessage: (msg: string) => { lastErrorMessage = msg; }
    }
  };
});

// Mock LanguageClient
let clientInstance: any = null;
let startCalled = false;
let stopCalled = false;
let startShouldFail = false;

vi.mock('vscode-languageclient/node', () => {
  class MockLanguageClient {
    id: string;
    name: string;
    serverOptions: any;
    clientOptions: any;

    constructor(id: string, name: string, serverOptions: any, clientOptions: any) {
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
import { activate, deactivate } from './extension';

describe('extension.ts', () => {
  beforeEach(() => {
    mockWorkspaceFolders = undefined;
    mockConfig = {
      'lsp.path': 'sapphire'
    };
    lastErrorMessage = '';
    clientInstance = null;
    startCalled = false;
    stopCalled = false;
    startShouldFail = false;
  });

  it('should handle deactivate with no active client', () => {
    const res = deactivate();
    expect(res).toBeUndefined();
  });

  it('should handle activation with no workspace folders', () => {
    activate({} as any);
    expect(lastErrorMessage).toBe('Sapphire LSP requires an open workspace.');
    expect(clientInstance).toBeNull();
  });

  it('should activate successfully with default sapphire CLI setting', () => {
    mockWorkspaceFolders = [{ uri: { fsPath: '/mock/workspace' } }];
    activate({} as any);
    expect(clientInstance).not.toBeNull();
    expect(clientInstance.serverOptions.run.command).toBe('sapphire');
    expect(clientInstance.serverOptions.run.args).toEqual(['lsp']);
    expect(startCalled).toBe(true);
  });

  it('should activate successfully with custom executable path', () => {
    mockWorkspaceFolders = [{ uri: { fsPath: '/mock/workspace' } }];
    mockConfig['lsp.path'] = '/usr/local/bin/sapphire';
    activate({} as any);
    expect(clientInstance).not.toBeNull();
    expect(clientInstance.serverOptions.run.command).toBe('/usr/local/bin/sapphire');
    expect(clientInstance.serverOptions.run.args).toEqual(['lsp']);
  });

  it('should show error message if LanguageClient fails to start', async () => {
    mockWorkspaceFolders = [{ uri: { fsPath: '/mock/workspace' } }];
    startShouldFail = true;
    activate({} as any);
    // Wait for the start promise rejection to handle
    await new Promise(resolve => setTimeout(resolve, 15));
    expect(lastErrorMessage).toBe('Failed to start Sapphire Language Server: Start failed mock');
  });

  it('should handle deactivate with active client', async () => {
    mockWorkspaceFolders = [{ uri: { fsPath: '/mock/workspace' } }];
    activate({} as any);
    const res = deactivate();
    expect(res).toBeDefined();
    await res;
    expect(stopCalled).toBe(true);
  });
});
