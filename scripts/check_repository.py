"""Read-only publication preflight; not a substitute for reviewing git's index."""

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP = {".git", ".venv", "node_modules", "dist", "__pycache__",
        ".pytest_cache", ".ruff_cache", ".vite"}


def main() -> None:
    errors: list[str] = []
    for directory, folders, files in os.walk(ROOT):
        folders[:] = [name for name in folders if name not in SKIP]
        for name in [*folders, *files]:
            path = Path(directory) / name
            relative = path.relative_to(ROOT)
            if not str(relative).isascii():
                errors.append(f"Non-ASCII project path: {relative}")
            if path.is_file() and path.stat().st_size > 50 * 1024 * 1024:
                errors.append(f"Large publication candidate: {relative}")
    for name in ("geocache.json", "road_matrix_cache.json", "road_geometry_cache.json"):
        if not (ROOT / "data" / "generated" / name).is_file():
            errors.append(f"Required cache missing: {name}")
    package = json.loads((ROOT / "frontend/package.json").read_text(encoding="utf-8"))
    lock = json.loads((ROOT / "frontend/package-lock.json").read_text(encoding="utf-8"))
    for key in ("dependencies", "devDependencies"):
        if package.get(key, {}) != lock["packages"][""].get(key, {}):
            errors.append(f"Frontend lockfile mismatch: {key}")
    if errors:
        raise SystemExit("\n".join(errors))
    print("Publication preflight passed: ASCII paths, cache presence, sizes, lockfile.")
    print("Review git ls-files separately for secrets and redistribution permissions.")


if __name__ == "__main__":
    main()
