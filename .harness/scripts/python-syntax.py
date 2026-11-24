"""Parse backend Python sources without importing them or writing bytecode."""

from __future__ import annotations

import ast
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python-syntax.py <source-directory>", file=sys.stderr)
        return 2

    source_root = Path(sys.argv[1])
    if not source_root.is_dir():
        print(f"source directory does not exist: {source_root}", file=sys.stderr)
        return 2

    failures: list[str] = []
    checked = 0
    for path in sorted(source_root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        checked += 1
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, UnicodeError, SyntaxError) as exc:
            failures.append(f"{path}: {exc}")

    if failures:
        print("Python syntax regression failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1

    print(f"Python syntax regression passed ({checked} files).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
