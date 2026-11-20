from __future__ import annotations

import unittest
from pathlib import Path

from scripts.code_sandbox import docker_command


class CodeSandboxTest(unittest.TestCase):
    def test_docker_hardening_flags(self):
        command, name = docker_command(Path("."), "scipal-app:latest", "test_x", 30)
        text = " ".join(command)
        self.assertIn("--network none", text)
        self.assertIn("--read-only", text)
        self.assertIn("--cap-drop ALL", text)
        self.assertIn("--security-opt no-new-privileges", text)
        self.assertIn("--user 65534:65534", text)
        self.assertIn("--memory 512m", text)
        self.assertIn("--pids-limit 128", text)
        self.assertIn("test_x", text)
        self.assertTrue(name.startswith("scipal-sandbox-"))


if __name__ == "__main__":
    unittest.main()
