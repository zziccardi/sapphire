"""Test utilities for output suppression and common test helpers."""

import contextlib
import io
import os
import sys
import unittest
from unittest.mock import patch


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


class QuietTestCase(unittest.TestCase):
  """TestCase base class that automatically silences stdout and stderr."""

  def setUp(self):
    super().setUp()
    self._stdout_io = io.StringIO()
    self._stderr_io = io.StringIO()
    self._stdout_patcher = patch("sys.stdout", self._stdout_io)
    self._stderr_patcher = patch("sys.stderr", self._stderr_io)
    self._stdout_patcher.start()
    self._stderr_patcher.start()

    # Redirect low-level OS file descriptors 1 and 2 to devnull so child subprocesses are silent
    self._null_fd = os.open(os.devnull, os.O_WRONLY)
    self._old_stdout_fd = os.dup(1)
    self._old_stderr_fd = os.dup(2)
    os.dup2(self._null_fd, 1)
    os.dup2(self._null_fd, 2)

  def tearDown(self):
    os.dup2(self._old_stdout_fd, 1)
    os.dup2(self._old_stderr_fd, 2)
    os.close(self._old_stdout_fd)
    os.close(self._old_stderr_fd)
    os.close(self._null_fd)
    self._stderr_patcher.stop()
    self._stdout_patcher.stop()
    super().tearDown()
