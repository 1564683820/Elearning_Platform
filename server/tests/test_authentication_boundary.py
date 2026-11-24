from datetime import timedelta
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from app.api import deps
from app.core.security import create_token, create_exam_scan_token
from app.db.database import get_db


class AuthenticationBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.app = FastAPI()
        self.user = SimpleNamespace(id=42, role='student')
        self.result = Mock(scalar_one_or_none=Mock(side_effect=lambda: self.user))
        self.db = SimpleNamespace(execute=AsyncMock(return_value=self.result))

        async def database():
            yield self.db

        self.app.dependency_overrides[get_db] = database

        @self.app.get('/user')
        async def user(value=Depends(deps.get_current_user)):
            return {'id': value.id}

        @self.app.get('/teacher')
        async def teacher(value=Depends(deps.get_current_teacher)):
            return {'id': value.id}

        @self.app.get('/admin')
        async def admin(value=Depends(deps.get_current_admin)):
            return {'id': value.id}

        @self.app.get('/download')
        async def download(value=Depends(deps.get_current_teacher_id_download)):
            return {'id': value}

        @self.app.get('/user-download')
        async def user_download(value=Depends(deps.get_current_user_id_download)):
            return {'id': value}

        @self.app.get('/scan')
        async def scan(value=Depends(deps.get_exam_scan_principal)):
            return {'id': value.teacher_id}

    async def request(self, path, token=None, authorization=None):
        headers = {}
        if token is not None:
            headers['Authorization'] = f'Bearer {token}'
        if authorization is not None:
            headers['Authorization'] = authorization
        async with AsyncClient(transport=ASGITransport(app=self.app), base_url='http://test') as client:
            return await client.get(path, headers=headers)

    async def test_missing_or_wrong_authorization_is_401_with_bearer_challenge(self):
        for header in (None, 'Basic abc', 'Bearer '):
            with self.subTest(header=header):
                response = await self.request('/user', authorization=header)
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.headers.get('www-authenticate'), 'Bearer')
        self.db.execute.assert_not_awaited()

    async def test_invalid_and_expired_token_rejected_before_database(self):
        for token in ('invalid', create_token(42, timedelta(seconds=-1))):
            response = await self.request('/user', token)
            self.assertEqual(response.status_code, 401)
        self.db.execute.assert_not_awaited()

    async def test_subject_must_be_a_positive_database_identifier(self):
        for subject in ('abc', '0', '-1', '9223372036854775808', '99999999999999999999'):
            for route in ('/user', '/download', '/user-download', '/scan'):
                with self.subTest(subject=subject, route=route):
                    response = await self.request(route, create_token(42, extra_claims={'sub': subject}))
                    self.assertEqual(response.status_code, 401)
            with self.assertRaises(ValueError):
                await deps.get_current_user_id_ws(create_token(42, extra_claims={'sub': subject}))
        self.db.execute.assert_not_awaited()

    async def test_valid_snowflake_subject_keeps_full_precision(self):
        identifier = 9007199254740993
        self.user.id = identifier
        token = create_token(identifier)
        response = await self.request('/user', token)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['id'], identifier)
        self.assertEqual(await deps.get_current_user_id_ws(token), identifier)
        statement = self.db.execute.call_args.args[0].compile()
        self.assertIn(identifier, statement.params.values())

    async def test_real_dependencies_preserve_role_matrix(self):
        for role, expected in [('student', [200, 403, 403]), ('teacher', [200, 200, 403]), ('admin', [200, 200, 200])]:
            self.user.role = role
            for route, status in zip(('/user', '/teacher', '/admin'), expected):
                with self.subTest(role=role, route=route):
                    self.assertEqual((await self.request(route, create_token(42))).status_code, status)

    async def test_restricted_scan_token_cannot_become_general_access(self):
        self.user.role = 'teacher'
        token = create_exam_scan_token(42, 12, timedelta(minutes=10))
        for route in ('/user', '/download', '/user-download'):
            self.assertEqual((await self.request(route, token)).status_code, 401)
        self.assertEqual((await self.request('/scan', token)).status_code, 200)
        with self.assertRaises(ValueError):
            await deps.get_current_user_id_ws(token)

    async def test_deleted_user_cannot_use_regular_login(self):
        self.user = None
        self.assertEqual((await self.request('/user', create_token(42))).status_code, 401)
