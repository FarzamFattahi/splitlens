import { test, expect, type Page, type Download } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { join } from 'node:path';
import { unzipSync, zipSync, strToU8 } from 'fflate';

async function ready(page: Page) {
  await page.goto('/');
  await expect(
    page.getByRole('heading', { name: 'Product inspection', exact: true }),
  ).toBeVisible();
  await expect(page.getByRole('button', { name: 'Import dataset', exact: true })).toBeEnabled();
}
async function navigate(page: Page, name: string) {
  await page
    .getByRole('navigation', { name: 'Workspace navigation' })
    .getByRole('button', { name })
    .click();
}
async function downloadBytes(download: Download) {
  const path = await download.path();
  expect(path).toBeTruthy();
  return readFile(path!);
}
async function download(page: Page, name: string) {
  const pending = page.waitForEvent('download');
  await page.getByRole('button', { name, exact: true }).click();
  return downloadBytes(await pending);
}

test('demo runs the actual worker, exposes leakage evidence, and reviews individual images', async ({
  page,
}) => {
  const errors: string[] = [];
  const remoteRequests: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  page.on('request', (request) => {
    if (/^https?:/.test(request.url()) && new URL(request.url()).hostname !== '127.0.0.1')
      remoteRequests.push(request.url());
  });
  await ready(page);
  await expect(
    page.locator('.metric').filter({ hasText: 'Images analyzed' }).locator('strong'),
  ).toHaveText('29');
  await navigate(page, 'Review findings');
  await page.getByRole('button', { name: /^Leakage/ }).click();
  await page.locator('.finding-row').first().click();
  const dialog = page.getByRole('dialog');
  await expect(dialog.getByRole('heading', { name: 'Split leakage', exact: true })).toBeVisible();
  await expect(dialog.locator('.evidence')).toHaveCount(2);
  await dialog.getByRole('button', { name: 'Exclude', exact: true }).last().click();
  await expect(dialog.getByRole('button', { name: 'Exclude', exact: true }).last()).toHaveAttribute(
    'aria-pressed',
    'true',
  );
  await dialog.getByRole('button', { name: 'Keep', exact: true }).first().click();
  await dialog.getByRole('button', { name: 'Done', exact: true }).click();
  await expect(page.locator('.finding-row').first()).toContainText('Reviewed');
  await navigate(page, 'Export & handoff');
  await expect(page.locator('.export-summary')).toContainText(
    '2 reviewed · 1 excluded · 28 included',
  );
  expect(errors).toEqual([]);
  expect(remoteRequests).toEqual([]);
});

