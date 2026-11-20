import fs from 'node:fs';
import path from 'node:path';

export interface DocPageMeta {
  slug: string;
  file: string;
  title: string;
  group: 'Getting Started' | 'Language Reference' | 'Compiler & Testing';
  summary: string;
}

export const DOC_PAGES: DocPageMeta[] = [
  {
    slug: 'development',
    file: 'development.md',
    title: 'Developer Setup & CLI',
    group: 'Getting Started',
    summary: 'Environment setup, pipenv commands, ANTLR regeneration, and transpiler CLI usage.',
  },
  {
    slug: 'style-guide',
    file: 'style_guide.md',
    title: 'Style Guide',
    group: 'Getting Started',
    summary: 'Formatting, 80-char line limits, naming conventions, and idiomatic Sapphire.',
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
    summary: 'Modules under lib/std/ including math, testing, utf8, and utilities.',
  },
  {
    slug: 'compiler',
    file: 'compiler.md',
    title: 'Compiler Architecture',
    group: 'Compiler & Testing',
    summary: 'ANTLR4 parser, AST, semantic passes, arena escape checker, and code generators.',
  },
  {
    slug: 'testing',
    file: 'testing.md',
    title: 'Testing Framework',
    group: 'Compiler & Testing',
    summary: 'Writing @test functions and running suites with sapphire test.',
  },
];

export function docFileExists(fileName: string): boolean {
  const docsDir = fs.existsSync(path.resolve(process.cwd(), '../docs'))
    ? path.resolve(process.cwd(), '../docs')
    : path.resolve(process.cwd(), 'docs');
  return fs.existsSync(path.resolve(docsDir, fileName));
}
