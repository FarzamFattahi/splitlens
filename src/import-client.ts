import type { InputImage } from './types';
export function importImages(files: File[], signal: AbortSignal): Promise<InputImage[]> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) {
      reject(new DOMException('Import canceled.', 'AbortError'));
      return;
    }
    const worker = new Worker(new URL('./import.worker.ts', import.meta.url), { type: 'module' });
    const cleanup = () => {
      worker.terminate();
      signal.removeEventListener('abort', cancel);
    };
    const cancel = () => {
      cleanup();
      reject(new DOMException('Import canceled.', 'AbortError'));
    };
    signal.addEventListener('abort', cancel, { once: true });
    worker.onmessage = ({ data }) => {
      cleanup();
      if (data.error) reject(new Error(data.error));
      else resolve(data.images);
    };
    worker.onerror = (e) => {
      cleanup();
      reject(new Error(e.message || 'Dataset import failed.'));
    };
    // webkitRelativePath is not reliably retained by structured cloning File.
    worker.postMessage(files.map((file) => ({ file, path: file.webkitRelativePath || file.name })));
  });
}
