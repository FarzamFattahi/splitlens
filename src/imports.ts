import { Unzip, UnzipInflate } from 'fflate';
import type { InputImage } from './types';

export const IMPORT_LIMITS = {
  files: 1500,
  totalBytes: 300 * 1024 * 1024,
  fileBytes: 30 * 1024 * 1024,
};
const IMAGE_EXTENSION = /\.(jpe?g|png|webp|bmp|avif)$/i;
function safePath(path: string): string {
  const normalized = path.replaceAll('\\', '/');
  if (
    normalized.startsWith('/') ||
    /^[a-z]:/i.test(normalized) ||
    normalized.includes('\0') ||
    normalized.split('/').some((part) => part === '..')
  )
    throw new Error(`Unsafe archive path: ${path.slice(0, 100)}`);
  return normalized
    .split('/')
    .filter((part) => part && part !== '.')
    .join('/');
}
interface ZipEntry {
  path: string;
  size: number;
  crc: number;
}
function preflightZip(bytes: Uint8Array): Map<string, ZipEntry> {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  let end = -1;
  for (let offset = bytes.length - 22; offset >= Math.max(0, bytes.length - 65557); offset--) {
    if (
      view.getUint32(offset, true) === 0x06054b50 &&
      offset + 22 + view.getUint16(offset + 20, true) === bytes.length
    ) {
      end = offset;
      break;
    }
  }
  if (end < 0) throw new Error('Invalid ZIP: the central directory is missing.');
  const entries = view.getUint16(end + 10, true),
    directorySize = view.getUint32(end + 12, true),
    directoryStart = view.getUint32(end + 16, true);
  if (
    view.getUint16(end + 4, true) ||
    view.getUint16(end + 6, true) ||
    entries !== view.getUint16(end + 8, true)
  )
    throw new Error('Multi-part ZIP archives are not supported.');
  if (entries === 65535 || directorySize === 0xffffffff || directoryStart === 0xffffffff)
    throw new Error('ZIP64 archives are not supported.');
  if (entries > 10000 || directoryStart + directorySize > end)
    throw new Error('Invalid or oversized ZIP directory.');
  const allowed = new Map<string, ZipEntry>(),
    names = new Set<string>();
  let offset = directoryStart,
    total = 0;
  const decoder = new TextDecoder('utf-8', { fatal: true });
  for (let i = 0; i < entries; i++) {
    if (offset + 46 > end || view.getUint32(offset, true) !== 0x02014b50)
      throw new Error('Invalid ZIP directory entry.');
    const flags = view.getUint16(offset + 8, true),
      method = view.getUint16(offset + 10, true),
      compressed = view.getUint32(offset + 20, true),
      size = view.getUint32(offset + 24, true);
    const nameLength = view.getUint16(offset + 28, true),
      extraLength = view.getUint16(offset + 30, true),
      commentLength = view.getUint16(offset + 32, true);
    const next = offset + 46 + nameLength + extraLength + commentLength;
    if (next > directoryStart + directorySize || size === 0xffffffff || compressed === 0xffffffff)
      throw new Error('Invalid ZIP entry or unsupported ZIP64 data.');
    const rawName = bytes.subarray(offset + 46, offset + 46 + nameLength);
    const name =
      flags & 0x800
        ? decoder.decode(rawName)
        : Array.from(rawName, (byte) => String.fromCharCode(byte)).join('');
    const path = safePath(name);
    if (names.has(path)) throw new Error(`ZIP contains a duplicate path: ${path}`);
    names.add(path);
    if (flags & 1) throw new Error('Encrypted ZIP archives are not supported.');
    if (IMAGE_EXTENSION.test(path) && !name.endsWith('/')) {
      if (method !== 0 && method !== 8)
        throw new Error(`Unsupported ZIP compression for ${path}. Use a standard ZIP archive.`);
      if (size > IMPORT_LIMITS.fileBytes) throw new Error(`${path} exceeds the 30 MB image limit.`);
      if (size > Math.max(1024 * 1024, compressed * 200))
        throw new Error(`ZIP entry ${path} has an unsafe expansion ratio.`);
      total += size;
      if (total > IMPORT_LIMITS.totalBytes || allowed.size >= IMPORT_LIMITS.files)
        throw new Error('ZIP exceeds the 1,500 image or 300 MB expanded-data limit.');
      allowed.set(name, { path, size, crc: view.getUint32(offset + 16, true) });
    }
    offset = next;
  }
  if (offset !== directoryStart + directorySize) throw new Error('Invalid ZIP directory size.');
  return allowed;
}
function crc32(bytes: Uint8Array): number {
  let crc = -1;
  for (const byte of bytes) {
    crc ^= byte;
    for (let i = 0; i < 8; i++) crc = (crc >>> 1) ^ (0xedb88320 & -(crc & 1));
  }
  return (crc ^ -1) >>> 0;
}
function extractZip(
  bytes: Uint8Array,
  entries: Map<string, ZipEntry>,
): Array<{ path: string; bytes: Uint8Array }> {
  const result: Array<{ path: string; bytes: Uint8Array }> = [],
    started = new Set<string>();
  let actualTotal = 0;
  const unzip = new Unzip((file) => {
    safePath(file.name);
    const entry = entries.get(file.name);
    if (!entry) return;
    if (started.has(file.name)) throw new Error('ZIP contains duplicate local entries.');
    started.add(file.name);
    const chunks: Uint8Array[] = [];
    let length = 0;
    file.ondata = (error, data, final) => {
      if (error) throw new Error(`Could not decompress ${entry.path}: ${error.message}`);
      length += data.length;
      actualTotal += data.length;
      if (
        length > entry.size ||
        length > IMPORT_LIMITS.fileBytes ||
        actualTotal > IMPORT_LIMITS.totalBytes
      ) {
        file.terminate();
        throw new Error('ZIP expansion exceeded its declared size or safety limit.');
      }
      chunks.push(data);
      if (final) {
        if (length !== entry.size) throw new Error(`Truncated ZIP image: ${entry.path}`);
        const output = new Uint8Array(length);
        let offset = 0;
        for (const chunk of chunks) {
          output.set(chunk, offset);
          offset += chunk.length;
        }
        if (crc32(output) !== entry.crc) throw new Error(`Corrupt ZIP image: ${entry.path}`);
        result.push({ path: entry.path, bytes: output });
      }
    };
    file.start();
  });
  unzip.register(UnzipInflate);
  // Small compressed chunks cap transient allocations even if ZIP metadata lies.
  for (let offset = 0; offset < bytes.length; offset += 8192)
    unzip.push(bytes.subarray(offset, offset + 8192), offset + 8192 >= bytes.length);
  if (result.length !== entries.size)
    throw new Error('ZIP is incomplete or its local entries disagree with the directory.');
  return result;
}

