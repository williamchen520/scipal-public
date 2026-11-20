"""C2: JavaScript/TypeScript parser tests."""

from __future__ import annotations

import unittest

from code_rag.parsers import parse_javascript, parse_typescript


class JsTsParserTests(unittest.TestCase):
    def test_javascript_function_class_method(self) -> None:
        units, edges = parse_javascript(
            'import x from "./x";\nexport function hello(a) { return a; }\n'
            "class Box { run() { return 1; } }\n",
            "a.js",
        )
        names = {unit.symbol_name: unit.unit_type for unit in units}
        self.assertEqual(names["hello"], "function")
        self.assertEqual(names["Box"], "class")
        self.assertEqual(names["run"], "method")
        self.assertTrue(edges)

    def test_typescript_interface_and_arrow(self) -> None:
        units, _ = parse_typescript(
            "interface A { x: number }\nexport const f = (n: number) => n + 1;\n",
            "a.ts",
        )
        names = {unit.symbol_name: unit.unit_type for unit in units}
        self.assertEqual(names["A"], "type")
        self.assertEqual(names["f"], "function")


if __name__ == "__main__":
    unittest.main()
