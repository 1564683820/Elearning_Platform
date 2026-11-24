import unittest

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.deps import get_current_teacher_id
from app.api.v1.agent_skill import router
from app.db.database import Base, get_db
from app.models.agent_skill import AgentSkill
from app.models.user import User


class QASkillTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as connection:
            await connection.run_sync(lambda conn: Base.metadata.create_all(conn, tables=[User.__table__, AgentSkill.__table__]))
        async with self.sessions.begin() as db:
            db.add_all([
                User(id=5, openid="teacher-5", account="teacher-five"),
                User(id=6, openid="teacher-6", account="teacher-six"),
                AgentSkill(teacher_id=5, skill_type="exam", name="讲评建议", raw_content="# 示例", is_active=1),
            ])
        self.teacher = 5
        app = FastAPI()
        app.include_router(router)

        async def db_session():
            async with self.sessions.begin() as db:
                yield db

        app.dependency_overrides[get_db] = db_session
        app.dependency_overrides[get_current_teacher_id] = lambda: self.teacher
        self.client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        self.route = "/teaching-assistant/skills"

    async def asyncTearDown(self):
        await self.client.aclose()
        await self.engine.dispose()

    async def upload(self, name, content, skill_type="qa"):
        return await self.client.post(f"{self.route}/upload", data={"skill_type": skill_type},
                                      files={"file": (name, content, "application/octet-stream")})

    async def test_shared_skill_list_and_secure_storage_without_activation(self):
        content = "---\r\nname: 讲评建议\r\nskill_type: ppt\r\n---\r\n设定课堂讲评顺序"
        response = await self.upload("lesson-review.markdown", content.encode())
        self.assertEqual(response.status_code, 200, response.text)
        saved = response.json()["data"]
        self.assertEqual((saved["file_name"], saved["skill_type"]), ("lesson-review.markdown", "qa"))
        self.assertFalse(saved["is_active"])
        self.assertEqual(saved["prompt_snippet"], "")
        self.assertEqual((await self.upload("alternate.md", content.encode())).status_code, 409)
        listed = await self.client.get(self.route, params={"skill_type": "qa"})
        self.assertEqual([item["id"] for item in listed.json()["data"]["items"]], [saved["id"]])
        legacy = await self.client.get(self.route, params={"skill_type": "exam"})
        self.assertEqual(legacy.json()["data"]["items"][0]["file_name"], "讲评建议.md")
        self.assertEqual((await self.client.post(f"{self.route}/{saved['id']}/activate")).status_code, 409)
        active = await self.client.get(f"{self.route}/active/current")
        self.assertEqual([item["skill_type"] for item in active.json()["data"]["items"]], ["exam"])
        active_qa = await self.client.get(f"{self.route}/active/current", params={"skill_type": "qa"})
        self.assertIsNone(active_qa.json()["data"])

        self.teacher = 6
        invisible = await self.client.get(self.route, params={"skill_type": "qa"})
        self.assertEqual(invisible.json()["data"]["items"], [])
        self.assertEqual((await self.client.get(f"{self.route}/{saved['id']}")).status_code, 404)
        self.assertEqual((await self.upload("lesson-review.md", content.encode())).status_code, 200)

    async def test_invalid_question_skill_reports_failed_validation(self):
        for filename, data, status in (
            ("lesson.pdf", b"test", 400),
            ("empty.md", b"", 400),
            ("binary.md", b"\x00sample", 400),
            ("wrong-encoding.md", b"\xff", 400),
            ("no-name.md", b"---\ndescription: test\n---\n", 400),
            ("non-string-name.md", b"---\nname: [test]\n---\n", 400),
            ("bad-yaml.md", b"---\nname: [test\n---\n", 400),
            ("large.md", b"x" * (48 * 1024 + 1), 413),
        ):
            with self.subTest(filename=filename):
                response = await self.upload(filename, data)
                self.assertEqual(response.status_code, status, response.text)
        self.assertEqual((await self.client.get(self.route, params={"skill_type": "qa"})).json()["data"]["items"], [])
