import fs from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import { renderDocFile } from '../lib/markdown';
import { DOC_PAGES, docFileExists } from './docs';

const ALL_SITE_DOCS: Array<{ route: string; file: string }> = [
  ...DOC_PAGES.map((d) => ({ route: `/docs/${d.slug}`, file: d.file })),
  { route: '/compare/cpp', file: 'cpp_comparison.md' },
  { route: '/compare/lua', file: 'lua_comparison.md' },
  { route: '/compare/rust', file: 'rust_comparison.md' },
  { route: '/compare/swift', file: 'swift_comparison.md' },
];

const REGISTERED_FENCE_LANGS = new Set([
  '',
  'sapphire',
  'sp',
  'python',
  'py',
  'lua',
  'bash',
  'sh',
  'shell',
  'rust',
  'rs',
  'cpp',
  'c++',
  'c',
  'swift',
  'json',
  'text',
  'txt',
  'mermaid',
]);

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

  it('renders all site docs with valid internal anchors, rewritten repo links, and supported fences', async () => {
    const docsDir = fs.existsSync(path.resolve(process.cwd(), '../docs'))
      ? path.resolve(process.cwd(), '../docs')
      : path.resolve(process.cwd(), 'docs');

    const renderedByRoute = new Map<string, { html: string; ids: Set<string>; file: string }>();

    for (const entry of ALL_SITE_DOCS) {
      const raw = fs.readFileSync(path.resolve(docsDir, entry.file), 'utf-8');
      for (const match of raw.matchAll(/^```([a-zA-Z0-9_+.-]*)/gm)) {
        const lang = (match[1] ?? '').trim().toLowerCase();
        expect(
          REGISTERED_FENCE_LANGS.has(lang),
          `Unsupported fenced language "${lang}" in docs/${entry.file}`,
        ).toBe(true);
      }

      const rendered = await renderDocFile(entry.file);
      const ids = new Set<string>();
      for (const idMatch of rendered.html.matchAll(/<h[1-6]\s+id="([^"]+)"/g)) {
        ids.add(idMatch[1]);
      }
      renderedByRoute.set(entry.route, { html: rendered.html, ids, file: entry.file });
    }

    const brokenAnchors: string[] = [];
    const unrewrittenLinks: string[] = [];

    for (const [route, { html, ids, file }] of renderedByRoute.entries()) {
      for (const hrefMatch of html.matchAll(/<a\s+[^>]*href="([^"]+)"/g)) {
        const href = hrefMatch[1];
        if (href.startsWith('http://') || href.startsWith('https://') || href.startsWith('mailto:')) {
          continue;
        }
        if (/\.py($|#)|\.sp($|#)/.test(href)) {
          unrewrittenLinks.push(`${file}: ${href}`);
        }
        if (href.startsWith('#')) {
          const anchor = href.slice(1);
          if (anchor && !ids.has(anchor)) {
            brokenAnchors.push(`${file} -> ${href}`);
          }
          continue;
        }
        const hashIdx = href.indexOf('#');
        if (hashIdx >= 0) {
          const targetRoute = href.slice(0, hashIdx);
          const anchor = href.slice(hashIdx + 1);
          const target = renderedByRoute.get(targetRoute);
          if (target && anchor && !target.ids.has(anchor)) {
            brokenAnchors.push(`${file} (${route}) -> ${href}`);
          }
        }
      }
    }

    expect(unrewrittenLinks).toEqual([]);
    expect(brokenAnchors).toEqual([]);
  }, 30000);
});
