/* global importScripts, loadPyodide */
let pyodide = null;
let initPromise = null;

async function initPyodide(bundleUrl) {
  if (initPromise) return initPromise;
  initPromise = (async () => {
    self.postMessage({ type: 'status', message: 'Loading Pyodide WebAssembly runtime...' });
    importScripts('https://cdn.jsdelivr.net/pyodide/v0.27.5/full/pyodide.js');
    pyodide = await loadPyodide({
      indexURL: 'https://cdn.jsdelivr.net/pyodide/v0.27.5/full/',
    });

    self.postMessage({ type: 'status', message: 'Installing antlr4-python3-runtime...' });
    await pyodide.loadPackage('micropip');
    const micropip = pyodide.pyimport('micropip');
    await micropip.install('antlr4-python3-runtime');

    self.postMessage({ type: 'status', message: 'Mounting Sapphire compiler...' });
    const resp = await fetch(bundleUrl);
    if (!resp.ok) {
      throw new Error(`Failed to fetch compiler bundle (${resp.status})`);
    }
    const bundle = await resp.json();

    for (const [relPath, content] of Object.entries(bundle.files)) {
      const fullPath = `/sapphire/${relPath}`;
      const dir = fullPath.slice(0, fullPath.lastIndexOf('/'));
      pyodide.FS.mkdirTree(dir);
      pyodide.FS.writeFile(fullPath, content, { encoding: 'utf8' });
    }

    await pyodide.runPythonAsync(`
import os, sys
if '/sapphire' not in sys.path:
    sys.path.insert(0, '/sapphire')
os.chdir('/sapphire')
from src.code_gen.transpiler import transpile_file
`);

    self.postMessage({ type: 'ready' });
  })();
  return initPromise;
}

async function compileAndRun(source) {
  if (!pyodide) {
    throw new Error('Pyodide is not initialized yet.');
  }
  pyodide.globals.set('_sapphire_source', source);
  const rawJson = await pyodide.runPythonAsync(`
import contextlib, io, json, os, sys, traceback
from src.code_gen.transpiler import transpile_file

with open('/sapphire/playground.sp', 'w', encoding='utf-8') as f:
    f.write(_sapphire_source)

stdout_buf = io.StringIO()
stderr_buf = io.StringIO()
python_code = ''
lua_code = ''
ok = True

try:
    transpile_file('/sapphire/playground.sp', '/sapphire/out.py', target='python', quiet=True, raise_on_error=True, use_runtime_module=False)
    with open('/sapphire/out.py', 'r', encoding='utf-8') as f:
        python_code = f.read()
except Exception as exc:
    ok = False
    stderr_buf.write(f"Compilation Error (Python target):\\n{exc}\\n")

try:
    transpile_file('/sapphire/playground.sp', '/sapphire/out.lua', target='lua', quiet=True, raise_on_error=True, use_runtime_module=False)
    with open('/sapphire/out.lua', 'r', encoding='utf-8') as f:
        lua_code = f.read()
except Exception as exc:
    if ok:
        stderr_buf.write(f"Lua Transpilation Warning:\\n{exc}\\n")

if ok and python_code:
    exec_ns = {'__name__': '__main__', '__file__': '/sapphire/out.py'}
    with contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(stderr_buf):
        try:
            exec(compile(python_code, '/sapphire/out.py', 'exec'), exec_ns)
        except SystemExit:
            pass
        except Exception:
            ok = False
            traceback.print_exc(file=stderr_buf)

json.dumps({
    'ok': ok,
    'stdout': stdout_buf.getvalue(),
    'stderr': stderr_buf.getvalue(),
    'pythonCode': python_code,
    'luaCode': lua_code,
})
`);
  return JSON.parse(rawJson);
}

self.onmessage = async (event) => {
  const data = event.data;
  try {
    if (data.type === 'init') {
      await initPyodide(data.bundleUrl);
    } else if (data.type === 'run') {
      const result = await compileAndRun(data.source);
      self.postMessage({ type: 'result', ...result });
    }
  } catch (err) {
    self.postMessage({
      type: 'error',
      error: err instanceof Error ? err.message : String(err),
    });
  }
};
