from datetime import date, timedelta
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch
from sqlalchemy.dialects import mysql
from app.services.stats_service import StatsService


class StatsConsistencyTests(unittest.IsolatedAsyncioTestCase):
    async def test_failed_database_increment_never_publishes_cache_or_commits(self):
        db = SimpleNamespace(execute=AsyncMock(side_effect=RuntimeError('database failure')),
                             flush=AsyncMock(), commit=AsyncMock())
        with patch('app.services.stats_service.get_redis', AsyncMock()) as redis:
            with self.assertRaises(RuntimeError):
                await StatsService.increment_quiz_stat(db, 7, True)
        redis.assert_not_awaited()
        db.commit.assert_not_awaited()

    async def test_incorrect_quiz_does_not_add_to_correct_count(self):
        db = SimpleNamespace(execute=AsyncMock(), flush=AsyncMock(), commit=AsyncMock())
        with patch('app.services.stats_service.get_redis', AsyncMock(return_value=None)):
            await StatsService.increment_quiz_stat(db, 7, False)
        compiled = db.execute.call_args.args[0].compile(dialect=mysql.dialect())
        self.assertEqual(compiled.params['quiz_count'], 1)
        self.assertEqual(compiled.params['quiz_correct'], 0)
        db.commit.assert_not_awaited()

    async def test_dashboard_week_uses_same_seven_day_bounds(self):
        db = SimpleNamespace(execute=AsyncMock(return_value=Mock(scalar=Mock(return_value=0))))
        with patch('app.services.stats_service.get_redis', AsyncMock(return_value=None)):
            data = await StatsService.get_dashboard(db, 7)
        params = db.execute.call_args_list[1].args[0].compile().params
        self.assertIn(date.today() - timedelta(days=6), params.values())
        self.assertIn(date.today(), params.values())
        self.assertEqual(data.words_learned_week, 0)

    async def test_quiz_increment_uses_atomic_insert_with_addition(self):
        db = SimpleNamespace(execute=AsyncMock(return_value=Mock(scalar_one_or_none=Mock(return_value=None))), flush=AsyncMock(), add=Mock())
        with patch('app.services.stats_service.get_redis', AsyncMock(return_value=None)):
            await StatsService.increment_quiz_stat(db, 7, True)
        statements = [str(call.args[0].compile(dialect=mysql.dialect())) for call in db.execute.call_args_list]
        self.assertEqual(len(statements), 1)
        self.assertIn('ON DUPLICATE KEY UPDATE', statements[0])
        self.assertIn('quiz_count = (user_daily_stats.quiz_count +', statements[0])
        self.assertIn('quiz_correct = (user_daily_stats.quiz_correct +', statements[0])

    async def test_word_increment_uses_atomic_insert_for_learn_and_review(self):
        for review, column in [(False, 'words_learned'), (True, 'words_reviewed')]:
            with self.subTest(review=review):
                db = SimpleNamespace(execute=AsyncMock(return_value=Mock(scalar_one_or_none=Mock(return_value=None))), flush=AsyncMock(), add=Mock())
                with patch('app.services.stats_service.get_redis', AsyncMock(return_value=None)):
                    await StatsService.increment_word_stat(db, 7, review)
                sql = str(db.execute.call_args.args[0].compile(dialect=mysql.dialect()))
                self.assertIn('ON DUPLICATE KEY UPDATE', sql)
                self.assertIn(f'{column} = (user_daily_stats.{column} +', sql)

    async def test_weekly_query_covers_exactly_seven_dates(self):
        db = SimpleNamespace(execute=AsyncMock(return_value=Mock(
            scalars=Mock(return_value=Mock(all=Mock(return_value=[]))))))
        with patch('app.services.stats_service.get_redis', AsyncMock(return_value=None)):
            result = await StatsService.get_weekly_stats(db, 7)
        params = db.execute.call_args.args[0].compile().params
        self.assertIn(date.today() - timedelta(days=6), params.values())
        self.assertIn(date.today(), params.values())
        self.assertEqual(result['accuracy'], 0)
