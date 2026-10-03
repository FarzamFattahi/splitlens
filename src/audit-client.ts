import type { AuditResult, AuditSettings, InputImage } from './types';

export function analyzeFiles(
  inputs: InputImage[],
  settings: AuditSettings,
  onProgress: (done: number, total: number) => void,
  signal?: AbortSignal,
): Promise<AuditResult> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException('Analysis cancelled.', 'AbortError'));
      return;
    }
    const worker = new Worker(new URL('./audit.worker.ts', import.meta.url), { type: 'module' });
    const cleanup = () => {
      worker.terminate();
      signal?.removeEventListener('abort', abort);
    };
    const abort = () => {
      cleanup();
      reject(new DOMException('Analysis cancelled.', 'AbortError'));
    };
    signal?.addEventListener('abort', abort, { once: true });
    worker.onmessage = ({
      data,
    }: MessageEvent<{
      type: string;
      done: number;
      total: number;
      result: AuditResult;
      message: string;
    }>) => {
      if (data.type === 'progress') onProgress(data.done, data.total);
      else if (data.type === 'result') {
        cleanup();
        resolve(data.result);
      } else if (data.type === 'error') {
        cleanup();
        reject(new Error(data.message));
      }
    };
    worker.onerror = (event) => {
      cleanup();
      reject(new Error(event.message || 'Image analysis worker failed.'));
    };
    worker.postMessage({ inputs, settings });
  });
}
