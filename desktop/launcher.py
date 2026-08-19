import os
import sys
from pathlib import Path
from urllib.parse import urlencode, urlparse, urlunparse, parse_qsl

import webview


MODE_MAP = {
    "milyzebra-cajera": "cashier",
    "milyzebra-vendedor": "sales",
    "milyzebra-bodeguero": "warehouse",
    "milyzebra-driver": "driver",
}


def executable_mode() -> str:
    stem = Path(sys.executable if getattr(sys, "frozen", False) else __file__).stem.lower()
    return MODE_MAP.get(stem, os.getenv("MZ_APP_MODE", "cashier"))


def build_url(base_url: str, mode: str) -> str:
    parsed = urlparse(base_url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["mode"] = mode
    return urlunparse(parsed._replace(query=urlencode(query)))


def main() -> None:
    base_url = os.getenv("MZ_APP_URL", "http://localhost:8080")
    mode = executable_mode()
    title = {
        "cashier": "Mily Zebra — Cajera",
        "sales": "Mily Zebra — Vendedor",
        "warehouse": "Mily Zebra — Bodega",
        "driver": "Mily Zebra — Driver",
    }.get(mode, "Mily Zebra")
    webview.create_window(
        title,
        build_url(base_url, mode),
        width=1360,
        height=820,
        min_size=(900, 600),
        background_color="#fff9fc",
    )
    webview.start(private_mode=False)


if __name__ == "__main__":
    main()
