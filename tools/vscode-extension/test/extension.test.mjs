import { describe, it, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import { mockState } from './mock-state.mjs';
import { activate, deactivate } from '../out/extension.js';

describe('extension.ts', () => {
  beforeEach(() => {
    mockState.reset();
  });

  it('should handle deactivate with no active client', () => {
    const res = deactivate();
    assert.equal(res, undefined);
  });

  it('should handle activation with no workspace folders', () => {
    activate({});
    assert.equal(mockState.lastErrorMessage, 'Sapphire LSP requires an open workspace.');
    assert.equal(mockState.clientInstance, null);
  });

  it('should activate successfully with default sapphire CLI setting', () => {
    mockState.workspaceFolders = [{ uri: { fsPath: '/mock/workspace' } }];
    activate({});
    assert.notEqual(mockState.clientInstance, null);
    assert.equal(mockState.clientInstance.serverOptions.run.command, 'sapphire');
    assert.deepEqual(mockState.clientInstance.serverOptions.run.args, ['lsp']);
    assert.equal(mockState.startCalled, true);
  });

  it('should activate successfully with custom executable path', () => {
    mockState.workspaceFolders = [{ uri: { fsPath: '/mock/workspace' } }];
    mockState.config['lsp.path'] = '/usr/local/bin/sapphire';
    activate({});
    assert.notEqual(mockState.clientInstance, null);
    assert.equal(mockState.clientInstance.serverOptions.run.command, '/usr/local/bin/sapphire');
    assert.deepEqual(mockState.clientInstance.serverOptions.run.args, ['lsp']);
  });

  it('should show error message if LanguageClient fails to start', async () => {
    mockState.workspaceFolders = [{ uri: { fsPath: '/mock/workspace' } }];
    mockState.startShouldFail = true;
    activate({});
    // Wait for the start promise rejection to handle
    await new Promise((resolve) => setTimeout(resolve, 15));
    assert.equal(
      mockState.lastErrorMessage,
      "Failed to start Sapphire Language Server ('sapphire lsp'): Start failed mock. Please ensure 'sapphire' is installed on your system PATH or configure 'sapphire.lsp.path' in VS Code settings."
    );
  });

  it('should handle deactivate with active client', async () => {
    mockState.workspaceFolders = [{ uri: { fsPath: '/mock/workspace' } }];
    activate({});
    const res = deactivate();
    assert.notEqual(res, undefined);
    await res;
    assert.equal(mockState.stopCalled, true);
  });
});
