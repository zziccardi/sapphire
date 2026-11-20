# Website Guidelines (`web/`)

- **Stack**: Astro + Tailwind CSS v4 + Shiki + Pagefind, deployed to GitHub Pages
  at `/sapphire` (`astro.config.mjs`).
- **Routing**: Always wrap internal links and asset paths with `withBase()` from
  `src/lib/url.ts`.
- **Content sources**: Docs come from `../docs/` (`src/data/docs.ts`) and
  examples from `../samples/` (`src/data/examples.ts`). Keep them as the single
  source of truth rather than duplicating content in `web/`.
- **Astro whitespace**: Use explicit `{' '}` between inline text and adjacent
  tags (`<span>`, `<code>`) across newlines so Astro does not collapse spaces.
- **Theme & Diagrams**: Dark mode is controlled via `[data-theme="dark"]` on
  `<html>`. Dynamic client-side widgets (such as Mermaid diagrams) must observe
  `data-theme` changes and re-render accordingly.
- **Verification**: Run `npm test` and `npm run build` in `web/` after changes.
