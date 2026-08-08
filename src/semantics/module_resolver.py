"""Module path resolution utility for Sapphire imports."""

import os
from typing import Optional


def resolve_module_path(import_path: str, source_file_path: Optional[str] = None) -> Optional[str]:
  """Resolves a Sapphire module import path (e.g. 'game.entities.entity') to an absolute file path on disk."""
  parts = import_path.split(".")
  suffixes = []
  for i in range(len(parts)):
    suffixes.append("/".join(parts[i:]) + ".sp")

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

  # 3. Built-in library directory
  root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
  lib_dir = os.path.join(root_dir, "lib")
  search_dirs.append(lib_dir)
  if import_path.startswith("std."):
    search_dirs.append(os.path.join(lib_dir, "std"))

  for d in search_dirs:
    for suffix in suffixes:
      candidate = os.path.join(d, suffix)
      if os.path.isfile(candidate):
        return os.path.abspath(candidate)

  return None
