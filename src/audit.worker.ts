import {
  differenceHash,
  grayscale,
  inferMetadata,
  meanRgb,
  qualityMetrics,
  reanalyze,
} from './engine';
import type { AuditSettings, ImageRecord, InputImage } from './types';

const scope = self as unknown as {
  onmessage:
    ((event: MessageEvent<{ inputs: InputImage[]; settings: AuditSettings }>) => void) | null;
  postMessage: (message: unknown) => void;
};
const MAX_PIXELS = 40_000_000;
const ascii = (bytes: Uint8Array, start: number, length: number) =>
  String.fromCharCode(...bytes.subarray(start, start + length));
function checkAnimation(bytes: Uint8Array) {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  if (bytes.length >= 3 && ascii(bytes, 0, 3) === 'GIF')
    throw new Error('GIF images are excluded. Export a still PNG or JPEG frame before importing.');
  if (bytes.length >= 24 && view.getUint32(0) === 0x89504e47) {
    let offset = 8;
    while (offset + 12 <= bytes.length) {
      const size = view.getUint32(offset),
        type = ascii(bytes, offset + 4, 4);
      if (type === 'acTL')
        throw new Error('Animated PNG images are excluded. Export a still frame before importing.');
      if (type === 'IEND' || size > bytes.length - offset - 12) break;
      offset += size + 12;
    }
  }
  if (
    bytes.length >= 30 &&
    ascii(bytes, 0, 4) === 'RIFF' &&
    ascii(bytes, 8, 4) === 'WEBP' &&
    ascii(bytes, 12, 4) === 'VP8X' &&
    bytes[20] & 2
  )
    throw new Error('Animated WebP images are excluded. Export a still frame before importing.');
  if (bytes.length >= 16 && ascii(bytes, 4, 4) === 'ftyp') {
    const boxSize = view.getUint32(0);
    for (let offset = 8; offset + 4 <= Math.min(boxSize, bytes.length); offset += 4)
      if (offset !== 12 && ascii(bytes, offset, 4) === 'avis')
        throw new Error(
          'AVIF image sequences are excluded. Export a still frame before importing.',
        );
  }
}
function headerDimensions(bytes: Uint8Array): [number, number] | undefined {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  if (bytes.length >= 24 && view.getUint32(0) === 0x89504e47)
    return [view.getUint32(16), view.getUint32(20)];
  if (bytes.length >= 10 && String.fromCharCode(...bytes.subarray(0, 3)) === 'GIF')
    return [view.getUint16(6, true), view.getUint16(8, true)];
  if (bytes.length >= 26 && bytes[0] === 66 && bytes[1] === 77)
    return [Math.abs(view.getInt32(18, true)), Math.abs(view.getInt32(22, true))];
  if (bytes.length >= 30 && ascii(bytes, 0, 4) === 'RIFF' && ascii(bytes, 8, 4) === 'WEBP') {
    const kind = ascii(bytes, 12, 4);
    if (kind === 'VP8X')
      return [
        1 + bytes[24] + (bytes[25] << 8) + (bytes[26] << 16),
        1 + bytes[27] + (bytes[28] << 8) + (bytes[29] << 16),
      ];
    if (kind === 'VP8 ' && ascii(bytes, 23, 3) === '\x9d\x01\x2a')
      return [view.getUint16(26, true) & 0x3fff, view.getUint16(28, true) & 0x3fff];
    if (kind === 'VP8L' && bytes[20] === 0x2f) {
      const bits = view.getUint32(21, true);
      return [1 + (bits & 0x3fff), 1 + ((bits >>> 14) & 0x3fff)];
    }
  }
  if (bytes.length >= 4 && bytes[0] === 255 && bytes[1] === 216) {
    let offset = 2;
    while (offset + 4 < bytes.length) {
      if (bytes[offset] !== 255) break;
      while (bytes[offset] === 255) offset++;
      const marker = bytes[offset++];
      if (marker === 217 || marker === 218) break;
      if (marker === 1 || (marker >= 208 && marker <= 215)) continue;
      const length = view.getUint16(offset);
      if (length < 2 || offset + length > bytes.length) break;
      if (
        [192, 193, 194, 195, 197, 198, 199, 201, 202, 203, 205, 206, 207].includes(marker) &&
        length >= 7
      )
        return [view.getUint16(offset + 5), view.getUint16(offset + 3)];
      offset += length;
    }
  }
  return undefined;
}
function assertDimensions(width: number, height: number) {
  if (!width || !height || width * height > MAX_PIXELS)
    throw new Error('Image exceeds the 40 megapixel decode limit or has invalid dimensions.');
}
async function dataUrl(blob: Blob): Promise<string> {
  const bytes = new Uint8Array(await blob.arrayBuffer());
  let binary = '';
  for (let offset = 0; offset < bytes.length; offset += 8192)
    binary += String.fromCharCode(...bytes.subarray(offset, offset + 8192));
  return `data:${blob.type};base64,${btoa(binary)}`;
}
async function analyze(input: InputImage): Promise<ImageRecord> {
  const metadata = inferMetadata(input.path);
  const base: ImageRecord = {
    id: input.id,
    path: input.path,
    split: input.split ?? metadata.split,
    label: metadata.label,
    width: 0,
    height: 0,
    bytes: input.file.size,
    sha256: '',
    dhash: '',
    brightness: 0,
    sharpness: 0,
    thumbnail: '',
  };
  let bitmap: ImageBitmap | undefined;
  try {
    const bytes = await input.file.arrayBuffer();
    checkAnimation(new Uint8Array(bytes));
    const dimensions = headerDimensions(new Uint8Array(bytes));
    if (dimensions) assertDimensions(...dimensions);
    base.sha256 = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)), (byte) =>
      byte.toString(16).padStart(2, '0'),
    ).join('');
    bitmap = await createImageBitmap(input.file);
    assertDimensions(bitmap.width, bitmap.height);
    base.width = bitmap.width;
    base.height = bitmap.height;
    const canvas = new OffscreenCanvas(128, 128),
      context = canvas.getContext('2d', { willReadFrequently: true });
    if (!context) throw new Error('This browser cannot create a canvas for image analysis.');
    // Composite transparent pixels on white so alpha does not silently become black.
    context.fillStyle = '#ffffff';
    context.fillRect(0, 0, 128, 128);
    context.drawImage(bitmap, 0, 0, 128, 128);
    const rgba = context.getImageData(0, 0, 128, 128).data;
    Object.assign(base, qualityMetrics(grayscale(rgba), 128, 128));
    base.meanRgb = meanRgb(rgba);
    canvas.width = 9;
    canvas.height = 8;
    context.fillStyle = '#ffffff';
    context.fillRect(0, 0, 9, 8);
    context.drawImage(bitmap, 0, 0, 9, 8);
    base.dhash = differenceHash(grayscale(context.getImageData(0, 0, 9, 8).data));
    const scale = Math.min(1, 280 / Math.max(bitmap.width, bitmap.height));
    canvas.width = Math.max(1, Math.round(bitmap.width * scale));
    canvas.height = Math.max(1, Math.round(bitmap.height * scale));
    context.fillStyle = '#ffffff';
    context.fillRect(0, 0, canvas.width, canvas.height);
    context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    base.thumbnail = await dataUrl(
      await canvas.convertToBlob({ type: 'image/jpeg', quality: 0.78 }),
    );
  } catch (error) {
    base.error = error instanceof Error ? error.message : 'Unsupported or corrupt image.';
  } finally {
    bitmap?.close();
  }
  return base;
}
scope.onmessage = async ({ data }) => {
  const start = performance.now();
  try {
    if (typeof OffscreenCanvas === 'undefined' || typeof createImageBitmap === 'undefined')
      throw new Error(
        'Image analysis requires a modern browser with worker canvas support. Try a recent Chrome, Edge, or Firefox.',
      );
    if (!crypto.subtle)
      throw new Error('Secure browser context required. Open SplitLens over HTTPS or localhost.');
    const images: ImageRecord[] = [];
    for (const input of data.inputs) {
      images.push(await analyze(input));
      scope.postMessage({ type: 'progress', done: images.length, total: data.inputs.length });
    }
    scope.postMessage({
      type: 'result',
      result: {
        images,
        findings: reanalyze(images, data.settings),
        settings: data.settings,
        elapsed: performance.now() - start,
      },
    });
  } catch (error) {
    scope.postMessage({
      type: 'error',
      message: error instanceof Error ? error.message : 'Analysis failed.',
    });
  }
};
