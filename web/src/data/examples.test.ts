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

  it('includes host-interop, delegation, and testing samples with valid previews', () => {
    const bySlug = new Map(SAMPLE_EXAMPLES.map((e) => [e.slug, e]));
    expect(bySlug.get('love2d_demo')?.generatedPreview?.lang).toBe('lua');
    expect(bySlug.get('love2d_demo')?.generatedPreview?.code).toContain('function love.update');
    expect(bySlug.get('love2d_demo')?.runnableInPlayground).toBe(false);
    expect(bySlug.get('python_interop')).toBeDefined();
    expect(bySlug.get('multi_parent_delegation_demo')?.runnableInPlayground).toBe(true);
    expect(bySlug.get('sample_test')).toBeDefined();
  });
});
