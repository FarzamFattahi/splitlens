import { expect, it } from 'vitest';
import fixture from '../python/tests/fixtures/matching.json';
import { reanalyze } from '../src/engine';
import { DEFAULT_SETTINGS, type ImageRecord } from '../src/types';

it('matches the Python engine on shared cached image measurements', () => {
  const images = fixture.images.map((image) => ({
    bytes: 0,
    thumbnail: '',
    label: 'class',
    ...image,
  })) as ImageRecord[];
  const actual = reanalyze(images, DEFAULT_SETTINGS).map(({ kind, imageIds }) => ({
    kind,
    imageIds,
  }));
  expect(actual).toEqual(fixture.expected);
});
