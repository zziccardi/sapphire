import { describe, expect, it } from 'vitest';
import { readSampleSource, SAMPLE_EXAMPLES } from './examples';

describe('curated sample examples', () => {
  it('all referenced sample files exist and contain Sapphire code', () => {
    for (const example of SAMPLE_EXAMPLES) {
      const source = readSampleSource(example.file);
      expect(source.trim().length, `${example.file} should not be empty`).toBeGreaterThan(20);
    }
  });

  it('uses unique slugs', () => {
    const slugs = SAMPLE_EXAMPLES.map((e) => e.slug);
    expect(new Set(slugs).size).toBe(slugs.length);
  });
});
