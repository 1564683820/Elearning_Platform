import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from app.services.membership_service import MembershipService


class MembershipTransactionTests(unittest.IsolatedAsyncioTestCase):
    def database(self, *rows):
        return SimpleNamespace(execute=AsyncMock(side_effect=[Mock(scalar_one_or_none=Mock(return_value=r)) for r in rows]),
            commit=AsyncMock(), flush=AsyncMock(), add=Mock())

    async def test_failed_activation_never_commits_consumed_code(self):
        code = SimpleNamespace(status='active', expire_at=None, plan='vip_student', duration_months=1)
        db = self.database(code)
        with patch.object(MembershipService, '_apply_membership_to_user', AsyncMock(side_effect=ValueError('用户不存在'))):
            with self.assertRaises(ValueError):
                await MembershipService.redeem_code(db, 1, 'test-code')
        db.commit.assert_not_awaited()

    async def test_redeem_preserves_code_deadline_and_reports_actual_renewal(self):
        deadline = datetime.now() + timedelta(days=3)
        prior_expire = datetime.now() + timedelta(days=60)
        code = SimpleNamespace(status='active', expire_at=deadline, plan='vip_student', duration_months=1)
        user = SimpleNamespace(membership='vip_student', membership_expire=prior_expire)
        db = self.database(code, user)
        result = await MembershipService.redeem_code(db, 1, 'test-code')
        self.assertEqual(code.expire_at, deadline)
        self.assertGreater(user.membership_expire, prior_expire + timedelta(days=29))
        self.assertEqual(result['expire_at'], user.membership_expire.isoformat())
        db.commit.assert_awaited_once()
        self.assertIsNotNone(db.execute.call_args_list[0].args[0]._for_update_arg)

    async def test_paid_callback_retry_never_activates_twice(self):
        db = self.database(SimpleNamespace(payment_status='paid'))
        with patch.object(MembershipService, '_apply_membership_to_user', AsyncMock()) as apply:
            result = await MembershipService.handle_payment_callback(db, 'test-order')
        self.assertEqual(result['status'], 'already_paid')
        apply.assert_not_awaited()
        db.commit.assert_not_awaited()

    async def test_callback_activation_failure_never_commits_paid_order(self):
        order = SimpleNamespace(payment_status='pending', user_id=1, plan='vip_student', duration_months=1, expire_at=datetime.now())
        db = self.database(order)
        with patch.object(MembershipService, '_apply_membership_to_user', AsyncMock(side_effect=ValueError('用户不存在'))):
            with self.assertRaises(ValueError):
                await MembershipService.handle_payment_callback(db, 'test-order')
        db.commit.assert_not_awaited()

    async def test_callback_grants_full_duration_from_payment_not_order_creation(self):
        old_expire = datetime.now() - timedelta(days=10)
        order = SimpleNamespace(payment_status='pending', user_id=1, plan='vip_student', duration_months=1, expire_at=old_expire)
        user = SimpleNamespace(membership='free', membership_expire=None)
        db = self.database(order, user)
        result = await MembershipService.handle_payment_callback(db, 'test-order')
        self.assertGreater(user.membership_expire, datetime.now() + timedelta(days=29))
        self.assertEqual(order.expire_at, user.membership_expire)
        self.assertEqual(result['expire_at'], user.membership_expire.isoformat())
        db.commit.assert_awaited_once()
        for call in db.execute.call_args_list:
            self.assertIsNotNone(call.args[0]._for_update_arg)

    async def test_cancelled_order_cannot_be_activated(self):
        db = self.database(SimpleNamespace(payment_status='cancelled'))
        with self.assertRaises(ValueError):
            await MembershipService.handle_payment_callback(db, 'test-order')
        db.commit.assert_not_awaited()

    async def test_used_code_is_rejected_before_user_changes(self):
        db = self.database(SimpleNamespace(status='used'))
        with self.assertRaises(ValueError):
            await MembershipService.redeem_code(db, 1, 'test-code')
        self.assertEqual(db.execute.await_count, 1)
        db.commit.assert_not_awaited()
