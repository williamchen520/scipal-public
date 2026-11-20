"""Tests for the Step 1 Flask app factory."""

from __future__ import annotations

import unittest
from unittest import mock

from api_server_factory import AppConfig, create_app


class AppFactoryTest(unittest.TestCase):
    def test_contract_mode_skips_env_and_tenancy(self) -> None:
        with mock.patch("services.db.env_guard.check_env") as check_env, mock.patch(
            "services.tenancy.bootstrap_default_workspace"
        ) as bootstrap:
            app = create_app(AppConfig(strict_env=False, bootstrap_tenancy=False))

        self.assertEqual(app.name, "api_server")
        check_env.assert_not_called()
        bootstrap.assert_not_called()

    def test_default_mode_runs_env_and_tenancy(self) -> None:
        with mock.patch("services.db.env_guard.check_env") as check_env, mock.patch(
            "services.tenancy.bootstrap_default_workspace"
        ) as bootstrap:
            app = create_app()

        self.assertEqual(app.name, "api_server")
        check_env.assert_called_once()
        bootstrap.assert_called_once()


if __name__ == "__main__":
    unittest.main()
