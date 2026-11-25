# AI agents and human readability

As AI coding agents write a larger share of application code, the primary
bottleneck shifts from typing speed to **verification** and **human review**.
This guide explains how Sapphire's design supports both human readability and
agent-driven development, how to configure an effective agent workflow, and
what trade-offs to expect.

## Why a static language matters with AI agents

Optimizing a programming language for fewer keystrokes matters less when agents
generate boilerplate effortlessly. What matters more is how reliably a toolchain
catches mistakes before code runs and how quickly a human can audit the result:

* **The compiler as a verification oracle**: High-velocity code generation also
  produces bugs at high velocity. Sapphire's static type checker, compile-time
  null safety (`T?`), exhaustive `match`, immutability by default, and
  scope-bound reference exclusivity turn whole classes of subtle agent mistakes
  into immediate, deterministic compile errors.
* **Static safety over dynamic targets**: When targeting dynamic runtimes such
  as Lua or Python, raw target code makes it easy for an agent to introduce
  silent typos, `nil` dereferences, or shared mutable table bugs that only
  surface deep at runtime. Compiling Sapphire down to those targets closes that
  gap without sacrificing runtime interoperability.
* **Lower review overhead**: Because mutability, ownership, and public module
  surfaces are explicit in the syntax, humans reviewing agent-written diffs can
  verify architectural intent without tracing every helper function.

### Honest trade-offs

Using a specialized language with AI agents is not free:

* **Training-data gravity**: Mainstream languages (TypeScript, Python, Rust, Go)
  have broad LLM pretraining coverage and zero-shot fluency. Sapphire requires
  loading a compact language reference into agent context.
* **Modest iteration tax**: Stricter semantic checks (such as parameter
  ordering, container unwrap freezes, and escape rules) can add one to three
  compile-fix cycles compared to a dynamic language.
* **Smaller ecosystem**: You rely on Sapphire's standard library and host
  interop (`@extern` / `@export`) rather than a massive native package registry.

In practice, this trades a small amount of upfront context and compile-fix
churn for significantly fewer silent runtime bugs.

## Human readability

Sapphire is designed to be readable at a glance by developers coming from Rust,
Swift, TypeScript, or Python:

* **Familiar syntax synthesis**: `struct`, `impl`, `trait`, and `match` follow
  Rust conventions; `let`/`var`, `T?`, `?.`, `??`, and `guard let` follow Swift;
  `__init__`, named arguments, and `none` follow Python. Most files are
  immediately legible without consulting the full
  [language specification](SPEC.md).
* **Intent visible at the signature**:
  * `func` vs. `var func` shows immediately whether a method can mutate `self`.
  * `var` on a parameter marks an exclusive mutable borrow at the call contract.
  * `export { ... }` at the top of a module summarizes its public API.
  * No lifetime annotations (`'a`) and no hidden exceptions keep control flow
    linear and uncluttered.
* **Conventions worth learning once**:
  * Optional unwrapping uses `?=` (`if let item ?= opt`, `guard var x ?= opt`).
  * `yield` produces a value from a multi-statement block arm in a
    value-producing `match` expression, and suspends execution inside a
    `Coroutine<T>`.
  * Dynamic prototypal delegation (`proto` / `clone` inside an `Arena`) uses
    explicit lexical scopes and copy-on-write semantics.

## Recommended agent workflow

Agents perform best in Sapphire when paired with a concise language reference
and a tight compile-and-test loop:

1. **Provide the language skill in context**: Load Sapphire's compact agent
   reference (`.agents/skills/sapphire-lang/SKILL.md` in this repository) so
   the agent starts with exact syntax, borrowing rules, and idioms instead of
   guessing from neighboring languages.
2. **Type-check with JSON diagnostics after edits**: Run `sapphire check` with
   `--json` so the agent receives structured file, line, column, and error
   messages without parsing prose:

   ```bash
   sapphire check path/to/file.sp --json
   sapphire check path/to/file.sp -t lua --json
   ```

3. **Verify behavior with native tests**: Run the built-in test runner against
   each target backend you ship:

   ```bash
   sapphire test path/to/file_test.sp
   sapphire test path/to/file_test.sp -t lua
   ```

See the [testing framework guide](testing.md) and [quickstart](quickstart.md)
for CLI setup and test suite patterns.

## Common agent pitfalls

Because agents carry strong muscle memory from Rust, Swift, Lua, and Python,
most first-pass compile errors fall into a handful of predictable patterns:

* **Null literal drift**: Writing `nil`, `None`, or `null` instead of `none`.
* **Optional unwrap syntax**: Writing `=` instead of `?=` in `if let` /
  `guard let`, or writing `let var` instead of `var` for mutable unwraps.
* **Punctuation**: Omitting statement semicolons `;` or trailing commas `,` on
  `match` arms.
* **Parameter ordering**: Placing `var` parameters before immutable parameters,
  or required parameters after defaulted parameters.
* **Struct up-casting**: Attempting `Child as Parent` (prohibited to prevent
  object slicing) instead of defining a behavioral `trait`.
* **Container unwrap freezes**: Mutating an outer `Array` or `Map` while an
  `if var` or `guard var` binding from `.get(k)` is still live.

All of these are caught statically by `sapphire check` before any code runs.
For formatting and idiomatic conventions, see the [style guide](style_guide.md).
