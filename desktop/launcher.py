import os
from pathlib import Path

import webview


def storage_path() -> str:
    explicit = os.getenv("MZ_CACHE_DIR")
    if explicit:
        path = Path(explicit).expanduser()
    else:
        base = Path(os.getenv("LOCALAPPDATA") or os.getenv("APPDATA") or Path.home())
        path = base / "MilyZebra" / "WebView2"
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


def main() -> None:
    # El ejecutable no implementa un cliente separado: carga exactamente el mismo /admin web.
    # El rol, permisos y sucursal vienen del usuario autenticado y del backend.
    url = os.getenv("MZ_APP_URL", "http://localhost/admin").strip()
    webview.create_window(
        "Mily Zebra",
        url,
        width=1360,
        height=820,
        min_size=(900, 600),
        background_color="#fff9fc",
    )
    # Windows usa Edge WebView2 (Chromium). Persistimos su perfil para que la misma PWA
    # conserve cookies, localStorage/IndexedDB, Service Worker y la cola de ventas offline.
    webview.start(
        gui="edgechromium",
        private_mode=False,
        storage_path=storage_path(),
        debug=False,
    )


if __name__ == "__main__":
    main()
