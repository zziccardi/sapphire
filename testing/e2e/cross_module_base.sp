/*
 * Helper module for cross_module_test.sp.
 * Defines an enum, a trait, and a base struct for cross-module inheritance
 * and trait dispatch E2E verification.
 */

export {
  BaseActor,
  BaseKind,
  Renderable,
  read_render_score,
}

enum BaseKind {
  HERO = "hero",
  FOE  = "foe",
}

trait Renderable {
  func render_score(): int;
}

struct BaseActor {
  var base_power: int = 10;
  var kind: BaseKind = BaseKind.HERO;
}

impl Renderable for BaseActor {
  func render_score(): int {
    return self.base_power;
  }
}

func read_render_score(r: Renderable): int {
  return r.render_score();
}
