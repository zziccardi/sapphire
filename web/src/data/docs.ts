import fs from 'node:fs';
import path from 'node:path';

export interface DocPageMeta {
  slug: string;
  file: string;
  title: string;
  group: 'Getting Started' | 'Language Reference' | 'Compiler & Contributing';
  summary: string;
}

export const DOC_PAGES: DocPageMeta[] = [
  {
    slug: 'quickstart',
    file: 'quickstart.md',
    title: 'Quickstart',
    group: 'Getting Started',
    summary: 'Install the CLI and VS Code extension, run your first program, and launch a Love2D project.',
  },
  {
    slug: 'host-interop',
    file: 'host_interop.md',
    title: 'Host Interop & Love2D',
    group: 'Getting Started',
    summary: 'Bind Lua and Python host APIs with @extern/@export, use lib.love2d, live hot-reload, and source maps.',
  },
  {
    slug: 'style-guide',
    file: 'style_guide.md',
    title: 'Style Guide',
    group: 'Getting Started',
    summary: 'Formatting, 80-char line limits, naming conventions, and idiomatic Sapphire.',
  },
  {
    slug: 'ai-agents',
    file: 'ai_agents.md',
    title: 'AI Agents & Readability',
    group: 'Getting Started',
    summary: 'Human readability, compiler-verified AI agent workflows, and common cross-language pitfalls.',
  },
  {
    slug: 'spec',
    file: 'SPEC.md',
    title: 'Language Specification',
    group: 'Language Reference',
    summary: 'Definitive Sapphire syntax, memory model, RAII, traits, arenas, and coroutines.',
  },
  {
    slug: 'builtins',
    file: 'builtins.md',
    title: 'Built-in Types & Functions',
    group: 'Language Reference',
    summary: 'Core primitives, String, Array, Map, Range, Arena, Ref<T>, and SharedRef<T>.',
  },
  {
    slug: 'stdlib',
    file: 'stdlib.md',
    title: 'Standard Library',
    group: 'Language Reference',
    summary: 'Standard modules (fs, math, os, testing, time, utf8) and built-in Love2D bindings (lib.love2d).',
  },
  {
    slug: 'compiler',
    file: 'compiler.md',
    title: 'Compiler Architecture',
    group: 'Compiler & Contributing',
    summary: 'ANTLR4 parser, AST, semantic passes, arena escape checker, and code generators.',
  },
  {
    slug: 'testing',
    file: 'testing.md',
    title: 'Testing Framework',
    group: 'Compiler & Contributing',
    summary: 'Writing @test functions and running suites with sapphire test.',
  },
  {
    slug: 'development',
    file: 'development.md',
    title: 'Contributor Setup & CLI',
    group: 'Compiler & Contributing',
    summary: 'Contributor environment setup, pipenv commands, ANTLR regeneration, and packaging.',
  },
];

export function docFileExists(fileName: string): boolean {
  const docsDir = fs.existsSync(path.resolve(process.cwd(), '../docs'))
    ? path.resolve(process.cwd(), '../docs')
    : path.resolve(process.cwd(), 'docs');
  return fs.existsSync(path.resolve(docsDir, fileName));
}
