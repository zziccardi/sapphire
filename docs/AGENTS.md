# Documentation Guidelines (`docs/`)

- `docs/` is rendered directly by the Astro site in `web/` using `marked`
  (`web/src/lib/markdown.ts`), not Jekyll.
- Do **not** use Jekyll/Kramdown directives (`{: .no_toc }`, `{: .text-delta }`,
  `{:toc}`) or Jekyll-only HTML TOC blocks in `docs/*.md`; they render as
  literal text on the website.
- Table of contents navigation is generated automatically from `##` and `###`
  headings by `web/src/pages/docs/[slug].astro`.
- Relative links between docs (e.g. `SPEC.md`, `rust_comparison.md`) are
  rewritten to site routes via `DOC_LINK_MAP` in `web/src/lib/markdown.ts`;
  update that map when adding new doc pages.
- Keep language comparisons (`*_comparison.md`) focused strictly on comparing
  the languages themselves—not host frameworks (e.g. Love2D) or third-party
  dialects.
- Use `Lua 5.1` only in technical docs where the target version matters;
  otherwise refer simply to `Lua`.
