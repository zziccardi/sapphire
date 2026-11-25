# Quickstart

This guide gets you from installation to running standalone Sapphire programs,
native test suites, and Love2D applications with live hot-reloading.

If you plan to contribute to the Sapphire compiler or regenerate the ANTLR4
grammar, see the [contributor setup guide](development.md) instead.

## Installing the CLI

Sapphire requires Python 3.12 or newer. Install the CLI globally with `pipx`
(recommended for an isolated command) or `pip`:

```bash
pipx install sapphire-lang
```

Or with `pip`:

```bash
pip install sapphire-lang
```

Verify the installation:

```bash
sapphire --help
```

## Installing the VS Code extension

Sapphire ships with a Language Server Protocol (LSP) server and VS Code
extension providing syntax highlighting, hover types, diagnostics, and
autocompletion.

Download `sapphire-0.1.0.vsix` from the GitHub releases page and install it:

```bash
code --install-extension sapphire-0.1.0.vsix
```

You can also open VS Code, go to the Extensions pane, open the `...` menu, and
select **Install from VSIX...**.

## Your first Sapphire program

All executable logic in Sapphire lives inside functions, and standalone
programs start at `func main()`. Create a file named `hello.sp`:

```sapphire
struct Vector2 {
  var x: float = 0.0;
  var y: float = 0.0;
}

struct Player: Vector2 {
  let name: String;
  var health: int = 100;
}

impl Player {
  var func move_by(dx: float, dy: float) {
    self.x += dx;
    self.y += dy;
  }
}

func main() {
  var hero = Player { name = "Aria", x = 10.0, y = 20.0 };
  hero.move_by(dx = 5.0, dy = -3.0);
  print(f"{hero.name} is at ({hero.x}, {hero.y}) with {hero.health} HP");
}
```

Run it directly (transpiling to Python by default):

```bash
sapphire hello.sp
```

To compile and run against Lua 5.1 (requires `lua`, `luajit`, or `lua5.1` on
your `PATH`):

```bash
sapphire hello.sp -t lua
```

To emit transpiled source files without executing them:

```bash
# Emit Python
sapphire build hello.sp -o hello.py

# Emit Lua 5.1 and a Source Map v3 sidecar (hello.lua.map)
sapphire build hello.sp -t lua -o hello.lua
```

## Running a Love2D project with live hot-reload

Sapphire includes typed Love2D bindings under `lib.love2d` and built-in dev
mode hot-reloading. Create a file named `game.sp`:

```sapphire
import lib.love2d.enums;
import lib.love2d.graphics;
import lib.love2d.love2d;

let love = love2d.love;
var box_x = 120.0;

@export("love.update")
func update(dt: float) {
  if love.keyboard.isDown(enums.KeyCode.Right) {
    box_x += 220.0 * dt;
  }
}

@export("love.draw")
func draw() {
  love.graphics.clear(r = 0.08, g = 0.1, b = 0.14);
  love.graphics.setColorRgba(0.3, 0.75, 1.0);
  love.graphics.rectangle(mode = enums.DrawMode.Fill, x = box_x, y = 140.0,
                          width = 64.0, height = 64.0);
}
```

Launch it in Love2D with live hot-reloading enabled:

```bash
sapphire run game.sp -t love2d -o main.lua --dev
```

Saving changes to `game.sp` incrementally re-transpiles `main.lua`, patches
structs and prototypes in-place without losing live state, and invokes any
`@on_reload` lifecycle hooks. For full details on `@extern`, `@export`, source
maps, and Python interop, see [Host interop & Love2D](host_interop.md).

## Type-checking and testing

Type-check a file and its transitive imports without generating code:

```bash
sapphire check hello.sp
sapphire check game.sp -t lua --json
```

Write unit tests using `std.testing` and `@test` methods, then run the built-in
test runner:

```bash
sapphire test
sapphire test --json
```

See the [testing framework guide](testing.md) for assertions, fixtures, and
test suite structure.

## Next steps

* Read [Host interop & Love2D](host_interop.md) to bind external Lua or Python
  host APIs and use live hot-reloading.
* Explore the [language specification](SPEC.md) for structs, traits,
  prototypes, lexical arenas, optionals, and coroutines.
* Follow the [style guide](style_guide.md) for idiomatic Sapphire formatting
  and naming conventions.
* Browse the [standard library](stdlib.md) and
  [built-in types & functions](builtins.md).
* See [AI agents and human readability](ai_agents.md) for configuring AI coding
  agents with Sapphire's skill reference and JSON diagnostics loop.
