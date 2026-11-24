/*
 * E2E Test: heap_smart_refs_test.sp
 * Tests Ref<T>, SharedRef<T>, and WeakRef<T> with move semantics.
 */

struct Node {
  var val: int;
}

impl Node {
  func double_val(): int {
    return self.val * 2;
  }
}

@test
func test_unique_ref(): int {
  let r = Ref(Node { val = 21 });
  return r.double_val();
}

@test
func test_shared_ref_cycle_breaking(): int {
  let s1 = SharedRef(Node { val = 42 });
  let s2 = s1.share();
  let w = s1.downgrade();
  if let active ?= w.upgrade() {
    return active.val;
  }
  return 0;
}

@test
func test_shared_from_move(): int {
  var r = Ref(Node { val = 99 });
  let s = SharedRef(move r);
  return s.val;
}

trait TextureHandle {
  func width(): int;
}

struct MockTexture {
  var w: int;
}

impl TextureHandle for MockTexture {
  func width(): int {
    return self.w;
  }
}

struct AssetEntry {
  var name: String;
  var tex: TextureHandle;
  var tags: [String: int];
}

struct AssetCache {
  var entries: [String: SharedRef<AssetEntry>] = {};
}

impl AssetCache {
  func get_entry(key: String): SharedRef<AssetEntry>? {
    if let item ?= self.entries.get(key) {
      return item.share();
    }
    return none;
  }
}

func read_shared_asset(entry: SharedRef<AssetEntry>): int {
  let tag_val = entry.tags.get("tier") ?? 0;
  return entry.tex.width() + tag_val;
}

@test
func test_shared_ref_in_maps_with_trait_fields_and_aliases(): int {
  var cache = AssetCache {};
  let asset = SharedRef(AssetEntry {
    name = "hero",
    tex = MockTexture { w = 32 },
    tags = {"tier": 5},
  });
  cache.entries["hero"] = asset.share();
  cache.entries["path/hero"] = move asset;

  if let h ?= cache.entries.get("hero") {
    cache.entries["player"] = h.share();
  }

  var total = 0;
  if let a1 ?= cache.get_entry("hero") {
    total += read_shared_asset(a1);
  }
  if let a2 ?= cache.get_entry("path/hero") {
    total += read_shared_asset(a2);
  }
  if let a3 ?= cache.get_entry("player") {
    total += read_shared_asset(a3);
  }
  // 3 aliases * (32 + 5) = 111
  return total;
}
