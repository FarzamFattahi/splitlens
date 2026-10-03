import { importFiles } from './imports';
const scope = self as unknown as {
  onmessage: ((e: MessageEvent<{ file: File; path: string }[]>) => void) | null;
  postMessage: (data: unknown) => void;
};
scope.onmessage = async ({ data }) => {
  try {
    const files = data.map(({ file, path }) => {
      Object.defineProperty(file, 'webkitRelativePath', { value: path });
      return file;
    });
    scope.postMessage({ images: await importFiles(files) });
  } catch (e) {
    scope.postMessage({ error: e instanceof Error ? e.message : String(e) });
  }
};
