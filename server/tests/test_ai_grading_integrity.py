import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from app.api.v1 import quiz
from app.api.deps import get_current_user_id
from app.db.database import get_db
from app.services.ai_service import AIService
from app.services.quiz_service import QuizService


class AIGradingIntegrityTests(unittest.IsolatedAsyncioTestCase):
    async def test_invalid_model_output_never_becomes_passing_learning_record(self):
        for method in ('score_translation', 'score_essay'):
            for raw in ('not json', '{}', '[]', '{"score":true}', '{"score":101}', '{"score":-1}', '{"score":"60"}', '{"score":NaN}'):
                with self.subTest(method=method, raw=raw):
                    db = SimpleNamespace(add=Mock(), flush=AsyncMock())
                    with patch.object(AIService, 'chat_completion', AsyncMock(return_value=raw)), patch(
                        'app.services.quiz_service.StatsService.increment_quiz_stat', AsyncMock()) as stats:
                        with self.assertRaises(ValueError):
                            await getattr(QuizService, method)(db, 7, 'Topic', 'Answer', 'Reference')
                    db.add.assert_not_called()
                    stats.assert_not_awaited()

    async def test_valid_scores_keep_feedback_and_statistics(self):
        for method in ('score_translation', 'score_essay'):
            for score in (0, 59, 60, 100):
                db = SimpleNamespace(add=Mock(), flush=AsyncMock())
                raw = '```json\n{"score":' + str(score) + ',"feedback":"review"}\n```'
                with self.subTest(method=method, score=score), patch.object(
                    AIService, 'chat_completion', AsyncMock(return_value=raw)), patch(
                    'app.services.quiz_service.StatsService.increment_quiz_stat', AsyncMock()) as stats:
                    result = await getattr(QuizService, method)(db, 7, 'Topic', 'Answer', 'Reference')
                self.assertEqual(result['score'], score)
                self.assertEqual(result['feedback'], 'review')
                stats.assert_awaited_once_with(db, 7, score >= 60)
                db.add.assert_called_once()

    async def test_bad_model_response_returns_502_for_both_http_endpoints(self):
        app = FastAPI()
        app.include_router(quiz.router, prefix='/api/v1')
        db = SimpleNamespace(add=Mock(), flush=AsyncMock())

        async def database():
            yield db

        app.dependency_overrides[get_db] = database
        app.dependency_overrides[get_current_user_id] = lambda: 7
        with patch.object(AIService, 'chat_completion', AsyncMock(return_value='bad JSON')), patch(
            'app.services.quiz_service.StatsService.increment_quiz_stat', AsyncMock()):
            async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
                for mode, topic_field in [('translation', 'source_text'), ('essay', 'essay_topic')]:
                    response = await client.post(f'/api/v1/quiz/{mode}/score', json={
                        topic_field: 'Topic', 'user_answer': 'Answer', 'reference': 'Reference'})
                    self.assertEqual(response.status_code, 502)
        db.add.assert_not_called()
