import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from app.api.v1.teaching_tasks import router
from app.api.deps import get_current_teacher_id
from app.db.database import get_db


class TeachingTaskTests(unittest.IsolatedAsyncioTestCase):
    async def test_foreign_class_does_not_create_task(self):
        app = FastAPI()
        app.include_router(router, prefix='/api/v1')
        db = SimpleNamespace(add=Mock())

        async def database():
            yield db

        app.dependency_overrides[get_db] = database
        app.dependency_overrides[get_current_teacher_id] = lambda: 7
        with patch('app.api.v1.teaching_tasks.TeacherService._verify_class_ownership',
                   AsyncMock(side_effect=ValueError('forbidden'))):
            async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
                response = await client.post('/api/v1/teaching-tasks', json={'class_id': 8, 'objective': '生成练习'})
        self.assertEqual(response.status_code, 404)
        db.add.assert_not_called()

    async def test_foreign_task_is_hidden_and_query_is_owner_scoped(self):
        app = FastAPI()
        app.include_router(router, prefix='/api/v1')
        db = SimpleNamespace(execute=AsyncMock(return_value=Mock(scalar_one_or_none=Mock(return_value=None))))

        async def database():
            yield db

        app.dependency_overrides[get_db] = database
        app.dependency_overrides[get_current_teacher_id] = lambda: 7
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
            response = await client.get('/api/v1/teaching-tasks/9007199254740993')
        self.assertEqual(response.status_code, 404)
        query = db.execute.call_args.args[0].compile()
        self.assertIn('teaching_task.teacher_id', str(query))
        self.assertIn(7, query.params.values())
