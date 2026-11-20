import fs from 'node:fs';
import path from 'node:path';

const EXCLUDED_DIRS = new Set(['__pycache__', 'lsp', '.pytest_cache']);
const EXCLUDED_FILES = new Set(['llvm_transpiler.py', 'llvm_transpiler_test.py']);

function walkFiles(dir, repoRoot, out) {
  if (!fs.existsSync(dir)) return;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (EXCLUDED_DIRS.has(entry.name)) continue;
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      walkFiles(fullPath, repoRoot, out);
    } else if (entry.isFile()) {
      if (EXCLUDED_FILES.has(entry.name)) continue;
      if (entry.name.endsWith('_test.py')) continue;
      if (
        entry.name.endsWith('.py') ||
        entry.name.endsWith('.sp') ||
        entry.name.endsWith('.lua')
      ) {
        const rel = path.relative(repoRoot, fullPath).replace(/\\/g, '/');
        out[rel] = fs.readFileSync(fullPath, 'utf-8');
      }
    }
  }
}

export function buildCompilerBundle(repoRoot) {
  /** @type {Record<string, string>} */
  const files = {};
  walkFiles(path.join(repoRoot, 'src'), repoRoot, files);
  walkFiles(path.join(repoRoot, 'lib', 'std'), repoRoot, files);
  return {
    generatedAt: new Date().toISOString(),
    fileCount: Object.keys(files).length,
    files,
  };
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const webDir = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
  const repoRoot = path.resolve(webDir, '..');
  const outDir = path.join(webDir, 'public');
  fs.mkdirSync(outDir, { recursive: true });
  const bundle = buildCompilerBundle(repoRoot);
  const outPath = path.join(outDir, 'sapphire-compiler.json');
  fs.writeFileSync(outPath, JSON.stringify(bundle), 'utf-8');
  console.log(`Bundled ${bundle.fileCount} compiler & stdlib files to ${outPath}`);
}
