import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import sitemap from '@astrojs/sitemap';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig } from 'astro/config';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const tmGrammarPath = path.resolve(
  __dirname,
  '../tools/vscode-extension/syntaxes/sapphire.tmLanguage.json',
);
const sapphireGrammar = JSON.parse(fs.readFileSync(tmGrammarPath, 'utf-8'));

export default defineConfig({
  site: 'https://zziccardi.github.io',
  base: '/sapphire',
  integrations: [sitemap()],
  vite: {
    plugins: [tailwindcss()],
  },
  markdown: {
    shikiConfig: {
      themes: {
        light: 'github-light',
        dark: 'github-dark-default',
      },
      langs: [
        {
          ...sapphireGrammar,
          name: 'sapphire',
          aliases: ['sp'],
          scopeName: 'source.sapphire',
        },
      ],
    },
  },
});
