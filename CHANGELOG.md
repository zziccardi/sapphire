# Changelog

All notable changes to Sapphire will be documented in this file.

The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
* Core Sapphire compiler pipeline (ANTLR4 grammar, AST builder, semantic
  analyzer, borrow/escape/arena checker, and type checker).
* Multi-target transpilers targeting Python and Lua 5.1 (with Love2D support,
  source map v3 generation, and runtime stack-trace demangling), plus an
  experimental LLVM IR backend.
* Static structural inheritance (`struct Child: Parent`), zero-vtable traits,
  opt-in arena-managed prototypes (`proto` / `clone` with CoW), generics via
  monomorphization, optionals (`T?`), `guard` clauses, `match` expressions,
  explicit `move` / RAII (`__del__`), and stackless `Coroutine<T>`.
* Standard library (`lib/std/`) and Love2D host bindings (`lib/love2d/`).
* Unified `sapphire` CLI (`run`, `build`, `check`, `test`, `parse`, `dump-ast`)
  with live hot-reloading (`--dev`) and JSON diagnostics (`--json`).
* Language Server Protocol (LSP) server (`src/lsp/`) and VS Code extension
  (`tools/vscode-extension/`).
* Documentation site and browser playground (`web/`).
