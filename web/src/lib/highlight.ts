import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHighlighter, type Highlighter } from 'shiki';

let highlighterPromise: Promise<Highlighter> | null = null;

function loadSapphireGrammar() {
  const __dirname = path.dirname(fileURLToPath(import.meta.url));
  const grammarPath = path.resolve(
    __dirname,
    '../../../tools/vscode-extension/syntaxes/sapphire.tmLanguage.json',
  );
  const raw = JSON.parse(fs.readFileSync(grammarPath, 'utf-8'));
  return {
    ...raw,
    name: 'sapphire',
    aliases: ['sp'],
    scopeName: 'source.sapphire',
  };
}

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
        'swift',
        'text',
      ],
    });
  }
  return highlighterPromise;
}

export async function highlightCode(code: string, lang: string = 'sapphire'): Promise<string> {
  const highlighter = await getSapphireHighlighter();
  return highlighter.codeToHtml(code.trimEnd(), {
    lang,
    themes: {
      light: 'github-light',
      dark: 'github-dark-default',
    },
  });
}
