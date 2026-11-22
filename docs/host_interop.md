# Host interop & Love2D

Sapphire is designed to interoperate directly with external host runtimes—such
as Lua engines (including **Love2D**) and Python libraries—without FFI glue
code or runtime wrapper overhead.

Host bindings are declared purely in Sapphire using traits, structs, and two
compile-time annotations: `@extern` and `@export`.

## Core interop primitives

### Binding host globals with `@extern`

`@extern` binds a Sapphire variable to a global symbol or module provided by
the host runtime without emitting a local declaration. Extern declarations must
specify an explicit type and cannot have an initializer expression:

```sapphire
@extern
var love: LoveEngine;

@extern("wsgiref.simple_server")
var wsgiref: WsgiModule;
```

On the Python backend, passing a module path string (`@extern("pkg.mod")`)
automatically imports that host module and binds it to the Sapphire identifier.

### Exporting callbacks and aliasing methods with `@export`

`@export("native.name")` controls the exact symbol emitted in generated code:

* **Host callbacks**: Placing `@export("love.update")` on a top-level function
  emits `function love.update(dt) ... end` directly in Lua, registering it as
  an engine callback with zero trampoline overhead.
* **Trait method aliasing**: Placing `@export("setColor")` on a trait method
  lets Sapphire expose clean, strongly typed overloads that all compile down to
  the same host API name.

### Trait-based host APIs and resource handles

Traits model external host modules and opaque runtime objects cleanly:

* **`static func`** methods on a trait represent module functions and transpile
  to Lua dot syntax (`love.graphics.rectangle(...)`).
* **Instance `func` / `var func`** methods omit `static` and transpile to Lua
  colon syntax (`image:getWidth()`), modeling opaque host resource handles.

```sapphire
trait Image {
  func getWidth(): float;
  func getHeight(): float;
}

trait Graphics {
  @export("setColor")
  static func setColorRgba(r: float, g: float, b: float, a: float = 1.0);

  static func newImage(path: String): Image;
}
```

## Love2D interop

Sapphire ships with modular, strongly typed Love2D bindings under `lib.love2d`
as a first-class example of host interoperability.

### Built-in `lib.love2d` modules

* `lib.love2d.love2d`: Master binding exporting `LoveEngine` and
  `@extern var love`.
* `lib.love2d.graphics`: `Graphics`, `Image`, `Canvas`, `Font`, `Quad`, and
  `Color`.
* `lib.love2d.enums`: Typed string enums (`DrawMode`, `KeyCode`, `FilterMode`,
  `WrapMode`, `AlignMode`, `ArcMode`, `GamepadButton`, `GamepadAxis`).
* `lib.love2d.keyboard`: Keyboard polling and key-repeat controls.
* `lib.love2d.mouse`: Cursor management and mouse button/position queries.
* `lib.love2d.joystick`: `Joystick` trait for gamepad and joystick callbacks.
* `lib.love2d.timer`: Frame delta time, FPS queries, and sleep helpers.
* `lib.love2d.event`: Engine lifecycle events such as `quit`.

### Complete Love2D example

Because `lib.love2d` uses typed enums, named arguments, and compile-time checks,
typos in draw modes, key names, or argument types are caught before Love2D ever
launches:

```sapphire
import lib.love2d.enums;
import lib.love2d.graphics;
import lib.love2d.love2d;

let SPEED = 240.0;
let love = love2d.love;

var hero_x = 200.0;
var hero_y = 200.0;

@export("love.load")
func load() {
  love.graphics.setBackgroundColor(r = 0.08, g = 0.1, b = 0.15);
}

@export("love.update")
func update(dt: float) {
  if love.keyboard.isDown(enums.KeyCode.Left) ||
     love.keyboard.isDown(enums.KeyCode.A) {
    hero_x -= SPEED * dt;
  }
  if love.keyboard.isDown(enums.KeyCode.Right) ||
     love.keyboard.isDown(enums.KeyCode.D) {
    hero_x += SPEED * dt;
  }
}

@export("love.draw")
func draw() {
  love.graphics.clear(r = 0.08, g = 0.1, b = 0.15);
  love.graphics.setColorRgba(0.9, 0.35, 0.45);
  love.graphics.circle(mode = enums.DrawMode.Fill, x = hero_x, y = hero_y,
                       radius = 24.0);
  love.graphics.setColorRgba(1.0, 1.0, 1.0);
  love.graphics.print(text = f"FPS: {love.timer.getFPS()}",
                      x = 12.0, y = 12.0);
}
```

Build and run with Love2D:

```bash
# Transpile to Lua 5.1 (emits main.lua and main.lua.map)
sapphire build samples/love2d_demo.sp -t lua -o main.lua
love .

# Release build without source maps or runtime demangler
sapphire build samples/love2d_demo.sp -t lua -o main.lua --no_sourcemap
```

> **Note on quad-less drawing**: Love2D rejects `nil` as argument #2 of
> `love.graphics.draw`. Use `drawImageAt` / `drawCanvasAt` when drawing without
> a `Quad`, and `drawImage` / `drawCanvas` only when passing a valid `Quad`.

## Live hot-reloading (`--dev` and `@on_reload`)

When iterating on interactive apps or games, launch with `--dev` to watch
project `.sp` files and reload changes live:

```bash
sapphire run samples/love2d_demo.sp -t love2d -o main.lua --dev
```

During a hot-reload:

1. Sapphire detects modified `.sp` files and incrementally re-transpiles the
   project.
2. Existing struct and prototype metatables are patched **in-place**, updating
   method implementations without discarding live game or application state.
3. Functions annotated with `@on_reload` execute automatically so you can
   refresh derived caches, log reload status, or tweak live parameters:

```sapphire
@on_reload
func handle_reload() {
  print("[Hot Reload] Updated logic while preserving live state.");
}
```

## Source maps & stack-trace demangling

Debugging transpiled code usually forces you to mentally map generated Lua line
numbers back to source files. Sapphire solves this automatically during Lua
builds:

1. **Standard Source Map v3 (`.lua.map`)**: Emitted alongside generated `.lua`
   files using Base64 VLQ mappings with embedded `sourcesContent` for IDE and
   debugger tooling.
2. **Embedded `_SP_LINE_MAP` demangler**: Translates runtime stack traces back
   to original `.sp` filenames, line numbers, and source snippets.
3. **Love2D error-screen hook**: Intercepts uncaught errors in Love2D so both
   terminal output and Love2D's graphical crash screen report your original
   `.sp` code rather than generated Lua lines.

Pass `--no_sourcemap` to strip both the `.lua.map` file and the runtime
demangler for compact release builds.

## Python host interop

The same `@extern`, `@export`, and trait handle mechanics work natively on the
Python backend. For example, you can bind Python's `wsgiref.simple_server` and
export a typed WSGI callback:

```sapphire
trait BytesHandle {
  func decode(): String;
}

trait StrEncoder {
  @export("encode")
  func to_bytes(text: String, encoding: String = "utf-8"): BytesHandle;
}

@extern
var str: StrEncoder;

@export("app")
func wsgi_handler(
    environ: [String: String],
    start_response: (String, [[String]]) -> void): [BytesHandle] {
  let path = environ.get("PATH_INFO") ?? "/";
  start_response("200 OK", [["Content-Type", "text/plain; charset=utf-8"]]);
  return [str.to_bytes(f"Hello from Sapphire at {path}\n")];
}
```

See the full runnable example in `samples/python_interop.sp`, and consult
[Standard library](stdlib.md#love2d-game-engine-bindings-liblove2d) and
[Language specification](SPEC.md#host-runtime-interoperability-annotations) for
complete details.
