"""Local text extraction and numbered choice blocks from private paper originals."""
import logging
import re
import unicodedata
from collections import defaultdict
from collections.abc import Iterable
from io import BytesIO

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.exam_models import TeacherExam
from app.models.stats import UserDocument
from app.services.document_processor import DocumentProcessor
from app.services.document_scope import EXAM_SOURCE
from app.utils.revisions import is_paper_draft


logger = logging.getLogger(__name__)
MAX_SOURCE_TEXT = 12_000
NUMBER = re.compile(r"(?m)^\s*(?:第\s*(\d{1,3})\s*题\s*[:：、.]?|[（(]?(\d{1,3})[、.)])\s*")
OPTION = re.compile(r"(?<!\S)([A-H])[.)、:]\s*")


def _ocr_pdf(data: bytes) -> str:
    import fitz
    from PIL import Image

    texts = []
    with fitz.open(stream=data, filetype="pdf") as document:
        for index in range(min(document.page_count, 4)):
            page = document.load_page(index)
            scale = min(2, 1600 / max(page.rect.width, page.rect.height, 1))
            pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), colorspace=fitz.csGRAY)
            image = Image.frombytes("L", (pixmap.width, pixmap.height), pixmap.samples)
            texts.append(DocumentProcessor._ocr_image(image, timeout=4))
    return "\n".join(texts)


def extract_source_text(kind: str, data: bytes) -> str:
    try:
        if kind == "word":
            text = DocumentProcessor._extract_docx(BytesIO(data))
        elif kind == "pdf":
            text = DocumentProcessor._extract_pdf_with_pypdf(BytesIO(data), max_pages=40)
            if not text.strip():
                text = _ocr_pdf(data)
        else:
            from PIL import Image

            with Image.open(BytesIO(data)) as image:
                image.thumbnail((1900, 1900))
                text = DocumentProcessor._ocr_image(image, timeout=4)
        return text.strip()[:MAX_SOURCE_TEXT]
    except (ImportError, OSError, RuntimeError, ValueError):
        logger.info("Exam original text unavailable for file kind %s", kind)
        return ""


def _choice_blocks(text: str):
    parts = NUMBER.split(unicodedata.normalize("NFKC", text))
    for offset in range(1, len(parts), 3):
        number, alternate, body = parts[offset:offset + 3]
        marks = list(OPTION.finditer(body))
        labels = [mark[1] for mark in marks]
        if len(labels) < 2 or labels != [chr(65 + index) for index in range(len(labels))]:
            continue
        stem = " ".join(body[:marks[0].start()].split())
        if len(stem) < 6:
            continue
        options = {}
        for index, mark in enumerate(marks):
            end = marks[index + 1].start() if index + 1 < len(marks) else len(body)
            value = body[mark.end():end].strip().split("\n\n", 1)[0]
            options[mark[1]] = " ".join(value.split())[:160]
        if all(options.values()):
            yield int(number or alternate), (stem[:400], options)


async def read_original_questions(
    db: AsyncSession, exams: Iterable[TeacherExam],
) -> dict[int, dict[int, tuple[str, dict[str, str]]]]:
    paper_exams = {exam.id: exam.teacher_id for exam in exams if is_paper_draft(exam.answer_sheet_config)}
    if not paper_exams:
        return {}
    questions = defaultdict(dict)
    conflicts = set()
    documents = await db.execute(select(UserDocument.exam_id, UserDocument.user_id, UserDocument.parsed_text).where(
        UserDocument.exam_id.in_(paper_exams), UserDocument.user_id.in_(set(paper_exams.values())),
        UserDocument.doc_category == EXAM_SOURCE, UserDocument.parse_status == 2,
    ))
    for exam_id, teacher_id, text in documents:
        if teacher_id != paper_exams.get(exam_id) or not text:
            continue
        for number, payload in _choice_blocks(text):
            current = questions[exam_id].setdefault(number, payload)
            if current != payload:
                conflicts.add((exam_id, number))
    for exam_id, number in conflicts:
        del questions[exam_id][number]
    return dict(questions)
