from io import BytesIO
import json
import random
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from PIL import Image, ImageDraw
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.schema import CreateTable

from app.api.deps import get_current_teacher_id
from app.api.v1.exam import router
from app.db.database import get_db
from app.models.class_models import Class, ClassStudent, ClassStudentInfo, ClassTeacher
from app.models.exam_models import ExamGradingLog, ExamSubmission, TeacherExam
from app.models.scan_models import ExamScanRecord, WrongQuestionBook
from app.models.stats import UserDocument
from app.models.user import User
from app.services.fixed_paper_review import PaperReviewError, stage_recognition


def sample_photo(variant=0):
    with BytesIO() as data:
        Image.new("RGB", (32, 28), (140 + variant, 180, 160)).save(data, format="PNG")
        return data.getvalue()


class FixedPaperReviewTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.photo_dir = self.enterContext(TemporaryDirectory())
        self.enterContext(patch.dict("os.environ", {"PAPER_SCAN_DIR": self.photo_dir}))
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as conn:
            for model in (TeacherExam, ExamScanRecord, ExamSubmission, ExamGradingLog, ClassTeacher, Class,
                          ClassStudent, ClassStudentInfo, User, WrongQuestionBook, UserDocument):
                await conn.execute(CreateTable(model.__table__))
        layout = {"paper_draft": {"template_id": "41", "template_name": "测试模板"},
                  "paper_review": {"mode": "provided_fixed", "layout_id": "synthetic", "layout_version": "1"}}
        questions = [
            {"type": "choice", "question_number": 1, "option_count": 4, "options": ["A", "B", "C", "D"], "score": 2, "answer": "B"},
            {"type": "choice", "question_number": 2, "option_count": 3, "options": ["A", "B", "C"], "score": 4, "answer": "C"},
        ]
        async with self.sessions.begin() as db:
            db.add_all([
                TeacherExam(id=42, teacher_id=7, class_id=0, title="无班级", questions=questions, answer_sheet_config=layout),
                TeacherExam(id=43, teacher_id=7, class_id=10, title="有班级", questions=questions, answer_sheet_config=layout),
                UserDocument(id=82, exam_id=42, user_id=7, filename="原件.pdf", file_type="pdf", file_size=100,
                             storage_key="fixture-42", doc_category="exam_source", source_order=1),
                UserDocument(id=83, exam_id=43, user_id=7, filename="原件.pdf", file_type="pdf", file_size=100,
                             storage_key="fixture-43", doc_category="exam_source", source_order=1),
                Class(id=10, name="八年级 2 班", invite_code="fixture10", created_by=7),
                ClassTeacher(id=1, class_id=10, teacher_id=7),
                ClassStudentInfo(id=63, class_id=10, student_number=1, student_name="样例", exam_number="00824"),
                ClassStudent(id=3, class_id=10, student_id=112),
                User(id=112, nickname="样例", openid="student-fixture", account="student"),
            ])
        self.teacher_id = 7
        app = FastAPI()
        app.include_router(router)

        async def db_session():
            async with self.sessions() as db:
                try:
                    yield db
                    await db.commit()
                except Exception:
                    await db.rollback()
                    raise

        app.dependency_overrides[get_db] = db_session
        app.dependency_overrides[get_current_teacher_id] = lambda: self.teacher_id
        self.client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test/teacher/exam/")

    async def asyncTearDown(self):
        await self.client.aclose()
        await self.engine.dispose()

    async def stage(self, request_id, *, exam_id=42, number="00824", marked="C", uncertain=(), variant=0,
                    layout="synthetic", photo_data=None, failure_state=None, exam_number_length=None):
        async with self.sessions.begin() as db:
            record = await stage_recognition(
                db, exam_id, 7, request_id=request_id, layout_id=layout, layout_version="1",
                photo_data=sample_photo(variant) if photo_data is None else photo_data, photo_suffix=".png", exam_number=number,
                raw_answers=[{"question_number": 1, "student_answer": "B"}, {"question_number": 2, "student_answer": marked}],
                uncertain_questions=list(uncertain), failure_state=failure_state,
                exam_number_length=exam_number_length,
            )
            return f"{exam_id}/fixed-reviews/{record.id}"

    async def read(self, path):
        response = await self.client.get(path)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["data"]

    async def confirm(self, path, view):
        previous = view["previous_grade"] or {}
        return await self.client.post(path + "/confirm", json={
            "revision": view["revision"], "previous_submission_id": previous.get("submission_id"),
            "previous_grade_version": previous.get("grade_version"),
        })

    async def test_handwritten_card_requires_full_ascii_number_and_preserves_leading_zero(self):
        path = await self.stage("handwritten-1", number="", exam_number_length=5)
        review = await self.read(path)
        self.assertEqual(review["exam_number_length"], 5)
        for invalid in ("00824X", "000824", "008２4"):
            response = await self.client.put(path, json={"revision": review["revision"], "exam_number": invalid})
            self.assertEqual(response.status_code, 422, response.text)
        partial = await self.client.put(path, json={"revision": review["revision"], "exam_number": "0082"})
        self.assertEqual(partial.status_code, 200, partial.text)
        short = partial.json()["data"]
        self.assertEqual((await self.confirm(path, short)).status_code, 422)
        full = await self.client.put(path, json={"revision": short["revision"], "exam_number": "00824"})
        self.assertEqual(full.status_code, 200, full.text)
        confirmed = await self.confirm(path, full.json()["data"])
        self.assertEqual(confirmed.status_code, 200, confirmed.text)
        self.assertEqual((await self.read(path))["exam_number"], "00824")

    async def test_pending_edits_confirm_and_retry_keep_one_submission(self):
        with self.assertRaisesRegex(PaperReviewError, "版式与试卷不一致"):
            await self.stage("wrong-card", layout="different")
        path = await self.stage("first", number="", marked="AB", uncertain=(2,))
        self.assertEqual(path, await self.stage("first", number="", marked="AB", uncertain=(2,)))
        with self.assertRaisesRegex(PaperReviewError, "其他照片"):
            await self.stage("first", variant=1)
        original = await self.read(path)
        queue = await self.read("42/fixed-reviews")
        self.assertEqual((queue["total"], queue["items"][0]["id"]), (1, original["id"]))
        self.assertTrue(original["questions"][1]["needs_review"])
        self.assertEqual((await self.confirm(path, original)).status_code, 422)
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(select(func.count()).select_from(ExamSubmission)), 0)
        corrected = await self.client.put(path, json={
            "revision": original["revision"], "exam_number": " 00824 ", "answers": {"2": "C"},
        })
        self.assertEqual(corrected.status_code, 200, corrected.text)
        view = corrected.json()["data"]
        self.assertEqual(view["exam_number"], "00824")
        conflict = await self.confirm(path, original)
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.json()["error_code"], "paper_review_conflict")
        confirmed = await self.confirm(path, view)
        self.assertEqual(confirmed.status_code, 200, confirmed.text)
        receipt = confirmed.json()["data"]
        self.assertEqual((receipt["score"], receipt["grade_version"]), (6, 1))
        self.assertEqual((await self.confirm(path, view)).json()["data"], receipt)
        self.assertEqual(await self.read("42/fixed-reviews"), {"total": 0, "items": []})
        self.teacher_id = 8
        self.assertEqual((await self.client.get(path)).status_code, 404)
        self.teacher_id = 7
        async with self.sessions() as db:
            row = await db.get(ExamSubmission, int(receipt["submission_id"]))
            self.assertEqual(row.unmatched_exam_number, "00824")
            self.assertEqual(await db.scalar(select(func.count()).select_from(ExamGradingLog)), 1)

    async def test_regrade_requires_current_version_and_keeps_old_review(self):
        initial = await self.stage("initial")
        receipt = (await self.confirm(initial, await self.read(initial))).json()["data"]
        second = await self.stage("second", marked="")
        competing = await self.stage("third")
        preview = await self.read(second)
        stale = await self.read(competing)
        self.assertEqual(preview["previous_grade"]["grade_version"], 1)
        self.assertEqual(preview["previous_grade"]["max_score"], 6)
        replaced = await self.confirm(second, preview)
        self.assertEqual(replaced.status_code, 200, replaced.text)
        current = replaced.json()["data"]
        self.assertEqual((current["submission_id"], current["grade_version"], current["score"]), (receipt["submission_id"], 2, 2))
        conflict = await self.confirm(competing, stale)
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.json(), {"detail": "已有成绩已变化，请重新核对后确认", "error_code": "paper_review_conflict"})
        latest = await self.read(competing)
        self.assertEqual(latest["previous_grade"]["grade_version"], 2)
        confirmed = await self.confirm(competing, latest)
        self.assertEqual(confirmed.status_code, 200, confirmed.text)
        self.assertEqual(confirmed.json()["data"]["grade_version"], 3)
        self.assertEqual((await self.read(initial))["status"], "replaced")
        self.assertEqual((await self.read(initial))["receipt"]["score"], 6)

    async def test_regrade_from_detail_reuses_photo_without_replacing_score_until_confirmed(self):
        initial = await self.stage("original")
        original = await self.read(initial)
        posted = await self.confirm(initial, original)
        self.assertEqual(posted.status_code, 200, posted.text)
        receipt = posted.json()["data"]
        record = f'42/grading-records/{receipt["submission_id"]}'
        request = {"grade_version": 1, "request_id": "record-regrade"}

        self.teacher_id = 8
        self.assertEqual((await self.client.post(record + "/regrade", json=request)).status_code, 404)
        self.teacher_id = 7
        prepared = await self.client.post(record + "/regrade", json=request)
        self.assertEqual(prepared.status_code, 200, prepared.text)
        result = prepared.json()["data"]
        self.assertEqual((await self.client.post(record + "/regrade", json=request)).json()["data"], result)
        reopened = await self.client.post(record + "/regrade", json={**request, "request_id": "different-tab"})
        self.assertEqual(reopened.json()["data"], result)
        self.assertEqual((await self.read("42/fixed-reviews"))["total"], 1)
        self.assertEqual((await self.read(record))["score"], 6)

        route = f'42/fixed-reviews/{result["scan_id"]}'
        draft = await self.read(route)
        self.assertEqual(draft["regrade_submission_id"], receipt["submission_id"])
        self.assertEqual(draft["questions"], original["questions"])
        self.assertEqual((await self.client.get(route + "/photo")).content, sample_photo())
        invalid = await self.client.put(route, json={"revision": draft["revision"], "exam_number": "00825"})
        self.assertEqual(invalid.status_code, 422)
        response = await self.client.put(route, json={"revision": draft["revision"], "exam_number": "00824", "answers": {"2": ""}})
        self.assertEqual(response.status_code, 200, response.text)
        confirmed = await self.confirm(route, response.json()["data"])
        self.assertEqual(confirmed.status_code, 200, confirmed.text)
        self.assertEqual(confirmed.json()["data"]["submission_id"], receipt["submission_id"])
        self.assertEqual((await self.read(record))["score"], 2)
        self.assertEqual((await self.read(initial))["receipt"]["score"], 6)
        self.assertEqual((await self.client.post(record + "/regrade", json={**request, "request_id": "new-request"})).status_code, 409)
        self.assertEqual((await self.client.post(record + "/regrade", json=request)).json()["data"], result)

    async def test_records_can_filter_and_page_grade_rows_with_scan_attempts(self):
        first = await self.stage("submitted", exam_id=43)
        grade = (await self.confirm(first, await self.read(first))).json()["data"]
        pending = await self.stage("pending", exam_id=43, variant=1)
        failed = await self.stage("failed", exam_id=43, number="", variant=2, failure_state="retake")
        discarded = await self.stage("discarded", exam_id=43, number="00826", variant=3)
        discarded_revision = (await self.read(discarded))["revision"]
        self.assertEqual((await self.client.post(discarded + "/discard", json={
            "revision": discarded_revision, "reason": "样例",
        })).status_code, 200)
        root = "43/grading-records"
        original = await self.read(root)
        self.assertEqual((original["total"], original["pending"]), (1, 0))

        mixed = await self.read(root + "?include_scans=true&page_size=2")
        second = await self.read(root + "?include_scans=true&page_size=2&page=2")
        self.assertEqual((mixed["total"], mixed["confirmed"], mixed["pending"]), (4, 1, 1))
        self.assertEqual({(item["id"], item["record_kind"], item["status"]) for item in mixed["items"] + second["items"]}, {
            (grade["submission_id"], "submission", "confirmed"), (pending.split("/")[-1], "scan", "review"),
            (failed.split("/")[-1], "scan", "failed"), (discarded.split("/")[-1], "scan", "historical"),
        })

        filtered = await self.read(root + "?include_scans=true&status=review&search=样例")
        self.assertEqual(filtered["total"], 1)
        self.assertEqual((filtered["items"][0]["id"], filtered["items"][0]["score"]), (pending.split("/")[-1], None))
        failed_rows = await self.read(root + "?include_scans=true&status=failed")
        self.assertEqual([item["id"] for item in failed_rows["items"]], [failed.split("/")[-1]])
        async with self.sessions.begin() as db:
            await db.execute(delete(ClassTeacher).where(ClassTeacher.class_id == 10))
        self.assertEqual((await self.read(root + "?include_scans=true"))["total"], 1)
        self.teacher_id = 8
        self.assertEqual((await self.client.get(root + "?include_scans=true")).status_code, 404)

    async def test_exam_card_view_searches_and_pages_by_paper_state_and_recent_activity(self):
        from datetime import datetime

        async with self.sessions.begin() as db:
            first = await db.get(TeacherExam, 42)
            first.title = "Unit 3 % 周练"
            first.created_at = first.updated_at = datetime(2026, 10, 20)
            second = await db.get(TeacherExam, 43)
            second.title = "Unit 3 随堂测"
            second.created_at = second.updated_at = datetime(2026, 10, 18)
        staged = await self.stage("confirmed", exam_id=43)
        self.assertEqual((await self.confirm(staged, await self.read(staged))).status_code, 200)
        await self.stage("pending", exam_id=43)
        legacy = await self.read("list?status=draft")
        self.assertEqual([item["id"] for item in legacy["items"]], [42, 43])
        self.assertNotIn("confirmed_count", legacy["items"][0])
        result = await self.read("list?grading_view=true&search=unit%203&page_size=1")
        self.assertEqual(result["total"], 2)
        card = result["items"][0]
        self.assertEqual((card["id"], card["class_name"], card["paper_state"]), (43, "八年级 2 班", "grading"))
        self.assertEqual((card["confirmed_count"], card["pending_count"]), (1, 1))
        self.assertGreater(card["updated_at"], card["created_at"])
        page_two = await self.read("list?grading_view=true&search=unit%203&page_size=1&page=2")
        self.assertEqual([item["id"] for item in page_two["items"]], [42])
        matches = await self.read("list?search=%25&paper_status=draft&page_size=1")
        self.assertEqual((matches["total"], [item["id"] for item in matches["items"]]), (1, [42]))
        grading = await self.read("list?paper_status=grading")
        self.assertEqual((grading["total"], [item["id"] for item in grading["items"]]), (1, [43]))
        beyond = await self.read("list?paper_status=grading&page_size=1&page=2")
        self.assertEqual((beyond["total"], beyond["items"]), (1, []))
        self.teacher_id = 8
        self.assertEqual((await self.read("list?grading_view=true"))["total"], 0)

    async def test_close_and_reopen_share_a_versioned_paper_state(self):
        state_path = "42/paper-grading-state"

        async def change(target, revision):
            return await self.client.put(state_path, json={"state": target, "revision": revision})

        initial = await self.read(state_path)
        self.assertEqual((initial["state"], initial["recognition_blocker"]), ("draft", "固定答题卡版式未配置"))
        preview = await self.client.get("42/fixed-card/reference")
        self.assertEqual((preview.status_code, preview.content), (204, b""))
        self.assertEqual((await change("completed", 0)).status_code, 409)
        self.assertEqual((await change("grading", 0)).status_code, 409)
        first = await self.stage("first")
        self.assertEqual((await self.confirm(first, await self.read(first))).status_code, 200)
        pending = await self.stage("second", number="00825")
        state = await self.read(state_path)
        self.assertEqual((state["state"], state["confirmed"], state["pending"], state["expected"]), ("grading", 1, 1, None))
        self.assertEqual((await change("completed", 0)).status_code, 409)
        self.assertEqual((await self.confirm(pending, await self.read(pending))).status_code, 200)
        closed = await change("completed", 0)
        self.assertEqual(closed.status_code, 200, closed.text)
        state = closed.json()["data"]
        self.assertEqual((state["state"], state["revision"], state["confirmed"], state["pending"]), ("completed", 1, 2, 0))
        self.assertIsNotNone(state["closed_at"])
        rows = (await self.read("list"))["items"]
        listed = next(item for item in rows if str(item["id"]) == "42")
        self.assertEqual((listed["paper_state"], listed["status"]), ("completed", "draft"))
        self.assertEqual((await change("completed", 0)).json()["data"], state)
        with self.assertRaisesRegex(PaperReviewError, "批卷已结束"):
            await self.stage("too-late", number="00826")
        self.assertEqual((await self.read(first))["receipt"]["grade_version"], 1)
        self.teacher_id = 8
        self.assertEqual((await change("grading", 1)).status_code, 404)
        self.teacher_id = 7
        reopened = await change("grading", 1)
        self.assertEqual(reopened.status_code, 200, reopened.text)
        self.assertEqual((reopened.json()["data"]["state"], reopened.json()["data"]["revision"]), ("grading", 2))
        self.assertIsNone(reopened.json()["data"]["closed_at"])
        self.assertEqual((await change("completed", 0)).status_code, 409)
        await self.stage("additional", number="00826")
        self.assertEqual((await self.read(state_path))["pending"], 1)
        async with self.sessions() as db:
            exam = await db.get(TeacherExam, 42)
            self.assertEqual(exam.status, "draft")
            self.assertEqual(exam.answer_sheet_config["paper_review"]["layout_id"], "synthetic")

    async def test_fixed_upload_uses_registered_artwork_and_preserves_request_results(self):
        import cv2
        import numpy as np

        directory = Path(self.photo_dir) / "calibrations" / "synthetic" / "1"
        directory.mkdir(parents=True)
        self.enterContext(patch.dict("os.environ", {"PAPER_FIXED_CARD_LAYOUT_DIR": str(directory.parents[1])}))
        reference = Image.new("L", (840, 1080), "white")
        draw = ImageDraw.Draw(reference)
        randomizer = random.Random(7)
        for x, y in ((30, 35), (615, 35), (30, 850), (615, 850)):
            for _ in range(90):
                ox, oy = x + randomizer.randrange(170), y + randomizer.randrange(170)
                draw.rectangle((ox, oy, ox + randomizer.randrange(3, 15), oy + randomizer.randrange(3, 15)), fill=0)
        def region(x, y, size=16):
            return {"cx": x, "cy": y, "w": size, "h": size}
        questions = {number: {label: region(300 + 32 * index, 430 + 40 * number)
                              for index, label in enumerate(labels)}
                     for number, labels in ((1, "ABCD"), (2, "ABC"))}
        number_columns = [{str(digit): region(530 + 35 * col, 390 + digit * 24, 10)
                           for digit in range(10)} for col in range(2)]
        calibration = {
            "identity_regions": [region(115, 120, 144), region(700, 935, 144)],
            "question_regions": questions, "exam_number_columns": number_columns,
        }
        reference.save(directory / "reference.png")
        (directory / "layout.json").write_text(json.dumps(calibration), encoding="utf8")
        preview = await self.client.get("42/fixed-card/reference")
        self.assertEqual(preview.status_code, 200, preview.text if preview.status_code != 200 else "")
        self.assertEqual(preview.headers["content-type"], "image/png")
        self.assertEqual(preview.headers["x-paper-layout-version"], "1")
        self.assertEqual(preview.headers["cache-control"], "private, no-store")
        self.assertEqual(preview.content, (directory / "reference.png").read_bytes())
        self.teacher_id = 8
        self.assertEqual((await self.client.get("42/fixed-card/reference")).status_code, 404)
        self.teacher_id = 7
        self.assertTrue((await self.read("42/paper-grading-state"))["recognition_available"])
        self.assertEqual((await self.read("43/paper-grading-state"))["recognition_available"], True)
        self.assertEqual((await self.read("42/paper-grading-state"))["state"], "ready")
        draft = await self.read("42/paper-draft")

        filled = reference.copy()
        painter = ImageDraw.Draw(filled)
        for roi in (questions[1]["B"], questions[2]["A"], questions[2]["C"], number_columns[0]["0"], number_columns[1]["7"]):
            x, y, radius = roi["cx"], roi["cy"], roi["w"] // 2
            painter.rectangle((x - radius, y - radius, x + radius, y + radius), fill=0)
        source = np.float32([[0, 0], [839, 0], [839, 1079], [0, 1079]])
        target = np.float32([[27, 22], [807, 55], [826, 1049], [45, 1020]])
        photo = cv2.warpPerspective(np.array(filled), cv2.getPerspectiveTransform(source, target), (860, 1100), borderValue=255)
        success, encoded = cv2.imencode(".png", photo)
        self.assertTrue(success)
        photo_bytes = encoded.tobytes()

        async def upload(request_id, content):
            return await self.client.post("42/fixed-scan", data={"request_id": request_id},
                                          files={"image": ("capture.png", content, "image/png")})

        async with self.sessions.begin() as db:
            original = await db.get(UserDocument, 82)
            original.doc_category = "chat_attachment"
        unavailable = await self.read("42/paper-grading-state")
        self.assertEqual((unavailable["state"], unavailable["recognition_blocker"]), ("draft", "请先添加试卷原件"))
        listing = await self.read("list")
        self.assertEqual({str(item["id"]): item["paper_state"] for item in listing["items"]}, {"42": "draft", "43": "ready"})
        blocked = await upload("camera_001", photo_bytes)
        self.assertEqual((blocked.status_code, blocked.json()["detail"]), (409, "请先添加试卷原件"))
        finalize = {"finalize": True, "title": "确认试卷", "revision": draft["revision"]}
        blocked_save = await self.client.put("42/paper-draft", json=finalize)
        self.assertEqual((blocked_save.status_code, blocked_save.json()["detail"]), (409, "请先添加试卷原件"))
        self.assertEqual((await self.read("42/paper-draft"))["title"], draft["title"])
        async with self.sessions.begin() as db:
            original = await db.get(UserDocument, 82)
            original.doc_category = "exam_source"
        missing_values = calibration["question_regions"][2].pop("C")
        (directory / "layout.json").write_text(json.dumps(calibration), encoding="utf8")
        invalid = await self.read("42/paper-grading-state")
        self.assertEqual((invalid["state"], invalid["recognition_blocker"]), ("draft", "固定答题卡第 2 题缺少 C 选项"))
        calibration["question_regions"][2]["C"] = missing_values
        (directory / "layout.json").write_text(json.dumps(calibration), encoding="utf8")
        finalized = await self.client.put("42/paper-draft", json=finalize)
        self.assertEqual(finalized.status_code, 200, finalized.text)
        self.assertEqual((await self.read("42/paper-grading-state"))["state"], "ready")

        response = await upload("camera_001", photo_bytes)
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()["data"]
        self.assertEqual(result["state"], "review")
        self.assertEqual((await upload("camera_001", photo_bytes)).json()["data"], result)
        self.assertEqual((await upload("camera_001", sample_photo())).status_code, 409)
        review = await self.read(f"42/fixed-reviews/{result['scan_id']}")
        self.assertEqual(review["exam_number"], "07")
        self.assertEqual([question["marked"] for question in review["questions"]], ["B", "AC"])
        self.assertTrue(review["questions"][1]["needs_review"])
        self.assertEqual((await upload("camera_002", sample_photo())).json()["data"]["state"], "retake")
        wrong = filled.copy()
        ImageDraw.Draw(wrong).rectangle((40, 45, 185, 195), fill=255)
        with BytesIO() as image:
            wrong.save(image, format="PNG")
            result = await upload("camera_003", image.getvalue())
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()["data"]["state"], "layout_mismatch")
        self.assertEqual((await self.read("42/fixed-reviews"))["total"], 1)
        attempts = await self.read("42/fixed-reviews?status=failed")
        self.assertEqual(attempts["total"], 2)
        failed_scan = await self.read(f"42/fixed-reviews/{result.json()['data']['scan_id']}")
        self.assertEqual((failed_scan["status"], failed_scan["reason"]), ("failed", "答题卡版式不匹配"))
        self.assertTrue(failed_scan["has_photo"])
        self.teacher_id = 8
        self.assertEqual((await upload("camera_001", photo_bytes)).status_code, 404)
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(select(func.count()).select_from(ExamSubmission)), 0)
            self.assertEqual(await db.scalar(select(func.count()).select_from(ExamScanRecord)
                                            .where(ExamScanRecord.status == "failed")), 2)

    async def test_confirmed_multiple_marks_score_zero_and_remain_distinct_from_blank(self):
        path = await self.stage("multiple", marked="BA", uncertain=(2,))
        original = await self.read(path)
        self.assertEqual(original["questions"][1]["raw_marked"], "BA")
        self.assertTrue(original["questions"][1]["needs_review"])
        draft = {"revision": original["revision"], "exam_number": "00824"}
        for invalid in (["A", "A"], ["A", "D"], ["A"]):
            result = await self.client.put(path, json={**draft, "invalid_answers": {"2": invalid}})
            self.assertEqual(result.status_code, 422, result.text)
        conflict = await self.client.put(path, json={**draft, "answers": {"2": ""}, "invalid_answers": {"2": ["A", "B"]}})
        self.assertEqual(conflict.status_code, 422, conflict.text)
        edited = await self.client.put(path, json={**draft, "invalid_answers": {"2": [" b ", "C"]}})
        self.assertEqual(edited.status_code, 200, edited.text)
        view = edited.json()["data"]
        question = view["questions"][1]
        self.assertEqual((question["marked"], question["raw_marked"], question["score"]), ("BC", "BA", 0))
        self.assertTrue(question["invalid_mark"])
        self.assertFalse(question["needs_review"])
        confirmed = await self.confirm(path, view)
        self.assertEqual(confirmed.status_code, 200, confirmed.text)
        receipt = confirmed.json()["data"]
        self.assertEqual((receipt["score"], receipt["max_score"]), (2, 6))
        details = await self.read(f"42/grading-records/{receipt['submission_id']}")
        second = details["questions"][1]
        self.assertEqual((second["marked"], second["raw"], second["invalid_mark"]), ("BC", "BA", True))
        blank = await self.stage("blank", number="00825", marked="")
        self.assertEqual((await self.confirm(blank, await self.read(blank))).status_code, 200)
        stats = await self.read("42/grading-knowledge?question_number=2")
        self.assertEqual(stats["count"], 2)
        self.assertEqual(stats["questions"][0]["distribution"], {"无效填涂": 1, "空白": 1, "C": 0})
        self.assertEqual(stats["questions"][0]["correct"], 0)

    async def test_discard_keeps_photo_and_unlocks_ungraded_draft(self):
        path = await self.stage("discard")
        original = await self.read(path)
        draft = await self.read("42/paper-draft")
        body = {"title": "重新配置", "answers": {"2": "A"}, "revision": draft["revision"]}
        self.assertEqual((await self.client.put("42/paper-draft", json=body)).status_code, 409)
        request = {"revision": original["revision"], "reason": "  答题卡拍反  "}
        self.assertEqual((await self.client.post(path + "/discard", json={**request, "revision": "stale"})).status_code, 409)
        self.teacher_id = 8
        self.assertEqual((await self.client.post(path + "/discard", json=request)).status_code, 404)
        self.teacher_id = 7
        for _ in range(2):
            response = await self.client.post(path + "/discard", json=request)
            self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual((await self.read("42/fixed-reviews"))["total"], 0)
        history = await self.read("42/fixed-reviews?status=discarded")
        self.assertEqual((history["total"], history["items"][0]["reason"]), (1, "答题卡拍反"))
        updated = await self.client.put("42/paper-draft", json=body)
        self.assertEqual(updated.status_code, 200, updated.text)
        history_view = await self.read(path)
        self.assertEqual((history_view["status"], history_view["reason"]), ("discarded", "答题卡拍反"))
        self.assertIsNotNone(history_view["updated_at"])
        self.assertEqual((await self.client.get(path + "/photo")).content, sample_photo())
        self.assertEqual((await self.confirm(path, original)).status_code, 409)

    async def test_withdraw_preserves_grade_and_removes_it_from_effective_results(self):
        path = await self.stage("withdraw", exam_id=43, marked="A")
        final = await self.confirm(path, await self.read(path))
        self.assertEqual(final.status_code, 200, final.text)
        submission_id = final.json()["data"]["submission_id"]
        record_path = f"43/grading-records/{submission_id}"
        action = record_path + "/withdraw"
        self.assertEqual((await self.read(record_path))["withdrawable_grade_version"], 1)
        valid = {"grade_version": 1, "reason": "照片归错学生"}
        self.assertEqual((await self.client.post(action, json={**valid, "grade_version": 3})).status_code, 409)
        self.teacher_id = 8
        self.assertEqual((await self.client.post(action, json=valid)).status_code, 404)
        self.teacher_id = 7
        close = await self.client.put("43/paper-grading-state", json={"state": "completed", "revision": 0})
        self.assertEqual(close.status_code, 200, close.text)
        self.assertEqual((await self.client.post(action, json=valid)).status_code, 409)
        reopened = await self.client.put("43/paper-grading-state", json={"state": "grading", "revision": 1})
        self.assertEqual(reopened.status_code, 200, reopened.text)
        for _ in range(2):
            result = await self.client.post(action, json=valid)
            self.assertEqual(result.status_code, 200, result.text)
            self.assertEqual(result.json()["data"]["grade_version"], 2)
        state = await self.read("43/paper-grading-state")
        self.assertEqual((state["state"], state["confirmed"]), ("grading", 0))
        record = await self.read(record_path)
        self.assertEqual((record["status"], record["score"], record["withdrawable_grade_version"]), ("historical", 2, None))
        self.assertEqual((record["history"][0]["action"], record["history"][0]["reason"]), ("paper_withdraw", valid["reason"]))
        self.assertEqual(len(record["history"]), 2)
        self.assertEqual((await self.read(path))["status"], "withdrawn")
        self.assertEqual((await self.client.get(record_path + "/photo")).content, sample_photo())
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(select(func.count()).select_from(WrongQuestionBook)), 0)
        new_scan = await self.stage("restore", exam_id=43, marked="C")
        view = await self.read(new_scan)
        self.assertTrue(view["previous_grade"]["withdrawn"])
        self.assertEqual(view["previous_grade"]["grade_version"], 2)
        result = await self.confirm(new_scan, view)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()["data"], {"submission_id": submission_id, "grade_version": 3, "score": 6, "max_score": 6})
        self.assertEqual((await self.read("43/paper-grading-state"))["confirmed"], 1)

    async def test_private_photos_remain_bound_to_the_approved_scan(self):
        with self.assertRaises(PaperReviewError) as invalid:
            await self.stage("bad-photo", photo_data=b"not an image")
        self.assertEqual(invalid.exception.status, 415)
        self.assertEqual(list(Path(self.photo_dir).rglob("*.png")), [])
        initial = await self.stage("initial", exam_id=43)
        response = await self.client.get(initial + "/photo")
        self.assertEqual(response.status_code, 200, response.text if response.status_code != 200 else "")
        self.assertEqual(response.content, sample_photo())
        self.assertEqual(response.headers["cache-control"], "private, no-store")
        self.assertEqual(response.headers["content-type"], "image/png")
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")
        self.assertTrue((await self.read(initial))["has_photo"])
        self.assertEqual((await self.client.get(initial.replace("43/", "42/", 1) + "/photo")).status_code, 404)
        final = await self.confirm(initial, await self.read(initial))
        self.assertEqual(final.status_code, 200, final.text)
        record = f"43/grading-records/{final.json()['data']['submission_id']}"
        self.assertTrue((await self.read(record))["has_photo"])
        self.assertEqual((await self.client.get(record + "/photo")).content, sample_photo())
        replacement = await self.stage("replacement", exam_id=43, variant=1)
        self.assertEqual((await self.confirm(replacement, await self.read(replacement))).status_code, 200)
        self.assertEqual((await self.client.get(initial + "/photo")).content, sample_photo())
        self.assertEqual((await self.client.get(record + "/photo")).content, sample_photo(1))
        self.teacher_id = 8
        self.assertEqual((await self.client.get(initial + "/photo")).status_code, 404)
        self.assertEqual((await self.client.get(record + "/photo")).status_code, 404)
        self.teacher_id = 7
        async with self.sessions.begin() as db:
            await db.execute(delete(ClassTeacher).where(ClassTeacher.class_id == 10))
        self.assertEqual((await self.client.get(initial + "/photo")).status_code, 404)
        self.assertEqual((await self.client.get(record + "/photo")).status_code, 404)

    async def test_class_match_syncs_wrong_book_and_blocks_legacy_adjustment(self):
        path = await self.stage("unmatched", exam_id=43, number="824", marked="A")
        view = await self.read(path)
        self.assertIsNone(view["student_name"])
        self.assertEqual((await self.confirm(path, view)).status_code, 422)
        result = await self.client.put(path, json={"revision": view["revision"], "exam_number": "00824"})
        self.assertEqual(result.status_code, 200, result.text)
        matched = result.json()["data"]
        self.assertEqual(matched["student_name"], "样例")
        final = await self.confirm(path, matched)
        self.assertEqual(final.status_code, 200, final.text)
        submission = final.json()["data"]["submission_id"]
        blocked = await self.client.post(f"43/submissions/{submission}/review", json={"adjustments": []})
        self.assertEqual(blocked.status_code, 409)
        async with self.sessions() as db:
            wrong = await db.scalar(select(WrongQuestionBook).where(WrongQuestionBook.submission_id == int(submission)))
            self.assertEqual((wrong.student_id, wrong.question_index, wrong.student_answer), (112, 2, "A"))
        rescan = await self.stage("fix", exam_id=43)
        self.assertEqual((await self.confirm(rescan, await self.read(rescan))).status_code, 200)
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(select(func.count()).select_from(WrongQuestionBook)), 0)
