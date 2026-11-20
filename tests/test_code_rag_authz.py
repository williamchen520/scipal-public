"""C1: workspace/library authorization tests."""

from __future__ import annotations

import os
import unittest
from unittest import mock

from code_rag.api import create_app
from code_rag.authz import authorize_library


class CodeAuthzTests(unittest.TestCase):
    def test_authorize_library(self) -> None:
        with mock.patch("code_rag.authz.library_workspace", return_value="ws_a"):
            self.assertTrue(authorize_library("lib_a", "ws_a"))
            self.assertFalse(authorize_library("lib_a", "ws_b"))

    def test_code_api_requires_workspace_when_configured(self) -> None:
        client = create_app().test_client()
        env = {
            "SCIPAL_INTERNAL_TOKEN": "t",
            "SCIPAL_CODE_WORKSPACE_REQUIRED": "1",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            response = client.post(
                "/libraries/lib_1/search",
                headers={"X-SCIPAL-Internal-Token": "t"},
                json={"query": "f"},
            )
        self.assertEqual(response.status_code, 403)

    def test_code_api_rejects_wrong_workspace(self) -> None:
        client = create_app().test_client()
        env = {
            "SCIPAL_INTERNAL_TOKEN": "t",
            "SCIPAL_CODE_WORKSPACE_REQUIRED": "1",
        }
        with mock.patch.dict(os.environ, env, clear=False), mock.patch(
            "code_rag.api.authorize_library", return_value=False
        ):
            response = client.post(
                "/libraries/lib_1/search",
                headers={
                    "X-SCIPAL-Internal-Token": "t",
                    "X-SCIPAL-Workspace-Id": "ws_b",
                },
                json={"query": "f"},
            )
        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
