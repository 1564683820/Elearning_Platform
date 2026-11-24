"""Private exam originals backed by user_document rows and non-public files."""
import hashlib
import logging
import os
import re
from pathlib import Path
from shutil import copyfile
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.paths import SERVER_DIR, UPLOADS_DIR
from app.models.exam_models import TeacherExam
from app.models.stats import UserDocument
from app.schemas.exam_sources import ExamSourceOut
from app.schemas.paper_draft import PaperDraftOut
from app.services.document_scope import EXAM_SOURCE
from app.services.exam_source_text import extract_source_text
from app.services.paper_draft import PaperDraftError, prepare_paper_copy, read_paper_draft
from app.services.private_document_files import FORMATS, PrivateFileError, validate_private_file
from app.utils.revisions import is_paper_draft


logger = logging.getLogger(__name__)
MAX_TOTAL_BYTES = 50 * 1024 * 1024
MAX_FILES = 10


def _root() -> Path:
    root = Path(os.environ.get("PAPER_SOURCE_DIR") or SERVER_DIR / "data" / "paper_sources").resolve()
    if root.is_relative_to(UPLOADS_DIR.resolve()):
        raise PaperDraftError(500, "原件存储不可用")
    return root


def _path(key: str) -> Path | None:
    if not re.fullmatch(r"\d+/\d+/[0-9a-f]{64}/[0-9a-f]{32}\.(?:pdf|docx|jpe?g|png|webp)", key):
        return None
    base = _root()
    target = (base / key).resolve()
    return target if target.is_relative_to(base) else None


async def _exam(db: AsyncSession, teacher_id: int, exam_id: int, *, edit: bool = False):
    query = select(TeacherExam).where(TeacherExam.id == exam_id, TeacherExam.teacher_id == teacher_id)
    exam = await db.scalar(query.with_for_update() if edit else query)
    if exam is None:
        raise PaperDraftError(404, "试卷不存在")
    if edit and (exam.status != "draft" or not is_paper_draft(exam.answer_sheet_config)):
        raise PaperDraftError(409, "请先保存可编辑的纸质草稿")


def _sources(exam_id: int, teacher_id: int):
    return select(UserDocument).where(
        UserDocument.doc_category == EXAM_SOURCE, UserDocument.exam_id == exam_id, UserDocument.user_id == teacher_id,
    )


def _out(document: UserDocument) -> ExamSourceOut:
    return ExamSourceOut(id=str(document.id), name=document.filename, size=document.file_size,
                         kind=document.file_type, order=document.source_order)


async def list_sources(db: AsyncSession, teacher_id: int, exam_id: int) -> list[ExamSourceOut]:
    await _exam(db, teacher_id, exam_id)
    return [_out(document) for document in await db.scalars(_sources(exam_id, teacher_id).order_by(UserDocument.source_order))]


async def add_source(db: AsyncSession, teacher_id: int, exam_id: int, filename: str, data: bytes) -> ExamSourceOut:
    await _exam(db, teacher_id, exam_id)
    try:
        ext = await run_in_threadpool(validate_private_file, filename, data)
    except PrivateFileError as error:
        raise PaperDraftError(error.status, str(error)) from error
    digest = hashlib.sha256(filename.encode("utf-8") + b"\x00" + data).hexdigest()
    prefix = f"{teacher_id}/{exam_id}/{digest}/"
    kind = FORMATS[ext][0]
    previous = await db.scalar(_sources(exam_id, teacher_id).where(UserDocument.storage_key.startswith(prefix)))
    text = None if previous and previous.parse_status == 2 else await run_in_threadpool(extract_source_text, kind, data)
    await _exam(db, teacher_id, exam_id, edit=True)
    existing = list(await db.scalars(
        _sources(exam_id, teacher_id).with_for_update().execution_options(populate_existing=True),
    ))
    for document in existing:
        if document.storage_key.startswith(prefix):
            target = _path(document.storage_key)
            if target is None:
                raise PaperDraftError(500, "原件存储不可用")
            if not await run_in_threadpool(target.is_file):
                await run_in_threadpool(_write_file, target, data)
            metadata = _out(document)
            if document.parse_status != 2 and (text or document.parse_status != 3):
                document.parsed_text = text or None
                document.parse_status = 2 if text else 3
                await db.commit()
            return metadata
    if len(existing) >= MAX_FILES or sum(document.file_size for document in existing) + len(data) > MAX_TOTAL_BYTES:
        raise PaperDraftError(413, "每份试卷最多上传 10 个原件，总大小不超过 50 MB")
    order = max((doc.source_order for doc in existing), default=0) + 1
    if order > 32767:
        raise PaperDraftError(409, "该试卷的原件顺序已达上限")
    if text is None:
        text = await run_in_threadpool(extract_source_text, kind, data)
    key = f"{prefix}{uuid4().hex}{ext}"
    path = _path(key)
    if path is None:
        raise PaperDraftError(500, "原件存储不可用")
    document = UserDocument(user_id=teacher_id, filename=filename, file_type=kind, file_size=len(data),
                            storage_key=key, doc_category=EXAM_SOURCE, exam_id=exam_id, source_order=order,
                            parsed_text=text or None, parse_status=2 if text else 3)
    await run_in_threadpool(_write_file, path, data)
    try:
        db.add(document)
        await db.flush()
    except SQLAlchemyError:
        await run_in_threadpool(_delete_file, path)
        raise
    metadata = _out(document)
    # Keep the unique private file on uncertain commits so a retry can locate the committed row.
    await db.commit()
    return metadata


