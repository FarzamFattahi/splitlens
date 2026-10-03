import type { AuditSettings, Finding, ImageRecord, Split } from './types';

const SPLITS: Record<string, Split> = {
  train: 'train',
  training: 'train',
  val: 'validation',
  valid: 'validation',
  validation: 'validation',
  test: 'test',
  testing: 'test',
};
export function inferMetadata(path: string): { split: Split; label: string } {
  const parts = path.replaceAll('\\', '/').split('/').filter(Boolean);
  const index = parts.findIndex((part) => SPLITS[part.toLowerCase()]);
  return {
    split: index < 0 ? 'unassigned' : SPLITS[parts[index].toLowerCase()],
    label: index >= 0 && index < parts.length - 2 ? parts[index + 1] : 'unlabeled',
  };
}

export function hamming(a: string, b: string): number {
  let bits = BigInt(`0x${a}`) ^ BigInt(`0x${b}`),
    count = 0;
  while (bits) {
    bits &= bits - 1n;
    count++;
  }
  return count;
}

// A BK-tree searches only branches that can lie inside the Hamming radius.
class HashIndex {
  private root?: {
    hash: string;
    records: ImageRecord[];
    children: Map<number, NonNullable<HashIndex['root']>>;
  };
  add(record: ImageRecord) {
    if (!this.root) {
      this.root = { hash: record.dhash, records: [record], children: new Map() };
      return;
    }
    let node = this.root;
    while (true) {
      const distance = hamming(record.dhash, node.hash);
      if (distance === 0) {
        node.records.push(record);
        return;
      }
      const next = node.children.get(distance);
      if (next) node = next;
      else {
        node.children.set(distance, { hash: record.dhash, records: [record], children: new Map() });
        return;
      }
    }
  }
  search(hash: string, radius: number): Array<{ record: ImageRecord; distance: number }> {
    const matches: Array<{ record: ImageRecord; distance: number }> = [];
    const stack = this.root ? [this.root] : [];
    while (stack.length) {
      const node = stack.pop()!;
      const distance = hamming(hash, node.hash);
      if (distance <= radius) for (const record of node.records) matches.push({ record, distance });
      for (const [edge, child] of node.children)
        if (edge >= distance - radius && edge <= distance + radius) stack.push(child);
    }
    return matches;
  }
}

export function grayscale(rgba: Uint8ClampedArray): Float64Array {
  const pixels = new Float64Array(rgba.length / 4);
  for (let i = 0; i < pixels.length; i++)
    pixels[i] = rgba[i * 4] * 0.299 + rgba[i * 4 + 1] * 0.587 + rgba[i * 4 + 2] * 0.114;
  return pixels;
}

export function meanRgb(rgba: Uint8ClampedArray): [number, number, number] {
  const channels: [number, number, number] = [0, 0, 0];
  const count = rgba.length / 4;
  if (!count) return channels;
  for (let i = 0; i < rgba.length; i += 4)
    for (let channel = 0; channel < 3; channel++) channels[channel] += rgba[i + channel];
  return channels.map((value) => value / count) as [number, number, number];
}

export function qualityMetrics(
  pixels: Float64Array,
  width: number,
  height: number,
): { brightness: number; sharpness: number } {
  let brightness = 0,
    sum = 0,
    squares = 0,
    count = 0;
  for (const value of pixels) brightness += value;
  for (let y = 1; y < height - 1; y++)
    for (let x = 1; x < width - 1; x++) {
      const i = y * width + x;
      const laplacian =
        pixels[i - width] + pixels[i + width] + pixels[i - 1] + pixels[i + 1] - 4 * pixels[i];
      sum += laplacian;
      squares += laplacian * laplacian;
      count++;
    }
  return {
    brightness: pixels.length ? brightness / pixels.length : 0,
    sharpness: count ? Math.max(0, squares / count - (sum / count) ** 2) : 0,
  };
}

export function differenceHash(pixels: Float64Array): string {
  if (pixels.length !== 72) throw new Error('dHash requires a 9 × 8 grayscale image.');
  let value = 0n;
  for (let y = 0; y < 8; y++)
    for (let x = 0; x < 8; x++)
      value = (value << 1n) | (pixels[y * 9 + x] > pixels[y * 9 + x + 1] ? 1n : 0n);
  return value.toString(16).padStart(16, '0');
}

