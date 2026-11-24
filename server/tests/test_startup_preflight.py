import importlib.util
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch
from sqlalchemy.exc import OperationalError


script = Path(__file__).resolve().parents[2] / '.harness/scripts/check-database.py'
spec = importlib.util.spec_from_file_location('startup_preflight', script)
preflight = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preflight)


class StartupPreflightTests(unittest.TestCase):
    def test_errors_give_distinct_recovery_steps(self):
        self.assertIn('Start-Service MySQL80', preflight.failure_hint(2003))
        self.assertIn('MYSQL_USER/MYSQL_PASSWORD', preflight.failure_hint(1045))
        self.assertIn('MYSQL_DATABASE/WORDS_DATABASE', preflight.failure_hint(1049))

    @patch.object(preflight, 'create_engine')
    def test_success_only_reads_both_databases(self, create_engine):
        engines = [MagicMock(), MagicMock()]
        create_engine.side_effect = engines
        self.assertEqual(preflight.main(), 0)
        self.assertEqual(create_engine.call_count, 2)
        for engine in engines:
            execute = engine.connect.return_value.__enter__.return_value.execute
            self.assertEqual(str(execute.call_args.args[0]), 'SELECT 1')
            engine.dispose.assert_called_once()

    @patch.object(preflight, 'create_engine')
    def test_connection_failure_disposes_engine_without_exposing_password(self, create_engine):
        engine = create_engine.return_value
        engine.connect.side_effect = OperationalError(
            'connect', {}, Exception(2003, 'sensitive-password'))
        with patch('builtins.print') as output:
            self.assertEqual(preflight.main(), 1)
        engine.dispose.assert_called_once()
        self.assertNotIn('sensitive-password', str(output.call_args_list))
