import { describe, expect, it } from 'vitest';
import { DOC_PAGES, docFileExists } from './docs';

describe('documentation registry', () => {
  it('all doc files exist in docs/', () => {
    for (const doc of DOC_PAGES) {
      expect(docFileExists(doc.file), `${doc.file} should exist in docs/`).toBe(true);
    }
  });

  it('uses unique slugs', () => {
    const slugs = DOC_PAGES.map((d) => d.slug);
    expect(new Set(slugs).size).toBe(slugs.length);
  });
});
