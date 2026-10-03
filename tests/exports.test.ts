import { describe, expect, it } from 'vitest';
import {
  buildHtml,
  buildManifest,
  buildReport,
  csvCell,
  escapeHtml,
  prepareDatasetEntries,
  reviewDecision,
  safeArchivePath,
  safeFilename,
} from '../src/exports';
import { DEFAULT_SETTINGS, type AuditResult, type ImageRecord } from '../src/types';

const record = (id: string, path = `train/class/${id}.png`): ImageRecord => ({
  id,
  path,
  split: 'train',
  label: 'class',
  width: 512,
  height: 384,
  bytes: 4,
  sha256: 'abc',
  dhash: 'abcd',
  brightness: 120,
  sharpness: 100,
  thumbnail: 'data:image/png;base64,YWJj',
});
const result: AuditResult = {
  images: [record('a'), record('b'), record('c')],
  findings: [
    {
      id: 'pair',
      kind: 'duplicate',
      imageIds: ['a', 'b'],
      title: 'Duplicate files',
      detail: 'Same bytes',
    },
  ],
  settings: DEFAULT_SETTINGS,
  elapsed: 100,
};

describe('safe exports', () => {
  it('escapes untrusted HTML characters', () => {
    expect(escapeHtml('<img src=x onerror="bad"> & \'')).toBe(
      '&lt;img src=x onerror=&quot;bad&quot;&gt; &amp; &#39;',
    );
  });
  it('neutralizes spreadsheet formula injection without corrupting CSV quoting', () => {
    expect(csvCell('=HYPERLINK("evil")')).toBe('"\'=HYPERLINK(""evil"")"');
    expect(csvCell('  +cmd')).toBe('"\'  +cmd"');
    expect(csvCell('\tformula')).toBe('"\'\tformula"');
    expect(csvCell('ordinary,path')).toBe('"ordinary,path"');
  });
  it('uses only explicit decisions and leaves the default unreviewed', () => {
    expect(reviewDecision('a', { a: 'keep' })).toBe('keep');
    expect(reviewDecision('b', { a: 'keep' })).toBe('unreviewed');
    expect(reviewDecision('toString', {})).toBe('unreviewed');
  });
  it('omits thumbnails and exports all rows with explicit review state', () => {
    const report = buildReport(result, { a: 'keep', b: 'exclude' }, 'My dataset');
    expect(report.images.map((image) => image.decision)).toEqual(['keep', 'exclude', 'unreviewed']);
    expect(JSON.stringify(report)).not.toContain('thumbnail');
    const csv = buildManifest(result, { b: 'exclude' });
    expect(csv).toContain('"exclude"');
    expect(csv).toContain('"unreviewed"');
    expect(csv.split('\r\n')).toHaveLength(4);
  });
  it('escapes titles, paths and findings and rejects unsafe thumbnail URLs', () => {
    const unsafe: AuditResult = {
      ...result,
      images: [{ ...record('a', '<script>alert(1)</script>'), thumbnail: 'javascript:alert(1)' }],
      findings: [{ ...result.findings[0], title: '<svg onload="bad">', imageIds: ['a'] }],
    };
    const html = buildHtml(unsafe, {}, '<script>name</script>');
    expect(html).not.toContain('<script>');
    expect(html).not.toContain('javascript:');
    expect(html).toContain('&lt;svg onload=&quot;bad&quot;&gt;');
    expect(html).toContain('Preview unavailable');
  });
  it('sanitizes filenames and traversal without losing split directories', () => {
    expect(safeFilename('../../My dataset?!')).toBe('My-dataset');
    expect(safeFilename('!?')).toBe('splitlens');
    expect(safeArchivePath('../../train\\CON.png')).toBe('train/_CON.png');
    expect(safeArchivePath('test/class/a:b.png')).toBe('test/class/a_b.png');
  });
  it('preserves kept and unreviewed bytes, excludes only explicit exclusions, handles collisions', async () => {
    const audit: AuditResult = {
      ...result,
      images: [record('a', 'train/class/a:b.png'), record('b'), record('c', 'train/class/a?b.png')],
    };
    const inputs = audit.images.map((image) => ({
      id: image.id,
      path: image.path,
      file: new File([image.id], image.path, { type: 'image/png' }),
    }));
    const entries = await prepareDatasetEntries(audit, inputs, { a: 'keep', b: 'exclude' });
    expect(new TextDecoder().decode(entries['images/train/class/a_b.png'])).toBe('a');
    expect(new TextDecoder().decode(entries['images/train/class/a_b-2.png'])).toBe('c');
    expect(Object.keys(entries)).toHaveLength(4);
    expect(entries['images/train/class/b.png']).toBeUndefined();
    expect(new TextDecoder().decode(entries['manifest.csv'])).toContain(
      '"images/train/class/a_b-2.png"',
    );
  });
  it('fails explicitly if an included original is missing', async () => {
    await expect(prepareDatasetEntries(result, [], {})).rejects.toThrow(
      'Original file unavailable',
    );
  });
});
