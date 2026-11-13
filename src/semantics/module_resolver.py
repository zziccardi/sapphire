"""Module path resolution utility for Sapphire imports."""

import importlib.util
import os
import sys
from typing import Optional


def find_sapphire_lib_dir() -> Optional[str]:
  """Locates Sapphire standard library across local and installed locations."""
  # 1. Environment variable override
  env_dir = os.environ.get("SAPPHIRE_LIB_DIR")
  if env_dir and os.path.isdir(env_dir):
    return os.path.abspath(env_dir)

  # 2. Local repository or parent directory of package
  curr_dir = os.path.abspath(os.path.dirname(__file__))
  repo_root = os.path.abspath(os.path.join(curr_dir, "..", ".."))
  candidate = os.path.join(repo_root, "lib")
  if os.path.isdir(candidate):
    return candidate

  # 3. Direct sibling of src (e.g. site-packages/lib)
  src_dir = os.path.abspath(os.path.join(curr_dir, ".."))
  parent_dir = os.path.dirname(src_dir)
  candidate = os.path.join(parent_dir, "lib")
  if os.path.isdir(candidate):
    return candidate

  # 4. Importlib module spec lookup for installed lib.std
  try:
    spec = importlib.util.find_spec("lib.std")
    if spec:
      if spec.origin:
        std_dir = os.path.dirname(os.path.abspath(spec.origin))
        lib_parent = os.path.dirname(std_dir)
        if os.path.isdir(lib_parent):
          return lib_parent
      elif spec.submodule_search_locations:
        for loc in spec.submodule_search_locations:
          lib_parent = os.path.dirname(os.path.abspath(loc))
          if os.path.isdir(lib_parent):
            return lib_parent
  except Exception:
    pass

  # 5. System prefix installation directories
  prefix_candidates = [
      os.path.join(sys.prefix, "lib", "sapphire"),
      os.path.join(sys.prefix, "share", "sapphire", "lib"),
      os.path.join(sys.prefix, "lib", "sapphire", "lib"),
  ]
  for candidate in prefix_candidates:
    if os.path.isdir(candidate):
      return os.path.abspath(candidate)

  return None


def resolve_module_path(
    import_path: str, source_file_path: Optional[str] = None
) -> Optional[str]:
  """Resolves a Sapphire module import path to an absolute path on disk."""
  rel_path = import_path.replace(".", "/") + ".sp"

  search_dirs = []

  # 1. Search directory of source_file_path (strictly bounded to source
  #    file's directory root or enclosing package root when import_path
  #    starts with an ancestor directory name)
  if source_file_path:
    source_dir = os.path.abspath(os.path.dirname(source_file_path))
    search_dirs.append(source_dir)
    if "." in import_path:
      top_pkg = import_path.split(".")[0]
      curr = source_dir
      while curr and curr != os.path.dirname(curr):
        if os.path.basename(curr) == top_pkg:
          pkg_root = os.path.dirname(curr)
          if pkg_root not in search_dirs:
            search_dirs.append(pkg_root)
          break
        curr = os.path.dirname(curr)

  # 2. Search current working directory
  cwd = os.path.abspath(os.getcwd())
  if cwd not in search_dirs:
    search_dirs.append(cwd)

  # 3. Built-in library directories (lib, lib/std, lib/love2d, and parent)
  lib_dir = find_sapphire_lib_dir()
  if lib_dir:
    lib_parent = os.path.dirname(lib_dir)
    if lib_parent not in search_dirs:
      search_dirs.append(lib_parent)
    if lib_dir not in search_dirs:
      search_dirs.append(lib_dir)
    std_dir = os.path.join(lib_dir, "std")
    if os.path.isdir(std_dir) and std_dir not in search_dirs:
      search_dirs.append(std_dir)
    love2d_dir = os.path.join(lib_dir, "love2d")
    if os.path.isdir(love2d_dir) and love2d_dir not in search_dirs:
      search_dirs.append(love2d_dir)

  for d in search_dirs:
    candidate = os.path.join(d, rel_path)
    if os.path.isfile(candidate):
      return os.path.abspath(candidate)

  return None
