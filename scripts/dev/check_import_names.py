"""Check that every `from <project module> import name` resolves at runtime."""

import ast
import importlib
import sys
from pathlib import Path

sys.path[:0] = [".", "apps"]
bad, cache = [], {}
for pkg in ("bagel", "apps", "third_party", "tests"):
    for p in Path(pkg).rglob("*.py"):
        if (
            "node_modules" in p.parts
            or "release_candidate_v1" in p.parts
            or "scripts/androidworld" in str(p)
        ):
            continue
        for n in ast.walk(ast.parse(p.read_text())):
            if (
                isinstance(n, ast.ImportFrom)
                and n.module
                and not n.level
                and n.module.split(".")[0] in ("bagel", "apps", "third_party")
            ):
                if n.module not in cache:
                    try:
                        cache[n.module] = importlib.import_module(n.module)
                    except Exception as e:
                        cache[n.module] = e
                mod = cache[n.module]
                if isinstance(mod, Exception):
                    bad.append(
                        f"{p}:{n.lineno}: cannot import {n.module}: {type(mod).__name__}: {str(mod)[:80]}"
                    )
                    continue
                for a in n.names:
                    if a.name != "*" and not hasattr(mod, a.name):
                        try:
                            importlib.import_module(f"{n.module}.{a.name}")
                        except Exception:
                            bad.append(f"{p}:{n.lineno}: {n.module} has no {a.name}")
print("\n".join(bad) or "all imported names resolve")

raise SystemExit(bool(bad))
