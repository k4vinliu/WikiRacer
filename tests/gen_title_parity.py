"""Emit speedrun.wiki.titles_match answers for the cross-lane contract test.

Run from the repo root when the case table in web/src/lib/links.test.ts changes:
    python3.11 tests/gen_title_parity.py
"""
import json
import sys
from pathlib import Path

# run as `python3.11 tests/gen_title_parity.py` from the repo root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from speedrun.wiki import titles_match  # noqa: E402

CASES = [
    ("Snake", "Snake"), ("Snake", "snake"),
    ("Guido_van_Rossum", "Guido van Rossum"),
    ("Barack Obama", "barack obama"), ("AIDS", "Aids"),
    ("Python (programming language)", "python (PROGRAMMING language)"),
    ("A  double  space", "A double space"), ("  Snake  ", "Snake"),
    ("Caf%C3%A9", "Café"), ("Snake", "Snakes"),
    ("Monty_Python%27s_Flying_Circus", "Monty Python's Flying Circus"),
]
out = {f"{a}\0{b}": titles_match(a, b) for a, b in CASES}
path = "web/src/lib/__fixtures__/py_title_parity.json"
json.dump(out, open(path, "w"), indent=1, ensure_ascii=False)
print(f"wrote {path}: {sum(out.values())}/{len(out)} match")
