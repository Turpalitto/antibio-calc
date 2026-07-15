#!/usr/bin/env python3
"""Explore clinrecs.json fields for prefilter design."""
import orjson
from config import CLINRECS_JSON

d = orjson.loads(CLINRECS_JSON.read_bytes())
print(f"Total items: {len(d)}")
print(f"First item keys: {list(d[0].keys())}")
print()

for i in d[:3]:
    print(f"Id={i['Id']} Name={str(i.get('Name',''))[:60]}")
    mkbs = i.get("Mkbs", [])
    mkb_str = "; ".join(f"{m.get('MkbCode','')} {m.get('MkbName','')[:30]}" for m in mkbs) if mkbs else "(none)"
    print(f"  MKB: {mkb_str}")
    print(f"  pdf_path: {i.get('pdf_path','')}")
    print(f"  abx_level: {i.get('abx_level','')}")
    print(f"  has_antibiotics: {i.get('has_antibiotics',0)}")
    print(f"  category: {i.get('category','')}")
    print()

# Count abx_level distribution
from collections import Counter
levels = Counter(i.get("abx_level","?") for i in d)
print(f"abx_level distribution: {dict(levels)}")

cats = Counter(i.get("category","?") for i in d)
print(f"category distribution: {dict(cats)}")

abx = Counter(i.get("has_antibiotics",0) for i in d)
print(f"has_antibiotics distribution: {dict(abx)}")
