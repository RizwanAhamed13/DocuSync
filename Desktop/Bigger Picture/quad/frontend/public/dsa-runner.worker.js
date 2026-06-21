/**
 * DSA Code Runner Web Worker
 *
 * Handles client-side execution for Python (via Pyodide WASM) and JavaScript
 * (via isolated Function evaluation). Falls back to server for Java/C++/Go.
 *
 * Message protocol:
 *   IN:  { id, type: 'run', slug, code, language, testCases }
 *        { id, type: 'run-custom', code, language, stdin }
 *   OUT: { id, type: 'result', data }
 *        { id, type: 'error', message }
 *        { id, type: 'status', message }   (progress updates)
 */

let pyodide = null;
let pyodideLoading = false;
let pyodideReady = false;

// ── Pyodide loader ────────────────────────────────────────────────────────────

async function loadPyodide() {
  if (pyodideReady) return pyodide;
  if (pyodideLoading) {
    // Wait for existing load
    while (pyodideLoading) await new Promise(r => setTimeout(r, 100));
    return pyodide;
  }
  pyodideLoading = true;
  try {
    importScripts('https://cdn.jsdelivr.net/pyodide/v0.27.5/full/pyodide.js');
    pyodide = await loadPyodide({ indexURL: 'https://cdn.jsdelivr.net/pyodide/v0.27.5/full/' });
    pyodideReady = true;
    self.postMessage({ type: 'pyodide-ready' });
  } catch (e) {
    pyodide = null;
  } finally {
    pyodideLoading = false;
  }
  return pyodide;
}

// Pre-load Pyodide in background as soon as the worker starts
loadPyodide();

// ── Python runner (Pyodide) ───────────────────────────────────────────────────

async function runPython(code, testCases) {
  const py = await loadPyodide();
  if (!py) throw new Error('Pyodide failed to load. Falling back to server.');

  const harness = `
import json, sys, traceback

${code}

__cases = ${JSON.stringify(testCases.map(t => t.input))}
__results = []
for __args in __cases:
    try:
        __out = solve(*__args)
        __results.append({"ok": True, "value": __out})
    except Exception as __e:
        __results.append({"ok": False, "error": str(__e)})

print(json.dumps(__results))
`.trim();

  // Capture stdout
  const captured = [];
  py.setStdout({ batched: (s) => captured.push(s) });
  py.setStderr({ batched: () => {} });

  try {
    await py.runPythonAsync(harness);
  } catch (e) {
    const tb = e.message || String(e);
    throw new Error(tb.replace(/File "<exec>"/g, 'your code'));
  }

  const lastLine = captured.join('').trim().split('\n').pop();
  let rawResults;
  try {
    rawResults = JSON.parse(lastLine);
  } catch {
    throw new Error('Could not parse output: ' + (captured.join('').slice(0, 300)));
  }

  let passed = 0;
  const results = testCases.map((tc, i) => {
    const r = rawResults[i] || { ok: false, error: 'No output' };
    if (!r.ok) return { input: tc.input, expected: tc.expected_output, actual: null, passed: false, error: r.error };
    const ok = JSON.stringify(r.value) === JSON.stringify(tc.expected_output);
    if (ok) passed++;
    return { input: tc.input, expected: tc.expected_output, actual: r.value, passed: ok };
  });

  return { passed, total: testCases.length, results, language: 'python', engine: 'client' };
}

async function runPythonCustom(code, stdin) {
  const py = await loadPyodide();
  if (!py) throw new Error('Pyodide not available');

  // Redirect stdin
  const stdinLines = stdin.split('\n');
  let lineIdx = 0;
  py.setStdin({ readline: () => (stdinLines[lineIdx++] || '') + '\n' });

  const captured = [];
  const errors = [];
  py.setStdout({ batched: s => captured.push(s) });
  py.setStderr({ batched: s => errors.push(s) });

  let exitCode = 0;
  try {
    await py.runPythonAsync(code);
  } catch (e) {
    errors.push(e.message || String(e));
    exitCode = 1;
  }

  return { stdout: captured.join(''), stderr: errors.join(''), exit_code: exitCode };
}

// ── JavaScript runner (sandboxed eval) ───────────────────────────────────────

