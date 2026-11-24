import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from httpx import ASGITransport, AsyncClient

from app.core.frontend import ASSET_CACHE, FrontendMiddleware


class FrontendServingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        workspace = Path(self.enterContext(TemporaryDirectory()))
        self.web = workspace / "web"
        self.h5 = workspace / "h5"
        for root, content in ((self.web, "Web 管理端"), (self.h5, "移动批卷")):
            (root / "assets").mkdir(parents=True)
            (root / "index.html").write_text(content, encoding="utf-8")
            (root / "assets" / "entry-B1234567.js").write_text(content, encoding="utf-8")

        app = FastAPI()
        app.add_middleware(FrontendMiddleware, web_dist=self.web, h5_dist=self.h5)

        @app.post("/api/v1/files")
        async def upload(request: Request):
            async with request.form() as form:
                item = form["file"]
                content = await item.read()
                return {"filename": item.filename, "size": len(content), "payload": content.decode("ascii")}

        @app.get("/api/v1/events")
        async def events():
            return StreamingResponse(iter(["event: chunk\ndata: first\n\n", "event: done\ndata: end\n\n"]),
                                     media_type="text/event-stream")

        self.client = await self.enterAsyncContext(
            AsyncClient(transport=ASGITransport(app=app), base_url="http://test"),
        )

    async def test_routes_select_their_own_bundle_and_cache_by_type(self):
        redirect = await self.client.get("/h5", params={"session": "9007199254740993"})
        self.assertEqual((redirect.status_code, redirect.headers["location"]),
                         (308, "/h5/?session=9007199254740993"))
        for prefix, deep_link, content in (
            ("/h5", "/exams/42/records", "移动批卷"),
            ("/Elearning", "/teaching-assistant/42", "Web 管理端"),
        ):
            with self.subTest(prefix=prefix):
                html = await self.client.get(prefix + deep_link)
                self.assertEqual((html.status_code, html.text, html.headers["cache-control"]), (200, content, "no-cache"))
                self.assertTrue(html.headers["content-type"].startswith("text/html"))
                head = await self.client.head(prefix + deep_link)
                self.assertEqual((head.status_code, head.content), (200, b""))
                code = await self.client.get(f"{prefix}/assets/entry-B1234567.js")
                self.assertEqual((code.status_code, code.text, code.headers["cache-control"]), (200, content, ASSET_CACHE))
                self.assertIn("javascript", code.headers["content-type"])
                missing = await self.client.get(f"{prefix}/assets/missing.js")
                self.assertEqual((missing.status_code, missing.json()), (404, {"detail": "Not Found"}))

    async def test_missing_h5_bundle_keeps_web_and_api_available(self):
        (self.h5 / "index.html").unlink()
        self.assertEqual((await self.client.get("/h5/exams/42")).status_code, 404)
        self.assertEqual((await self.client.get("/Elearning/teaching-assistant")).text, "Web 管理端")
        self.assertEqual((await self.client.get("/api/v1/events")).status_code, 200)

    async def test_shared_api_alias_preserves_upload_and_event_stream(self):
        for path in ("/api/v1", "/Elearning/api/v1"):
            with self.subTest(path=path):
                upload = await self.client.post(f"{path}/files", files={"file": ("scan.png", b"paper-upload")})
                self.assertEqual(upload.json(), {"filename": "scan.png", "size": 12, "payload": "paper-upload"})
                stream = await self.client.get(f"{path}/events")
                self.assertTrue(stream.headers["content-type"].startswith("text/event-stream"))
                self.assertEqual(stream.text, "event: chunk\ndata: first\n\nevent: done\ndata: end\n\n")
        missing = await self.client.get("/Elearning/api/v1/not-present")
        self.assertEqual((missing.status_code, missing.json()), (404, {"detail": "Not Found"}))
