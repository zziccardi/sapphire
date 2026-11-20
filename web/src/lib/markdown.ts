import fs from 'node:fs';
import path from 'node:path';
import { Marked } from 'marked';
import { highlightCode } from './highlight';
import { withBase } from './url';

export interface TocHeading {
  depth: number;
  text: string;
  slug: string;
}

export interface RenderedMarkdown {
  html: string;
  headings: TocHeading[];
  title: string;
}

const DOC_LINK_MAP: Record<string, string> = {
  'SPEC.md': '/docs/spec',
  'builtins.md': '/docs/builtins',
  'stdlib.md': '/docs/stdlib',
  'compiler.md': '/docs/compiler',
  'development.md': '/docs/development',
  'style_guide.md': '/docs/style-guide',
  'testing.md': '/docs/testing',
  'rust_comparison.md': '/compare/rust',
  'cpp_comparison.md': '/compare/cpp',
  'swift_comparison.md': '/compare/swift',
};

const SUPPORTED_LANGS = new Set([
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
]);

export function slugify(text: string): string {
  return text
    .toLowerCase()
    .replace(/<[^>]+>/g, '')
    .replace(/[^a-z0-9\s-]/g, '')
    .trim()
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-');
}

export function rewriteMarkdownHref(href: string): string {
  if (!href || href.startsWith('http://') || href.startsWith('https://') || href.startsWith('#')) {
    return href;
  }
  const [rawPath, hash] = href.split('#');
  const baseName = path.basename(rawPath);
  const mapped = DOC_LINK_MAP[baseName];
  if (mapped) {
    return withBase(hash ? `${mapped}#${hash}` : mapped);
  }
  if (rawPath.endsWith('.sp')) {
    return `https://github.com/zziccardi/sapphire/blob/main/${rawPath.replace(/^\.\.\//, '')}`;
  }
  return href;
}

function normalizeLang(lang?: string): string {
  const clean = (lang ?? 'text').trim().toLowerCase().split(/\s+/)[0];
  if (clean === 'sp') return 'sapphire';
  if (clean === 'py') return 'python';
  if (clean === 'sh' || clean === 'shell') return 'bash';
  if (clean === 'rs') return 'rust';
  if (clean === 'c++') return 'cpp';
  return SUPPORTED_LANGS.has(clean) ? clean : 'text';
}

export async function renderMarkdownString(source: string): Promise<RenderedMarkdown> {
  const headings: TocHeading[] = [];
  const usedSlugs = new Map<string, number>();
  let title = '';

  const codeBlocks: Array<{ token: string; code: string; lang: string }> = [];

  const marked = new Marked();
  marked.use({
    renderer: {
      heading({ tokens, depth }) {
        const text = this.parser.parseInline(tokens);
        const plainText = text.replace(/<[^>]+>/g, '');
        if (depth === 1 && !title) {
          title = plainText;
        }
        let slug = slugify(plainText) || 'section';
        const count = usedSlugs.get(slug) ?? 0;
        usedSlugs.set(slug, count + 1);
        if (count > 0) {
          slug = `${slug}-${count}`;
        }
        if (depth === 2 || depth === 3) {
          headings.push({ depth, text: plainText, slug });
        }
        return `<h${depth} id="${slug}">${text}</h${depth}>\n`;
      },
      code({ text, lang }) {
        const cleanLang = (lang ?? '').trim().toLowerCase();
        if (cleanLang === 'mermaid') {
          return `<pre class="mermaid">${text.replace(/</g, '&lt;').replace(/>/g, '&gt;')}</pre>\n`;
        }
        const token = `<!--SAPPHIRE_CODE_BLOCK_${codeBlocks.length}-->`;
        codeBlocks.push({ token, code: text, lang: normalizeLang(lang) });
        return `${token}\n`;
      },
      link({ href, title: linkTitle, tokens }) {
        const text = this.parser.parseInline(tokens);
        const rewritten = rewriteMarkdownHref(href ?? '');
        const titleAttr = linkTitle ? ` title="${linkTitle}"` : '';
        const external = rewritten.startsWith('http://') || rewritten.startsWith('https://');
        const relAttr = external ? ' target="_blank" rel="noopener noreferrer"' : '';
        return `<a href="${rewritten}"${titleAttr}${relAttr}>${text}</a>`;
      },
    },
  });

  let html = await marked.parse(source);

  for (const block of codeBlocks) {
    const highlighted = await highlightCode(block.code, block.lang);
    html = html.replace(block.token, highlighted);
  }

  return { html, headings, title };
}

export async function renderDocFile(relativeDocPath: string): Promise<RenderedMarkdown> {
  const docsDir = fs.existsSync(path.resolve(process.cwd(), '../docs'))
    ? path.resolve(process.cwd(), '../docs')
    : path.resolve(process.cwd(), 'docs');
  const fullPath = path.resolve(docsDir, relativeDocPath);
  const content = fs.readFileSync(fullPath, 'utf-8');
  return renderMarkdownString(content);
}
