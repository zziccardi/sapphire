export function resolve(specifier, context, nextResolve) {
  if (specifier === 'vscode') {
    return {
      shortCircuit: true,
      url: new URL('./mocks/vscode.mjs', import.meta.url).href
    };
  }
  if (specifier === 'vscode-languageclient/node') {
    return {
      shortCircuit: true,
      url: new URL('./mocks/vscode-languageclient.mjs', import.meta.url).href
    };
  }
  return nextResolve(specifier, context);
}
