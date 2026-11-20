import path from 'node:path';
import { describe, expect, it } from 'vitest';
import { buildCompilerBundle } from './bundle-compiler.mjs';

describe('Pyodide compiler bundle', () => {
  it('includes core compiler entrypoints and excludes tests and LSP', () => {
    const repoRoot = path.resolve(process.cwd(), '..');
    const bundle = buildCompilerBundle(repoRoot);

    expect(bundle.fileCount).toBeGreaterThan(20);
    expect(bundle.files['src/code_gen/transpiler.py']).toBeDefined();
    expect(bundle.files['src/semantics/type_checker.py']).toBeDefined();
    expect(bundle.files['src/parser/gen/SapphireParser.py']).toBeDefined();
    expect(bundle.files['src/code_gen/llvm_transpiler.py']).toBeUndefined();
    expect(bundle.files['src/semantics/type_checker_test.py']).toBeUndefined();
    expect(Object.keys(bundle.files).some((k) => k.startsWith('src/lsp/'))).toBe(false);
  });
});
