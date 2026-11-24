import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from app.services.wrong_book_service import WrongBookService


class WrongBookSyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_corrected_answer_removes_old_wrong_record(self):
        existing = SimpleNamespace()
        submission = SimpleNamespace(id=1, exam_id=2, student_id=3, wrong_count=1,
            ai_grade_detail=[{'index': 0, 'question_number': 21, 'is_correct': True, 'score': 2, 'max_score': 2}])
        db = SimpleNamespace(get=AsyncMock(return_value=SimpleNamespace(id=2, questions=[{}])),
            execute=AsyncMock(return_value=Mock(scalar_one_or_none=Mock(return_value=existing))),
            delete=AsyncMock(), flush=AsyncMock(), add=Mock())
        count = await WrongBookService.save_from_submission(db, submission)
        db.delete.assert_awaited_once_with(existing)
        self.assertEqual(count, 0)
        self.assertEqual(submission.wrong_count, 0)

    async def test_existing_wrong_answer_still_counts_and_uses_printed_number(self):
        existing = SimpleNamespace(score=0, max_score=2, student_answer='A', correct_answer='B', ai_comment='')
        submission = SimpleNamespace(id=1, exam_id=2, student_id=3, wrong_count=1,
            ai_grade_detail=[{'index': 0, 'question_number': 21, 'is_correct': False, 'score': 0, 'max_score': 2, 'user_answer': 'C'}])
        db = SimpleNamespace(get=AsyncMock(return_value=SimpleNamespace(id=2, questions=[{}])),
            execute=AsyncMock(return_value=Mock(scalar_one_or_none=Mock(return_value=existing))),
            delete=AsyncMock(), flush=AsyncMock(), add=Mock())
        count = await WrongBookService.save_from_submission(db, submission)
        self.assertEqual(count, 1)
        self.assertEqual(submission.wrong_count, 1)
        self.assertEqual(existing.student_answer, 'C')
        query = db.execute.call_args.args[0]
        self.assertIn(21, query.compile().params.values())
        db.add.assert_not_called()
