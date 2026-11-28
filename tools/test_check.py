#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Unit tests for tools/check.py. Run with python3 tools/check.py."""

from __future__ import annotations

import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

TOOLS = Path(__file__).resolve().parent


def load_check():
    spec = importlib.util.spec_from_file_location('check', TOOLS / 'check.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LinkCheckTest(unittest.TestCase):
    def setUp(self) -> None:
        self.check = load_check()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.docs = self.root / 'docs'
        self.docs.mkdir()
        (self.docs / 'present.md').write_text('# present\n', encoding='utf-8')

    def problems(self, text: str) -> list[tuple[int, str]]:
        (self.docs / 'page.md').write_text(text, encoding='utf-8')
        return [(line, target) for _, line, target
                in self.check.relative_link_problems(self.root)]

    def test_resolving_relative_link_passes(self) -> None:
        self.assertEqual(self.problems('[ok](present.md#section)\n'), [])

    def test_external_anchor_absolute_and_image_links_are_skipped(self) -> None:
        text = ('[web](https://example.invalid/x) [mail](mailto:a@b)\n'
                '[top](#here) [abs](/etc/passwd) ![image](missing.png)\n')
        self.assertEqual(self.problems(text), [])

    def test_missing_relative_link_reports_its_line(self) -> None:
        text = 'first\n\n[gone](missing.md)\n'
        self.assertEqual(self.problems(text), [(3, 'missing.md')])

    def test_fenced_code_blocks_are_ignored(self) -> None:
        text = '```\n[not a link](missing.md)\n```\n[real](missing.md)\n'
        self.assertEqual(self.problems(text), [(4, 'missing.md')])

    def test_percent_encoded_target_is_decoded(self) -> None:
        (self.docs / 'with space.md').write_text('x\n', encoding='utf-8')
        self.assertEqual(self.problems('[space](with%20space.md)\n'), [])


class ManifestDocCheckTest(unittest.TestCase):
    def setUp(self) -> None:
        self.check = load_check()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'docs/agents').mkdir(parents=True)
        (self.root / 'integration.json').write_text(json.dumps({
            'schema_version': 1,
            'repos': [{'name': 'alpha'}, {'name': 'beta'}],
        }), encoding='utf-8')

    def write_doc(self, text: str) -> None:
        (self.root / 'docs/agents/integration-and-builds.md').write_text(
            text, encoding='utf-8')

    def test_named_forks_pass(self) -> None:
        self.write_doc('| alpha | `work/forks/alpha` |\n| beta | `work/forks/beta` |\n')
        with redirect_stdout(io.StringIO()):
            self.assertEqual(self.check.check_manifest_docs(self.root), 0)

    def test_unnamed_fork_fails(self) -> None:
        self.write_doc('| alpha | `work/forks/alpha` |\n')
        with redirect_stdout(io.StringIO()):
            self.assertEqual(self.check.check_manifest_docs(self.root), 1)


class JsonGlobTest(unittest.TestCase):
    def test_json_outside_work_and_private_is_parsed(self) -> None:
        check = load_check()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'good.json').write_text('{"a": 1}\n', encoding='utf-8')
            for skipped in ('work', 'private'):
                (root / skipped).mkdir()
                (root / skipped / 'bad.json').write_text('{', encoding='utf-8')
            with redirect_stdout(io.StringIO()):
                self.assertEqual(check.check_json(root), 0)


if __name__ == '__main__':
    unittest.main()
