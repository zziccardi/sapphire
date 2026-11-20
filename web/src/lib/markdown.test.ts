import { describe, expect, it } from 'vitest';
import { renderMarkdownString, rewriteMarkdownHref, slugify } from './markdown';

describe('markdown helpers', () => {
  it('slugifies headings consistently', () => {
    expect(slugify('Dual-Paradigm Code Reuse')).toBe('dual-paradigm-code-reuse');
    expect(slugify('Optionals (`T?`) & Guard')).toBe('optionals-t-guard');
  });

  it('rewrites relative doc links to Astro routes', () => {
    expect(rewriteMarkdownHref('SPEC.md#optionals')).toBe('/docs/spec#optionals');
    expect(rewriteMarkdownHref('rust_comparison.md')).toBe('/compare/rust');
    expect(rewriteMarkdownHref('https://example.com')).toBe('https://example.com');
  });

  it('extracts headings and highlights Sapphire code blocks', async () => {
    const md = [
      '# Main Title',
      '## First Section',
      'See [Spec](SPEC.md) for details.',
      '```sapphire',
      'let x: int = 42;',
      '```',
    ].join('\n');

    const result = await renderMarkdownString(md);
    expect(result.title).toBe('Main Title');
    expect(result.headings).toEqual([
      { depth: 2, text: 'First Section', slug: 'first-section' },
    ]);
    expect(result.html).toContain('class="shiki');
    expect(result.html).toContain('href="/docs/spec"');
  });
});
