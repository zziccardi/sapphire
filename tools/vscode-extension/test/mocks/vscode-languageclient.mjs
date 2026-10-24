import { mockState } from '../mock-state.mjs';

export class LanguageClient {
  constructor(id, name, serverOptions, clientOptions) {
    this.id = id;
    this.name = name;
    this.serverOptions = serverOptions;
    this.clientOptions = clientOptions;
    mockState.clientInstance = this;
  }

  start() {
    mockState.startCalled = true;
    if (mockState.startShouldFail) {
      return Promise.reject('Start failed mock');
    }
    return Promise.resolve();
  }

  stop() {
    mockState.stopCalled = true;
    return Promise.resolve();
  }
}