test('filename search, split corrections, settings reanalysis and decisions stay consistent', async ({
  page,
}) => {
  await ready(page);
  await navigate(page, 'Image library');
  await page.getByRole('textbox', { name: 'Search filenames' }).fill('thumbnail-only');
  await expect(page.locator('.image-card')).toHaveCount(1);
  await page
    .getByRole('combobox', { name: 'Split for test/ceramic/thumbnail-only.png', exact: true })
    .selectOption('validation');
  await page.getByRole('combobox', { name: 'Filter by split', exact: true }).selectOption('test');
  await expect(page.getByRole('heading', { name: 'No matching images' })).toBeVisible();
  await page
    .getByRole('combobox', { name: 'Filter by split', exact: true })
    .selectOption('validation');
  await page.locator('.image-preview').click();
  await page.getByRole('dialog').getByRole('button', { name: 'Keep', exact: true }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Done', exact: true }).click();
  await page.getByRole('button', { name: 'Audit settings', exact: true }).click();
  const settings = page.getByRole('dialog');
  const minimum = settings.getByRole('slider', { name: /Minimum shortest side/ });
  await minimum.focus();
  await page.keyboard.press('Home');
  await settings.getByRole('button', { name: 'Apply settings', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('review decisions are preserved');
  await navigate(page, 'Export & handoff');
  const report = JSON.parse((await download(page, 'Download JSON')).toString());
  expect(report.settings.minSize).toBe(0);
  const image = report.images.find((item: { path: string }) =>
    item.path.endsWith('thumbnail-only.png'),
  );
  expect(image).toMatchObject({ split: 'validation', decision: 'keep' });
  expect(report.findings.some((finding: { kind: string }) => finding.kind === 'small')).toBe(false);
});

test('JSON, CSV, standalone HTML and curated ZIP agree and keep original bytes', async ({
  page,
}) => {
  await ready(page);
  await navigate(page, 'Image library');
  await page.getByRole('textbox', { name: 'Search filenames' }).fill('copy-from-train');
  await page.locator('.image-preview').click();
  await page.getByRole('dialog').getByRole('button', { name: 'Exclude', exact: true }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Done', exact: true }).click();
  await navigate(page, 'Export & handoff');
  const report = JSON.parse((await download(page, 'Download JSON')).toString());
  expect(report).toMatchObject({
    schemaVersion: 1,
    tool: 'SplitLens',
    dataset: 'Product inspection',
  });
  expect(report.images).toHaveLength(29);
  expect(
    report.images.filter((image: { decision: string }) => image.decision === 'exclude'),
  ).toHaveLength(1);
  expect(report.images[0]).not.toHaveProperty('thumbnail');
  const csv = (await download(page, 'Download CSV')).toString('utf8');
  expect(csv.startsWith('\uFEFF"id","path","archive_path"')).toBe(true);
  expect(csv.split('\r\n')).toHaveLength(30);
  expect(csv).toContain(
    '"validation/ceramic/copy-from-train.png","","validation","ceramic","exclude"',
  );
  const html = (await download(page, 'Download report')).toString();
  expect(html).toContain('Content-Security-Policy');
  expect(html).toContain('data:image/');
  expect(html).toContain('All images and decisions');
  expect(html).toContain('validation/ceramic/copy-from-train.png');
  expect(html).not.toMatch(/<script\b|https?:\/\//i);
  const entries = unzipSync(await download(page, 'Export dataset ZIP'));
  const imagePaths = Object.keys(entries).filter((path) => path.startsWith('images/'));
  expect(imagePaths).toHaveLength(28);
  expect(entries['images/validation/ceramic/copy-from-train.png']).toBeUndefined();
  for (const image of report.images.filter(
    (item: { decision: string }) => item.decision !== 'exclude',
  )) {
    const bytes = entries[`images/${image.path}`];
    expect(bytes, image.path).toBeDefined();
    expect(bytes.length).toBe(image.bytes);
    expect(createHash('sha256').update(bytes).digest('hex')).toBe(image.sha256);
  }
  expect(new TextDecoder().decode(entries['manifest.csv'])).toContain('"exclude"');
  expect(new TextDecoder().decode(entries['README.txt'])).toContain('without re-encoding');
});

test('local PNG and folder import, unreadable images, ZIP splits and archive validation', async ({
  page,
}, testInfo) => {
  await ready(page);
  // Generate a real PNG fixture without a second native image dependency.
  const png = Buffer.from(
    await page.evaluate(() => {
      const canvas = document.createElement('canvas');
      canvas.width = 320;
      canvas.height = 256;
      const context = canvas.getContext('2d')!;
      context.fillStyle = '#386658';
      context.fillRect(0, 0, 320, 256);
      context.fillStyle = '#eedbb1';
      context.fillRect(90, 40, 130, 190);
      return canvas.toDataURL('image/png').split(',')[1];
    }),
    'base64',
  );
  const upload = page.locator('input[type=file]').first();
  await upload.setInputFiles([
    { name: 'valid.png', mimeType: 'image/png', buffer: png },
    { name: 'broken.png', mimeType: 'image/png', buffer: Buffer.from('not image bytes') },
  ]);
  await expect(page.getByRole('heading', { name: 'My image dataset', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Import dataset', exact: true })).toBeEnabled();
  await navigate(page, 'Image library');
  await expect(page.locator('.image-card')).toHaveCount(2);
  await expect(page.locator('.broken-image')).toContainText('Unreadable');
  await upload.setInputFiles({
    name: 'my-collection.zip',
    mimeType: 'application/zip',
    buffer: Buffer.from(zipSync({ 'train/product/a.png': png, 'val/product/b.png': png })),
  });
  await expect(page.getByRole('heading', { name: 'my-collection', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Import dataset', exact: true })).toBeEnabled();
  await expect(
    page.locator('.metric').filter({ hasText: 'Leakage candidates' }).locator('strong'),
  ).toHaveText('1');
  await upload.setInputFiles({
    name: 'broken.zip',
    mimeType: 'application/zip',
    buffer: Buffer.from('this is not a zip'),
  });
  await expect(page.getByRole('alert')).toContainText('Invalid ZIP');
  await expect(page.getByRole('heading', { name: 'my-collection', exact: true })).toBeVisible();
  await upload.setInputFiles({
    name: 'unsafe.zip',
    mimeType: 'application/zip',
    buffer: Buffer.from(zipSync({ '../escape.png': png })),
  });
  await expect(page.getByRole('alert')).toContainText('Unsafe archive path');
  await upload.setInputFiles({
    name: 'empty.zip',
    mimeType: 'application/zip',
    buffer: Buffer.from(zipSync({ 'notes.txt': strToU8('no images') })),
  });
  await expect(page.getByRole('alert')).toContainText('No supported images');
  const directory = testInfo.outputPath('camera-dataset');
  for (const split of ['train', 'test']) {
    const folder = join(directory, split, 'products');
    await mkdir(folder, { recursive: true });
    await writeFile(join(folder, `${split}-capture.png`), png);
  }
  await page.locator('input[type=file]').nth(1).setInputFiles(directory);
  await expect(page.getByRole('heading', { name: 'camera-dataset', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Import dataset', exact: true })).toBeEnabled();
  await navigate(page, 'Export & handoff');
  const imported = JSON.parse((await download(page, 'Download JSON')).toString());
  expect(imported.images.map((image: { split: string }) => image.split).sort()).toEqual([
    'test',
    'train',
  ]);
  expect(
    imported.images.every((image: { path: string }) => image.path.startsWith('camera-dataset/')),
  ).toBe(true);
});

for (const width of [1440, 390, 320]) {
  test(`accessible workspace and dialogs have no horizontal overflow at ${width}px`, async ({
    page,
  }, testInfo) => {
    test.setTimeout(60_000);
    await page.setViewportSize({ width, height: 900 });
    await ready(page);
    const check = async () => {
      const results = await new AxeBuilder({ page })
        .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
        .analyze();
      expect
        .soft(
          results.violations.map((violation) => ({
            id: violation.id,
            description: violation.description,
            nodes: violation.nodes.map((node) => node.target),
          })),
        )
        .toEqual([]);
      expect
        .soft(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
        .toBe(true);
    };
    await check();
    await page.screenshot({ path: testInfo.outputPath(`overview-${width}.png`), fullPage: true });
    await navigate(page, 'Review findings');
    await check();
    await page.locator('.finding-row').first().click();
    await check();
    await page.keyboard.press('Escape');
    await expect(page.getByRole('dialog')).toHaveCount(0);
    await page.getByRole('button', { name: 'Audit settings', exact: true }).click();
    await check();
    await page.keyboard.press('Escape');
    await navigate(page, 'Image library');
    await check();
    await navigate(page, 'Export & handoff');
    await check();
  });
}
