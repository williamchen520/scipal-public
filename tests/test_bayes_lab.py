from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from flask import Flask

from plugins.bayes_lab.routes import build_bayes_blueprint
from plugins.bayes_lab.service import BayesianStudy


class BayesStudyTest(unittest.TestCase):
    def test_bounds(self):
        study = BayesianStudy([(0.0, 1.0), (-1.0, 1.0)])
        point = study.suggest()
        self.assertEqual(len(point), 2)
        self.assertTrue(0.0 <= point[0] <= 1.0)
        self.assertTrue(-1.0 <= point[1] <= 1.0)

    def test_observe_and_suggest(self):
        study = BayesianStudy([(0.0, 1.0)], seed=1)
        for value in [0.0, 0.25, 0.5, 0.75, 1.0]:
            study.observe([value], -(value - 0.7) ** 2)
        point = study.suggest()
        self.assertTrue(0.0 <= point[0] <= 1.0)

    def test_invalid_point(self):
        study = BayesianStudy([(0.0, 1.0)])
        with self.assertRaises(ValueError):
            study.observe([2.0], 0.0)


class BayesRoutesTest(unittest.TestCase):
    def test_create_observe_suggest(self):
        app = Flask(__name__)
        app.register_blueprint(build_bayes_blueprint())
        client = app.test_client()
        created = client.post("/api/bayes-lab/studies", json={"bounds": [[0, 1]]}).get_json()
        study_id = created["study_id"]
        self.assertEqual(client.post(f"/api/bayes-lab/studies/{study_id}/observe", json={"point": [0.5], "value": -1}).status_code, 200)
        response = client.post(f"/api/bayes-lab/studies/{study_id}/suggest", json={})
        self.assertEqual(response.status_code, 200)
        self.assertIn("point", response.get_json())


if __name__ == "__main__":
    unittest.main()