function runJS(code, testCases) {
  const harness = `
${code}

const __cases = ${JSON.stringify(testCases.map(t => t.input))};
const __results = [];
for (const __args of __cases) {
  try {
    const __v = solve(...__args);
    __results.push({ ok: true, value: __v });
  } catch(__e) {
    __results.push({ ok: false, error: String(__e) });
  }
}
return JSON.stringify(__results);
`.trim();

  let rawResults;
  try {
    // eslint-disable-next-line no-new-func
    const fn = new Function(harness);
    rawResults = JSON.parse(fn());
  } catch (e) {
    throw new Error(String(e));
  }

  let passed = 0;
  const results = testCases.map((tc, i) => {
    const r = rawResults[i] || { ok: false, error: 'No output' };
    if (!r.ok) return { input: tc.input, expected: tc.expected_output, actual: null, passed: false, error: r.error };
    const ok = JSON.stringify(r.value) === JSON.stringify(tc.expected_output);
    if (ok) passed++;
    return { input: tc.input, expected: tc.expected_output, actual: r.value, passed: ok };
  });

  return { passed, total: testCases.length, results, language: 'javascript', engine: 'client' };
}

function runJSCustom(code, stdin) {
  const lines = stdin.split('\n');
  let lineIdx = 0;
  const captured = [];

  const harness = `
const __inputLines = ${JSON.stringify(lines)};
let __lineIdx = 0;
const readline = () => __inputLines[__lineIdx++] || '';
const console = { log: (...a) => __captured.push(a.map(String).join(' ')) };
${code}
`.trim();

  try {
    // eslint-disable-next-line no-new-func
    const fn = new Function('__captured', harness);
    fn(captured);
    return { stdout: captured.join('\n'), stderr: '', exit_code: 0 };
  } catch (e) {
    return { stdout: '', stderr: String(e), exit_code: 1 };
  }
}

// ── TypeScript runner (compile + eval) ───────────────────────────────────────

function runTS(code, testCases) {
  // Strip TypeScript type annotations, then delegate to JS runner
  const jsCode = code
    .replace(/:\s*[A-Za-z<>\[\]|&]+(\s*=>)?/g, (m, arrow) => arrow ? ' =>' : '')
    .replace(/<[^>]+>/g, '')
    .replace(/\bas\s+\w[\w<>[\]]*\b/g, '');
  const result = runJS(jsCode, testCases);
  return { ...result, language: 'typescript', engine: 'client' };
}

// ── CLIENT_SIDE_LANGS ─────────────────────────────────────────────────────────

const CLIENT_LANGS = new Set(['python', 'py', 'javascript', 'js', 'typescript', 'ts']);

// ── Message handler ───────────────────────────────────────────────────────────

self.onmessage = async ({ data }) => {
  const { id, type } = data;

  try {
    if (type === 'run') {
      const { slug, code, language, testCases } = data;
      const lang = (language || 'python').toLowerCase();

      if (!CLIENT_LANGS.has(lang)) {
        // Signal: fall back to server
        self.postMessage({ id, type: 'fallback', reason: `${lang} requires server execution` });
        return;
      }

      self.postMessage({ id, type: 'status', message: `Running ${lang} in browser...` });

      let result;
      if (lang === 'python' || lang === 'py') {
        result = await runPython(code, testCases);
      } else if (lang === 'javascript' || lang === 'js') {
        result = runJS(code, testCases);
      } else if (lang === 'typescript' || lang === 'ts') {
        result = runTS(code, testCases);
      }

      self.postMessage({ id, type: 'result', data: result });

    } else if (type === 'run-custom') {
      const { code, language, stdin } = data;
      const lang = (language || 'python').toLowerCase();

      if (!CLIENT_LANGS.has(lang)) {
        self.postMessage({ id, type: 'fallback', reason: `${lang} requires server execution` });
        return;
      }

      let result;
      if (lang === 'python' || lang === 'py') {
        result = await runPythonCustom(code, stdin || '');
      } else if (lang === 'javascript' || lang === 'js') {
        result = runJSCustom(code, stdin || '');
      } else {
        result = runJSCustom(code, stdin || ''); // TS fallback
      }

      self.postMessage({ id, type: 'result', data: result });
    }
  } catch (err) {
    self.postMessage({ id, type: 'error', message: err.message || String(err) });
  }
};
