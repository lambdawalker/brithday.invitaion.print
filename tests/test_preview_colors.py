import json
from pathlib import Path
import tempfile
import threading
import unittest
from http.server import HTTPServer
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import preview


class PreviewTests(unittest.TestCase):
    def test_save_preserves_layout_and_comments(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "theme.css"
            original = preview.THEME.read_text(encoding="utf-8")
            path.write_text(original, encoding="utf-8")
            colors = preview.read_colors(path)
            colors["text-color"] = "#ABCDEF"
            preview.save_colors(colors, path)
            self.assertEqual(path.read_text(encoding="utf-8"),
                             original.replace("--text-color: #fff2ce;", "--text-color: #abcdef;"))
            self.assertEqual(preview.read_colors(path)["text-color"], "#abcdef")
            colors["text-color"] = "red; display:none"
            before = path.read_bytes()
            with self.assertRaises(ValueError):
                preview.save_colors(colors, path)
            self.assertEqual(path.read_bytes(), before)
            with self.assertRaises(ValueError):
                preview.save_colors({}, path)

    def test_editor_render_and_protected_save(self):
        server = HTTPServer(("127.0.0.1", 0), preview.make_handler(Path("unused.png"), "Guest", "secret"))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            with urlopen(base) as response:
                self.assertIn("Save colors", response.read().decode())
            with patch("preview.data_uri", return_value="data:image/png;base64,AA=="):
                with urlopen(base + "/invitation?name=%3Cscript%3E") as response:
                    html = response.read().decode()
                    self.assertIn("&lt;script&gt;", html)
                    self.assertIn("--text-color: #fff2ce;", html)
                    self.assertNotIn("{% include", html)
                    self.assertIn("window.drawOrnaments", html)
            body = json.dumps(preview.read_colors()).encode()
            with patch("preview.save_colors") as save:
                with self.assertRaises(HTTPError) as denied:
                    urlopen(Request(base + "/colors", data=body))
                self.assertEqual(denied.exception.code, 403)
                save.assert_not_called()
                with urlopen(Request(base + "/colors", data=body,
                                     headers={"X-Preview-Token": "secret"})) as response:
                    self.assertTrue(json.load(response)["saved"])
                save.assert_called_once_with(preview.read_colors())
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()
