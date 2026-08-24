#!/usr/bin/env python3
"""Fail when release metadata tells different version stories."""

from __future__ import annotations

import ast
import json
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def fastapi_version() -> str:
    tree = ast.parse((ROOT / "backend/app/main.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if not any(isinstance(target, ast.Name) and target.id == "APP_VERSION" for target in targets):
            continue
        value = node.value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            return value.value
    raise RuntimeError("APP_VERSION no fue encontrado en backend/app/main.py")


def main() -> int:
    expected = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    backend = tomllib.loads((ROOT / "backend/pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    frontend = json.loads((ROOT / "frontend/package.json").read_text(encoding="utf-8"))["version"]
    api = fastapi_version()

    versions = {
        "VERSION": expected,
        "backend": str(backend),
        "frontend": str(frontend),
        "api": str(api),
    }
    mismatches = {key: value for key, value in versions.items() if value != expected}
    if mismatches:
        print(f"RELEASE_CONSISTENCY=FAIL expected={expected} values={versions}")
        return 1

    print(f"RELEASE_VERSION={expected}")
    print("RELEASE_CONSISTENCY=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
