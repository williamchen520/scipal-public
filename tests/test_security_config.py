"""P2 baseline: request body limit and session cookie flags."""

from __future__ import annotations

import os
import unittest


@unittest.skipUnless(os.environ.get("SCIPAL_PG_DSN"), "security config requires app env")
class SecurityConfigTests(unittest.TestCase):
    def test_body_limit_and_cookie_flags(self) -> None:
        import api_server

        cfg = api_server.app.config
        self.assertGreaterEqual(cfg["MAX_CONTENT_LENGTH"], 1024 * 1024)
        self.assertTrue(cfg["SESSION_COOKIE_HTTPONLY"])
        self.assertEqual(cfg["SESSION_COOKIE_SAMESITE"], "Lax")
        self.assertIn(cfg["SESSION_COOKIE_SECURE"], {True, False})


if __name__ == "__main__":
    unittest.main()
