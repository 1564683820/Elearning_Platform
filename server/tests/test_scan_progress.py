import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from app.models.class_models import ClassStudentInfo
from app.services.exam_service import ExamService


class ScanProgressTests(unittest.IsolatedAsyncioTestCase):
    async def test_ungraded_roster_does_not_require_registered_user_fields(self):
        roster = ClassStudentInfo(
            id=101, class_id=7, student_number=1,
            student_name='Test learner', exam_number='000123',
        )
        db = SimpleNamespace(
            get=AsyncMock(return_value=SimpleNamespace(teacher_id=42, class_id=7)),
            execute=AsyncMock(side_effect=[
                Mock(scalar=Mock(return_value=0)),
                Mock(scalar=Mock(return_value=1)),
                Mock(scalars=Mock(return_value=Mock(all=Mock(return_value=[roster])))),
                [],
            ]),
        )

        result = await ExamService.get_scan_progress(db, 5, 42)

        self.assertEqual(result['total_students'], 1)
        self.assertEqual(result['progress_pct'], 0)
        self.assertEqual(result['ungraded_students'][0]['student_name'], 'Test learner')
        self.assertIsNone(result['ungraded_students'][0]['student_id'])
        self.assertEqual(result['ungraded_students'][0]['roster_id'], 101)
        self.assertEqual(result['ungraded_students'][0]['exam_number'], '000123')

    async def test_other_teachers_cannot_read_scan_progress(self):
        db = SimpleNamespace(
            get=AsyncMock(return_value=SimpleNamespace(teacher_id=43)),
            execute=AsyncMock(),
        )
        result = await ExamService.get_scan_progress(db, 5, 42)
        self.assertIn('error', result)
        db.execute.assert_not_awaited()
