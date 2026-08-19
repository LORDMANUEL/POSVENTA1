import json
import tomllib
from pathlib import Path

from app.main import APP_VERSION


def test_product_version_is_single_source_consistent() -> None:
    root = Path(__file__).resolve().parents[2]
    version = (root / "VERSION").read_text(encoding="utf-8").strip()
    backend = tomllib.loads((root / "backend" / "pyproject.toml").read_text(encoding="utf-8"))
    frontend = json.loads((root / "frontend" / "package.json").read_text(encoding="utf-8"))
    assert version == "0.12.1"
    assert backend["project"]["version"] == version
    assert frontend["version"] == version
    assert APP_VERSION == version
