"""Standard library OS module for Sapphire (Python target)."""

import os as _os
import sys as _sys
from typing import List, Optional


def args() -> List[str]:
  """Returns process command-line arguments."""
  return list(_sys.argv)


def get_env(name: str) -> Optional[str]:
  """Retrieves the value of an environment variable, or None if not set."""
  return _os.environ.get(name)


def set_env(name: str, value: str) -> None:
  """Sets an environment variable to the given string value."""
  _os.environ[name] = str(value)


def exit(code: int = 0) -> None:
  """Terminates the current process with the given exit code."""
  _sys.exit(code)
