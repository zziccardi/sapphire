"""Standard library UTF-8 module for Sapphire (Python target)."""

from typing import Optional


def size(s: str) -> Optional[int]:
  try:
    s.encode("utf-8")
    return len(s)
  except UnicodeEncodeError:
    return None


def offset(s: str, n: int, i: Optional[int] = None) -> Optional[int]:
  if i is None:
    i = 1 if n >= 0 else len(s.encode("utf-8")) + 1
  raw = s.encode("utf-8")
  if i < 0:
    i = len(raw) + 1 + i
  if i < 1 or i > len(raw) + 1:
    return None
  prefix_chars = len(raw[: i - 1].decode("utf-8", errors="ignore"))
  target_char = prefix_chars + (n - 1 if n > 0 else n)
  if n == 0:
    return i
  if target_char < 0 or target_char > len(s):
    return None
  return len(s[:target_char].encode("utf-8")) + 1


def sub(s: str, start_char: int, end_char: Optional[int] = None) -> str:
  if not s:
    return ""
  return s[start_char:end_char]
