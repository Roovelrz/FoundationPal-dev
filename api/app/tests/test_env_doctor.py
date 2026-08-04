import os
from django.core.management import call_command
from django.test import SimpleTestCase


def _run_env_doctor(env: dict, strict: bool = False) -> int:
    backup = os.environ.copy()
    try:
        os.environ.update(env)
        args = []
        if strict:
            args.append('--strict')
        try:
            call_command('env_doctor', *args)
            return 0
        except SystemExit as e:  # command raises SystemExit for non-zero
            return int(e.code or 0)
    finally:
        os.environ.clear()
        os.environ.update(backup)


class EnvDoctorTests(SimpleTestCase):
    def test_production_requires_a_distinct_jwt_signing_key(self):
        code = _run_env_doctor(
            {
                'DEBUG': '0',
                'SECRET_KEY': 'test',
                'JWT_SIGNING_KEY': 'test',
                'REDIS_URL': 'redis://localhost:6379/0',
            }
        )
        self.assertGreater(code, 0)

    def test_debug_environment_without_payment_settings_passes(self):
        code = _run_env_doctor(
            {
                'DEBUG': '1',
                'SECRET_KEY': 'test',
                'JWT_SIGNING_KEY': 'test-jwt-signing-key',
                'CORS_ALLOW_ALL': '0',
                'ALLOWED_HOSTS': 'localhost,127.0.0.1',
                'REDIS_URL': 'redis://localhost:6379/0',
            },
            strict=True,
        )
        self.assertEqual(code, 0)
