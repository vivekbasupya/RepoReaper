"""Immutable evaluator: copied into an image, never exposed to the patch adapter."""
import importlib.util
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location("bounds", Path(sys.argv[1]) / "bounds.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
assert module.contains(0, 10)
assert not module.contains(-1, 10)
assert not module.contains(11, 10)
assert module.contains(10, 10), "REAPER_EXPECTED_BOUNDARY_FAILURE"
print("Trusted boundary and regression checks passed")
