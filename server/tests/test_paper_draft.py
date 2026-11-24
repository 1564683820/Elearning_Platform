import unittest

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.deps import get_current_teacher_id
from app.api.v1.exam import router
from app.db.database import Base, get_db
from app.models.class_models import ClassTeacher
from app.models.exam_models import AnswerSheetTemplate, ExamSubmission, TeacherExam
from app.models.scan_models import ExamScanRecord
from app.models.user import User
from app.utils.revisions import template_revision


class PaperDraftTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        models = (AnswerSheetTemplate, ClassTeacher, ExamSubmission, TeacherExam, ExamScanRecord, User)
        async with self.engine.begin() as connection:
            await connection.run_sync(lambda conn: Base.metadata.create_all(conn, tables=[m.__table__ for m in models]))
        template = AnswerSheetTemplate(id=12, teacher_id=7, name="单选评分", choice_questions=[
            {"option_count": 4, "score": 2, "correct_answer": "A"},
            {"option_count": 3, "score": 4},
        ])
        self.template_token = template_revision(template)
        async with self.sessions() as db:
            db.add_all([template, ClassTeacher(id=1, teacher_id=7, class_id=8),
                        User(id=7, openid="test-teacher", account="paper-test", role="teacher")])
            await db.commit()
        app = FastAPI()
        app.include_router(router, prefix="/api/v1")

        async def db_session():
            async with self.sessions() as db:
                yield db
                await db.commit()

        self.teacher_id = 7
        app.dependency_overrides[get_db] = db_session
        app.dependency_overrides[get_current_teacher_id] = lambda: self.teacher_id
        self.client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test/api/v1/teacher/exam/")

    async def asyncTearDown(self):
        await self.client.aclose()
        await self.engine.dispose()

    async def test_replay_draft_creation_keeps_identity_and_original_revision(self):
        fields = {"title": "首次保存", "request_id": "draft-request-421"}
        created = await self.client.post("paper-drafts", json=fields)
        self.assertEqual(created.status_code, 200, created.text)
        original = created.json()["data"]
        replayed = await self.client.post("paper-drafts", json=fields)
        self.assertEqual(replayed.status_code, 200, replayed.text)
        self.assertEqual(replayed.json()["data"]["id"], original["id"])

        path = f"{original['id']}/paper-draft"
        updated = await self.client.put(path, json={"title": "另一端续编", "revision": original["revision"]})
        self.assertEqual(updated.status_code, 200, updated.text)
        replayed = await self.client.post("paper-drafts", json=fields)
        self.assertEqual(replayed.status_code, 200, replayed.text)
        self.assertEqual(replayed.json()["data"]["title"], "另一端续编")
        self.assertEqual(replayed.json()["data"]["created_revision"], original["revision"])
        self.assertNotEqual(replayed.json()["data"]["revision"], original["revision"])

        conflict = await self.client.post("paper-drafts", json={**fields, "title": "请求内容已更改"})
        self.assertEqual(conflict.status_code, 409, conflict.text)
        invalid = await self.client.post("paper-drafts", json={**fields, "request_id": "!"})
        self.assertEqual(invalid.status_code, 422, invalid.text)

        async with self.sessions() as db:
            db.add(User(id=9, openid="another-paper-teacher", account="another-paper-test", role="teacher"))
            await db.commit()
        self.teacher_id = 9
        another = await self.client.post("paper-drafts", json=fields)
        self.assertEqual(another.status_code, 200, another.text)
        self.assertNotEqual(another.json()["data"]["id"], original["id"])

    async def test_resume_same_draft_and_preserve_template_snapshot(self):
        fields = {"title": "纸质试卷", "description": "讲评备注", "class_id": "8", "template_id": "12",
                  "template_revision": self.template_token, "answers": {"1": "D"}}
        created = await self.client.post("paper-drafts", json=fields)
        self.assertEqual(created.status_code, 200, created.text)
        original = created.json()["data"]
        path = f"{original['id']}/paper-draft"
        self.assertEqual(original["questions"][0]["answer"], "D")
        self.assertEqual(original["questions"][1]["answer"], "")
        self.assertEqual(original["description"], "讲评备注")
        async with self.sessions() as db:
            template = await db.get(AnswerSheetTemplate, 12)
            template.choice_questions = [{"option_count": 2, "score": 10}]
            await db.commit()
        response = await self.client.put(path, json={
            "title": "续编试卷", "description": original["description"], "class_id": "8",
            "revision": original["revision"], "answers": {"2": "B"},
        })
        self.assertEqual(response.status_code, 200, response.text)
        saved = response.json()["data"]
        self.assertEqual(saved["id"], original["id"])
        self.assertEqual([row["score"] for row in saved["questions"]], [2, 4])
        self.assertEqual([row["answer"] for row in saved["questions"]], ["D", "B"])
        stale = await self.client.put(path, json={"title": "旧页面", "revision": original["revision"]})
        self.assertEqual(stale.status_code, 409)
        stale_template = await self.client.post("paper-drafts", json=fields)
        self.assertEqual(stale_template.status_code, 409)
        self.assertEqual((await self.client.get(path)).json()["data"]["title"], "续编试卷")

    async def test_save_and_resume_nonconsecutive_card_question_numbers(self):
        fields = {"title": "卡面题号", "template_id": "12", "template_revision": self.template_token,
                  "question_numbers": [21, 36], "answers": {"21": "B", "36": "C"}}
        for invalid in ([21], [21, 21], [0, 36], [True, 36]):
            response = await self.client.post("paper-drafts", json={**fields, "question_numbers": invalid})
            self.assertEqual(response.status_code, 422, response.text)
        created = await self.client.post("paper-drafts", json=fields)
        self.assertEqual(created.status_code, 200, created.text)
        draft = created.json()["data"]
        self.assertEqual([(row["question_number"], row["answer"]) for row in draft["questions"]], [(21, "B"), (36, "C")])
        path = f"{draft['id']}/paper-draft"
        updated = await self.client.put(path, json={
            "title": "续编", "revision": draft["revision"], "answers": {"36": "A"},
        })
        self.assertEqual(updated.status_code, 200, updated.text)
        reread = await self.client.get(path)
        self.assertEqual([(row["question_number"], row["answer"]) for row in reread.json()["data"]["questions"]],
                         [(21, "B"), (36, "A")])

    async def test_archive_removes_template_from_selection_but_preserves_existing_draft(self):
        fields = {"title": "保留旧模板", "template_id": "12", "template_revision": self.template_token, "answers": {"1": "D"}}
        created = await self.client.post("paper-drafts", json=fields)
        self.assertEqual(created.status_code, 200, created.text)
        draft = created.json()["data"]
        template_path = "answer-sheet-templates/12"
        self.teacher_id = 9
        self.assertEqual((await self.client.delete(template_path)).status_code, 404)
        self.teacher_id = 7
        for _ in range(2):
            result = await self.client.delete(template_path)
            self.assertEqual(result.json()["data"], {"deleted": True, "archived": True})
        self.assertEqual((await self.client.get("templates/list")).json()["data"], [])
        historic = (await self.client.get(template_path)).json()["data"]
        self.assertEqual(historic["id_str"], "12")
        self.assertTrue(historic["archived_at"])
        self.assertEqual((await self.client.post("paper-drafts", json=fields)).status_code, 409)

        saved = await self.client.put(f"{draft['id']}/paper-draft", json={
            "title": "继续使用原评分", "revision": draft["revision"], "answers": {"2": "C"},
        })
        self.assertEqual(saved.status_code, 200, saved.text)
        state = saved.json()["data"]
        self.assertEqual(state["template_name"], "单选评分")
        self.assertEqual([row["score"] for row in state["questions"]], [2, 4])
        self.assertEqual([row["answer"] for row in state["questions"]], ["D", "C"])
        fresh = await self.client.post("answer-sheet-template", json={
            "name": "单选评分", "choice_questions": state["questions"], "create_only": True,
        })
        self.assertEqual(fresh.status_code, 200, fresh.text)
        self.assertNotEqual(fresh.json()["data"]["id_str"], historic["id_str"])

    async def test_edit_template_by_revision_and_reject_duplicate_names(self):
        data = {"name": "单选评分", "choice_questions": [{"option_count": 4, "score": 7}], "create_only": True}
        self.assertEqual((await self.client.post("answer-sheet-template", json=data)).status_code, 409)
        path = "answer-sheet-templates/12"
        updated = await self.client.put(path, json={**data, "name": "新评分", "revision": self.template_token})
        self.assertEqual(updated.status_code, 200, updated.text)
        item = updated.json()["data"]
        self.assertEqual((item["id_str"], item["name"], item["total_score"]), ("12", "新评分", 7))
        self.assertEqual((await self.client.put(path, json={**data, "revision": self.template_token})).status_code, 409)
        await self.client.delete(path)
        self.assertEqual((await self.client.put(path, json={**data, "revision": item["revision"]})).status_code, 409)

    async def test_paper_filter_keeps_legacy_template_list_and_details_compatible(self):
        mixed = await self.client.post("answer-sheet-template", json={
            "name": "网页端旧模板", "choice_questions": [{"type": "multi_choice", "option_count": 4, "score": 7}],
        })
        self.assertEqual(mixed.status_code, 200, mixed.text)
        mixed_id = mixed.json()["data"]["id_str"]
        all_items = (await self.client.get("templates/list")).json()["data"]
        self.assertEqual({entry["id_str"] for entry in all_items}, {"12", mixed_id})
        paper_items = (await self.client.get("templates/list?paper_only=true")).json()["data"]
        self.assertEqual([entry["id_str"] for entry in paper_items], ["12"])
        details = (await self.client.get(f"answer-sheet-templates/{mixed_id}")).json()["data"]
        self.assertFalse(details["paper_compatible"])

    async def test_ownership_and_legacy_writers_cannot_mutate_paper_draft(self):
        foreign_class = await self.client.post("paper-drafts", json={"title": "试卷", "class_id": 9})
        self.assertEqual(foreign_class.status_code, 404)
        response = await self.client.post("paper-drafts", json={"title": "试卷"})
        exam_id = response.json()["data"]["id"]
        for endpoint, body in (
            (f"{exam_id}/publish", {"class_id": 8}),
            (f"{exam_id}/scan", {}),
            (f"{exam_id}/mobile-grade-session", {}),
            (f"{exam_id}/generate-printable-sheet", {}),
        ):
            blocked = await self.client.post(endpoint, json=body)
            self.assertEqual(blocked.status_code, 409, (endpoint, blocked.text))
        self.assertEqual((await self.client.put(exam_id, json={"title": "越界写入"})).status_code, 409)
        self.teacher_id = 9
        self.assertEqual((await self.client.get(f"{exam_id}/paper-draft")).status_code, 404)
