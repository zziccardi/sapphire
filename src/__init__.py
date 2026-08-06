"""Sapphire package root."""

import os
import sys

_src_dir = os.path.dirname(os.path.abspath(__file__))
_root_dir = os.path.dirname(_src_dir)

if _root_dir not in sys.path:
  sys.path.insert(0, _root_dir)
if _src_dir not in sys.path:
  sys.path.insert(0, _src_dir)
