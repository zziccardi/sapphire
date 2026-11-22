import { describe, expect, it } from 'vitest';
import { renderMarkdownString, rewriteMarkdownHref, slugify } from './markdown';

describe('markdown helpers', () => {
  it('slugifies headings consistently', () => {
    expect(slugify('Dual-Paradigm Code Reuse')).toBe('dual-paradigm-code-reuse');
    expect(slugify('Optionals (`T?`) & Guard')).toBe('optionals-t-guard');
  });

  it('rewrites relative doc links to Astro routes', () => {
    expect(rewriteMarkdownHref('SPEC.md#optionals')).toBe('/docs/spec#optionals');
    expect(rewriteMarkdownHref('quickstart.md')).toBe('/docs/quickstart');
    expect(rewriteMarkdownHref('host_interop.md#love2d-interop')).toBe('/docs/host-interop#love2d-interop');
    expect(rewriteMarkdownHref('lua_comparison.md')).toBe('/compare/lua');
    expect(rewriteMarkdownHref('rust_comparison.md')).toBe('/compare/rust');
    expect(rewriteMarkdownHref('https://example.com')).toBe('https://example.com');
  });

  it('strips nested or malformed HTML tags safely in slugify', () => {
    expect(slugify('<scr<script>ipt>Hello</script> World')).toBe('hello-world');
    expect(slugify('<span><b>Nested</b></span> Heading!')).toBe('nested-heading');
  });

  it('extracts headings and highlights Sapphire code blocks', async () => {
    const md = [
      '# Main Title',
      '## First Section',
      '## Using `Ref<T>` Safely',
      '## <scr<script>ipt>Alert</script> Ignored',
      'See [Spec](SPEC.md) for details.',
      '```sapphire',
      'let x: int = 42;',
      '```',
    ].join('\n');

    const result = await renderMarkdownString(md);
    expect(result.title).toBe('Main Title');
    expect(result.headings).toEqual([
      { depth: 2, text: 'First Section', slug: 'first-section' },
      { depth: 2, text: 'Using Ref<T> Safely', slug: 'using-reft-safely' },
      { depth: 2, text: 'Alert Ignored', slug: 'alert-ignored' },
    ]);
    expect(result.html).toContain('class="shiki');
    expect(result.html).toContain('href="/docs/spec"');
  });

  it('preserves Coroutine<T> and __del__ heading slugs matching cross-doc anchors', async () => {
    const md = [
      '### Coroutines (`Coroutine<T>`)',
      '### Deterministic destructors (`__del__`)',
    ].join('\n');
    const result = await renderMarkdownString(md);
    expect(result.headings).toEqual([
      { depth: 3, text: 'Coroutines (Coroutine<T>)', slug: 'coroutines-coroutinet' },
      {
        depth: 3,
        text: 'Deterministic destructors (__del__)',
        slug: 'deterministic-destructors-__del__',
      },
    ]);
  });

  it('rewrites relative .py and .sp links to GitHub and sanitizes unsafe URIs', async () => {
    expect(rewriteMarkdownHref('src/parser/ast.py')).toBe(
      'https://github.com/zziccardi/sapphire/blob/main/src/parser/ast.py',
    );
    expect(rewriteMarkdownHref('../samples/overview.sp')).toBe(
      'https://github.com/zziccardi/sapphire/blob/main/samples/overview.sp',
    );
    expect(rewriteMarkdownHref('javascript:alert(1)')).toBe('#');
    expect(rewriteMarkdownHref('  JaVaScRiPt:alert(1)')).toBe('#');

    const md = '[bad](javascript:alert(1) "a\\" onmouseover=\\"x")';
    const result = await renderMarkdownString(md);
    expect(result.html).toContain('href="#"');
    expect(result.html).not.toContain('javascript:');
    expect(result.html).not.toContain('" onmouseover="');
  });

  it('renders json, c, txt fences and preserves $&, $$, and $\' inside code blocks', async () => {
    const md = [
      '```json',
      '{"pattern": "$& $$ $\' $` $1"}',
      '```',
      '```c',
      'int main(void) { return 0; }',
      '```',
      '```txt',
      'plain text $& ok',
      '```',
    ].join('\n');
    const result = await renderMarkdownString(md);
    expect(result.html).not.toContain('SAPPHIRE_CODE_BLOCK_');
    expect(result.html).toContain('$&#x26;');
    expect(result.html).toContain('$$');
    expect(result.html).toContain("$'");
    expect(result.html).toContain('$`');
    expect(result.html).toContain('plain text');
  });
});
