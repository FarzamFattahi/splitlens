import { describe, expect, it } from 'vitest';
import { zipSync, strToU8 } from 'fflate';
import {
  differenceHash,
  grayscale,
  hamming,
  inferMetadata,
  meanRgb,
  qualityMetrics,
  reanalyze,
} from '../src/engine';
import { importFiles } from '../src/imports';
import { DEFAULT_SETTINGS, type ImageRecord } from '../src/types';

const record = (id: string, overrides: Partial<ImageRecord> = {}): ImageRecord => ({
  id,
  path: `train/cat/${id}.jpg`,
  split: 'train',
  label: 'cat',
  width: 640,
  height: 480,
  bytes: 123,
  sha256: id,
  dhash: 'a55aa55aa55aa55a',
  brightness: 120,
  sharpness: 100,
  thumbnail: '',
  ...overrides,
});
const kinds = (images: ImageRecord[]) =>
  reanalyze(images, DEFAULT_SETTINGS).map((finding) => finding.kind);

describe('dataset metadata', () => {
  it('infers aliases without confusing substrings', () => {
    expect(inferMetadata('dataset\\VALID\\dogs\\frame.png')).toEqual({
      split: 'validation',
      label: 'dogs',
    });
    expect(inferMetadata('training/cats/cat.png')).toEqual({ split: 'train', label: 'cats' });
    expect(inferMetadata('testing/image.png')).toEqual({ split: 'test', label: 'unlabeled' });
    expect(inferMetadata('my-training-images/cat.png')).toEqual({
      split: 'unassigned',
      label: 'unlabeled',
    });
  });
});
describe('exact duplicates and leakage', () => {
  it('groups all matching SHA256 files and detects cross-split copies', () => {
    const findings = reanalyze(
      [
        record('a', { sha256: 'same' }),
        record('b', { sha256: 'same', split: 'test' }),
        record('c', { sha256: 'same', split: 'validation' }),
      ],
      DEFAULT_SETTINGS,
    );
    expect(findings.map((item) => item.kind)).toEqual(['leakage', 'duplicate']);
    expect(findings[0].imageIds).toEqual(['a', 'b', 'c']);
  });
  it('does not claim unassigned files form cross-split leakage', () => {
    expect(
      kinds([
        record('a', { sha256: 'same' }),
        record('b', { sha256: 'same', split: 'unassigned' }),
      ]),
    ).toEqual(['duplicate']);
  });
  it('does not put corrupt files in duplicate groups', () => {
    expect(
      kinds([
        record('a', { sha256: 'same', error: 'bad decode' }),
        record('b', { sha256: 'same' }),
      ]),
    ).toEqual(['broken']);
  });
});
describe('near duplicate candidates', () => {
  it('measures a genuine 64-bit Hamming distance', () => {
    expect(hamming('ffffffffffffffff', '0000000000000000')).toBe(64);
    expect(hamming('a55aa55aa55aa55a', 'a55aa55aa55aa55b')).toBe(1);
  });
  it('separately flags similar cross-split candidates', () => {
    const findings = reanalyze(
      [record('a'), record('b', { dhash: 'a55aa55aa55aa55b', split: 'test' })],
      DEFAULT_SETTINGS,
    );
    expect(findings.map((item) => item.kind)).toEqual(['leakage', 'similar']);
    expect(findings[0].distance).toBe(1);
  });
  it('gates mismatched exposure, aspect ratio, flat hashes, and distant hashes', () => {
    expect(kinds([record('a'), record('b', { brightness: 180 })])).toEqual([]);
    expect(kinds([record('a'), record('b', { width: 900 })])).toEqual([]);
    expect(
      kinds([
        record('a', { dhash: '0000000000000000' }),
        record('b', { dhash: '0000000000000001' }),
      ]),
    ).toEqual([]);
    expect(kinds([record('a'), record('b', { dhash: '5aa55aa55aa55aa5' })])).toEqual([]);
  });
  it('suppresses strongly different hues with otherwise identical grayscale geometry', () => {
    const copper = record('copper', { meanRgb: [222, 206, 193], brightness: 209.3 });
    const ceramic = record('ceramic', {
      split: 'test',
      meanRgb: [202, 211, 215],
      brightness: 208.76,
    });
    expect(kinds([copper, ceramic])).toEqual([]);
  });
  it('accepts mild color jitter and compatible additive exposure shifts', () => {
    const original = record('a', { meanRgb: [130, 120, 110], brightness: 121.85 });
    const jitter = record('b', {
      meanRgb: [138, 119, 116],
      brightness: 124.339,
      dhash: 'a55aa55aa55aa55b',
    });
    const brighter = record('c', { meanRgb: [145, 135, 125], brightness: 136.85 });
    expect(kinds([original, jitter])).toEqual(['similar']);
    expect(kinds([original, brighter])).toEqual(['similar']);
  });
  it('keeps SHA256 exact-copy findings regardless of color metadata', () => {
    expect(
      kinds([
        record('a', { sha256: 'same', meanRgb: [240, 80, 30] }),
        record('b', { sha256: 'same', split: 'test', meanRgb: [20, 80, 240] }),
      ]),
    ).toEqual(['leakage', 'duplicate']);
  });
  it('preserves compatibility with older records without mean color', () => {
    expect(kinds([record('a', { meanRgb: [240, 80, 30] }), record('b')])).toEqual(['similar']);
  });
  it('retuning the radius changes the result without decoding images', () => {
    const images = [record('a'), record('b', { dhash: 'a55aa55aa55aa55b' })];
    expect(reanalyze(images, { ...DEFAULT_SETTINGS, similarity: 0 })).toHaveLength(0);
    expect(reanalyze(images, { ...DEFAULT_SETTINGS, similarity: 1 })).toHaveLength(1);
  });
  it('BK-tree results match exhaustive comparison on varied hashes', () => {
    const base = 0xa55aa55aa55aa55an;
    const images = Array.from({ length: 30 }, (_, i) =>
      record(String(i), {
        dhash: (base ^ ((1n << BigInt(i)) | (1n << BigInt((i + 7) % 64))))
          .toString(16)
          .padStart(16, '0'),
      }),
    );
    const expected: string[] = [];
    for (let i = 0; i < images.length; i++)
      for (let j = i + 1; j < images.length; j++)
        if (hamming(images[i].dhash, images[j].dhash) <= 2) expected.push(`${i}:${j}`);
    const found = reanalyze(images, { ...DEFAULT_SETTINGS, similarity: 2 })
      .filter((item) => item.kind === 'similar')
      .map((item) => item.imageIds.join(':'));
    expect(found.sort()).toEqual(expected.sort());
  });
  it('summarizes dense candidate sets instead of allocating quadratic findings', () => {
    const images = Array.from({ length: 100 }, (_, i) =>
      record(String(i), { split: i % 2 ? 'test' : 'train' }),
    );
    const findings = reanalyze(images, DEFAULT_SETTINGS);
    expect(findings.filter((item) => item.kind === 'similar')).toHaveLength(2001);
    expect(findings.filter((item) => item.kind === 'leakage')).toHaveLength(2001);
    expect(
      findings.find((item) => item.title === '2950 additional similar pairs')?.detail,
    ).toContain('not necessarily all mutually similar');
    expect(
      findings.find((item) => item.title === '500 additional cross-split pairs'),
    ).toBeDefined();
  });
});
describe('quality measurements', () => {
  it('computes luminance with Rec.601 coefficients', () =>
    expect(grayscale(new Uint8ClampedArray([255, 0, 0, 255]))[0]).toBeCloseTo(76.245));
  it('computes channel means from composited RGB pixels', () =>
    expect(meanRgb(new Uint8ClampedArray([100, 50, 20, 255, 200, 100, 40, 255]))).toEqual([
      150, 75, 30,
    ]));
  it('gives a constant frame zero Laplacian variance', () =>
    expect(qualityMetrics(new Float64Array(128 * 128).fill(100), 128, 128)).toEqual({
      brightness: 100,
      sharpness: 0,
    }));
  it('finds high-frequency edges', () => {
    const pixels = Float64Array.from({ length: 128 * 128 }, (_, i) =>
      (i + Math.floor(i / 128)) % 2 ? 255 : 0,
    );
    expect(qualityMetrics(pixels, 128, 128).sharpness).toBeGreaterThan(100000);
  });
  it('hashes horizontal differences, validates dimensions', () => {
    expect(differenceHash(Float64Array.from({ length: 72 }, (_, i) => 9 - (i % 9)))).toBe(
      'ffffffffffffffff',
    );
    expect(differenceHash(Float64Array.from({ length: 72 }, (_, i) => i % 9))).toBe(
      '0000000000000000',
    );
    expect(() => differenceHash(new Float64Array(64))).toThrow('9 × 8');
  });
  it('emits exposure, blur and resolution hints', () =>
    expect(kinds([record('a', { brightness: 10, sharpness: 0, width: 20 })])).toEqual([
      'blur',
      'dark',
      'small',
    ]));
});
describe('safe imports', () => {
  it('keeps folder paths and skips non-image files', async () => {
    const file = new File(['png'], 'cat.png');
    Object.defineProperty(file, 'webkitRelativePath', { value: 'data/train/cat/cat.png' });
    const images = await importFiles([file, new File(['text'], 'readme.txt')]);
    expect(images).toHaveLength(1);
    expect(images[0].path).toBe('data/train/cat/cat.png');
  });
  it('imports a standard ZIP with nested paths', async () => {
    const bytes = zipSync({
      'data/train/cat/a.png': strToU8('image'),
      'README.txt': strToU8('info'),
    });
    const images = await importFiles([new File([bytes], 'dataset.zip')]);
    expect(images[0].path).toBe('data/train/cat/a.png');
    expect(await images[0].file.text()).toBe('image');
  });
  it('rejects traversal, invalid ZIP, and empty selections', async () => {
    await expect(
      importFiles([new File([zipSync({ '../cat.png': strToU8('bad') })], 'bad.zip')]),
    ).rejects.toThrow('Unsafe archive path');
    await expect(importFiles([new File(['zip?'], 'bad.zip')])).rejects.toThrow('Invalid ZIP');
    await expect(importFiles([new File(['text'], 'README.md')])).rejects.toThrow(
      'No supported images',
    );
  });
  it('checks image count before expansion', async () => {
    const entries = Object.fromEntries(
      Array.from({ length: 1501 }, (_, i) => [`${i}.png`, new Uint8Array(0)]),
    );
    await expect(importFiles([new File([zipSync(entries)], 'many.zip')])).rejects.toThrow(
      '1,500 image',
    );
  });
  it('rejects implausible compression ratios', async () => {
    const bytes = zipSync({ 'huge.bmp': new Uint8Array(2 * 1024 * 1024) });
    await expect(importFiles([new File([bytes], 'bomb.zip')])).rejects.toThrow(
      'unsafe expansion ratio',
    );
  });
  it('checks CRC integrity', async () => {
    const bytes = zipSync({ 'cat.png': strToU8('image') }, { level: 0 });
    const index = bytes.findIndex(
      (value, i) => value === 105 && bytes[i + 1] === 109 && bytes[i + 2] === 97,
    );
    bytes[index] = 104;
    await expect(importFiles([new File([bytes], 'corrupt.zip')])).rejects.toThrow(
      'Corrupt ZIP image',
    );
  });
});
