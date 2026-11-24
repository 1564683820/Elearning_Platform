import unittest
from unittest.mock import AsyncMock, patch
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from app.api.v1 import quiz, scenario
from app.api.deps import get_current_user_id
from app.db.database import get_db


class GenerationQueryContractTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(quiz.router, prefix='/api/v1')
        self.app.include_router(scenario.router, prefix='/api/v1')
        self.db = object()

        async def database():
            yield self.db

        self.app.dependency_overrides[get_db] = database
        self.app.dependency_overrides[get_current_user_id] = lambda: 7

    async def test_generation_query_values_reach_the_real_handlers(self):
        for kind, service, extra in [
            ('reading', 'generate_reading', ['高级']),
            ('translation', 'generate_translation', []),
            ('essay', 'generate_essay', []),
        ]:
            with self.subTest(kind=kind), patch.object(quiz.QuizService, service, AsyncMock(return_value={})) as generate:
                async with AsyncClient(transport=ASGITransport(app=self.app), base_url='http://test') as client:
                    response = await client.post(f'/api/v1/quiz/{kind}/generate', params={
                        'stage': 3, 'difficulty': '高级'}, json={})
                self.assertEqual(response.status_code, 200)
                generate.assert_awaited_once_with(self.db, 7, 3, *extra)

    async def test_custom_pagination_reaches_scenario_handlers(self):
        for path, owner, method in [
            ('/scenario/history', scenario.ScenarioService, 'list_scenarios'),
            ('/scenario/video/list', scenario.VideoService, 'list_user_videos'),
        ]:
            with self.subTest(path=path), patch.object(owner, method, AsyncMock(return_value={})) as listing:
                async with AsyncClient(transport=ASGITransport(app=self.app), base_url='http://test') as client:
                    response = await client.get('/api/v1' + path, params={'page': 2, 'page_size': 7})
                self.assertEqual(response.status_code, 200)
                listing.assert_awaited_once_with(self.db, 7, 2, 7)
