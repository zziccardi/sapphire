/*
 * E2E Test: cross_module_test.sp
 * Tests aliased module imports, cross-module struct inheritance, cross-module
 * trait dispatch, qualified ancestor static dispatch, and imported enum keys.
 */

import testing.e2e.cross_module_base as base_lib;

struct HeroActor: base_lib.BaseActor {
  var bonus: int = 5;
}

impl base_lib.Renderable for HeroActor {
  func render_score(): int {
    return base_lib.BaseActor.render_score(self) + self.bonus;
  }
}

@test
func test_cross_module_inheritance_trait_and_ancestor_dispatch(): int {
  let hero = HeroActor {
    base_power = 20,
    kind = base_lib.BaseKind.HERO,
    bonus = 7,
  };
  let weights: [base_lib.BaseKind: int] = {
    base_lib.BaseKind.HERO: 100,
    base_lib.BaseKind.FOE: 50,
  };
  let w = weights.get(hero.kind) ?? 0;
  // base_lib.read_render_score(hero) == 20 + 7 = 27; w == 100 -> 127
  return base_lib.read_render_score(hero) + w;
}
