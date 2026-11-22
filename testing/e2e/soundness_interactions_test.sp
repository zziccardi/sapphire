/*
 * E2E Soundness Matrix: soundness_interactions_test.sp
 * Verifies runtime soundness at feature intersections across Python and Lua 5.1:
 *  - Conditional move drop-flags inside loops & match arms
 *  - SharedRef / WeakRef upgrade & cycle breaking across closures
 *  - Proto CoW isolation across nested struct clones
 */

var SOUND_LOG: int = 0;

struct Guarded {
  var id: int;
}
impl Guarded {
  func __del__() {
    SOUND_LOG = SOUND_LOG * 10 + self.id;
  }
}

@test
func test_loop_reinit_and_conditional_move_drop_flags(): int {
  SOUND_LOG = 0;
  {
    var g = Guarded { id = 1 };
    for i in [2, 3] {
      if i == 2 {
        let taken = move g;
        let _keep = taken.id;
      }
      g = Guarded { id = i };
    }
  }
  // i=2: move g -> taken(1) drops at end of if (1); g=Guarded(2) (g was moved, no drop)
  // i=3: g=Guarded(3) destroys old Guarded(2) (12)
  // block exit: Guarded(3) drops (123)
  return SOUND_LOG;
}

struct SharedPayload {
  var val: int;
}

@test
func test_shared_weak_ref_upgrade_in_closure(): int {
  var out = 0;
  var weak_opt: WeakRef<SharedPayload>? = none;
  {
    let sr = SharedRef(SharedPayload { val = 42 });
    let w = sr.downgrade();
    weak_opt = w;
    let reader = () -> int {
      if let up ?= w.upgrade() {
        return up.val;
      }
      return -1;
    };
    out += reader();
  }
  // After sr exits scope, weak upgrade must return none
  if let w2 ?= weak_opt {
    if let up2 ?= w2.upgrade() {
      out += up2.val;
    } else {
      out += 100;
    }
  }
  return out;
}

struct Stats {
  var hp: int;
}
proto Unit {
  var stats: Stats;
}

@test
func test_proto_nested_struct_cow_isolation(): int {
  var a = Arena();
  let base = Unit { stats = Stats { hp = 100 } } in a;
  var c1 = clone base;
  var c2 = clone base;
  c1.stats.hp = 25;
  return base.stats.hp * 1000 + c1.stats.hp * 10 + c2.stats.hp;
}
