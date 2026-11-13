"""Standard library filesystem module for Sapphire (Python target)."""

import os as _os
from typing import Optional


def read_file(path: str) -> Optional[str]:
  """Reads file content as a string, or returns None if reading fails."""
  try:
    with open(path, "r", encoding="utf-8") as f:
      return f.read()
  except Exception:
    return None


def write_file(path: str, content: str) -> bool:
  """Writes string content to a file, returning True on success."""
  try:
    with open(path, "w", encoding="utf-8") as f:
      f.write(content)
    return True
  except Exception:
    return False


def remove_file(path: str) -> bool:
  """Removes the file at the given path, returning True on success."""
  try:
    _os.remove(path)
    return True
  except Exception:
    return False


def exists(path: str) -> bool:
  """Returns True if the specified file or directory path exists."""
  return _os.path.exists(path)
