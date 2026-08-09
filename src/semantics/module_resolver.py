"""Module path resolution utility for Sapphire imports."""

import os
from typing import Optional


def resolve_module_path(import_path: str, source_file_path: Optional[str] = None) -> Optional[str]:
  """Resolves a Sapphire module import path (e.g. 'entities.character' or 'constants') to an absolute file path on disk."""
  rel_path = import_path.replace(".", "/") + ".sp"

  search_dirs = []

  # 1. Search directories starting from source_file_path directory up to filesystem root
  if source_file_path:
    curr = os.path.abspath(os.path.dirname(source_file_path))
    while curr and curr != os.path.dirname(curr):
      search_dirs.append(curr)
      curr = os.path.dirname(curr)

  # 2. Search directories starting from current working directory up to filesystem root
  curr = os.path.abspath(os.getcwd())
  while curr and curr != os.path.dirname(curr):
    if curr not in search_dirs:
      search_dirs.append(curr)
    curr = os.path.dirname(curr)

  # 3. Built-in library directories (lib, lib/std, lib/love2d)
  root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
  lib_dir = os.path.join(root_dir, "lib")
  search_dirs.extend([lib_dir, os.path.join(lib_dir, "std"), os.path.join(lib_dir, "love2d")])

  for d in search_dirs:
    candidate = os.path.join(d, rel_path)
    if os.path.isfile(candidate):
      return os.path.abspath(candidate)

  return None
