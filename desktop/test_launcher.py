import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import launcher


class LauncherContractTests(unittest.TestCase):
    def test_single_app_opens_same_admin_web_without_role_query(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch.object(launcher.webview, "create_window") as create, patch.object(launcher.webview, "start") as start:
                launcher.main()
        self.assertEqual(create.call_args.args[1], "http://localhost/admin")
        self.assertEqual(start.call_args.kwargs["gui"], "edgechromium")
        self.assertFalse(start.call_args.kwargs["private_mode"])
        self.assertIn("MilyZebra", start.call_args.kwargs["storage_path"])

    def test_custom_https_url_is_used_as_is(self):
        with patch.dict(os.environ, {"MZ_APP_URL": "https://tienda.example/admin"}, clear=True):
            with patch.object(launcher.webview, "create_window") as create, patch.object(launcher.webview, "start"):
                launcher.main()
        self.assertEqual(create.call_args.args[1], "https://tienda.example/admin")


if __name__ == "__main__":
    unittest.main()
