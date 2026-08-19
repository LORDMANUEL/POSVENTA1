import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import launcher


class LauncherContractTests(unittest.TestCase):
    def test_default_url_targets_admin_through_reverse_proxy(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(launcher, "executable_mode", return_value="cashier"):
            with patch.object(launcher.webview, "create_window") as create, patch.object(launcher.webview, "start"):
                launcher.main()
        url = create.call_args.args[1]
        self.assertEqual(url, "http://localhost/admin?mode=cashier")

    def test_custom_https_url_preserves_query_and_adds_role(self):
        url = launcher.build_url("https://tienda.example/admin?tenant=mz", "warehouse")
        self.assertEqual(url, "https://tienda.example/admin?tenant=mz&mode=warehouse")


if __name__ == "__main__":
    unittest.main()
