"""`python -m clinical_engine.crosswalk` — build/verify the crosswalk artifact."""

from __future__ import annotations

import sys

from .builder import main

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
