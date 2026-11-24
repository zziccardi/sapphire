"""Standard library time module for Sapphire (Python target)."""

import time as _time


def now() -> float:
  """Returns current time in seconds since the Epoch as a float."""
  return float(_time.time())


def sleep(seconds: float) -> None:
  """Suspends execution of current thread for given number of seconds."""
  if seconds > 0:
    _time.sleep(seconds)
