import path from 'node:path';
import { describe, expect, it } from 'vitest';
import { buildCompilerBundle } from './bundle-compiler.mjs';

describe('Pyodide compiler bundle', () => {
  it('includes core compiler entrypoints and excludes tests and LSP', () => {
    const repoRoot = path.resolve(process.cwd(), '..');
    const bundle = buildCompilerBundle(repoRoot);

    expect(bundle.fileCount).toBeGreaterThan(20);
    expect(bundle.files['sapphire/code_gen/transpiler.py']).toBeDefined();
    expect(bundle.files['sapphire/semantics/type_checker.py']).toBeDefined();
    expect(bundle.files['sapphire/parser/gen/SapphireParser.py']).toBeDefined();
    expect(bundle.files['sapphire/code_gen/llvm_transpiler.py']).toBeUndefined();
    expect(bundle.files['sapphire/semantics/type_checker_basics_test.py']).toBeUndefined();
    expect(Object.keys(bundle.files).some((k) => k.startsWith('sapphire/lsp/'))).toBe(false);
  });
});
