import json
import unittest

from code_rag.implement import build_prompt, build_proposal, parse_response, validate_files


CARDS = [
    {
        "id": "E1",
        "symbol_name": "normalize",
        "path": "src/a.py",
        "start_line": 1,
        "end_line": 2,
        "snippet": "def normalize(x):\n    return x",
        "package_version": "1.0",
    }
]


class CodeImplementTest(unittest.TestCase):
    def test_parse_json_fence(self):
        data = parse_response('```json\n{"summary":"ok","files":[],"citations":[]}\n```')
        self.assertEqual(data["summary"], "ok")

    def test_prompt_contains_task_and_evidence(self):
        system, user = build_prompt("add normalize", ["src/a.py"], CARDS)
        self.assertIn("JSON", system)
        self.assertIn("add normalize", user)
        self.assertIn("[E1]", user)

    def test_validate_python_syntax(self):
        errors = validate_files([{"path": "src/a.py", "content": "def f(:\n"}], ["src/a.py"])
        self.assertTrue(any("syntax" in error for error in errors))

    def test_validate_rejects_path_escape(self):
        errors = validate_files([{"path": "../secret.py", "content": "x=1\n"}])
        self.assertTrue(any("unsafe" in error for error in errors))

    def test_proposal_is_not_applied(self):
        proposal = build_proposal(
            task="add normalize",
            data={
                "summary": "adds function",
                "files": [{"path": "src/a.py", "content": "def normalize(x):\n    return x\n"}],
                "citations": ["E1"],
            },
            items=CARDS,
            target_paths=["src/a.py"],
        )
        self.assertEqual(proposal["status"], "proposed")
        self.assertIn("not written", proposal["note"])
        self.assertTrue(proposal["validation"]["ok"])


if __name__ == "__main__":
    unittest.main()
