"""Module path resolution utility for Sapphire imports."""

import os
from typing import Optional


def resolve_module_path(import_path: str, source_file_path: Optional[str] = None) -> Optional[str]:
  """Resolves a Sapphire module import path (e.g. 'entities.character' or 'constants') to an absolute file path on disk."""
  rel_path = import_path.replace(".", "/") + ".sp"

  search_dirs = []

  # 1. Search directory of source_file_path (strictly bounded to source file's directory root
  #    or the enclosing package root when import_path starts with an ancestor directory name)
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

  # 3. Built-in library directories (lib, lib/std, lib/love2d)
  root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
  lib_dir = os.path.join(root_dir, "lib")
  search_dirs.extend([lib_dir, os.path.join(lib_dir, "std"), os.path.join(lib_dir, "love2d")])

  for d in search_dirs:
    candidate = os.path.join(d, rel_path)
    if os.path.isfile(candidate):
      return os.path.abspath(candidate)

  return None