def _write_file(path: Path, contents: bytes) -> None:
    temporary = path.with_suffix(".upload")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_bytes(contents)
        temporary.replace(path)
    except OSError as error:
        raise PaperDraftError(500, "原件存储不可用") from error
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            logger.warning("Exam source staging cleanup failed")


async def _source(db: AsyncSession, teacher_id: int, exam_id: int, source_id: int, *, edit: bool = False):
    await _exam(db, teacher_id, exam_id, edit=edit)
    document = await db.scalar(_sources(exam_id, teacher_id).where(UserDocument.id == source_id))
    if document is None:
        raise PaperDraftError(404, "原件不存在")
    return document


async def download_source(db: AsyncSession, teacher_id: int, exam_id: int, source_id: int) -> tuple[Path, str, str]:
    document = await _source(db, teacher_id, exam_id, source_id)
    path = _path(document.storage_key)
    if path is None or not await run_in_threadpool(path.is_file):
        raise PaperDraftError(404, "原件文件不存在")
    return path, document.filename, FORMATS[path.suffix.lower()][1]


async def remove_source(db: AsyncSession, teacher_id: int, exam_id: int, source_id: int) -> None:
    document = await _source(db, teacher_id, exam_id, source_id, edit=True)
    path = _path(document.storage_key)
    await db.delete(document)
    await db.commit()
    if path:
        await run_in_threadpool(_delete_file, path)


def _copy_source_file(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise PaperDraftError(409, "试卷原件缺失，请补齐后再复制")
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.link(source, destination)
        except OSError:
            copyfile(source, destination)
    except OSError as error:
        raise PaperDraftError(500, "试卷原件复制失败，请重试") from error


async def copy_paper_with_sources(db: AsyncSession, teacher_id: int, exam_id: int, request_id: str) -> PaperDraftOut:
    draft, created = await prepare_paper_copy(db, teacher_id, exam_id, request_id)
    if not created:
        return await read_paper_draft(db, teacher_id, draft.id)
    paths = []
    try:
        sources = await db.scalars(_sources(exam_id, teacher_id).order_by(UserDocument.source_order).with_for_update())
        for document in sources:
            original = _path(document.storage_key)
            if original is None or not document.storage_key.startswith(f"{teacher_id}/{exam_id}/"):
                raise PaperDraftError(409, "试卷原件不可用")
            key = f"{teacher_id}/{draft.id}/{original.parent.name}/{uuid4().hex}{original.suffix}"
            target = _path(key)
            if target is None:
                raise PaperDraftError(500, "原件存储不可用")
            paths.append(target)
            await run_in_threadpool(_copy_source_file, original, target)
            db.add(UserDocument(
                user_id=teacher_id, exam_id=draft.id, source_order=document.source_order, doc_category=EXAM_SOURCE,
                filename=document.filename, file_type=document.file_type, file_size=document.file_size,
                storage_key=key, parse_status=document.parse_status, parsed_text=document.parsed_text,
            ))
        result = await read_paper_draft(db, teacher_id, draft.id)
        await db.flush()
    except (PaperDraftError, SQLAlchemyError):
        await clean_exam_source_files(paths)
        raise
    # Preserve the new paths on ambiguous commits. The original exam lock serializes retries.
    await db.commit()
    return result


def _delete_file(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        logger.warning("Exam source requires storage cleanup: object=%s", path.name)


async def detach_exam_sources(db: AsyncSession, teacher_id: int, exam_id: int) -> list[Path]:
    """Called under the same locked exam row before the owning exam is deleted."""
    paths = []
    for doc in await db.scalars(_sources(exam_id, teacher_id)):
        if path := _path(doc.storage_key):
            paths.append(path)
        await db.delete(doc)
    return paths


async def clean_exam_source_files(paths: list[Path]) -> None:
    for path in paths:
        await run_in_threadpool(_delete_file, path)


def render_pdf_page(path: Path, page: int) -> tuple[bytes, int]:
    import fitz

    if path.suffix.lower() != ".pdf":
        raise PaperDraftError(415, "该文件不支持分页预览")
    try:
        with fitz.open(path) as document:
            if not 1 <= page <= document.page_count:
                raise PaperDraftError(404, "预览页不存在")
            selected = document.load_page(page - 1)
            scale = min(2, 1100 / max(selected.rect.width, selected.rect.height, 1))
            image = selected.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
            return image.tobytes("png"), document.page_count
    except (OSError, RuntimeError, ValueError) as error:
        raise PaperDraftError(422, "无法生成 PDF 预览，请下载原件查看") from error
