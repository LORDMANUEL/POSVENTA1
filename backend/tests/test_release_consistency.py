import subprocess
import sys
from pathlib import Path


def test_release_metadata_is_consistent() -> None:
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, str(root / "scripts/check-release-consistency.py")],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "RELEASE_CONSISTENCY=PASS" in result.stdout
