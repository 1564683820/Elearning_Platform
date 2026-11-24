import io
import json
import unittest
from contextlib import ExitStack
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, MockTransport, Response
from PIL import Image
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.schema import CreateTable
from starlette.requests import ClientDisconnect

from app.api.deps import get_current_teacher_id
from app.api.v1.teaching_assistant import router
from app.core.frontend import FrontendMiddleware
from app.db.database import get_db
from app.models.chat import ChatConversation, ChatMessage
from app.models.stats import UserDocument
from app.services import chat_attachments
from app.services.ai_service import AIService
from app.services.chat_requests import ChatRequestError, lock_conversation


class TeachingAttachmentTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as connection:
            # MySQL scopes index names to a table, while SQLite scopes them to the database.
            for model in (ChatConversation, ChatMessage, UserDocument):
                await connection.execute(CreateTable(model.__table__))
        async with self.sessions.begin() as db:
            db.add_all([
                ChatConversation(id=42, type=4, user_id=7),
                ChatConversation(id=43, type=4, user_id=7),
                ChatConversation(id=44, type=4, user_id=8),
            ])
        private = TemporaryDirectory()
        self.addCleanup(private.cleanup)
        self.root = Path(private.name)
        env = patch.dict("os.environ", {"CHAT_ATTACHMENT_DIR": private.name})
        env.start()
        self.addCleanup(env.stop)
        app = FastAPI()
        app.include_router(router)
        self.app = app

        async def db_session():
            async with self.sessions() as db:
                try:
                    yield db
                    await db.commit()
                except Exception:
                    await db.rollback()
                    raise

        self.teacher = 7
        app.dependency_overrides[get_db] = db_session
        app.dependency_overrides[get_current_teacher_id] = lambda: self.teacher
        self.client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test/teaching-assistant/")

    async def asyncTearDown(self):
        await self.client.aclose()
        await self.engine.dispose()

    async def upload_text(self):
        response = await self.client.post("upload?structured=true", files={"file": ("讲评.txt", b"sample evidence")})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["data"]

    async def test_upload_binding_context_history_and_download_scope(self):
        item = await self.upload_text()
        attachment = item["attachment_id"]
        self.assertNotIn("file_url", item)
        self.assertEqual((await self.client.get(f"attachments/{attachment}")).status_code, 404)
        async with self.sessions.begin() as db:
            db.add(ChatMessage(id=51, role="user", conversation_id=42, content="请讲评"))
            await db.flush()
            await chat_attachments.bind(db, 7, 51, [int(attachment)])
        history = (await self.client.get("sessions/42/messages")).json()["data"]["items"]
        self.assertEqual(history[0]["content"], "请讲评")
        self.assertEqual(history[0]["attachments"], [item])
        async with self.sessions() as db:
            text, sources = await chat_attachments.context(db, 7, 42)
            self.assertIn("sample evidence", text)
            self.assertEqual(sources[0]["type"], "chat_attachment")
            self.assertEqual(await chat_attachments.context(db, 7, 43), ("", []))
        downloaded = await self.client.get(f"attachments/{attachment}")
        self.assertEqual(downloaded.content, b"sample evidence")
        self.assertEqual(downloaded.headers["cache-control"], "private, no-store")
        self.teacher = 8
        self.assertEqual((await self.client.get(f"attachments/{attachment}")).status_code, 404)
        denied = await self.client.post("chat", json={"conversation_id": "44", "message": "盗用", "attachment_ids": [attachment]})
        self.assertEqual(denied.status_code, 404)
        self.teacher = 7
        denied_stream = await self.client.post("chat/stream", json={"conversation_id": "43", "message": "重复使用", "attachment_ids": [attachment]})
        self.assertIn("event: error", denied_stream.text)
        self.assertEqual((await self.client.get("sessions/43/messages")).json()["data"]["total"], 0)

    async def test_reject_invalid_files_and_store_ocr_text(self):
        invalid = await self.client.post("upload?structured=true", files={"file": ("伪造.png", b"no", "image/png")})
        self.assertEqual(invalid.status_code, 415)
        png = io.BytesIO()
        Image.new("RGB", (18, 18)).save(png, "PNG")
        image = {"file": ("试题.png", png.getvalue(), "image/png")}
        with patch.object(chat_attachments.DocumentProcessor, "_extract_image_text", return_value=""):
            failed = await self.client.post("upload?structured=true", files=image)
        self.assertEqual(failed.status_code, 422)
        self.assertFalse(list(self.root.rglob("*.png")))
        with patch.object(chat_attachments.DocumentProcessor, "_extract_image_text", return_value="Question 8"):
            success = await self.client.post("upload?structured=true", files=image)
        self.assertEqual(success.status_code, 200, success.text)
        async with self.sessions() as db:
            doc = await db.get(UserDocument, int(success.json()["data"]["attachment_id"]))
            self.assertEqual(doc.ocr_text, "Question 8")
            self.assertIsNone(doc.parsed_text)

    async def test_recent_history_cursor_is_stable_during_another_client_send(self):
        same_second = datetime(2026, 11, 22, 12)
        async with self.sessions.begin() as db:
            db.add_all([
                ChatMessage(id=message_id, role="user", conversation_id=42, content=str(message_id),
                            created_at=same_second)
                for message_id in range(51, 56)
            ])
            db.add(ChatMessage(id=60, role="user", conversation_id=43, content="other session"))
        path = "sessions/42/messages"
        legacy = (await self.client.get(path, params={"page_size": 2})).json()["data"]
        self.assertEqual([item["id"] for item in legacy["items"]], ["51", "52"])
        self.assertNotIn("next_before_id", legacy)

        newest = (await self.client.get(path, params={"latest": True, "page_size": 2})).json()["data"]
        self.assertEqual([item["id"] for item in newest["items"]], ["54", "55"])
        self.assertEqual(newest["next_before_id"], "54")
        async with self.sessions.begin() as db:
            db.add(ChatMessage(id=56, role="assistant", conversation_id=42, content="新消息",
                               created_at=same_second))

        older = (await self.client.get(path, params={"before_id": newest["next_before_id"], "page_size": 2})).json()["data"]
        self.assertEqual([item["id"] for item in older["items"]], ["52", "53"])
        first = (await self.client.get(path, params={"before_id": older["next_before_id"], "page_size": 2})).json()["data"]
        self.assertEqual([item["id"] for item in first["items"]], ["51"])
        self.assertIsNone(first["next_before_id"])
        self.assertEqual((await self.client.get(path, params={"before_id": "60"})).status_code, 400)
        self.teacher = 8
        self.assertEqual((await self.client.get(path, params={"latest": True})).status_code, 400)

    async def test_web_and_h5_continue_the_same_conversation_through_the_shared_api(self):
        self.app.include_router(router, prefix="/api/v1")
        self.app.add_middleware(FrontendMiddleware, web_dist=self.root / "web", h5_dist=self.root / "h5")
        base_url = "http://test/Elearning/api/v1/teaching-assistant/"

        async def complete(_db, _messages, *, stream=False, **_kwargs):
            if not stream:
                return "先讲第 8 题。"

            async def tokens():
                yield "第 8 题的选项 B 值得复盘。"

            return tokens()

        service = "app.services.teaching_assistant_service."
        with ExitStack() as mocks:
            for target, result in (
                ("IntentClassifier.classify", {"intent": "document_query"}),
                ("MemoryService.get_relevant_memories", []),
                ("find_exam_knowledge", None),
                ("TeachingAssistantService._multi_source_search", {}),
                ("TeachingAssistantService._load_active_skill_prompts", {}),
                ("TeachingAssistantService._update_conversation_summary", None),
                ("TeachingAssistantService._generate_suggestions", []),
            ):
                mocks.enter_context(patch(service + target, return_value=result))
            model = mocks.enter_context(patch(service + "AIService.chat_completion", side_effect=complete))
            async with (
                AsyncClient(transport=ASGITransport(app=self.app), base_url=base_url) as web,
                AsyncClient(transport=ASGITransport(app=self.app), base_url=base_url) as h5,
            ):
                created = await web.post("sessions", json={})
                self.assertEqual(created.status_code, 200, created.text)
                session_id = created.json()["data"]["id"]
                history = f"sessions/{session_id}/messages?latest=true"
                uploaded = await web.post("upload?structured=true",
                                          files={"file": ("讲评.txt", b"Question 8: option B")})
                self.assertEqual(uploaded.status_code, 200, uploaded.text)
                attachment = uploaded.json()["data"]
                first = await web.post("chat", json={
                    "conversation_id": session_id, "message": "请讲评第 8 题",
                    "attachment_ids": [attachment["attachment_id"]], "request_id": "web-first",
                })
                self.assertEqual(first.status_code, 200, first.text)
                opened = (await h5.get(history)).json()["data"]["items"]
                self.assertEqual([item["content"] for item in opened], ["请讲评第 8 题", "先讲第 8 题。"])
                self.assertEqual(opened[0]["attachments"], [attachment])

                followup = await h5.post("chat/stream", json={
                    "conversation_id": session_id, "message": "那道题要讲哪个选项？", "request_id": "h5-followup",
                })
                self.assertIn("event: done", followup.text)
                model_messages = model.call_args.args[1]
                self.assertIn({"role": "assistant", "content": "先讲第 8 题。"}, model_messages)
                self.assertIn("Question 8: option B", model_messages[-1]["content"])

                refreshed = (await web.get(history)).json()["data"]["items"]
                self.assertEqual([item["content"] for item in refreshed[-2:]],
                                 ["那道题要讲哪个选项？", "第 8 题的选项 B 值得复盘。"])
                self.assertEqual(refreshed[-1]["sources"][0]["id"], attachment["attachment_id"])
                receipt = await web.get(f"sessions/{session_id}/requests/h5-followup")
                self.assertEqual(receipt.json()["data"]["reply"]["message_id"], refreshed[-1]["id"])
                self.teacher = 8
                self.assertEqual((await h5.get(history)).status_code, 400)

    async def test_stream_sends_attachment_to_model_and_rolls_back_on_failure(self):
        attachment = (await self.upload_text())["attachment_id"]
        question = {"conversation_id": "42", "message": "请讲评附件", "attachment_ids": [attachment],
                    "request_id": "same-upload"}
        status_path = "sessions/42/requests/same-upload"

        async def answer():
            yield "附件包含可讲评的内容。"

        service = "app.services.teaching_assistant_service."
        with ExitStack() as mocks:
            for target, result in (
                ("IntentClassifier.classify", {"intent": "document_query"}),
                ("MemoryService.get_relevant_memories", []),
                ("find_exam_knowledge", None),
                ("TeachingAssistantService._multi_source_search", {}),
                ("TeachingAssistantService._load_active_skill_prompts", {}),
                ("TeachingAssistantService._update_conversation_summary", None),
                ("TeachingAssistantService._generate_suggestions", []),
            ):
                mocks.enter_context(patch(service + target, return_value=result))
            model = mocks.enter_context(patch(service + "AIService.chat_completion", side_effect=RuntimeError("mock model unavailable")))
            failed = await self.client.post("chat/stream", json=question)
            self.assertIn("event: error", failed.text)
            self.assertEqual((await self.client.get(status_path)).json()["data"], {"status": "unknown"})
            items = (await self.client.get("sessions/42/messages")).json()["data"]["items"]
            self.assertEqual(items, [])
            model.side_effect = None
            model.return_value = answer()
            sent = await self.client.post("chat/stream", json=question)
            self.assertIn("event: done", sent.text)
            self.assertIn("chat_attachment", sent.text)
            self.assertIn("sample evidence", model.call_args.args[1][-1]["content"])
            done = (await self.client.get(status_path)).json()["data"]
            self.assertEqual(done["status"], "completed")
            self.assertEqual(done["reply"]["content"], "附件包含可讲评的内容。")
            replay = await self.client.post("chat", json=question)
            self.assertEqual(replay.json()["data"], done["reply"])
            stream_replay = await self.client.post("chat/stream", json=question)
            self.assertIn(done["reply"]["message_id"], stream_replay.text)
            self.assertEqual(model.await_count, 2)
            for changed in ({**question, "message": "另外一个问题"}, {**question, "attachment_ids": []}):
                self.assertEqual((await self.client.post("chat", json=changed)).status_code, 409)
            self.teacher = 8
            self.assertEqual((await self.client.get(status_path)).status_code, 404)
            self.teacher = 7
        items = (await self.client.get("sessions/42/messages")).json()["data"]["items"]
        self.assertEqual([item["role"] for item in items], ["user", "assistant"])
        self.assertEqual(items[0]["attachments"][0]["attachment_id"], attachment)
        self.assertEqual(items[1]["sources"][0]["id"], attachment)

    async def test_client_disconnect_does_not_commit_partial_turn(self):
        attachment = (await self.upload_text())["attachment_id"]
        question = {"conversation_id": "42", "message": "连接断开", "attachment_ids": [attachment], "request_id": "cancelled"}
        payload = json.dumps(question).encode()
        path = "/teaching-assistant/chat/stream"
        scope = {
            "type": "http", "asgi": {"spec_version": "2.4"}, "http_version": "1.1", "method": "POST",
            "scheme": "http", "path": path, "raw_path": path.encode(), "query_string": b"",
            "headers": [(b"content-type", b"application/json")], "server": ("test", 80), "client": ("local", 1000),
        }

        async def receive():
            return {"type": "http.request", "body": payload, "more_body": False}

        async def send(message):
            if message["type"] == "http.response.body":
                self.assertIn(b"event: intent", message["body"])
                raise OSError("mock client disconnected")

        with patch("app.services.teaching_assistant_service.IntentClassifier.classify", return_value={"intent": "document_query"}):
            with self.assertRaises(ClientDisconnect):
                await self.app(scope, receive, send)
        status = await self.client.get("sessions/42/requests/cancelled")
        self.assertEqual(status.json()["data"], {"status": "unknown"})
        self.assertEqual((await self.client.get("sessions/42/messages")).json()["data"]["total"], 0)
        self.assertEqual((await self.client.get(f"attachments/{attachment}")).status_code, 404)

    async def test_owned_locked_conversation_reports_busy(self):
        conflict = OperationalError("select ... for update nowait", {}, Exception(3572))
        db = AsyncMock()
        db.scalar.side_effect = [42, conflict]
        with self.assertRaises(ChatRequestError) as raised:
            await lock_conversation(db, 7, 42)
        self.assertEqual(raised.exception.status, 409)
        self.assertEqual(db.scalar.await_count, 2)

        db.scalar.reset_mock()
        db.scalar.side_effect = [None]
        with self.assertRaises(ChatRequestError) as denied:
            await lock_conversation(db, 8, 42)
        self.assertEqual(denied.exception.status, 404)
        self.assertEqual(db.scalar.await_count, 1)

    async def test_model_stream_without_completion_is_not_a_final_reply(self):
        first_chunk = 'data: {"choices":[{"delta":{"content":"partial"}}]}\n\n'
        endings = (
            ("", False),
            ("data: [DONE]\n\n", True),
            ('data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n', True),
        )
        for ending, completed in endings:
            with self.subTest(ending=ending):
                transport = MockTransport(lambda _: Response(200, text=first_chunk + ending))
                with patch("app.services.ai_service.httpx.AsyncClient", return_value=AsyncClient(transport=transport)):
                    async def read_answer():
                        return [text async for text in AIService._stream_response("https://fixture.invalid", {}, {}, 2, True)]

                    if completed:
                        self.assertEqual(await read_answer(), ["partial"])
                    else:
                        with self.assertRaisesRegex(ValueError, "结束前断开"):
                            await read_answer()
