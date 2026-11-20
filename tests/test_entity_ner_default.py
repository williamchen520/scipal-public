"""S3.E: scispacy NER is opt-in, not a hot-path default."""

from __future__ import annotations

import os
import unittest
from unittest import mock

from services.search.agentic_search import _ner_disabled


class NerDefaultTests(unittest.TestCase):
    def test_default_disabled(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertTrue(_ner_disabled())

    def test_enable(self) -> None:
        with mock.patch.dict(os.environ, {"SCIPAL_ENABLE_NER": "1"}, clear=True):
            self.assertFalse(_ner_disabled())

    def test_explicit_disable_wins(self) -> None:
        with mock.patch.dict(
            os.environ, {"SCIPAL_ENABLE_NER": "1", "SCIPAL_DISABLE_NER": "1"}, clear=True
        ):
            self.assertTrue(_ner_disabled())


if __name__ == "__main__":
    unittest.main()
