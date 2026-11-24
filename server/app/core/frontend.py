"""Serve the packaged Web and H5 frontends without consuming API request bodies."""
from pathlib import Path

from starlette.concurrency import run_in_threadpool
from starlette.responses import FileResponse, RedirectResponse
from starlette.types import ASGIApp, Receive, Scope, Send


WEB_PREFIX = "/Elearning"
H5_PREFIX = "/h5"
ASSET_CACHE = "public, max-age=31536000, immutable"


def _frontend_file(root: Path, relative: str) -> Path | None:
    try:
        index = (root / "index.html").resolve()
        if not index.is_relative_to(root) or not index.is_file():
            return None
        candidate = (root / relative).resolve()
        if not candidate.is_relative_to(root):
            return None
        if candidate.is_file():
            return candidate
    except (OSError, RuntimeError, ValueError):
        return None
    if relative == "assets" or relative.startswith("assets/") or Path(relative).suffix:
        return None
    return index


class FrontendMiddleware:
    def __init__(self, app: ASGIApp, *, web_dist: Path, h5_dist: Path) -> None:
        self.app = app
        self.web_dist = web_dist.resolve()
        self.h5_dist = h5_dist.resolve()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        path = scope["path"]
        if path == f"{WEB_PREFIX}/api" or path.startswith(f"{WEB_PREFIX}/api/"):
            # Match the API path used by both Vite clients and retain the incoming body stream.
            api_scope = {**scope, "path": path[len(WEB_PREFIX):]}
            raw_path = scope.get("raw_path")
            if raw_path and raw_path.startswith(WEB_PREFIX.encode()):
                api_scope["raw_path"] = raw_path[len(WEB_PREFIX):]
            else:
                api_scope.pop("raw_path", None)
            await self.app(api_scope, receive, send)
            return
        if (scope["type"] != "http" or scope["method"] not in ("GET", "HEAD")
                or path in ("/api", "/uploads", "/health", "/docs", "/openapi.json", "/redoc")
                or path.startswith(("/api/", "/uploads/"))):
            await self.app(scope, receive, send)
            return

        prefix = H5_PREFIX if path == H5_PREFIX or path.startswith(f"{H5_PREFIX}/") else WEB_PREFIX
        root = self.h5_dist if prefix == H5_PREFIX else self.web_dist
        base = prefix if path == prefix or path.startswith(f"{prefix}/") else ""
        relative = path[len(base):].lstrip("/")
        file = await run_in_threadpool(_frontend_file, root, relative)
        if file is None:
            await self.app(scope, receive, send)
            return
        if path == prefix:
            query = scope.get("query_string", b"").decode("latin-1")
            response = RedirectResponse(f"{prefix}/" + (f"?{query}" if query else ""), status_code=308)
        else:
            cache = ASSET_CACHE if file.is_relative_to(root / "assets") else "no-cache"
            response = FileResponse(file, headers={"Cache-Control": cache})
        await response(scope, receive, send)
