from pathlib import Path


SERVER_DIR = Path(__file__).resolve().parents[2]
_LEGACY_UPLOADS_DIR = SERVER_DIR.parent / "backend" / "uploads"
UPLOADS_DIR = SERVER_DIR / "uploads"
# 已有工作区可以直接继续使用历史上传文件。
if not UPLOADS_DIR.is_dir() and _LEGACY_UPLOADS_DIR.is_dir():
    UPLOADS_DIR = _LEGACY_UPLOADS_DIR
