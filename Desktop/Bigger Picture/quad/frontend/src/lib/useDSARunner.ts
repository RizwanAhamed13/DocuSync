/**
 * useDSARunner — manages the dsa-runner Web Worker lifecycle.
 *
 * For Python and JS/TS, code runs entirely in the browser via Pyodide / Function().
 * For Java, C++, Go — falls through to the server API.
 *
 * Usage:
 *   const { run, runCustom, pyodideReady } = useDSARunner();
 *   const result = await run(slug, code, language, testCases);
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import api from './api';

interface TestCase {
  input: unknown[];
  expected_output: unknown;
}

interface RunResult {
  passed: number;
  total: number;
  results: {
    input: unknown;
    expected: unknown;
    actual: unknown;
    passed: boolean;
    error?: string;
  }[];
  error?: string;
  language?: string;
  engine?: 'client' | 'server';
}

interface CustomResult {
  stdout: string;
  stderr: string;
  exit_code: number;
}

const CLIENT_LANGS = new Set(['python', 'py', 'javascript', 'js', 'typescript', 'ts']);

let msgId = 0;
const nextId = () => String(++msgId);

export function useDSARunner() {
  const workerRef = useRef<Worker | null>(null);
  const pendingRef = useRef<Map<string, { resolve: Function; reject: Function }>>(new Map());
  const [pyodideReady, setPyodideReady] = useState(false);
  const [workerAvailable, setWorkerAvailable] = useState(false);

  useEffect(() => {
    if (typeof Worker === 'undefined') return;
    const worker = new Worker('/dsa-runner.worker.js');
    workerRef.current = worker;
    setWorkerAvailable(true);

    worker.onmessage = ({ data }) => {
      const { id, type } = data;

      if (type === 'pyodide-ready') {
        setPyodideReady(true);
        return;
      }
      if (type === 'status') {
        // Progress messages — ignored at hook level, caller can subscribe separately
        return;
      }

      const pending = pendingRef.current.get(id);
      if (!pending) return;
      pendingRef.current.delete(id);

      if (type === 'result') {
        pending.resolve(data.data);
      } else if (type === 'fallback') {
        // Resolve with a sentinel so caller knows to hit server
        pending.resolve({ __fallback: true, reason: data.reason });
      } else if (type === 'error') {
        pending.reject(new Error(data.message));
      }
    };

    worker.onerror = (e) => {
      console.warn('[DSARunner] worker error:', e.message);
      setWorkerAvailable(false);
    };

    return () => {
      worker.terminate();
      workerRef.current = null;
    };
  }, []);

  const workerCall = useCallback(
    (msg: Record<string, unknown>): Promise<unknown> => {
      return new Promise((resolve, reject) => {
        if (!workerRef.current) { reject(new Error('Worker not available')); return; }
        pendingRef.current.set(msg.id as string, { resolve, reject });
        workerRef.current.postMessage(msg);
      });
    },
    []
  );

  /**
   * Run code against seeded test cases.
   * Python / JS / TS → browser Worker
   * Java / C++ / Go → server API
   */
  const run = useCallback(
    async (
      slug: string,
      code: string,
      language: string,
      testCases: TestCase[]
    ): Promise<RunResult> => {
      const lang = language.toLowerCase();

      // Always server for compiled languages
      if (!CLIENT_LANGS.has(lang) || !workerAvailable) {
        const resp = await api.post<RunResult>('/dsa/run', { slug, code, language });
        return { ...resp.data, engine: 'server' };
      }

      const id = nextId();
      try {
        const result = await Promise.race([
          workerCall({ id, type: 'run', slug, code, language, testCases }),
          new Promise<never>((_, reject) => setTimeout(() => reject(new Error('Client timeout (30s)')), 30000)),
        ]) as RunResult & { __fallback?: boolean };

        if (result.__fallback) {
          // Worker said to fall back (e.g. Pyodide not loaded yet)
          const resp = await api.post<RunResult>('/dsa/run', { slug, code, language });
          return { ...resp.data, engine: 'server' };
        }

        return result;
      } catch (err: unknown) {
        // Worker threw — fall back to server
        const resp = await api.post<RunResult>('/dsa/run', { slug, code, language });
        return { ...resp.data, engine: 'server' };
      }
    },
    [workerAvailable, workerCall]
  );

  /**
   * Run code with custom stdin.
   * Python / JS → browser Worker
   * Others → server API
   */
  const runCustom = useCallback(
    async (code: string, language: string, stdin: string): Promise<CustomResult> => {
      const lang = language.toLowerCase();

      if (!CLIENT_LANGS.has(lang) || !workerAvailable) {
        const resp = await api.post<CustomResult>('/dsa/run-custom', { code, language, stdin });
        return resp.data;
      }

      const id = nextId();
      try {
        const result = await Promise.race([
          workerCall({ id, type: 'run-custom', code, language, stdin }),
          new Promise<never>((_, reject) => setTimeout(() => reject(new Error('Timeout')), 30000)),
        ]) as CustomResult & { __fallback?: boolean };

        if (result.__fallback) {
          const resp = await api.post<CustomResult>('/dsa/run-custom', { code, language, stdin });
          return resp.data;
        }
        return result;
      } catch {
        const resp = await api.post<CustomResult>('/dsa/run-custom', { code, language, stdin });
        return resp.data;
      }
    },
    [workerAvailable, workerCall]
  );

  return { run, runCustom, pyodideReady, workerAvailable };
}
