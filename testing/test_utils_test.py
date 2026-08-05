"""Unit tests for testing/test_utils.py."""

import sys
import unittest
from testing.test_utils import suppress_output


class TestUtilsTest(unittest.TestCase):

  def test_suppress_output_context_manager(self):
    """Verifies that suppress_output redirects stdout/stderr during context and restores them afterwards."""
    old_stdout = sys.stdout
    old_stderr = sys.stderr

    with suppress_output() as (out_io, err_io):
      self.assertIsNot(sys.stdout, old_stdout)
      self.assertIsNot(sys.stderr, old_stderr)
      print("hello stdout")
      print("hello stderr", file=sys.stderr)

    self.assertIs(sys.stdout, old_stdout)
    self.assertIs(sys.stderr, old_stderr)
    self.assertIn("hello stdout", out_io.getvalue())
    self.assertIn("hello stderr", err_io.getvalue())


if __name__ == "__main__":
  unittest.main()
