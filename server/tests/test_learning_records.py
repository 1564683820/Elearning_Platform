import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from pydantic import ValidationError
from app.schemas.common import WordProgressCreate, QuizSubmitRequest
from app.services.quiz_service import QuizService
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from app.api.v1.words import router as words_router
from app.api.v1.quiz import router as quiz_router
from app.api.deps import get_current_user_id
from app.db.database import get_db, get_words_db


class LearningValidationTests(unittest.TestCase):
    def test_mastery_range_matches_supported_levels(self):
        for level in range(4):
            self.assertEqual(WordProgressCreate(mastery_level=level).mastery_level, level)
        for level in (-1, 4):
            with self.assertRaises(ValidationError):
                WordProgressCreate(mastery_level=level)

    def test_negative_duration_cannot_reduce_learning_statistics(self):
        with self.assertRaises(ValidationError):
            QuizSubmitRequest(question_id=1, answer='A', time_spent=-1)
        self.assertEqual(QuizSubmitRequest(question_id=1, answer='A').time_spent, 0)


class MistakeRelearningTests(unittest.IsolatedAsyncioTestCase):
    async def test_correct_index_zero_is_used_when_correct_key_is_absent(self):
        question = SimpleNamespace(id=3, type=6, content={'correctIndex': 0}, stage=2)
        db = SimpleNamespace(execute=AsyncMock(return_value=Mock(
            scalar_one_or_none=Mock(return_value=question))), add=Mock(), flush=AsyncMock())
        with patch('app.services.quiz_service.StatsService.increment_quiz_stat', AsyncMock()) as stats:
            result = await QuizService.submit_answer(db, 7, QuizSubmitRequest(question_id=3, answer=0))
        self.assertTrue(result.is_correct)
        self.assertEqual(result.correct_answer, 0)
        stats.assert_awaited_once_with(db, 7, True)

    async def test_invalid_learning_requests_return_422_before_writing(self):
        app = FastAPI()
        app.include_router(words_router, prefix='/api/v1')
        app.include_router(quiz_router, prefix='/api/v1')
        db = SimpleNamespace(execute=AsyncMock(), add=Mock())

        async def database():
            yield db

        app.dependency_overrides[get_current_user_id] = lambda: 7
        app.dependency_overrides[get_db] = database
        app.dependency_overrides[get_words_db] = database
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
            for path, payload in [
                ('/words/1/progress', {'mastery_level': 4}),
                ('/words/1/progress', {'mastery_level': -1}),
                ('/quiz/submit', {'question_id': 1, 'answer': 'A', 'time_spent': -1}),
            ]:
                response = await client.post('/api/v1' + path, json=payload)
                self.assertEqual(response.status_code, 422)
        db.execute.assert_not_awaited()
        db.add.assert_not_called()

    async def test_wrong_again_returns_mastered_question_to_review(self):
        question = SimpleNamespace(id=3, type=1, content={'correct': 'A'}, stage=2)
        mistake = SimpleNamespace(wrong_count=1, mastered=1)
        db = SimpleNamespace(
            execute=AsyncMock(side_effect=[
                Mock(scalar_one_or_none=Mock(return_value=question)),
                Mock(scalar_one_or_none=Mock(return_value=mistake)),
            ]), add=Mock(), flush=AsyncMock(),
        )
        with patch('app.services.quiz_service.StatsService.increment_quiz_stat', AsyncMock()) as stats:
            result = await QuizService.submit_answer(db, 7, QuizSubmitRequest(question_id=3, answer='B'))
        self.assertFalse(result.is_correct)
        self.assertEqual(mistake.mastered, 0)
        self.assertEqual(mistake.wrong_count, 2)
        stats.assert_awaited_once_with(db, 7, False)
