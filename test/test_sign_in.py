import unittest

from automationv3.services import accounts
from automationv3.services.settings import Settings
from automationv3.web.auth import COOKIE

from .central import Central, link_path, sent_links


class TestSingleUser(unittest.TestCase):
    def setUp(self):
        self.server = Central(settings=Settings())

    def tearDown(self):
        self.server.close()

    def test_no_sign_in_and_everyone_is_admin(self):
        http = self.server.client()
        self.assertEqual(http.get("/reports/").status_code, 200)
        page = http.get("/admin/").get_data(as_text=True)
        self.assertIn("Admin", page)
        self.assertNotIn('href="/account"', http.get("/reports/").get_data(as_text=True))
        self.assertEqual(http.get("/auth/login").status_code, 302)


class TestCentralSignIn(unittest.TestCase):
    def setUp(self):
        self.server = Central()
        self.http = self.server.client()

    def tearDown(self):
        self.server.close()

    def test_pages_need_sign_in(self):
        response = self.http.get("/reports/?x=1")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/auth/login?next=/reports/?x%3D1", response.headers["Location"])
        api = self.http.get("/reports/", headers={"Accept": "application/json"})
        self.assertEqual(api.status_code, 401)
        self.assertEqual(self.http.get("/auth/login").status_code, 200)

    def test_the_login_page_is_styled_signed_out(self):
        page = self.http.get("/auth/login").get_data(as_text=True)
        self.assertIn('href="/static/css/automation.css"', page)
        import re
        sheets = re.findall(r'<link rel="stylesheet" href="([^"]+)"', page)
        self.assertIn("/plugins.css", sheets)
        for href in sheets:  # every one loads signed out
            with self.subTest(href):
                css = self.http.get(href)
                self.assertEqual(css.status_code, 200)
                css.close()

    def test_sign_in_by_link(self):
        with sent_links() as sent:
            page = self.http.post("/auth/login", data={"email": "Ann@Example.com",
                                                      "next": "/scratch/"})
        self.assertIn("Check your email", page.get_data(as_text=True))
        ((to, link, device),) = sent
        self.assertEqual((to, device), ("ann@example.com", None))

        # Opening the link only offers a button: scanners don't sign in
        shown = self.http.get(link_path(link))
        self.assertIn("Sign in as ann@example.com", shown.get_data(as_text=True))
        self.assertIsNone(self.http.get_cookie(COOKIE))

        signed = self.http.post(link_path(link))
        self.assertEqual(signed.status_code, 302)
        self.assertEqual(signed.headers["Location"], "/scratch/")
        cookie = self.http.get_cookie(COOKIE)
        self.assertTrue(cookie.http_only)
        self.assertEqual(cookie.same_site, "Lax")

        page = self.http.get("/reports/").get_data(as_text=True)
        self.assertIn("ann@example.com", page)
        self.assertIn('href="/account"', page)
        self.assertNotIn('href="/admin/"', page)

        # The link worked once
        self.assertEqual(self.server.client().post(link_path(link)).status_code, 410)

    def test_other_domains_are_turned_away(self):
        with sent_links() as sent:
            page = self.http.post("/auth/login", data={"email": "eve@evil.org"})
        self.assertEqual(page.status_code, 400)
        self.assertIn("@example.com", page.get_data(as_text=True))
        self.assertEqual(sent, [])

    def test_next_stays_on_this_site(self):
        with sent_links() as sent:
            self.http.post("/auth/login", data={"email": "ann@example.com",
                                                "next": "https://evil.org/"})
        response = self.http.post(link_path(sent[0][1]))
        self.assertEqual(response.headers["Location"], "/")

    def test_sign_out(self):
        http = self.server.client("ann@example.com")
        self.assertEqual(http.get("/reports/").status_code, 200)
        http.post("/auth/logout")
        self.assertEqual(http.get("/reports/").status_code, 302)

    def test_admin_page_is_for_admins(self):
        self.assertEqual(self.server.client("ann@example.com").get("/admin/").status_code, 403)
        lead = self.server.client("lead@example.com")
        page = lead.get("/admin/").get_data(as_text=True)
        self.assertIn("ann@example.com", page)
        self.assertIn('href="/admin/"', page)

    def test_devices_on_the_account_page(self):
        secret = self.server.token("user", "ann-laptop", "ann@example.com")
        http = self.server.client("ann@example.com")
        page = http.get("/account").get_data(as_text=True)
        self.assertIn("ann-laptop", page)
        with self.server.conn() as conn:
            (device,) = accounts.find_tokens(conn, "user")
        self.server.client("bob@example.com").post(f"/account/devices/{device.id}/revoke")
        with self.server.conn() as conn:
            self.assertIsNotNone(accounts.token_for(conn, secret))
        http.post(f"/account/devices/{device.id}/revoke")
        with self.server.conn() as conn:
            self.assertIsNone(accounts.token_for(conn, secret))

    def test_a_device_token_acts_as_its_user(self):
        secret = self.server.token("user", "laptop", "ann@example.com")
        headers = {"Authorization": f"Bearer {secret}"}
        self.assertEqual(self.http.get("/reports/", headers=headers).status_code, 200)
        bad = {"Authorization": "Bearer av3u_nope"}
        self.assertEqual(self.http.get("/reports/", headers=bad).status_code, 401)
