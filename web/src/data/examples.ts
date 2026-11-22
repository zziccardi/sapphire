import fs from 'node:fs';
import path from 'node:path';

export type ExampleCategory =
  | 'Overview'
  | 'Host Interop & Game Dev'
  | 'Memory & Arenas'
  | 'Concurrency & Control Flow';

export interface GeneratedPreview {
  label: string;
  lang: 'lua' | 'python';
  code: string;
  note?: string;
}

export interface SampleExample {
  slug: string;
  file: string;
  title: string;
  category: ExampleCategory;
  description: string;
  runnableInPlayground: boolean;
  guideHref?: string;
  guideLabel?: string;
  generatedPreview?: GeneratedPreview;
}

const LOVE2D_GENERATED_LUA = `-- Emitted by: sapphire build samples/love2d_demo.sp -t lua -o main.lua
local enums = require("lib.love2d.enums")
local graphics = require("lib.love2d.graphics")
local love2d = require("lib.love2d.love2d")

local SPEED = 250.0
local love = love2d.love
local hero_x = 200.0
local hero_y = 200.0

function love.load()
  love.graphics.setBackgroundColor(0.1, 0.1, 0.15)
end

function love.update(dt)
  if (love.keyboard.isDown(enums.KeyCode.Left) or love.keyboard.isDown(enums.KeyCode.A)) then
    hero_x = hero_x - (SPEED * dt)
  end
  if (love.keyboard.isDown(enums.KeyCode.Right) or love.keyboard.isDown(enums.KeyCode.D)) then
    hero_x = hero_x + (SPEED * dt)
  end
  if (love.keyboard.isDown(enums.KeyCode.Up) or love.keyboard.isDown(enums.KeyCode.W)) then
    hero_y = hero_y - (SPEED * dt)
  end
  if (love.keyboard.isDown(enums.KeyCode.Down) or love.keyboard.isDown(enums.KeyCode.S)) then
    hero_y = hero_y + (SPEED * dt)
  end
end

function love.draw()
  love.graphics.clear(0.1, 0.15, 0.2)
  love.graphics.setColor(0.2, 0.7, 0.5)
  love.graphics.rectangle(enums.DrawMode.Fill, 50.0, 50.0, 700.0, 500.0)
  love.graphics.setColor(0.9, 0.3, 0.4)
  love.graphics.circle(enums.DrawMode.Fill, hero_x, hero_y, 24.0)
  love.graphics.setColor(1.0, 1.0, 1.0)
  love.graphics.circle(enums.DrawMode.Line, hero_x, hero_y, 24.0)
  love.graphics.setColor(1.0, 1.0, 1.0)
  local fps_str = ("FPS: " .. tostring(love.timer.getFPS()))
  love.graphics.print(fps_str, 10.0, 10.0)
  love.graphics.print("Move with WASD or Arrow Keys", 10.0, 30.0)
end`;

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
    slug: 'love2d_demo',
    file: 'love2d_demo.sp',
    title: 'Love2D Host Bindings',
    category: 'Host Interop & Game Dev',
    description:
      'Zero-overhead Love2D callbacks via @export("love.update") and typed lib.love2d.* bindings compiling straight to Lua.',
    runnableInPlayground: false,
    guideHref: '/docs/host-interop',
    guideLabel: 'Host Interop Guide',
    generatedPreview: {
      label: 'Generated Lua',
      lang: 'lua',
      code: LOVE2D_GENERATED_LUA,
      note: 'Requires a local Love2D runtime to execute: run sapphire run samples/love2d_demo.sp -t love2d -o main.lua --dev.',
    },
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
    slug: 'multi_parent_delegation_demo',
    file: 'multi_parent_delegation_demo.sp',
    title: 'Multi-Parent Structural Delegation',
    category: 'Overview',
    description:
      'Compose multiple structs (struct Player: Position, Health) with compile-time method forwarding and zero vtables.',
    runnableInPlayground: true,
  },
  {
    slug: 'python_interop',
    file: 'python_interop.sp',
    title: 'Python Host Interop (WSGI)',
    category: 'Host Interop & Game Dev',
    description:
      'Bind Python standard library modules (wsgiref.simple_server) with @extern, @export, and opaque resource traits.',
    runnableInPlayground: false,
    guideHref: '/docs/host-interop#python-host-interop',
    guideLabel: 'Host Interop Guide',
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
    slug: 'raii_resource_demo',
    file: 'raii_resource_demo.sp',
    title: 'Deterministic RAII & __del__',
    category: 'Memory & Arenas',
    description:
      'Automatic LIFO resource cleanup via __del__ destructors, move semantics, and RVO.',
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
    category: 'Host Interop & Game Dev',
    description:
      'Entity updates, prototypal blueprints, and deterministic frame stepping runnable directly in the playground.',
    runnableInPlayground: true,
  },
  {
    slug: 'sample_test',
    file: 'sample_test.sp',
    title: 'Native Unit Testing (@test)',
    category: 'Overview',
    description:
      'Test suites with std.testing, set_up/tear_down fixtures, and @test methods executed via sapphire test.',
    runnableInPlayground: false,
    guideHref: '/docs/testing',
    guideLabel: 'Testing Guide',
  },
];

export function readSampleSource(fileName: string): string {
  const samplesDir = fs.existsSync(path.resolve(process.cwd(), '../samples'))
    ? path.resolve(process.cwd(), '../samples')
    : path.resolve(process.cwd(), 'samples');
  const fullPath = path.resolve(samplesDir, fileName);
  return fs.readFileSync(fullPath, 'utf-8');
}
