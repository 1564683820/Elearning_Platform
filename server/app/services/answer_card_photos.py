"""Private, content-addressed originals for fixed-card grading."""
import hashlib
import os
import re
from pathlib import Path
from tempfile import NamedTemporaryFile

from app.core.paths import SERVER_DIR, UPLOADS_DIR
from app.services.private_document_files import PrivateFileError, validate_private_file


MAX_SCAN_PHOTO_BYTES = 12 * 1024 * 1024


def photo_reference(data: bytes, suffix: str) -> tuple[str, str]:
    suffix = suffix.lower()
    if suffix == ".jpeg":
        suffix = ".jpg"
    if suffix not in {".jpg", ".png", ".webp"}:
        raise PrivateFileError(415, "答题卡照片仅支持 JPEG、PNG 和 WebP")
    if len(data) > MAX_SCAN_PHOTO_BYTES:
        raise PrivateFileError(413, "答题卡照片最多 12 MB")
    digest = hashlib.sha256(data).hexdigest()
    return f"fixed:{digest}{suffix}", digest


def _photo_path(exam_id: int, reference: str | None) -> Path | None:
    if not reference or not re.fullmatch(r"fixed:[a-f0-9]{64}\.(?:jpg|png|webp)", reference):
        return None
    root = Path(os.environ.get("PAPER_SCAN_DIR") or SERVER_DIR / "data" / "paper_scans").resolve()
    if root.is_relative_to(UPLOADS_DIR.resolve()):
        return None
    exam_root = root / str(exam_id)
    target = (exam_root / reference.removeprefix("fixed:")).resolve()
    return target if target.is_relative_to(exam_root) else None


def find_fixed_card_photo(exam_id: int, reference: str | None) -> Path | None:
    path = _photo_path(exam_id, reference)
    return path if path and path.is_file() else None


def save_fixed_card_photo(exam_id: int, reference: str, data: bytes) -> None:
    path = _photo_path(exam_id, reference)
    if path is None:
        raise PrivateFileError(500, "答题卡照片存储不可用")
    validate_private_file(path.name, data)
    if path.is_file():
        return
    temporary = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(data)
        os.replace(temporary, path)
    except OSError as error:
        raise PrivateFileError(500, "答题卡照片存储不可用") from error
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
