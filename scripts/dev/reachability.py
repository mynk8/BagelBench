"""Report project modules unreachable from the given entry points (static imports)."""

import ast
import sys
from pathlib import Path

ROOT = Path(sys.argv[1])
PKGS = ("bagel", "apps", "third_party")
ROOTS = sys.argv[2:]


def modname(path: Path) -> str:
    parts = list(path.relative_to(ROOT).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


modules: dict[str, Path] = {}
for pkg in PKGS:
    for p in (ROOT / pkg).rglob("*.py"):
        if "node_modules" in p.parts or "__pycache__" in p.parts:
            continue
        modules[modname(p)] = p


def imports_of(name: str) -> set[str]:
    path = modules[name]
    is_pkg = path.name == "__init__.py"
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return set()
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                anchor = name.split(".") if is_pkg else name.split(".")[:-1]
                anchor = anchor[: len(anchor) - (node.level - 1)]
                base = ".".join(anchor + ([base] if base else []))
            found.add(base)
            found.update(f"{base}.{a.name}" for a in node.names)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            # Dotted module strings (lazy alias maps, ``-m`` targets, uvicorn app paths).
            text = node.value.split(":")[0]
            if text.startswith(PKGS) and text in modules:
                found.add(text)
    return found


def resolve(target: str) -> list[str]:
    out = []
    parts = target.split(".")
    for i in range(1, len(parts) + 1):
        cand = ".".join(parts[:i])
        if cand in modules:
            out.append(cand)
    return out


seen: set[str] = set()
stack = [r for r in ROOTS if r in modules]
missing_roots = [r for r in ROOTS if r not in modules]
while stack:
    m = stack.pop()
    if m in seen:
        continue
    seen.add(m)
    for imp in imports_of(m):
        for r in resolve(imp):
            if r not in seen:
                stack.append(r)

unreached = sorted(m for m in modules if m not in seen)
lines = {m: sum(1 for _ in modules[m].open(encoding="utf-8")) for m in unreached}
print(f"roots missing: {missing_roots}")
print(
    f"reachable: {len(seen)}  unreachable: {len(unreached)}  unreachable lines: {sum(lines.values())}"
)
for m in unreached:
    print(f"{lines[m]:6d} {m}")
