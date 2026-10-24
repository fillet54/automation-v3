import tempfile
import unittest
from pathlib import Path

from automationv3.services import settings


class TestSettings(unittest.TestCase):
    def test_no_file_is_single_user(self):
        s = settings.load(None)
        self.assertFalse(s.central)
        self.assertIsNone(s.git)

    def test_a_full_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "server.toml"
            path.write_text('''
base_url = "https://auto.example.com/"

[auth]
allowed_domains = ["example.com"]
admins = ["Lead@example.com"]

[smtp]
host = "mail.example.com"
sender = "auto@example.com"

[git]
remote = "git@example.com:team/scripts.git"
''')
            s = settings.load(path, env={"AUTOMATION_WEBHOOK_SECRET": "shh"})
        self.assertTrue(s.central)
        self.assertEqual(s.base_url, "https://auto.example.com")
        self.assertEqual(s.auth.session_days, 30)
        self.assertEqual(s.auth.link_minutes, 15)
        self.assertTrue(s.auth.allows("ann@EXAMPLE.com"))
        self.assertFalse(s.auth.allows("ann@example.com.evil.org"))
        self.assertTrue(s.auth.is_admin("lead@example.com"))
        self.assertEqual(s.smtp.port, 25)
        self.assertEqual(s.git.webhook_secret, "shh")

    def test_mistakes_are_reported(self):
        cases = [
            ({"auth": {}}, "allowed_domains"),
            ({"auth": {"allowed_domains": ["x.com"], "sesion_days": 3}}, "sesion_days"),
            ({"smtp": {"port": 25}}, "host"),
            ({"git": {}}, "remote"),
            ({"colour": "blue"}, "colour"),
        ]
        for data, word in cases:
            with self.subTest(data=data):
                with self.assertRaisesRegex(settings.SettingsError, word):
                    settings.parse(data, env={})

    def test_unreadable_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.toml"
            path.write_text("auth = [")
            with self.assertRaisesRegex(settings.SettingsError, "TOML"):
                settings.load(path)
