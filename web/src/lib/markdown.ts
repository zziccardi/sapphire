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
  'quickstart.md': '/docs/quickstart',
  'host_interop.md': '/docs/host-interop',
  'SPEC.md': '/docs/spec',
  'builtins.md': '/docs/builtins',
  'stdlib.md': '/docs/stdlib',
  'compiler.md': '/docs/compiler',
  'development.md': '/docs/development',
  'style_guide.md': '/docs/style-guide',
  'testing.md': '/docs/testing',
  'lua_comparison.md': '/compare/lua',
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

function stripHtmlTags(input: string): string {
  let result = '';
  let tagDepth = 0;
  for (let i = 0; i < input.length; i++) {
    const ch = input[i];
    if (ch === '<') {
      tagDepth++;
    } else if (ch === '>') {
      if (tagDepth > 0) {
        tagDepth--;
      }
    } else if (tagDepth === 0) {
      result += ch;
    }
  }
  return result;
}

interface InlineToken {
  type?: string;
  text?: string;
  raw?: string;
  tokens?: InlineToken[];
}

function escapeHtmlAttr(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function isUnsafeUri(href: string): boolean {
  const normalized = href.replace(/[\u0000-\u001F\s]+/g, '').toLowerCase();
  return (
    normalized.startsWith('javascript:') ||
    normalized.startsWith('vbscript:') ||
    normalized.startsWith('data:')
  );
}

function extractPlainTextFromTokens(tokens: InlineToken[]): string {
  // Keep codespan contents (e.g. `Ref<T>`, `Coroutine<T>`) verbatim while
  // stripping raw HTML tags across non-code text segments.
  let out = '';
  let textBuf = '';
  const flushText = () => {
    if (textBuf) {
      out += stripHtmlTags(textBuf);
      textBuf = '';
    }
  };
  const walk = (items: InlineToken[]) => {
    for (const token of items) {
      if (token.type === 'html') {
        continue;
      }
      if (token.type === 'codespan' && typeof token.text === 'string') {
        flushText();
        out += token.text;
      } else if (token.tokens && token.tokens.length > 0) {
        walk(token.tokens);
      } else if (typeof token.text === 'string') {
        textBuf += token.text;
      }
    }
  };
  walk(tokens);
  flushText();
  return out;
}

function slugifyPlain(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9_\s-]/g, '')
    .trim()
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-');
}

export function slugify(text: string): string {
  return slugifyPlain(stripHtmlTags(text));
}

export function rewriteMarkdownHref(href: string): string {
  if (!href) {
    return '';
  }
  if (isUnsafeUri(href)) {
    return '#';
  }
  if (
    href.startsWith('http://') ||
    href.startsWith('https://') ||
    href.startsWith('mailto:') ||
    href.startsWith('#')
  ) {
    return href;
  }
  const hashIdx = href.indexOf('#');
  const rawPath = hashIdx >= 0 ? href.slice(0, hashIdx) : href;
  const hash = hashIdx >= 0 ? href.slice(hashIdx + 1) : '';
  const baseName = path.basename(rawPath);
  const mapped = DOC_LINK_MAP[baseName];
  if (mapped) {
    return withBase(hash ? `${mapped}#${hash}` : mapped);
  }
  if (rawPath.endsWith('.sp') || rawPath.endsWith('.py')) {
    const repoRel = rawPath.replace(/^(?:\.\.\/)+/, '').replace(/^\.\//, '');
    const suffix = hash ? `#${hash}` : '';
    return `https://github.com/zziccardi/sapphire/blob/main/${repoRel}${suffix}`;
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
  if (clean === 'txt') return 'text';
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
        const plainText = extractPlainTextFromTokens(tokens as InlineToken[]).trim();
        if (depth === 1 && !title) {
          title = plainText;
        }
        let slug = slugifyPlain(plainText) || 'section';
        const count = usedSlugs.get(slug) ?? 0;
        usedSlugs.set(slug, count + 1);
        if (count > 0) {
          slug = `${slug}-${count}`;
        }
        if (depth === 2 || depth === 3) {
          headings.push({ depth, text: plainText, slug });
        }
        return `<h${depth} id="${escapeHtmlAttr(slug)}">${text}</h${depth}>\n`;
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
        const safeHref = escapeHtmlAttr(rewritten);
        const titleAttr = linkTitle ? ` title="${escapeHtmlAttr(linkTitle)}"` : '';
        const external = rewritten.startsWith('http://') || rewritten.startsWith('https://');
        const relAttr = external ? ' target="_blank" rel="noopener noreferrer"' : '';
        return `<a href="${safeHref}"${titleAttr}${relAttr}>${text}</a>`;
      },
    },
  });

  let html = await marked.parse(source);

  for (const block of codeBlocks) {
    const highlighted = await highlightCode(block.code, block.lang);
    html = html.replace(block.token, () => highlighted);
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
