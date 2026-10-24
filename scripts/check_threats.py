#!/usr/bin/env python3
"""Checks THREATS.md against your real tests, so the document cannot drift from the code.

    python scripts/check_threats.py            (reads THREATS.md and tests/)

It reports:
  1. test names written in THREATS.md that do not exist in tests/ (typos, or renamed tests),
  2. rows marked "Done" that name no test and no check,
  3. tests that exist but are never mentioned in THREATS.md (a test with no threat is fine,
     but a long list can mean threats you forgot to write down).
Exit code 1 if (1) or (2) finds anything.
"""

import ast
import pathlib
import re
import sys

root = pathlib.Path(".")
threats_file = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else root / "THREATS.md"
if not threats_file.exists():
    sys.exit(f"{threats_file} not found")
text = threats_file.read_text(encoding="utf-8")

defined = set()
for path in (root / "tests").glob("test_*.py"):
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
            defined.add(node.name)

mentioned = set(re.findall(r"`?(test_[A-Za-z0-9_]+)`?", text))
missing = sorted(mentioned - defined)

no_evidence = []
for line in text.splitlines():
    if not line.startswith("|") or "| Done" not in line and "|Done" not in line:
        continue
    cells = [c.strip() for c in line.strip("|").split("|")]
    if cells and re.match(r"^[A-Z]-\d+", cells[0]) and not re.search(r"test_[A-Za-z0-9_]+|curl|check --deploy|settings|repository|process|startup|CI", line):
        no_evidence.append(cells[0])

print(f"{len(defined)} tests defined, {len(mentioned)} test names mentioned in {threats_file.name}")
if missing:
    print("\nNames in the threat list that match no test:")
    for name in missing:
        close = [d for d in defined if name.replace("test_", "").split("_")[0] in d][:2]
        print(f"  - {name}" + (f"   (maybe: {', '.join(close)})" if close else ""))
if no_evidence:
    print("\nRows marked Done that name no test or check: " + ", ".join(no_evidence))
unmentioned = sorted(defined - mentioned)
print(f"\n{len(unmentioned)} tests are not mentioned in the threat list (first 12):")
for name in unmentioned[:12]:
    print(f"  - {name}")
sys.exit(1 if missing or no_evidence else 0)
