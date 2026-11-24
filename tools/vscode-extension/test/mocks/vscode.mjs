import { mockState } from '../mock-state.mjs';

export const workspace = {
  getConfiguration: () => ({
    get: (key, defaultValue) =>
      mockState.config[key] !== undefined ? mockState.config[key] : defaultValue
  }),
  createFileSystemWatcher: () => ({}),
  get workspaceFolders() {
    return mockState.workspaceFolders;
  }
};

export const window = {
  showErrorMessage: (msg) => {
    mockState.lastErrorMessage = msg;
  },
  createOutputChannel: (name) => {
    const channel = {
      name,
      appendLine: (line) => {
        mockState.outputLines.push(line);
      },
      dispose: () => {}
    };
    mockState.outputChannel = channel;
    return channel;
  }
};
