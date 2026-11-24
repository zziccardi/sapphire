import { describe, it, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import Module, { createRequire } from 'node:module';
import { mockState } from './mock-state.mjs';
import * as vscodeMock from './mocks/vscode.mjs';
import * as lcMock from './mocks/vscode-languageclient.mjs';

const require = createRequire(import.meta.url);

// Verify real CommonJS resolution of vscode-languageclient/node works without mocks.
const resolvedLanguageClientNode = require.resolve('vscode-languageclient/node');

// Intercept CommonJS require('vscode') and require('vscode-languageclient/node')
// when loading the compiled CommonJS extension bundle.
const origLoad = Module._load;
Module._load = function (request, parent, isMain) {
  if (request === 'vscode') {
    return vscodeMock;
  }
  if (request === 'vscode-languageclient/node') {
    return lcMock;
  }
  return origLoad.call(this, request, parent, isMain);
};

const { activate, deactivate } = require('../out/extension.js');

describe('extension.ts', () => {
  beforeEach(() => {
    mockState.reset();
  });

  it('resolves vscode-languageclient/node under real Node CommonJS', () => {
    assert.ok(resolvedLanguageClientNode.endsWith('lib/node/main.js'));
  });

  it('should handle deactivate with no active client', () => {
    const res = deactivate();
    assert.equal(res, undefined);
  });

  it('should handle activation with no workspace folders', () => {
    activate({ subscriptions: [] });
    assert.equal(mockState.lastErrorMessage, 'Sapphire LSP requires an open workspace.');
    assert.equal(mockState.clientInstance, null);
  });

  it('should handle activation with empty workspace folders array', () => {
    mockState.workspaceFolders = [];
    activate({ subscriptions: [] });
    assert.equal(mockState.lastErrorMessage, 'Sapphire LSP requires an open workspace.');
    assert.equal(mockState.clientInstance, null);
  });

  it('should activate successfully with default sapphire CLI setting and register watcher', () => {
    mockState.workspaceFolders = [{ uri: { fsPath: '/mock/workspace' } }];
    const context = { subscriptions: [] };
    activate(context);
    assert.notEqual(mockState.clientInstance, null);
    assert.equal(mockState.clientInstance.serverOptions.run.command, 'sapphire');
    assert.deepEqual(mockState.clientInstance.serverOptions.run.args, ['lsp']);
    assert.equal(mockState.startCalled, true);
    assert.equal(context.subscriptions.length, 2);
    assert.equal(
      context.subscriptions[0],
      mockState.clientInstance.clientOptions.synchronize.fileEvents
    );
    assert.equal(context.subscriptions[1], mockState.outputChannel);
    assert.deepEqual(mockState.outputLines, [
      'Sapphire Language Support extension is now active!'
    ]);
  });

  it('should activate successfully with custom executable path', () => {
    mockState.workspaceFolders = [{ uri: { fsPath: '/mock/workspace' } }];
    mockState.config['lsp.path'] = '/usr/local/bin/sapphire';
    activate({ subscriptions: [] });
    assert.notEqual(mockState.clientInstance, null);
    assert.equal(mockState.clientInstance.serverOptions.run.command, '/usr/local/bin/sapphire');
    assert.deepEqual(mockState.clientInstance.serverOptions.run.args, ['lsp']);
  });

  it('should show error message if LanguageClient fails to start', async () => {
    mockState.workspaceFolders = [{ uri: { fsPath: '/mock/workspace' } }];
    mockState.startShouldFail = true;
    activate({ subscriptions: [] });
    // Wait for the start promise rejection to handle
    await new Promise((resolve) => setTimeout(resolve, 15));
    assert.equal(
      mockState.lastErrorMessage,
      "Failed to start Sapphire Language Server ('sapphire lsp'): Start failed mock. Please ensure 'sapphire' is installed on your system PATH or configure 'sapphire.lsp.path' in VS Code settings."
    );
  });

  it('should handle deactivate with active client', async () => {
    mockState.workspaceFolders = [{ uri: { fsPath: '/mock/workspace' } }];
    activate({ subscriptions: [] });
    const res = deactivate();
    assert.notEqual(res, undefined);
    await res;
    assert.equal(mockState.stopCalled, true);
    assert.equal(deactivate(), undefined);
  });
});
