import fs from 'node:fs';
import path from 'node:path';
import { createHighlighter, type Highlighter } from 'shiki';

let highlighterPromise: Promise<Highlighter> | null = null;

function loadSapphireGrammar() {
  const toolsDir = fs.existsSync(path.resolve(process.cwd(), '../tools'))
    ? path.resolve(process.cwd(), '../tools')
    : path.resolve(process.cwd(), 'tools');
  const grammarPath = path.resolve(
    toolsDir,
    'vscode-extension/syntaxes/sapphire.tmLanguage.json',
  );
  const raw = JSON.parse(fs.readFileSync(grammarPath, 'utf-8'));
  return {
    ...raw,
    name: 'sapphire',
    aliases: ['sp'],
    scopeName: 'source.sapphire',
  };
}

const LANG_ALIASES: Record<string, string> = {
  sp: 'sapphire',
  py: 'python',
  sh: 'bash',
  shell: 'bash',
  rs: 'rust',
  'c++': 'cpp',
  txt: 'text',
};

const REGISTERED_LANGS = new Set([
  'sapphire',
  'python',
  'lua',
  'bash',
  'rust',
  'cpp',
  'c',
  'swift',
  'json',
  'text',
]);

export async function getSapphireHighlighter(): Promise<Highlighter> {
  if (!highlighterPromise) {
    highlighterPromise = createHighlighter({
      themes: ['github-light', 'github-dark-default'],
      langs: [
        loadSapphireGrammar(),
        'python',
        'lua',
        'bash',
        'rust',
        'cpp',
        'c',
        'swift',
        'json',
        'text',
      ],
    });
  }
  return highlighterPromise;
}

export async function highlightCode(code: string, lang: string = 'sapphire'): Promise<string> {
  const highlighter = await getSapphireHighlighter();
  const clean = (lang || 'text').trim().toLowerCase().split(/\s+/)[0];
  const mapped = LANG_ALIASES[clean] ?? clean;
  const resolvedLang = REGISTERED_LANGS.has(mapped) ? mapped : 'text';
  return highlighter.codeToHtml(code.trimEnd(), {
    lang: resolvedLang,
    themes: {
      light: 'github-light',
      dark: 'github-dark-default',
    },
  });
}
