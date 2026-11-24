from datetime import timedelta
import unittest

from app.core.security import create_exam_scan_token, decode_token


class ExamScanTokenTests(unittest.TestCase):
    def test_scan_token_is_scoped_to_one_exam(self):
        token = create_exam_scan_token(
            user_id=42,
            exam_id=20260921001,
            expires_delta=timedelta(minutes=10),
        )

        payload = decode_token(token)

        self.assertIsNotNone(payload)
        self.assertEqual(payload["sub"], "42")
        self.assertEqual(payload["purpose"], "exam_scan")
        self.assertEqual(payload["exam_id"], "20260921001")
        self.assertIn("exp", payload)

    def test_expired_scan_token_is_rejected(self):
        token = create_exam_scan_token(
            user_id=42,
            exam_id=20260921001,
            expires_delta=timedelta(seconds=-1),
        )

        self.assertIsNone(decode_token(token))


if __name__ == "__main__":
    unittest.main()
