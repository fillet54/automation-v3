import unittest
from datetime import timedelta
from unittest import mock

from automationv3.services import accounts, mail
from automationv3.services.database import connect, init_db
from automationv3.services.settings import Auth, Smtp


AUTH = Auth(allowed_domains=("example.com",), admins=("lead@example.com",))


class AccountsTest(unittest.TestCase):
    def setUp(self):
        self.conn = connect(":memory:")
        init_db(self.conn)
        self.now = accounts.utcnow()

    def tearDown(self):
        self.conn.close()


class TestSignIn(AccountsTest):
    def test_a_link_signs_in_once_and_makes_the_user(self):
        token = accounts.request_sign_in(self.conn, AUTH, " Ann@Example.com ", self.now)
        self.assertIsNone(accounts.find_user(self.conn, "ann@example.com"))
        user, device = accounts.use_link(self.conn, token, self.now)
        self.assertEqual(user.email, "ann@example.com")
        self.assertEqual(user.name, "ann")
        self.assertIsNone(device)
        with self.assertRaisesRegex(accounts.AccountError, "already used|expired"):
            accounts.use_link(self.conn, token, self.now)

    def test_links_expire(self):
        token = accounts.request_sign_in(self.conn, AUTH, "ann@example.com", self.now)
        later = self.now + timedelta(minutes=AUTH.link_minutes, seconds=1)
        self.assertIsNone(accounts.pending_link(self.conn, token, later))
        with self.assertRaises(accounts.AccountError):
            accounts.use_link(self.conn, token, later)

    def test_only_allowed_domains(self):
        for email in ["ann@other.com", "not-an-email", ""]:
            with self.subTest(email=email):
                with self.assertRaises(accounts.AccountError):
                    accounts.request_sign_in(self.conn, AUTH, email, self.now)

    def test_secrets_are_stored_hashed(self):
        token = accounts.request_sign_in(self.conn, AUTH, "ann@example.com", self.now)
        stored = self.conn.execute("SELECT token_hash FROM login_links").fetchone()[0]
        self.assertNotEqual(stored, token)
        self.assertEqual(stored, accounts.digest(token))


class TestSessions(AccountsTest):
    def setUp(self):
        super().setUp()
        self.user = accounts.ensure_user(self.conn, "ann@example.com", self.now)

    def test_a_session_slides_while_used(self):
        token = accounts.create_session(self.conn, self.user, 30, self.now)
        day29 = self.now + timedelta(days=29)
        self.assertEqual(accounts.session_user(self.conn, token, 30, day29).email,
                         "ann@example.com")
        self.assertEqual(accounts.find_user(self.conn, "ann@example.com").last_seen_at,
                         accounts.iso(day29))
        # Used on day 29, so it still works on day 58
        self.assertIsNotNone(accounts.session_user(self.conn, token, 30,
                                                   self.now + timedelta(days=58)))

    def test_an_unused_session_expires(self):
        token = accounts.create_session(self.conn, self.user, 30, self.now)
        self.assertIsNone(accounts.session_user(self.conn, token, 30,
                                                self.now + timedelta(days=31)))
        self.assertIsNone(accounts.session_user(self.conn, token, 30, self.now))

    def test_sign_out(self):
        token = accounts.create_session(self.conn, self.user, 30, self.now)
        accounts.end_session(self.conn, token)
        self.assertIsNone(accounts.session_user(self.conn, token, 30, self.now))


class TestDeviceLogin(AccountsTest):
    def test_the_link_approves_the_device_which_gets_a_token_once(self):
        code, link = accounts.start_device_login(self.conn, AUTH, "ann@example.com",
                                                 "ann-laptop", self.now)
        self.assertIsNone(accounts.poll_device_login(self.conn, code, self.now))
        user, device = accounts.use_link(self.conn, link, self.now)
        self.assertEqual(device, "ann-laptop")
        secret = accounts.poll_device_login(self.conn, code, self.now)
        self.assertTrue(secret.startswith("av3u_"))
        token = accounts.token_for(self.conn, secret, self.now)
        self.assertEqual(token.user.email, "ann@example.com")
        self.assertEqual(token.name, "ann-laptop")
        with self.assertRaises(accounts.AccountError):
            accounts.poll_device_login(self.conn, code, self.now)

    def test_an_unapproved_device_login_expires(self):
        code, _ = accounts.start_device_login(self.conn, AUTH, "ann@example.com",
                                              "laptop", self.now)
        with self.assertRaisesRegex(accounts.AccountError, "expired"):
            accounts.poll_device_login(self.conn, code, self.now + timedelta(hours=1))


class TestTokens(AccountsTest):
    def test_worker_tokens_can_be_revoked(self):
        admin = accounts.ensure_user(self.conn, "lead@example.com")
        secret = accounts.create_token(self.conn, accounts.WORKER_TOKEN, "bench-1",
                                       created_by=admin)
        token = accounts.token_for(self.conn, secret)
        self.assertEqual((token.kind, token.name, token.created_by),
                         ("worker", "bench-1", "lead@example.com"))
        self.assertEqual([t.name for t in accounts.find_tokens(self.conn, "worker")],
                         ["bench-1"])
        self.assertTrue(accounts.revoke_token(self.conn, token.id))
        self.assertIsNone(accounts.token_for(self.conn, secret))
        self.assertEqual(accounts.find_tokens(self.conn, "worker"), [])

    def test_users_revoke_only_their_own(self):
        ann = accounts.ensure_user(self.conn, "ann@example.com")
        bob = accounts.ensure_user(self.conn, "bob@example.com")
        secret = accounts.create_token(self.conn, accounts.USER_TOKEN, "laptop", user=ann)
        token = accounts.token_for(self.conn, secret)
        self.assertFalse(accounts.revoke_token(self.conn, token.id, user=bob))
        self.assertTrue(accounts.revoke_token(self.conn, token.id, user=ann))

    def test_forget_expired(self):
        accounts.request_sign_in(self.conn, AUTH, "ann@example.com", self.now)
        accounts.forget_expired(self.conn, self.now + timedelta(days=1))
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM login_links").fetchone()[0], 0)


class TestMail(unittest.TestCase):
    def test_without_smtp_the_link_is_logged(self):
        with mock.patch("builtins.print") as printed, self.assertLogs("automationv3.mail"):
            self.assertFalse(mail.send_sign_in(None, "ann@example.com", "http://x/l", 15))
        self.assertIn("http://x/l", printed.call_args[0][0])

    def test_smtp(self):
        smtp = Smtp(host="mail", starttls=True, username="u", password="p",
                    sender="auto@example.com")
        with mock.patch("smtplib.SMTP") as SMTP:
            self.assertTrue(mail.send_sign_in(smtp, "ann@example.com", "http://x/l", 15,
                                              device="laptop"))
        server = SMTP.return_value.__enter__.return_value
        server.starttls.assert_called_once()
        server.login.assert_called_once_with("u", "p")
        message = server.send_message.call_args[0][0]
        self.assertIn("laptop", message["Subject"])
        self.assertIn("http://x/l", message.get_content())
