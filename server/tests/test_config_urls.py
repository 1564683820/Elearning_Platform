import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from pydantic import ValidationError
from sqlalchemy.engine import make_url
from app.core.config import Settings


class ConfigurationURLTests(unittest.TestCase):
    def setUp(self):
        env_patch = patch.dict("os.environ", {
            "SECRET_KEY": "fixture-app",
            "AES_SECRET_KEY": "fixture-encryption",
            "JWT_SECRET": "fixture-signing",
        })
        env_patch.start()
        self.addCleanup(env_patch.stop)

    def test_database_passwords_are_loaded_from_dotenv(self):
        with TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text("MYSQL_PASSWORD='fixture:@/#'\nREDIS_PASSWORD='fixture $:#'\n",
                                encoding="utf-8")
            with patch.dict("os.environ", {
                "SECRET_KEY": "fixture-app",
                "AES_SECRET_KEY": "fixture-encryption",
                "JWT_SECRET": "fixture-signing",
            }, clear=True):
                settings = Settings(_env_file=env_file)
        self.assertEqual(settings.mysql_connection_kwargs()["password"], "fixture:@/#")
        self.assertEqual(make_url(settings.REDIS_URL).password, "fixture $:#")

    def test_missing_or_empty_signing_secret_is_rejected(self):
        for env in ({}, {"JWT_SECRET": ""}):
            with self.subTest(env=env), patch.dict("os.environ", env, clear=True):
                with self.assertRaises(ValidationError) as raised:
                    Settings(_env_file=None, SECRET_KEY="fixture-app",
                             AES_SECRET_KEY="fixture-encryption")
                self.assertEqual([error["loc"] for error in raised.exception.errors()], [("JWT_SECRET",)])

    def test_reserved_characters_in_credentials_do_not_change_connection_target(self):
        settings = Settings(_env_file=None, MYSQL_USER='demo@user', MYSQL_PASSWORD='fake:@/#?[]',
            REDIS_PASSWORD='fake:@/#?[]')
        for value in (settings.DATABASE_URL, settings.WORDS_DATABASE_URL,
                      settings.SYNC_DATABASE_URL, settings.SYNC_WORDS_DATABASE_URL):
            parsed = make_url(value)
            self.assertEqual(parsed.username, 'demo@user')
            self.assertEqual(parsed.password, 'fake:@/#?[]')
            self.assertEqual(parsed.host, settings.MYSQL_HOST)
        redis = make_url(settings.REDIS_URL)
        self.assertEqual(redis.password, 'fake:@/#?[]')
        self.assertEqual(redis.host, settings.REDIS_HOST)

    def test_passwordless_redis_does_not_insert_an_empty_authentication_section(self):
        settings = Settings(_env_file=None, REDIS_PASSWORD='')
        self.assertNotIn('@', settings.REDIS_URL)
