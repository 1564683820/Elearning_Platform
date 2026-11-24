import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from app.api.v1 import documents
from app.api.deps import get_current_user_id
from app.db.database import get_db


class DocumentAccessTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(documents.router, prefix='/api/v1')
        self.db = SimpleNamespace(get=AsyncMock(return_value=SimpleNamespace(id=11, user_id=1, doc_category="other")))

        async def database():
            yield self.db

        self.app.dependency_overrides[get_db] = database
        self.app.dependency_overrides[get_current_user_id] = lambda: 1

    async def test_owner_can_read_job(self):
        with patch.object(documents, 'get_job', AsyncMock(return_value={'doc_id': 11, 'status': 'processing'})):
            async with AsyncClient(transport=ASGITransport(app=self.app), base_url='http://test') as client:
                response = await client.get('/api/v1/documents/jobs/test-job')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data']['status'], 'processing')

    async def test_foreign_job_is_hidden(self):
        self.app.dependency_overrides[get_current_user_id] = lambda: 2
        with patch.object(documents, 'get_job', AsyncMock(return_value={'doc_id': 11, 'error': 'private details'})):
            async with AsyncClient(transport=ASGITransport(app=self.app), base_url='http://test') as client:
                response = await client.get('/api/v1/documents/jobs/test-job')
        self.assertEqual(response.status_code, 404)
        self.assertNotIn('private details', response.text)

    async def test_foreign_document_progress_is_blocked_before_cache_read(self):
        self.app.dependency_overrides[get_current_user_id] = lambda: 2
        with patch.object(documents, 'get_progress', AsyncMock(return_value={'status': 'done'})) as cache:
            async with AsyncClient(transport=ASGITransport(app=self.app), base_url='http://test') as client:
                response = await client.get('/api/v1/documents/11/progress')
        self.assertEqual(response.status_code, 404)
        cache.assert_not_awaited()

    async def test_missing_document_does_not_expose_stale_progress(self):
        self.db.get.return_value = None
        with patch.object(documents, 'get_progress', AsyncMock(return_value={'status': 'done'})):
            async with AsyncClient(transport=ASGITransport(app=self.app), base_url='http://test') as client:
                response = await client.get('/api/v1/documents/11/progress')
        self.assertEqual(response.status_code, 404)

    async def test_anonymous_progress_requires_authentication(self):
        del self.app.dependency_overrides[get_current_user_id]
        async with AsyncClient(transport=ASGITransport(app=self.app), base_url='http://test') as client:
            response = await client.get('/api/v1/documents/11/progress')
        self.assertIn(response.status_code, (401, 403))

    async def test_expired_job_keeps_unknown_contract(self):
        with patch.object(documents, 'get_job', AsyncMock(return_value=None)):
            async with AsyncClient(transport=ASGITransport(app=self.app), base_url='http://test') as client:
                response = await client.get('/api/v1/documents/jobs/expired')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data']['status'], 'unknown')
        self.db.get.assert_not_awaited()

    async def test_failed_reindex_is_not_reported_as_success(self):
        self.db.commit = AsyncMock()
        with patch.object(documents.DocumentProcessor, 'reindex_document', AsyncMock(return_value={'success': False, 'error': '文档尚未解析'})):
            async with AsyncClient(transport=ASGITransport(app=self.app), base_url='http://test') as client:
                response = await client.post('/api/v1/documents/reindex?doc_id=11')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['detail'], '文档尚未解析')
