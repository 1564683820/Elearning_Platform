import importlib.util
import io
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from zipfile import ZipFile

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from docx import Document
from pypdf import PdfWriter
from PIL import Image
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.deps import get_current_teacher_id, get_current_user_id, get_current_user_id_download
from app.api.v1.documents import router as documents_router
from app.api.v1.exam import router as exam_router
from app.db.database import Base, get_db
from app.models.exam_models import ExamSubmission, TeacherExam
from app.models.scan_models import ExamScanRecord
from app.models.stats import UserDocument
from app.services.exam_knowledge import exam_question_chunks, find_exam_knowledge
from app.services.exam_source_text import read_original_questions


def example_pdf() -> bytes:
    output = io.BytesIO()
    writer = PdfWriter()
    for _ in range(2):
        writer.add_blank_page(width=160, height=220)
    writer.write(output)
    return output.getvalue()


def choice_docx(stem: str) -> bytes:
    output = io.BytesIO()
    document = Document()
    for line in (f"1. {stem}", "A. At six", "B. At seven", "C. At eight", "D. At nine"):
        document.add_paragraph(line)
    document.save(output)
    return output.getvalue()


class ExamSourcesTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as connection:
            await connection.run_sync(lambda conn: Base.metadata.create_all(
                conn, tables=[TeacherExam.__table__, ExamSubmission.__table__, UserDocument.__table__,
                              ExamScanRecord.__table__],
            ))
        async with self.sessions() as db:
            db.add_all([
                TeacherExam(id=42, teacher_id=7, class_id=0, title="试卷", questions=[],
                            answer_sheet_config={"paper_draft": {"created": True}}),
                TeacherExam(id=43, teacher_id=7, class_id=0, title="其他试卷", questions=[],
                            answer_sheet_config={"paper_draft": {"created": True}}),
            ])
            await db.commit()

        private = TemporaryDirectory()
        self.addCleanup(private.cleanup)
        self.root = Path(private.name)
        path = patch.dict("os.environ", {"PAPER_SOURCE_DIR": private.name})
        path.start()
        self.addCleanup(path.stop)
        app = FastAPI()
        app.include_router(exam_router, prefix="/api/v1")
        app.include_router(documents_router, prefix="/api/v1")

        async def db_session():
            async with self.sessions() as db:
                yield db
                await db.commit()

        self.teacher_id = 7
        app.dependency_overrides[get_db] = db_session
        for dependency in (get_current_teacher_id, get_current_user_id, get_current_user_id_download):
            app.dependency_overrides[dependency] = lambda: self.teacher_id
        self.client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test/api/v1/")

    async def asyncTearDown(self):
        await self.client.aclose()
        await self.engine.dispose()

    async def test_upload_retry_preview_and_private_access(self):
        path = "teacher/exam/42/sources"
        data = example_pdf()
        valid = {"file": ("试卷原件.pdf", data, "application/octet-stream")}
        first = await self.client.post(path, files=valid)
        self.assertEqual(first.status_code, 200, first.text)
        metadata = first.json()["data"]
        second = await self.client.post(path, files=valid)
        self.assertEqual(second.json()["data"]["id"], metadata["id"])
        item = f"{path}/{metadata['id']}"
        listing = (await self.client.get(path)).json()["data"]
        self.assertEqual(listing, [metadata])
        file = await self.client.get(item)
        self.assertEqual(file.content, data)
        self.assertEqual(file.headers["cache-control"], "private, no-store")
        preview = await self.client.get(f"{item}/preview?page=2")
        self.assertEqual(preview.status_code, 200, preview.text if preview.status_code != 200 else "")
        self.assertTrue(preview.content.startswith(b"\x89PNG"))
        self.assertEqual(preview.headers["x-page-count"], "2")
        self.assertEqual((await self.client.get(f"{item}/preview?page=3")).status_code, 404)
        self.assertEqual((await self.client.get(f"teacher/exam/43/sources/{metadata['id']}")).status_code, 404)
        self.assertEqual((await self.client.get("documents/")).json()["data"]["items"], [])
        self.assertEqual((await self.client.get(f"documents/{metadata['id']}/download")).status_code, 404)
        self.teacher_id = 8
        self.assertEqual((await self.client.get(path)).status_code, 404)
        self.assertEqual((await self.client.delete(item)).status_code, 404)
        self.teacher_id = 7
        self.assertEqual((await self.client.delete(item)).status_code, 200)
        self.assertFalse(list(self.root.rglob("*.pdf")))

    async def test_invalid_file_does_not_displace_saved_file_and_delete_cleans_up(self):
        path = "teacher/exam/42/sources"
        first = await self.client.post(path, files={"file": ("第一份.pdf", example_pdf(), "application/pdf")})
        self.assertEqual(first.status_code, 200)
        bad = await self.client.post(path, files={"file": ("乱码.pdf", b"plain text", "application/pdf")})
        self.assertEqual(bad.status_code, 415)
        with patch("app.services.exam_sources.MAX_FILES", 1):
            full = await self.client.post(path, files={"file": ("第二份.pdf", example_pdf(), "application/pdf")})
        self.assertEqual(full.status_code, 413)
        self.assertEqual(len((await self.client.get(path)).json()["data"]), 1)
        self.assertEqual((await self.client.delete("teacher/exam/42")).status_code, 200)
        self.assertFalse(list(self.root.rglob("*.pdf")))

    async def test_original_formats_and_upload_order(self):
        docx = io.BytesIO()
        with ZipFile(docx, "w") as archive:
            archive.writestr("[Content_Types].xml",
                             '<Types><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
            archive.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body/></w:document>')
        png = io.BytesIO()
        Image.new("RGB", (10, 10), "white").save(png, format="PNG")
        path = "teacher/exam/42/sources"
        word = await self.client.post(path, files={"file": ("试题.docx", docx.getvalue(), "application/octet-stream")})
        picture = await self.client.post(path, files={"file": ("试题.png", png.getvalue(), "application/octet-stream")})
        wrong_extension = await self.client.post(path, files={"file": ("试题.webp", png.getvalue(), "image/webp")})
        self.assertEqual((word.status_code, picture.status_code, wrong_extension.status_code), (200, 200, 415))
        self.assertEqual([item["kind"] for item in (await self.client.get(path)).json()["data"]], ["word", "image"])
        self.assertEqual((await self.client.delete(f"{path}/{word.json()['data']['id']}")).status_code, 200)
        replacement = await self.client.post(path, files={"file": ("试题.docx", docx.getvalue(), "application/octet-stream")})
        self.assertEqual(replacement.json()["data"]["order"], 3)

    async def test_paper_original_grounds_question_without_changing_answer_or_grades(self):
        stem = "When did the train leave?"
        original = choice_docx(stem)
        questions = [{"type": "choice", "question_number": 1, "options": ["A", "B", "C", "D"], "answer": "B", "score": 2}]
        async with self.sessions.begin() as db:
            exam = await db.get(TeacherExam, 42)
            exam.questions = questions
            db.add(ExamSubmission(id=81, exam_id=42, exam_number="0008", answers={"1": "B"},
                                  score=2, grading_status="teacher_reviewed"))
        path = "teacher/exam/42/sources"
        response = await self.client.post(path, files={"file": ("随堂测.docx", original)})
        self.assertEqual(response.status_code, 200, response.text)
        source_id = response.json()["data"]["id"]
        async with self.sessions() as db:
            result = await find_exam_knowledge(db, 7, None, f"{stem} 这道题正确率是多少？", [])
            self.assertEqual(result["exams"][0]["count"], 1)
            item = result["exams"][0]["questions"][0]
            self.assertEqual((item["stem"], item["answer"], item["correct"]), (stem, "B", 1))
            self.assertEqual(item["option_text"]["B"], "At seven")
            self.assertNotIn("0008", str(result))
            self.assertIsNone(await find_exam_knowledge(db, 8, None, "查询教师讲评风格", []))
            other_teacher = await find_exam_knowledge(db, 8, None, f"{stem} 正确率是多少？", [])
            self.assertEqual(other_teacher["exams"], [])
            exam = await db.get(TeacherExam, 42)
            self.assertEqual(exam.questions, questions)
            evidence = await read_original_questions(db, [exam])
            self.assertIn(stem, exam_question_chunks(exam, evidence[exam.id])[0]["content"])

        conflict = await self.client.post(path, files={"file": ("编号冲突.docx", choice_docx("How early did the bus arrive?"))})
        self.assertEqual(conflict.status_code, 200, conflict.text)
        detail = await self.client.get("teacher/exam/42/grading-knowledge?question_number=1")
        self.assertEqual(detail.json()["data"]["questions"][0]["stem"], "")

        await self.client.delete(f"{path}/{conflict.json()['data']['id']}")
        detail = await self.client.get("teacher/exam/42/grading-knowledge?question_number=1")
        self.assertEqual(detail.json()["data"]["questions"][0]["stem"], stem)
        await self.client.delete(f"{path}/{source_id}")
        detail = await self.client.get("teacher/exam/42/grading-knowledge?question_number=1")
        self.assertEqual(detail.json()["data"]["questions"][0]["stem"], "")
        self.assertEqual(detail.json()["data"]["questions"][0]["correct"], 1)

    async def test_pdf_and_image_use_shared_document_extractors(self):
        import fitz

        text = "1. When did the train leave?\nA. At six\nB. At seven"
        with fitz.open() as pdf:
            pdf.new_page().insert_text((30, 80), text)
            data = pdf.tobytes()
        path = "teacher/exam/42/sources"
        result = await self.client.post(path, files={"file": ("文字层.pdf", data)})
        self.assertEqual(result.status_code, 200, result.text)
        png = io.BytesIO()
        Image.new("RGB", (100, 100), "white").save(png, format="PNG")
        with patch("app.services.exam_source_text.DocumentProcessor._ocr_image", return_value=text):
            photo = await self.client.post(path, files={"file": ("图片.png", png.getvalue())})
        self.assertEqual(photo.status_code, 200, photo.text)
        async with self.sessions() as db:
            for item in (result, photo):
                document = await db.get(UserDocument, int(item.json()["data"]["id"]))
                self.assertEqual(document.parse_status, 2)
                self.assertIn("When did the train leave?", document.parsed_text)

    async def test_copy_completed_exam_keeps_original_results_and_creates_editable_draft(self):
        path = "teacher/exam/42"
        questions = [{"type": "choice", "question_number": 1, "options": list("ABCD"), "answer": "B", "score": 2}]
        original = choice_docx("When did the train leave?")
        source = await self.client.post(f"{path}/sources", files={"file": ("试题.docx", original)})
        self.assertEqual(source.status_code, 200, source.text)
        async with self.sessions.begin() as db:
            exam = await db.get(TeacherExam, 42)
            exam.questions = questions
            exam.total_score = 2
            exam.answer_sheet_config = {
                "paper_draft": {"template_id": "10", "template_revision": "old", "template_name": "单选"},
                "paper_review": {"mode": "provided_fixed", "layout_id": "registered", "layout_version": "1",
                                 "closed_at": "2026-11-22T16:00:00Z", "lifecycle_revision": 3},
            }
            db.add(ExamSubmission(id=90, exam_id=42, exam_number="0008", answers={"1": "B"},
                                  score=2, grading_status="teacher_reviewed"))
        route = f"{path}/paper-copy"
        payload = {"request_id": "one-copy-request"}
        self.teacher_id = 8
        self.assertEqual((await self.client.post(route, json=payload)).status_code, 404)
        self.teacher_id = 7
        first = await self.client.post(route, json=payload)
        self.assertEqual(first.status_code, 200, first.text)
        copied = first.json()["data"]
        copy_id = copied["id"]
        self.assertNotEqual(copy_id, "42")
        self.assertEqual((copied["title"], copied["template_revision"], copied["questions"][0]["answer"]),
                         ("试卷（副本）", "old", "B"))

        root = f"teacher/exam/{copy_id}"
        updated = await self.client.put(f"{root}/paper-draft", json={
            "title": "修正答案的新试卷", "revision": copied["revision"], "answers": {"1": "C"},
        })
        self.assertEqual(updated.status_code, 200, updated.text)
        retry = await self.client.post(route, json=payload)
        self.assertEqual(retry.json()["data"]["id"], copy_id)
        attachments = (await self.client.get(f"{root}/sources")).json()["data"]
        self.assertEqual(len(attachments), 1)
        self.assertNotEqual(attachments[0]["id"], source.json()["data"]["id"])
        self.assertEqual((await self.client.get(f"{root}/sources/{attachments[0]['id']}")).content, original)
        self.assertEqual((await self.client.delete(f"{root}/sources/{attachments[0]['id']}")).status_code, 200)
        self.assertEqual((await self.client.get(f"{path}/sources/{source.json()['data']['id']}")).content, original)
        async with self.sessions() as db:
            original_exam = await db.get(TeacherExam, 42)
            self.assertEqual(original_exam.questions, questions)
            self.assertEqual(original_exam.answer_sheet_config["paper_review"]["lifecycle_revision"], 3)
            target = await db.get(TeacherExam, int(copy_id))
            self.assertEqual(target.answer_sheet_config["paper_review"], {
                "mode": "provided_fixed", "layout_id": "registered", "layout_version": "1",
            })
            self.assertEqual(target.source_exam_ids, "42")
            self.assertEqual((await db.get(ExamSubmission, 90)).exam_id, 42)
            self.assertIsNone(await db.scalar(sa.select(ExamSubmission).where(ExamSubmission.exam_id == int(copy_id))))

    async def test_copy_with_missing_original_rolls_back_new_exam(self):
        response = await self.client.post("teacher/exam/42/sources", files={"file": ("原件.pdf", example_pdf())})
        self.assertEqual(response.status_code, 200, response.text)
        next(self.root.rglob("*.pdf")).unlink()
        result = await self.client.post("teacher/exam/42/paper-copy", json={"request_id": "missing-file"})
        self.assertEqual((result.status_code, result.json()["detail"]), (409, "试卷原件缺失，请补齐后再复制"))
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(sa.select(sa.func.count()).select_from(TeacherExam)), 2)


class ExamSourcesMigrationTests(unittest.TestCase):
    def test_nullable_legacy_fields_and_isolated_downgrade(self):
        revision_path = Path(__file__).resolve().parents[1] / "database/alembic/versions/0016_exam_source_documents.py"
        spec = importlib.util.spec_from_file_location("exam_source_revision", revision_path)
        revision = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(revision)
        with sa.create_engine("sqlite://").begin() as conn:
            conn.exec_driver_sql("CREATE TABLE user_document (id BIGINT PRIMARY KEY, filename TEXT NOT NULL)")
            conn.exec_driver_sql("INSERT INTO user_document VALUES (1, 'legacy.pdf')")
            context = MigrationContext.configure(conn)
            with Operations.context(context):
                revision.upgrade()
                self.assertEqual(conn.exec_driver_sql("SELECT exam_id, source_order FROM user_document").one(), (None, None))
                self.assertEqual(sa.inspect(conn).get_unique_constraints("user_document")[0]["column_names"], ["exam_id", "source_order"])
                revision.downgrade()
            self.assertEqual(conn.exec_driver_sql("SELECT * FROM user_document").one(), (1, "legacy.pdf"))
