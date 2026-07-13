import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import sycm_cli


class WindowsAuthTest(unittest.TestCase):
    def test_cookie_dict_filters_domains_and_prefers_sycm(self):
        items = [
            {"name": "_tb_token_", "value": "generic", "domain": ".taobao.com"},
            {"name": "_tb_token_", "value": "specific", "domain": "sycm.taobao.com"},
            {"name": "cna", "value": "123", "domain": ".taobao.com"},
            {"name": "ignored", "value": "x", "domain": "example.com"},
        ]
        self.assertEqual(
            sycm_cli._cookie_dict(items),
            {"_tb_token_": "specific", "cna": "123"},
        )

    def test_windows_browser_override(self):
        with tempfile.TemporaryDirectory() as directory:
            browser = Path(directory) / "chrome.exe"
            browser.touch()
            with patch.dict("os.environ", {"SYCM_BROWSER_PATH": str(browser)}, clear=False):
                self.assertEqual(sycm_cli._find_windows_browser(), browser)

    def test_windows_dispatches_to_cdp(self):
        expected = {"_tb_token_": "secret"}
        with patch("sycm_cli.platform.system", return_value="Windows"), patch(
            "sycm_cli._windows_cdp_cookies", return_value=expected
        ) as cdp:
            self.assertEqual(sycm_cli.load_taobao_cookies(), expected)
            cdp.assert_called_once_with()

    def test_windows_reuses_running_dedicated_browser(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            "os.environ", {"LOCALAPPDATA": directory}, clear=False
        ):
            state = Path(directory) / "sycm-cli"
            state.mkdir()
            (state / "cdp-port").write_text("32123", encoding="utf-8")
            with patch(
                "sycm_cli._cdp_cookies", return_value={"_tb_token_": "secret"}
            ), patch("sycm_cli.subprocess.Popen") as popen:
                self.assertEqual(
                    sycm_cli._windows_cdp_cookies(), {"_tb_token_": "secret"}
                )
                popen.assert_not_called()

    def test_gbk_replacement_handles_cli_emoji(self):
        buffer = io.BytesIO()
        stream = io.TextIOWrapper(buffer, encoding="gbk", errors="replace")
        stream.write("警告 ⚠️")
        stream.flush()
        self.assertIn("警告", buffer.getvalue().decode("gbk"))


if __name__ == "__main__":
    unittest.main()
