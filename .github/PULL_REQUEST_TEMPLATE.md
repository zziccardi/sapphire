## Summary

Describe the motivation and key changes in this pull request.

## Checklist

* [ ] `pipenv run lint` passes with zero errors
* [ ] `pipenv run test` passes with zero failures
* [ ] `pipenv run sapphire test` and `pipenv run sapphire test -t lua` pass
* [ ] If `grammar/Sapphire.g4` changed, regenerated `src/parser/gen/` with
  `pipenv run antlr`
* [ ] If language semantics or built-ins changed, updated `docs/SPEC.md`,
  `docs/builtins.md`, or `docs/stdlib.md`
* [ ] If any complete Sapphire sample in Markdown was edited, verified it
  compiles cleanly
