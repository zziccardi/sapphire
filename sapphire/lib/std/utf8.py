"""Standard library UTF-8 module for Sapphire (Python target)."""



def size(s: str) -> int | None:
  try:
    s.encode("utf-8")
    return len(s)
  except UnicodeEncodeError:
    return None


def _is_utf8_cont(b: int) -> bool:
  return 0x80 <= b <= 0xBF


def offset(s: str, n: int, i: int | None = None) -> int | None:
  raw = s.encode("utf-8")
  slen = len(raw)
  if i is None:
    i = 1 if n >= 0 else slen + 1
  elif i < 0:
    i = slen + 1 + i
  if i < 1 or i > slen + 1:
    return None
  if n == 0:
    while i > 1 and i <= slen and _is_utf8_cont(raw[i - 1]):
      i -= 1
    return i
  if i <= slen and _is_utf8_cont(raw[i - 1]):
    return None
  pos = i
  if n > 0:
    rem = n - 1
    while rem > 0:
      if pos > slen:
        return None
      pos += 1
      while pos <= slen and _is_utf8_cont(raw[pos - 1]):
        pos += 1
      rem -= 1
    return pos
  rem = -n
  while rem > 0:
    if pos <= 1:
      return None
    pos -= 1
    while pos > 1 and _is_utf8_cont(raw[pos - 1]):
      pos -= 1
    rem -= 1
  return pos


def sub(s: str, start_char: int, end_char: int | None = None) -> str:
  if not s:
    return ""
  return s[start_char:end_char]