export async function importFiles(files: File[]): Promise<InputImage[]> {
  if (files.reduce((total, file) => total + file.size, 0) > IMPORT_LIMITS.totalBytes)
    throw new Error('Selected files exceed the 300 MB import limit.');
  const images: InputImage[] = [];
  let totalBytes = 0;
  const append = (file: File, path: string) => {
    if (file.size > IMPORT_LIMITS.fileBytes)
      throw new Error(`${path} exceeds the 30 MB image limit.`);
    totalBytes += file.size;
    if (totalBytes > IMPORT_LIMITS.totalBytes || images.length >= IMPORT_LIMITS.files)
      throw new Error('Import exceeds 1,500 images or 300 MB of image data.');
    images.push({ id: `image-${images.length + 1}`, path, file });
  };
  for (const file of files) {
    const path = safePath(file.webkitRelativePath || file.name);
    if (/\.zip$/i.test(file.name)) {
      const bytes = new Uint8Array(await file.arrayBuffer());
      const entries = preflightZip(bytes);
      for (const entry of extractZip(bytes, entries))
        append(
          new File([entry.bytes.buffer as ArrayBuffer], entry.path.split('/').pop()!),
          entry.path,
        );
    } else if (IMAGE_EXTENSION.test(path)) append(file, path);
  }
  if (!images.length)
    throw new Error(
      'No supported images found. Choose JPG, PNG, WebP, BMP, AVIF images, an image folder, or a standard ZIP.',
    );
  return images;
}
