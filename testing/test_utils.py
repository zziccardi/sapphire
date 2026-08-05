"""Test utilities for output suppression and common test helpers."""

import contextlib
import io
import sys
import unittest


@contextlib.contextmanager
def suppress_output():
  """Suppresses stdout and stderr for the duration of the context."""
  new_stdout, new_stderr = io.StringIO(), io.StringIO()
  old_stdout, old_stderr = sys.stdout, sys.stderr
  try:
    sys.stdout, sys.stderr = new_stdout, new_stderr
    yield new_stdout, new_stderr
  finally:
    sys.stdout, sys.stderr = old_stdout, old_stderr
