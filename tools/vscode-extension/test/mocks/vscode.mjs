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
  }
};
