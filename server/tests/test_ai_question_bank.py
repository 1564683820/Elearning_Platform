from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock
from sqlalchemy.dialects import mysql
from app.services.quiz_service import QuizService


class AIQuestionBankTests(unittest.IsolatedAsyncioTestCase):
    async def test_existing_translation_uses_mysql_random_order_and_preserves_pair(self):
        existing = SimpleNamespace(id=123, content={'stem': '你好', 'reference': 'Hello'})
        db = SimpleNamespace(execute=AsyncMock(return_value=Mock(
            scalar_one_or_none=Mock(return_value=existing))))
        result = await QuizService.fetch_ai_question(db, 7, 'translation', 3)
        sql = str(db.execute.call_args.args[0].compile(dialect=mysql.dialect()))
        self.assertIn('ORDER BY rand()', sql)
        self.assertEqual(result['question_bank_id'], 123)
        self.assertEqual(result['stem'], '你好')
        self.assertEqual(result['reference'], 'Hello')
        self.assertIn('user_quiz_log', sql)
