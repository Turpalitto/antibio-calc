"""Golden Clinical Cases — doctor-verified input/output pairs (spec §10.1 Tier 3).

Infrastructure only. Case JSON files in this directory are authored and
verified by a physician (see README.md). Files starting with ``_`` and
``schema.json`` are infrastructure, not clinical cases.

The runner (runner.py) loads cases, runs the (unmodified) Engine, and reports
PASS/FAIL per assertion. It never modifies the Engine or the cases.
"""
