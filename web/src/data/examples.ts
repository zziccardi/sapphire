import fs from 'node:fs';
import path from 'node:path';

export type ExampleCategory =
  | 'Overview'
  | 'Memory & Arenas'
  | 'Concurrency & Control Flow'
  | 'Game Dev & Love2D';

export interface SampleExample {
  slug: string;
  file: string;
  title: string;
  category: ExampleCategory;
  description: string;
  runnableInPlayground: boolean;
}

export const SAMPLE_EXAMPLES: SampleExample[] = [
  {
    slug: 'overview',
    file: 'overview.sp',
    title: 'Language Overview',
    category: 'Overview',
    description:
      'Structs, traits, prototypal delegation, lexical arenas, optionals, and guard clauses in one tour.',
    runnableInPlayground: true,
  },
  {
    slug: 'arena_demo',
    file: 'arena_demo.sp',
    title: 'Lexical Arenas & Prototypes',
    category: 'Memory & Arenas',
    description:
      'Scoped Arena allocation with proto instances, clone shadowing, and copy-on-write isolation.',
    runnableInPlayground: true,
  },
  {
    slug: 'raii_resource_demo',
    file: 'raii_resource_demo.sp',
    title: 'Deterministic RAII & __del__',
    category: 'Memory & Arenas',
    description:
      'Automatic LIFO resource cleanup via __del__ destructors, move semantics, and RVO.',
    runnableInPlayground: true,
  },
  {
    slug: 'trait_subtyping_demo',
    file: 'trait_subtyping_demo.sp',
    title: 'Zero-Vtable Trait Polymorphism',
    category: 'Overview',
    description:
      'Compile-time trait dispatch and heterogeneous collections without vtable overhead.',
    runnableInPlayground: true,
  },
  {
    slug: 'coroutine_demo',
    file: 'coroutine_demo.sp',
    title: 'Stackless Coroutines',
    category: 'Concurrency & Control Flow',
    description:
      'Cooperative yielding with Coroutine<T>, .step(), .is_done(), and .reset().',
    runnableInPlayground: true,
  },
  {
    slug: 'match_demo',
    file: 'match_demo.sp',
    title: 'Pattern Matching & Enums',
    category: 'Concurrency & Control Flow',
    description:
      'Exhaustive match expressions over enums and tagged variants without exceptions.',
    runnableInPlayground: true,
  },
  {
    slug: 'game_loop',
    file: 'game_loop.sp',
    title: 'Simulation & Game Loop',
    category: 'Game Dev & Love2D',
    description:
      'Entity updates, multi-parent structural delegation, and deterministic frame stepping.',
    runnableInPlayground: true,
  },
  {
    slug: 'love2d_demo',
    file: 'love2d_demo.sp',
    title: 'Love2D Engine Bindings',
    category: 'Game Dev & Love2D',
    description:
      'Host callbacks via @export("love.update") and @extern var love for Lua 5.1 game targets.',
    runnableInPlayground: false,
  },
];

export function readSampleSource(fileName: string): string {
  const samplesDir = fs.existsSync(path.resolve(process.cwd(), '../samples'))
    ? path.resolve(process.cwd(), '../samples')
    : path.resolve(process.cwd(), 'samples');
  const fullPath = path.resolve(samplesDir, fileName);
  return fs.readFileSync(fullPath, 'utf-8');
}
