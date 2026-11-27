"""The source and the published files: no shell, standard library only, the schema in step."""

import ast
import json
import os
import re
import sys
import unittest

from tests import clips
from tests.clips import PUBLIC_TEXT, ROOT, SCHEMA, SOURCES, read

sys.path.insert(0, os.path.join(clips.ROOT, "scripts"))
import riffsheet_lib  # noqa: E402
import riffsheet_lib.schema  # noqa: E402


class Source(unittest.TestCase):
    def test_no_shell(self):
        for node in (n for path in SOURCES for n in ast.walk(ast.parse(read(path)))):
            if isinstance(node, ast.Call):
                for kw in node.keywords:
                    self.assertNotEqual(kw.arg, "shell", "a subprocess call names shell=")
                f = node.func
                name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
                owner = getattr(getattr(f, "value", None), "id", "")
                self.assertFalse(
                    owner == "os" and name in ("system", "popen") or name.startswith("spawn"), ast.dump(node)[:120]
                )

    def test_only_standard_library(self):
        optional = {"numpy", "faster_whisper"}  # imported only inside `transcribe`
        for node in (n for path in SOURCES for n in ast.walk(ast.parse(read(path)))):
            if isinstance(node, ast.ImportFrom) and node.level:
                continue  # within the package
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module]
                for n in names:
                    top = n.split(".")[0]
                    if top in optional or top == "riffsheet_lib":
                        continue
                    self.assertTrue(top in sys.builtin_module_names or self._stdlib(top), n)

    @staticmethod
    def _stdlib(name):
        if hasattr(sys, "stdlib_module_names"):  # Python 3.10+
            return name in sys.stdlib_module_names
        import importlib.util

        spec = importlib.util.find_spec(name)
        return bool(spec) and "site-packages" not in (spec.origin or "")

    def test_schema_file_matches_tool(self):
        with open(SCHEMA, encoding="utf-8") as f:
            on_disk = json.load(f)
        self.assertEqual(
            on_disk,
            json.loads(json.dumps(riffsheet_lib.schema.ANALYSIS_SCHEMA)),
            'schema/riffsheet.schema.json is out of date; rewrite it with: python3 -c "import json, sys; '
            "sys.path.insert(0, 'scripts'); import riffsheet_lib.schema as s; print(json.dumps(s.ANALYSIS_SCHEMA, "
            'indent=2))" > schema/riffsheet.schema.json',
        )

    def test_schema_uses_only_checked_keywords(self):
        def walk(node):
            if isinstance(node, dict):
                for k, v in node.items():
                    if k not in ("properties", "$defs"):
                        self.assertIn(k, riffsheet_lib.schema.SCHEMA_KEYWORDS)
                        walk(v)
                    else:
                        for x in v.values():
                            walk(x)
            elif isinstance(node, list):
                for x in node:
                    walk(x)

        walk({k: v for k, v in riffsheet_lib.schema.ANALYSIS_SCHEMA.items()})

    def test_validator_catches_problems(self):
        good = {"format_version": riffsheet_lib.FORMAT_VERSION}
        errs = riffsheet_lib.schema.validate(good, riffsheet_lib.schema.ANALYSIS_SCHEMA)
        self.assertTrue(any("missing prose" in e for e in errs))
        self.assertTrue(riffsheet_lib.schema.validate({"format_version": 99}, riffsheet_lib.schema.ANALYSIS_SCHEMA))
        self.assertEqual(riffsheet_lib.schema.validate(True, {"type": "integer"}), ["$: expected integer, found bool"])

    def test_examples_fit_the_schema(self):
        examples = os.path.join(ROOT, "examples")
        found = []
        for name in sorted(os.listdir(examples)):
            p = os.path.join(examples, name, "riffsheet.json")
            if os.path.exists(p):
                with open(p, encoding="utf-8") as f:
                    doc = json.load(f)
                self.assertEqual(riffsheet_lib.schema.validate(doc, riffsheet_lib.schema.ANALYSIS_SCHEMA), [], p)
                self.assertEqual(doc["format_version"], riffsheet_lib.FORMAT_VERSION, p)
                found.append(name)
        self.assertTrue(found, "no example riffsheet.json")

    def test_nothing_machine_specific(self):
        home = "/" + "Users" + "/"
        tmp = "/" + "private" + "/"
        examples = [
            os.path.join(r, f)
            for r, _, fs in os.walk(os.path.join(ROOT, "examples"))
            for f in fs
            if f.endswith((".md", ".json"))
        ]
        for path in SOURCES + (SCHEMA,) + PUBLIC_TEXT + tuple(examples):
            text = read(path)
            self.assertNotIn(home, text, path)
            self.assertNotIn(tmp, text, path)

    def test_public_words(self):
        """What users do with a video is remaking it: the documents and messages never call it copying."""
        banned = re.compile(r"\b(cop(y|ies|ied|ying)|clon(e|es|ed|ing)|steal\w*|stole\w*|expir\w*)\b", re.I)
        examples = [
            os.path.join(r, f) for r, _, fs in os.walk(os.path.join(ROOT, "examples")) for f in fs if f == "README.md"
        ]
        for path in SOURCES + (SCHEMA,) + PUBLIC_TEXT + tuple(examples):
            text = read(path).replace("git clone", "")  # a repository is cloned; that is not about a video
            hits = [m.group(0) for m in banned.finditer(text)]
            if path == os.path.join(ROOT, "README.md"):
                # one question takes the reader's own search word and answers it by contrast
                questions = text[text.index("## Questions") :]
                self.assertEqual(hits, ["clone"], path)
                self.assertIn("Can I use it to clone a video?", questions)
                continue
            self.assertEqual(sorted(set(hits)), [], path)


if __name__ == "__main__":
    unittest.main()
