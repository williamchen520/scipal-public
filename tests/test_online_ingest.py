"""D3 online ingest worker tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from services.online import ingest


class OnlineIngestTests(unittest.TestCase):
    def test_safe_url_rejects_private_and_file(self) -> None:
        for value in ("file:///etc/passwd", "http://127.0.0.1/a", "http://localhost/a"):
            with self.assertRaises(ingest.IngestError):
                ingest._safe_url(value)

    def test_redirect_revalidates_target(self) -> None:
        calls = []

        def safe(url):
            calls.append(url)
            if len(calls) > 1:
                raise ingest.IngestError("blocked redirect target")

        class Response:
            status_code = 302
            headers = {"Location": "http://127.0.0.1/secret"}

            def close(self):
                pass

        with mock.patch.object(ingest, "_safe_url", side_effect=safe), mock.patch.object(
            ingest.requests, "get", return_value=Response()
        ):
            with self.assertRaises(ingest.IngestError):
                ingest._fetch("https://public.example/paper")
        self.assertEqual(len(calls), 2)

    def test_no_url_uses_abstract(self) -> None:
        with mock.patch.object(
            ingest.abstract_paper,
            "ensure_abstract_paper",
            return_value={"paper_id": "paper_abs"},
        ), mock.patch.object(
            ingest.candidates,
            "mark_status",
            return_value={"ingest_status": "draft"},
        ) as mark:
            result = ingest.ingest(
                {
                    "candidate_id": "c1",
                    "url": "",
                    "source": "pubmed",
                    "external_id": "PMID:1",
                }
            )
        self.assertEqual(result["ingest_status"], "draft")
        mark.assert_called_once()

    def test_html_success(self) -> None:
        candidate = {
            "candidate_id": "c1",
            "url": "https://example.org/a",
            "best_format": "html",
        }
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            ingest, "_staging_root", return_value=Path(tmp)
        ), mock.patch.object(ingest, "_fetch", return_value=(b"<html></html>", "text/html")), mock.patch.object(
            ingest, "create_import", return_value={"import_id": "imp_1"}
        ) as create, mock.patch.object(
            ingest,
            "process_import",
            return_value={
                "items": [
                    {"status": "built", "parsed_json": {"paper_id": "paper_1"}, "error": ""}
                ]
            },
        ), mock.patch.object(
            ingest.candidates, "mark_status", return_value={"ingest_status": "draft"}
        ) as mark:
            result = ingest.ingest(candidate)
        self.assertEqual(result["ingest_status"], "draft")
        self.assertEqual(create.call_args.kwargs["origin"], "online")
        mark.assert_called_once()

    def test_format_priority(self) -> None:
        self.assertEqual(
            ingest._format({"best_format": "pdf", "url": "https://x/a.html"}, "text/html"),
            "html",
        )


if __name__ == "__main__":
    unittest.main()
