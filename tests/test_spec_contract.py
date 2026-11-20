"""Tests for the executable-contract compiler. Standard library only."""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import spec_compile  # noqa: E402


class ContractCompilerTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "contract").mkdir()
        (self.root / "contract" / "exceptions.json").write_text(
            json.dumps({"schema_version": 1, "exceptions": []}), encoding="utf-8"
        )
        (self.root / "scripts").mkdir()
        (self.root / ".githooks").mkdir()
        (self.root / "tests").mkdir()

        self.endpoints = [
            {"rule": "/health", "endpoint": "health", "methods": ["GET"], "status": "implemented"},
            {
                "rule": "/experiments/{experiment_id}",
                "endpoint": "get_experiment",
                "methods": ["GET"],
                "status": "implemented",
            },
        ]
        (self.root / "ARCHITECTURE.json").write_text(
            json.dumps(
                {
                    "meta": {"version": "0.1.0"},
                    "api": {"endpoints": self.endpoints},
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        for rel in (
            "README.md",
            "scripts/validate_arch.py",
            "scripts/spec_compile.py",
            "scripts/spec_check.py",
            ".githooks/pre-commit",
            "tests/test_guards.py",
        ):
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# fixture\n", encoding="utf-8")
        (self.root / "contract" / "spec.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "name": "fixture",
                    "source_commit": "fixture",
                    "architecture": "ARCHITECTURE.json",
                    "exceptions": "contract/exceptions.json",
                    "approval": "contract/approval.json",
                    "rules": [
                        {"id": "architecture.parse", "kind": "architecture_json", "check": "builtin:architecture_json", "severity": "blocking"},
                        {"id": "architecture.route_unique", "kind": "route_unique", "check": "builtin:route_unique", "severity": "blocking"},
                        {
                            "id": "repo.required_paths",
                            "kind": "required_paths",
                            "check": "builtin:required_paths",
                            "severity": "blocking",
                            "paths": [
                                "ARCHITECTURE.json",
                                "README.md",
                                "scripts/validate_arch.py",
                                "scripts/spec_compile.py",
                                "scripts/spec_check.py",
                                ".githooks/pre-commit",
                                "tests/test_guards.py",
                                "contract/exceptions.json",
                                "contract/approval.json",
                            ],
                        },
                        {
                            "id": "contract_tools.stdlib",
                            "kind": "stdlib_only",
                            "check": "builtin:stdlib_only",
                            "severity": "blocking",
                            "paths": ["scripts/spec_compile.py", "scripts/spec_check.py"],
                        },
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        spec_path = self.root / "contract" / "spec.json"
        spec_hash = hashlib.sha256(spec_path.read_bytes()).hexdigest()
        (self.root / "contract" / "approval.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "spec_sha256": spec_hash,
                    "approved_by": "human",
                    "approved_on": "2026-11-20",
                    "note": "fixture",
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_valid_contract_writes_and_checks(self) -> None:
        spec_compile.write(self.root)
        self.assertEqual(spec_compile.check(self.root), [])
        for name in ("manifest.json", "architecture_contract.json", "repo_layout.json"):
            data = json.loads((self.root / "spec_exec" / name).read_text(encoding="utf-8"))
            self.assertTrue(data["_generated"]["do_not_edit"])
            self.assertEqual(data["_generated"]["source"], "contract/spec.json")

    def test_duplicate_route_is_rejected(self) -> None:
        self.endpoints.append(dict(self.endpoints[0]))
        (self.root / "ARCHITECTURE.json").write_text(
            json.dumps({"api": {"endpoints": self.endpoints}}), encoding="utf-8"
        )
        _, errors = spec_compile.build_artifacts(self.root)
        self.assertTrue(any("duplicate route+method" in error for error in errors), errors)

    def test_missing_required_path_is_rejected(self) -> None:
        (self.root / "README.md").unlink()
        _, errors = spec_compile.build_artifacts(self.root)
        self.assertTrue(any("missing required paths" in error for error in errors), errors)

    def test_output_is_deterministic(self) -> None:
        first, errors = spec_compile.build_artifacts(self.root)
        second, errors_2 = spec_compile.build_artifacts(self.root)
        self.assertEqual(errors, [])
        self.assertEqual(errors_2, [])
        self.assertEqual(first, second)

    def test_non_stdlib_import_is_rejected(self) -> None:
        (self.root / "scripts" / "spec_compile.py").write_text("import requests\n", encoding="utf-8")
        _, errors = spec_compile.build_artifacts(self.root)
        self.assertTrue(any("non-stdlib import" in error for error in errors), errors)

    def _write_exception(self, *, expired: bool = False, target: str = "README.md") -> None:
        approved = "1999-01-01" if expired else "2026-01-01"
        expires = "2000-01-01" if expired else "2099-12-31"
        data = {
            "schema_version": 1,
            "exceptions": [
                {
                    "id": "EXC-001",
                    "rule": "repo.required_paths",
                    "target": target,
                    "reason": "temporary fixture for the contract test",
                    "approved_by": "human",
                    "approved_on": approved,
                    "expires_on": expires,
                }
            ],
        }
        (self.root / "contract" / "exceptions.json").write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8"
        )

    def test_registered_exception_suppresses_missing_path(self) -> None:
        (self.root / "README.md").unlink()
        self._write_exception()
        artifacts, errors = spec_compile.build_artifacts(self.root)
        self.assertFalse(any("missing required paths" in error for error in errors), errors)
        ledger = json.loads(artifacts["exceptions.json"])
        self.assertEqual(ledger["suppressed"][0]["exception"], "EXC-001")

    def test_expired_exception_is_rejected(self) -> None:
        (self.root / "README.md").unlink()
        self._write_exception(expired=True)
        _, errors = spec_compile.build_artifacts(self.root)
        self.assertTrue(any("expired exception" in error for error in errors), errors)

    def test_wildcard_exception_is_rejected(self) -> None:
        self._write_exception(target="*")
        _, errors = spec_compile.build_artifacts(self.root)
        self.assertTrue(any("wildcard target" in error for error in errors), errors)

    def test_unused_exception_is_rejected(self) -> None:
        self._write_exception(target="not-used")
        _, errors = spec_compile.build_artifacts(self.root)
        self.assertTrue(any("unused exceptions" in error for error in errors), errors)

    def test_spec_change_without_approval_is_rejected(self) -> None:
        path = self.root / "contract" / "spec.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["name"] = "changed without approval"
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        _, errors = spec_compile.build_artifacts(self.root)
        self.assertTrue(any("spec approval mismatch" in error for error in errors), errors)

    def test_tampered_generated_file_is_detected(self) -> None:
        spec_compile.write(self.root)
        target = self.root / "spec_exec" / "manifest.json"
        target.write_text(target.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        problems = spec_compile.check(self.root)
        self.assertTrue(any("stale" in problem for problem in problems), problems)


if __name__ == "__main__":
    unittest.main()
