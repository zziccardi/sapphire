export const mockState = {
  workspaceFolders: undefined,
  config: {
    'lsp.path': 'sapphire'
  },
  lastErrorMessage: '',
  clientInstance: null,
  startCalled: false,
  stopCalled: false,
  startShouldFail: false,
  outputChannel: null,
  outputLines: [],
  reset() {
    this.workspaceFolders = undefined;
    this.config = {
      'lsp.path': 'sapphire'
    };
    this.lastErrorMessage = '';
    this.clientInstance = null;
    this.startCalled = false;
    this.stopCalled = false;
    this.startShouldFail = false;
    this.outputChannel = null;
    this.outputLines = [];
  }
};
