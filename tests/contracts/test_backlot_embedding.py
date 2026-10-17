import json
import base64
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backlot import server


class TestBacklotEmbedding(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.projects = Path(self.tmp.name) / "projects"
        self.project = self.projects / "embedding-test"
        self.project.mkdir(parents=True)
        (self.project / "project.json").write_text(json.dumps({
            "project_id": "embedding-test", "title": "Embedding Test", "pipeline_type": "unknown"
        }), encoding="utf-8")
        (self.project / "renders").mkdir()
        (self.project / "renders" / "sample.mp4").write_bytes(b"range-test-content")
        (self.project / "assets").mkdir()
        (self.project / "assets" / "pixel.png").write_bytes(base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/FxoAAAAASUVORK5CYII="
        ))
        self.prefix = "/api/v1/openmontage/backlot"
        self.projects_patch = patch.object(server, "PROJECTS_DIR", self.projects)
        self.projects_patch.start()

    def tearDown(self):
        self.projects_patch.stop()
        self.tmp.cleanup()

    def client(self, prefix=""):
        return TestClient(server.create_app(base_path=prefix))

    def test_base_path_normalization(self):
        self.assertEqual(server.normalize_base_path(self.prefix), self.prefix)
        self.assertEqual(server.normalize_base_path(""), "")
        for invalid in ("relative", "//host/path", "/one/../two", "/with space", "/trailing/"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                server.normalize_base_path(invalid)

    def test_prefixed_html_imports_state_media_and_events(self):
        client = self.client(self.prefix)
        page = client.get("/p/embedding-test?embedded=1")
        self.assertEqual(page.status_code, 200)
        self.assertIn(f'<meta name="backlot-base-path" content="{self.prefix}">', page.text)
        self.assertIn(f'href="{self.prefix}/ui/board.css?', page.text)
        self.assertIn(f'src="{self.prefix}/ui/board.js?', page.text)

        script = client.get("/ui/board.js")
        self.assertEqual(script.status_code, 200)
        self.assertIn('from "./lib.js"', script.text)
        self.assertIn("controls above this panel", script.text)
        self.assertIn("getJSON(`/api/project/", script.text)
        helper = client.get("/ui/lib.js").text
        self.assertIn("new EventSource(backlotURL(url))", helper)

        state = client.get("/api/project/embedding-test/state")
        self.assertEqual(state.status_code, 200)
        self.assertEqual(state.json()["project_id"], "embedding-test")
        paths = {route.path for route in client.app.routes}
        self.assertIn("/api/project/{project_id}/events", paths)

    def test_prefix_empty_keeps_standalone_urls(self):
        client = self.client()
        page = client.get("/p/embedding-test")
        self.assertIn('content=""', page.text)
        self.assertIn('href="/ui/board.css?', page.text)
        script = client.get("/ui/lib.js").text
        self.assertIn("return `${prefix}${path.startsWith", script)

    def test_media_supports_head_and_range_and_rejects_path_traversal(self):
        client = self.client(self.prefix)
        url = "/media/embedding-test/renders/sample.mp4"
        head = client.head(url)
        self.assertEqual(head.status_code, 200)
        self.assertEqual(head.content, b"")
        get = client.get(url)
        self.assertEqual(head.headers["content-length"], get.headers["content-length"])
        ranged = client.get(url, headers={"Range": "bytes=0-4"})
        self.assertEqual(ranged.status_code, 206)
        self.assertEqual(ranged.content, b"range")
        self.assertEqual(ranged.headers["content-range"], "bytes 0-4/18")
        if_range = client.get(url, headers={"Range": "bytes=0-4", "If-Range": get.headers["etag"]})
        self.assertEqual(if_range.status_code, 206)
        stale_if_range = client.get(url, headers={"Range": "bytes=0-4", "If-Range": '"stale"'})
        self.assertEqual(stale_if_range.status_code, 200)
        invalid_range = client.get(url, headers={"Range": "bytes=999-"})
        self.assertEqual(invalid_range.status_code, 416)
        traversal = client.get("/media/embedding-test/%2e%2e/project.json")
        self.assertIn(traversal.status_code, {400, 403, 404})

    def test_thumb_supports_head_and_invalid_project_id_is_rejected(self):
        client = self.client(self.prefix)
        url = "/thumb/embedding-test/assets/pixel.png"
        self.assertEqual(client.head(url).status_code, 200)
        self.assertEqual(client.head(url).content, b"")
        self.assertEqual(client.get("/p/a%2Fb").status_code, 400)


if __name__ == "__main__":
    unittest.main()