export function reanalyze(images: ImageRecord[], settings: AuditSettings): Finding[] {
  const findings: Finding[] = [];
  const exact = new Map<string, ImageRecord[]>();
  const add = (
    kind: Finding['kind'],
    records: ImageRecord[],
    title: string,
    detail: string,
    distance?: number,
  ) => {
    findings.push({
      id: `${kind}:${records.map((record) => record.id).join(':')}`,
      kind,
      imageIds: records.map((record) => record.id),
      title,
      detail,
      ...(distance === undefined ? {} : { distance }),
    });
  };
  const crossesSplit = (records: ImageRecord[]) =>
    new Set(records.map((record) => record.split).filter((split) => split !== 'unassigned')).size >
    1;
  for (const record of images) {
    if (record.error) {
      add('broken', [record], 'Image could not be decoded', record.error);
      continue;
    }
    if (record.sha256) {
      const group = exact.get(record.sha256) ?? [];
      group.push(record);
      exact.set(record.sha256, group);
    }
    if (record.sharpness < settings.blur)
      add(
        'blur',
        [record],
        'Low edge detail',
        `Laplacian variance ${record.sharpness.toFixed(1)} on a 128 × 128 grayscale preview. Smooth subjects can also trigger this check.`,
      );
    if (record.brightness < settings.dark)
      add(
        'dark',
        [record],
        'Dark exposure',
        `Mean grayscale brightness ${record.brightness.toFixed(1)} / 255.`,
      );
    if (record.brightness > settings.bright)
      add(
        'bright',
        [record],
        'Bright exposure',
        `Mean grayscale brightness ${record.brightness.toFixed(1)} / 255.`,
      );
    if (Math.min(record.width, record.height) < settings.minSize)
      add(
        'small',
        [record],
        'Small image',
        `${record.width} × ${record.height} px; the shortest side is below ${settings.minSize} px.`,
      );
  }
  for (const group of exact.values())
    if (group.length > 1) {
      add(
        'duplicate',
        group,
        'Identical file copies',
        `${group.length} files share the same SHA-256 digest.`,
      );
      if (crossesSplit(group))
        add(
          'leakage',
          group,
          'Exact copies across splits',
          'Identical file bytes occur in multiple assigned splits. Review these copies before evaluating your model.',
        );
    }
  const index = new HashIndex();
  const pairLimit = 2000;
  let similarPairs = 0,
    leakagePairs = 0;
  const omittedSimilar = new Set<ImageRecord>(),
    omittedLeakage = new Set<ImageRecord>();
  const radius = Math.max(0, Math.min(12, Math.floor(settings.similarity)));
  for (const record of images) {
    if (record.error || !/^[0-9a-f]{16}$/i.test(record.dhash) || record.height <= 0) continue;
    const ones = hamming(record.dhash, '0000000000000000');
    // Flat hashes produce large false-positive groups (blank frames, gradients).
    if (ones < 5 || ones > 59) continue;
    for (const { record: other, distance } of index.search(record.dhash, radius)) {
      if (record.sha256 && record.sha256 === other.sha256) continue;
      const ratio = record.width / record.height,
        otherRatio = other.width / other.height;
      if (
        Math.abs(Math.log(ratio / otherRatio)) > 0.04 ||
        Math.abs(record.brightness - other.brightness) > 25
      )
        continue;
      // Subtract luminance from each channel: an exposure shift remains compatible,
      // while a strong hue change is less likely to be the same underlying image.
      if (
        record.meanRgb &&
        other.meanRgb &&
        record.meanRgb.some(
          (channel, i) =>
            Math.abs(channel - record.brightness - (other.meanRgb![i] - other.brightness)) > 12,
        )
      )
        continue;
      const pair = [other, record];
      similarPairs++;
      if (similarPairs <= pairLimit)
        add(
          'similar',
          pair,
          'Visually similar pair',
          `64-bit dHash distance ${distance} / 64, with compatible aspect ratio, exposure, and available mean-color measurements. Confirm visually; this is a candidate, not proof of identity.`,
          distance,
        );
      else for (const item of pair) omittedSimilar.add(item);
      if (crossesSplit(pair)) {
        leakagePairs++;
        if (leakagePairs <= pairLimit)
          add(
            'leakage',
            pair,
            'Similar images across splits',
            `A near-duplicate candidate spans assigned splits (dHash distance ${distance} / 64). Confirm visually before moving or excluding a file.`,
            distance,
          );
        else for (const item of pair) omittedLeakage.add(item);
      }
    }
    index.add(record);
  }
  if (omittedSimilar.size)
    add(
      'similar',
      [...omittedSimilar],
      `${similarPairs - pairLimit} additional similar pairs`,
      'This dense dataset exceeds the 2,000 detailed pair limit. These images participate in additional candidates; they are not necessarily all mutually similar. Lower the similarity distance or audit smaller batches to inspect each pair.',
    );
  if (omittedLeakage.size)
    add(
      'leakage',
      [...omittedLeakage],
      `${leakagePairs - pairLimit} additional cross-split pairs`,
      'This dense dataset exceeds the 2,000 detailed leakage pair limit. These images participate in additional cross-split candidates; the full pair list is summarized to keep memory bounded. Lower the similarity distance or audit smaller batches.',
    );
  const priority: Record<Finding['kind'], number> = {
    leakage: 0,
    duplicate: 1,
    similar: 2,
    broken: 3,
    blur: 4,
    dark: 5,
    bright: 6,
    small: 7,
  };
  return findings.sort((a, b) => priority[a.kind] - priority[b.kind]);
}
