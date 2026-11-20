"""N2 watch ImportSession bridge tests."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from services.watch import import_session


class WatchImportSessionTests(unittest.TestCase):
    def test_stage_jats_creates_import_and_returns_paper(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            xml = Path(tmp) / "PMC1.xml"
            xml.write_text("<article/>", encoding="utf-8")
            with mock.patch.object(
                import_session,
                "create_import",
                return_value={"import_id": "imp_watch"},
            ), mock.patch.object(
                import_session,
                "process_import",
                return_value={
                    "items": [
                        {"status": "built", "parsed_json": {"paper_id": "paper_watch_1"}}
                    ]
                },
            ):
                result = import_session.stage_jats(xml, {"doi": "10.1/x"})
        self.assertEqual(result["import_id"], "imp_watch")
        self.assertEqual(result["paper_id"], "paper_watch_1")

    def test_enabled_flag(self) -> None:
        with mock.patch.dict(os.environ, {"SCIPAL_WATCH_IMPORT_SESSION": "1"}):
            self.assertTrue(import_session.enabled())
        with mock.patch.dict(os.environ, {"SCIPAL_WATCH_IMPORT_SESSION": ""}):
            self.assertFalse(import_session.enabled())


if __name__ == "__main__":
    unittest.main()
