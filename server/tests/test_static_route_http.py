import unittest
from unittest.mock import AsyncMock, patch
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from app.api.v1 import knowledge_graph, favorites
from app.api.deps import get_current_teacher_id, get_current_user_id
from app.db.database import get_db


class StaticRouteHTTPTests(unittest.IsolatedAsyncioTestCase):
    async def test_graph_list_reaches_list_handler(self):
        app = FastAPI()
        app.include_router(knowledge_graph.router, prefix='/api/v1')
        app.dependency_overrides[get_current_teacher_id] = lambda: 7
        app.dependency_overrides[get_db] = lambda: None
        with patch.object(knowledge_graph.KnowledgeGraphService, 'list_graphs', AsyncMock(return_value={'items': []})) as service:
            async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
                response = await client.get('/api/v1/teacher/ppt/knowledge-graph/list')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data']['items'], [])
        service.assert_awaited_once()

    async def test_favorite_batch_reaches_batch_handler_without_real_deletion(self):
        app = FastAPI()
        app.include_router(favorites.router, prefix='/api/v1')
        app.dependency_overrides[get_current_user_id] = lambda: 7
        app.dependency_overrides[get_db] = lambda: None
        with patch.object(favorites.FavoriteService, 'batch_remove_favorites', AsyncMock(return_value={'deleted_count': 1})) as service:
            async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
                response = await client.request('DELETE', '/api/v1/favorites/batch', json={'ids': ['9007199254740993']})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data']['deleted_count'], 1)
        service.assert_awaited_once_with(None, 7, [9007199254740993])
