from __future__ import annotations

import unittest
from unittest import mock

from flask import Flask

from plugins.citation_integrity.routes import build_citation_integrity_blueprint
from plugins.citation_integrity import service


def crossref(title="A study", year=2020, retracted=False):
    return {
        "message": {
            "DOI": "10.1000/ABC",
            "title": [title],
            "author": [{"family": "Smith", "given": "Jane"}],
            "issued": {"date-parts": [[year, 1, 1]]},
            "container-title": ["Journal of Tests"],
            "update-to": [{"type": "retraction"}] if retracted else [],
        }
    }


def pubmed():
    return {
        "result": {
            "123": {
                "title": "A study",
                "pubdate": "2020 Jan",
                "authors": [{"name": "Smith J"}],
                "fulljournalname": "Journal of Tests",
                "articleids": [{"idtype": "doi", "value": "10.1000/abc"}],
            }
        }
    }


class CitationIntegrityTest(unittest.TestCase):
    def setUp(self):
        service._CACHE.clear()

    def test_normalize_doi(self):
        self.assertEqual(service.normalize_doi("https://doi.org/10.1000/ABC"), "10.1000/abc")
        self.assertEqual(service.normalize_doi("doi:10.1000/abc"), "10.1000/abc")

    def test_verified(self):
        result = service.check_reference(
            {"doi": "10.1000/abc", "title": "A study", "year": 2020, "authors": ["Jane Smith"]},
            lambda url: crossref(),
        )
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["issues"], [])

    def test_mismatch(self):
        result = service.check_reference(
            {"doi": "10.1000/abc", "title": "A different title", "year": 2019},
            lambda url: crossref(),
        )
        self.assertEqual(result["status"], "mismatch")
        fields = {issue["field"] for issue in result["issues"]}
        self.assertIn("year", fields)
        self.assertIn("title", fields)

    def test_retracted(self):
        result = service.check_reference({"doi": "10.1000/abc"}, lambda url: crossref(retracted=True))
        self.assertEqual(result["status"], "retracted")

    def test_pubmed_fallback(self):
        def fetcher(url):
            if "crossref" in url:
                raise service.NotFound(url)
            return pubmed()

        result = service.check_reference({"doi": "10.1000/abc", "pmid": "123"}, fetcher)
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["resolved"]["source"], "pubmed")

    def test_unverifiable(self):
        result = service.check_reference({"title": "No identifier"})
        self.assertEqual(result["status"], "unverifiable")

    def test_cache_hits_once(self):
        service._CACHE.clear()
        calls = []
        def fetcher(url):
            calls.append(url)
            return crossref()
        service.resolve_crossref("10.1000/cache", fetcher)
        service.resolve_crossref("10.1000/cache", fetcher)
        self.assertEqual(len(calls), 1)

    def test_route(self):
        app = Flask(__name__)
        app.register_blueprint(build_citation_integrity_blueprint())
        client = app.test_client()
        self.assertEqual(client.get("/api/citation-integrity/health").status_code, 200)
        with mock.patch(
            "plugins.citation_integrity.routes.check_reference",
            return_value={"status": "verified", "issues": [], "resolved": {}},
        ):
            response = client.post("/api/citation-integrity/check", json={"doi": "10.1000/abc"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["status"], "verified")


if __name__ == "__main__":
    unittest.main()
