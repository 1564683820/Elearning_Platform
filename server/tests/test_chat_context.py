from datetime import datetime
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from app.api.v1 import chat
from app.api.deps import get_current_user_id
from app.db.database import get_db
from app.schemas.common import ChatSendRequest
from app.services.chat_service import ChatService


class ChatContextTests(unittest.IsolatedAsyncioTestCase):
    def database(self, kind=1):
        session = SimpleNamespace(id=12, user_id=7, type=kind, scene_desc='', user_role='')
        history = [SimpleNamespace(role='assistant', content='Previous reply'), SimpleNamespace(role='user', content='Previous question')]
        db = SimpleNamespace(add=Mock(), flush=AsyncMock(), execute=AsyncMock(side_effect=[
            Mock(scalar_one_or_none=Mock(return_value=session)),
            Mock(scalars=Mock(return_value=Mock(all=Mock(return_value=history)))),
        ]))

        def populate():
            for i, call in enumerate(db.add.call_args_list):
                call.args[0].id = 100 + i
                call.args[0].created_at = datetime(2026, 11, 14)

        db.flush.side_effect = populate
        return db

    async def test_unavailable_cache_keeps_current_message_and_recent_database_history(self):
        db = self.database()
        with patch('app.services.chat_service.get_redis', AsyncMock(return_value=None), create=True), patch(
            'app.services.chat_service.AIService.chat_completion', AsyncMock(return_value='New reply')) as ai:
            result = await ChatService.send_message(db, 12, 7, ChatSendRequest(message='Current question'))
        messages = ai.call_args.args[1]
        self.assertEqual([m['content'] for m in messages], ['Previous question', 'Previous reply', 'Current question'])
        self.assertEqual(result['ai_message'].content, 'New reply')
        self.assertEqual(db.add.call_count, 2)
        params = db.execute.call_args_list[1].args[0].compile().params
        self.assertIn(19, params.values())

    async def test_generation_failure_never_adds_a_completed_message_pair(self):
        db = self.database()
        with patch('app.services.chat_service.get_redis', AsyncMock(return_value=None), create=True), patch(
            'app.services.chat_service.AIService.chat_completion', AsyncMock(side_effect=RuntimeError('unavailable'))):
            with self.assertRaises(RuntimeError):
                await ChatService.send_message(db, 12, 7, ChatSendRequest(message='Current question'))
        db.add.assert_not_called()
        db.flush.assert_not_awaited()

    async def test_empty_model_response_is_not_saved_as_an_answer(self):
        db = self.database()
        with patch('app.services.chat_service.get_redis', AsyncMock(return_value=None), create=True), patch(
            'app.services.chat_service.AIService.chat_completion', AsyncMock(return_value='   ')):
            with self.assertRaises(ValueError):
                await ChatService.send_message(db, 12, 7, ChatSendRequest(message='Current question'))
        db.add.assert_not_called()

    async def test_rag_answer_preserves_sources_and_avoids_regular_model_context_query(self):
        db = self.database(kind=2)
        sources = [{'title': 'Source', 'url': '/documents/1'}]
        with patch('app.services.chat_service.RAGService.answer_question', AsyncMock(
            return_value={'answer': 'Grounded answer', 'sources': sources})) as rag, patch(
            'app.services.chat_service.AIService.chat_completion', AsyncMock()) as ai:
            result = await ChatService.send_message(db, 12, 7, ChatSendRequest(message='Current question'))
        rag.assert_awaited_once_with(db, 'Current question', 7)
        ai.assert_not_awaited()
        self.assertEqual(db.execute.await_count, 1)
        self.assertEqual(result['ai_message'].sources, sources)


class ChatOwnershipTests(unittest.IsolatedAsyncioTestCase):
    async def test_foreign_or_missing_session_is_404_before_history_or_model_access(self):
        app = FastAPI()
        app.include_router(chat.router, prefix='/api/v1')
        db = SimpleNamespace(execute=AsyncMock(return_value=Mock(scalar_one_or_none=Mock(return_value=None))), add=Mock())

        async def database():
            yield db

        app.dependency_overrides[get_db] = database
        app.dependency_overrides[get_current_user_id] = lambda: 7
        with patch('app.services.chat_service.AIService.chat_completion', AsyncMock()) as ai:
            async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
                for method, route, body in [('GET', 'messages', None), ('POST', 'send', {'message': 'Question'}), ('POST', 'evaluate', None)]:
                    with self.subTest(route=route):
                        response = await client.request(method, f'/api/v1/chat/sessions/12/{route}', json=body)
                        self.assertEqual(response.status_code, 404)
        ai.assert_not_awaited()
        db.add.assert_not_called()
        self.assertEqual(db.execute.await_count, 3)
        for call in db.execute.call_args_list:
            statement = call.args[0].compile()
            self.assertIn('chat_conversation.user_id', str(statement))
            self.assertIn(7, statement.params.values())

    async def test_empty_answer_returns_502_without_message_write(self):
        app = FastAPI()
        app.include_router(chat.router, prefix='/api/v1')
        session = SimpleNamespace(id=12, type=3)
        db = SimpleNamespace(execute=AsyncMock(side_effect=[
            Mock(scalar_one_or_none=Mock(return_value=session)),
            Mock(scalars=Mock(return_value=Mock(all=Mock(return_value=[])))),
        ]), add=Mock(), flush=AsyncMock())

        async def database():
            yield db

        app.dependency_overrides[get_db] = database
        app.dependency_overrides[get_current_user_id] = lambda: 7
        with patch('app.services.chat_service.AIService.chat_completion', AsyncMock(return_value='')):
            async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
                response = await client.post('/api/v1/chat/sessions/12/send', json={'message': 'Question'})
        self.assertEqual(response.status_code, 502)
        db.add.assert_not_called()
        db.flush.assert_not_awaited()
