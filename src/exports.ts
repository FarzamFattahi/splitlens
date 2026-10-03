import { strToU8, zip } from 'fflate';
import type { AuditResult, Decision, InputImage } from './types';

export const escapeHtml = (value: unknown): string =>
  String(value ?? '').replace(
    /[&<>"']/g,
    (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!,
  );

/** Quote every cell and neutralize formulas, including formulas prefixed by whitespace. */
export function csvCell(value: unknown): string {
  let text = String(value ?? '');
  if (/^[\s\uFEFF]*[=+@-]/.test(text) || /^[\t\r\n]/.test(text)) text = `'${text}`;
  return `"${text.replace(/"/g, '""')}"`;
}

export function safeFilename(name: string): string {
  const clean = name
    .normalize('NFKC')
    .replace(/[^a-zA-Z0-9_-]+/g, '-')
    .replace(/^[-_]+|[-_]+$/g, '')
    .slice(0, 72);
  return clean || 'splitlens';
}

export function reviewDecision(
  id: string,
  decisions: Record<string, Decision>,
): 'keep' | 'exclude' | 'unreviewed' {
  const decision = Object.prototype.hasOwnProperty.call(decisions, id) ? decisions[id] : undefined;
  return decision === 'keep' || decision === 'exclude' ? decision : 'unreviewed';
}

export function buildReport(
  result: AuditResult,
  decisions: Record<string, Decision>,
  name: string,
) {
  return {
    schemaVersion: 1,
    tool: 'SplitLens',
    dataset: name,
    exportedAt: new Date().toISOString(),
    methodology:
      'SHA-256 byte equality; 64-bit difference hash from a 9 × 8 grayscale image; mean grayscale intensity and variance of a four-neighbor Laplacian on a 128 × 128 image. Alpha is composited on white. Near pairs require compatible aspect ratio and exposure; low-information hashes are skipped. Findings are review suggestions, not automatic exclusions.',
    settings: result.settings,
    elapsedMs: result.elapsed,
    images: result.images.map(({ thumbnail: _thumbnail, ...image }) => ({
      ...image,
      decision: reviewDecision(image.id, decisions),
    })),
    findings: result.findings,
  };
}

export function buildManifest(
  result: AuditResult,
  decisions: Record<string, Decision>,
  archivePaths?: Map<string, string>,
): string {
  const header = [
    'id',
    'path',
    'archive_path',
    'split',
    'label',
    'decision',
    'width',
    'height',
    'bytes',
    'sha256',
    'dhash',
    'brightness',
    'sharpness',
    'issues',
    'decode_error',
  ];
  const rows = result.images.map((image) => [
    image.id,
    image.path,
    archivePaths?.get(image.id) ?? '',
    image.split,
    image.label,
    reviewDecision(image.id, decisions),
    image.width,
    image.height,
    image.bytes,
    image.sha256,
    image.dhash,
    image.brightness,
    image.sharpness,
    [
      ...new Set(result.findings.filter((f) => f.imageIds.includes(image.id)).map((f) => f.kind)),
    ].join(';'),
    image.error ?? '',
  ]);
  return '\uFEFF' + [header, ...rows].map((row) => row.map(csvCell).join(',')).join('\r\n');
}

function safeThumbnail(source: string): string {
  return /^data:image\/(?:png|jpeg|webp);base64,[a-zA-Z0-9+/=]+$/.test(source) ? source : '';
}

export function buildHtml(
  result: AuditResult,
  decisions: Record<string, Decision>,
  name: string,
): string {
  const images = new Map(result.images.map((image) => [image.id, image]));
  const imageCard = (id: string) => {
    const record = images.get(id);
    if (!record) return '<p>Image unavailable</p>';
    const source = safeThumbnail(record.thumbnail);
    return `<figure>${source ? `<img src="${source}" alt="${escapeHtml(record.path)}">` : '<div class="missing">Preview unavailable</div>'}<figcaption><strong>${escapeHtml(record.path)}</strong><span>${escapeHtml(record.split)} · ${record.width} × ${record.height} · ${reviewDecision(id, decisions)}</span>${record.error ? `<span>${escapeHtml(record.error)}</span>` : ''}</figcaption></figure>`;
  };
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'"><title>${escapeHtml(name)} — SplitLens audit</title><style>
  *{box-sizing:border-box}body{margin:0;background:#f7f8fa;color:#242b39;font:16px/1.6 system-ui,sans-serif}main{max-width:1100px;margin:auto;padding:56px 24px}h1{font-size:42px;line-height:1.15;letter-spacing:-1.5px}h2{margin:0 0 12px;font-size:22px}h3{margin:0;font-size:17px}.eyebrow{font:12px monospace;letter-spacing:2px;text-transform:uppercase;color:#245bd8}.stats{display:flex;gap:24px;flex-wrap:wrap;margin:32px 0}.stats div{padding:16px 24px;background:#fff;border:1px solid #e0e5ee;border-radius:12px}.stats b{display:block;font-size:28px}section{margin:32px 0;padding:24px;border:1px solid #e0e5ee;background:#fff;border-radius:16px}.evidence,.inventory{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:16px}figure{margin:0;background:#f5f7fb;border:1px solid #e1e6ee;border-radius:10px;overflow:hidden}img{display:block;width:100%;height:180px;object-fit:contain;background:#edf0f6}figcaption{padding:12px;font-size:12px;overflow-wrap:anywhere}figcaption span{display:block;color:#58687e}.missing{height:180px;display:grid;place-items:center;color:#5d6e87}p{max-width:85ch}.pill{font:11px monospace;text-transform:uppercase;color:#245bd8}code{font-size:12px;overflow-wrap:anywhere}@media print{body{background:white}section,figure{break-inside:avoid}main{padding:0}h1{font-size:28px}}
  </style></head><body><main><p class="eyebrow">SplitLens / Dataset quality audit</p><h1>${escapeHtml(name)}</h1><p>Exported ${escapeHtml(new Date().toISOString())}. Findings help you investigate dataset quality. Every decision is yours.</p><div class="stats"><div><b>${result.images.length}</b>images</div><div><b>${result.findings.length}</b>findings</div><div><b>${result.images.filter((i) => reviewDecision(i.id, decisions) === 'exclude').length}</b>manually excluded</div></div>
  <section><h2>How to interpret this report</h2><p>Exact matches use SHA-256 over original file bytes. Cross-split exact or perceptually similar pairs are leakage candidates. A 64-bit difference hash compares adjacent grayscale pixels in a 9 × 8 image; a small distance is a suggestion, not proof. Near pairs require compatible aspect ratio and exposure, and low-information hashes are skipped. Blurriness uses variance of a four-neighbor Laplacian; low-detail products may score low even when focused. Exposure uses mean grayscale brightness. Small images and decode failures need a separate review.</p><p>Quality analysis resizes each image to 128 × 128. Transparent pixels are composited on white. These heuristics are not learned embeddings, an accuracy guarantee, or a substitute for reviewing labels. A hash comparison cannot establish whether independent source captures share a subject.</p><p>Settings: similarity distance ≤ ${escapeHtml(result.settings.similarity)}; blur &lt; ${escapeHtml(result.settings.blur)}; dark &lt; ${escapeHtml(result.settings.dark)}; bright &gt; ${escapeHtml(result.settings.bright)}; shortest side &lt; ${escapeHtml(result.settings.minSize)} px.</p><p>The clean ZIP excludes only images you explicitly marked <strong>exclude</strong>. Kept and unreviewed originals remain unchanged. Audit suggestions never delete files.</p></section>
  ${result.findings.map((finding) => `<section><p class="pill">${escapeHtml(finding.kind)}${finding.distance !== undefined ? ` · hash distance ${escapeHtml(finding.distance)}` : ''}</p><h2>${escapeHtml(finding.title)}</h2><p>${escapeHtml(finding.detail)}</p><div class="evidence">${finding.imageIds.map(imageCard).join('')}</div></section>`).join('')}
  <section><h2>All images and decisions</h2><div class="inventory">${result.images.map((i) => imageCard(i.id)).join('')}</div></section><footer>SplitLens · Private, browser-based analysis · No images uploaded by this report.</footer></main></body></html>`;
}

function download(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 30_000);
}

export function downloadReport(
  result: AuditResult,
  decisions: Record<string, Decision>,
  name: string,
): void {
  download(
    new Blob([JSON.stringify(buildReport(result, decisions, name), null, 2)], {
      type: 'application/json',
    }),
    `${safeFilename(name)}-audit.json`,
  );
}
export function downloadManifest(
  result: AuditResult,
  decisions: Record<string, Decision>,
  name: string,
): void {
  download(
    new Blob([buildManifest(result, decisions)], { type: 'text/csv;charset=utf-8' }),
    `${safeFilename(name)}-manifest.csv`,
  );
}
export function downloadHtml(
  result: AuditResult,
  decisions: Record<string, Decision>,
  name: string,
): void {
  download(
    new Blob([buildHtml(result, decisions, name)], { type: 'text/html;charset=utf-8' }),
    `${safeFilename(name)}-report.html`,
  );
}

/** Remove traversal, Windows-special names, control characters and filesystem delimiters. */
export function safeArchivePath(path: string): string {
  const parts = path
    .replace(/\\/g, '/')
    .split('/')
    .filter((part) => part && part !== '.' && part !== '..')
    .map((part) => {
      let clean =
        part
          .replace(/[<>:"|?*\x00-\x1F]/g, '_')
          .replace(/[. ]+$/g, '')
          .slice(0, 120) || '_';
      if (/^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)/i.test(clean)) clean = `_${clean}`;
      return clean;
    });
  return parts.join('/') || 'image';
}

export async function prepareDatasetEntries(
  result: AuditResult,
  inputs: InputImage[],
  decisions: Record<string, Decision>,
): Promise<Record<string, Uint8Array>> {
  const entries: Record<string, Uint8Array> = Object.create(null);
  const originals = new Map(inputs.map((input) => [input.id, input]));
  const archivePaths = new Map<string, string>();
  const usedPaths = new Set<string>();
  for (const image of result.images) {
    if (reviewDecision(image.id, decisions) === 'exclude') continue;
    const input = originals.get(image.id);
    if (!input)
      throw new Error(
        `Original file unavailable: ${image.path}. Please run the audit again before exporting.`,
      );
    const safe = `images/${safeArchivePath(image.path)}`;
    let target = safe;
    let count = 2;
    while (usedPaths.has(target.toLocaleLowerCase('en-US'))) {
      const dot = safe.lastIndexOf('.');
      const slash = safe.lastIndexOf('/');
      target =
        dot > slash ? `${safe.slice(0, dot)}-${count++}${safe.slice(dot)}` : `${safe}-${count++}`;
    }
    usedPaths.add(target.toLocaleLowerCase('en-US'));
    entries[target] = new Uint8Array(await input.file.arrayBuffer());
    archivePaths.set(image.id, target);
  }
  entries['manifest.csv'] = strToU8(buildManifest(result, decisions, archivePaths));
  entries['README.txt'] = strToU8(
    'SplitLens reviewed dataset\n\nOnly manually excluded images were removed from this export. Kept and unreviewed original files are included without re-encoding. Broken files remain unless excluded. The manifest includes all audited images, decisions, and safe archive paths. Empty archive paths denote excluded images. Paths are sanitized and renamed when necessary to prevent unsafe or colliding archive entries.\n',
  );
  return entries;
}

export async function downloadCleanDataset(
  result: AuditResult,
  inputs: InputImage[],
  decisions: Record<string, Decision>,
  name: string,
): Promise<void> {
  const entries = await prepareDatasetEntries(result, inputs, decisions);
  const bytes = await new Promise<Uint8Array>((resolve, reject) =>
    zip(entries, { level: 1 }, (error, data) => (error ? reject(error) : resolve(data))),
  );
  download(
    new Blob([new Uint8Array(bytes).buffer], { type: 'application/zip' }),
    `${safeFilename(name)}-reviewed.zip`,
  );
}
