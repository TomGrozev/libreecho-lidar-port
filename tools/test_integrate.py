#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Unit tests for tools/integrate.py. Run with python3 tools/check.py."""

from __future__ import annotations

import fcntl
import importlib.util
import os
import subprocess
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

TOOLS = Path(__file__).resolve().parent


def load_integrate():
    spec = importlib.util.spec_from_file_location('integrate', TOOLS / 'integrate.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ['git', '-C', str(repo), *args], check=True, capture_output=True, text=True
    )


def git_out(repo: Path, *args: str) -> str:
    return git(repo, *args).stdout.strip()


def commit(repo: Path, name: str, body: str, message: str) -> str:
    (repo / name).write_text(body, encoding='utf-8')
    git(repo, 'add', name)
    git(repo, 'commit', '-q', '-m', message)
    return git_out(repo, 'rev-parse', 'HEAD')


class AuditTest(unittest.TestCase):
    def setUp(self) -> None:
        self.integrate = load_integrate()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ws = Path(self.tmp.name)
        self.repo = self.ws / 'work/forks/alpha'
        self.repo.mkdir(parents=True)
        git(self.repo, 'init', '-q', '-b', 'main')
        git(self.repo, 'config', 'user.name', 'Test')
        git(self.repo, 'config', 'user.email', 'test@example.invalid')
        git(self.repo, 'config', 'commit.gpgsign', 'false')
        self.base = commit(self.repo, 'README', 'base\n', 'base')

    def entry(self, *branches: str) -> dict:
        return {
            'name': 'alpha',
            'path': 'work/forks/alpha',
            'base': 'main',
            'topics': [{'branch': branch} for branch in branches],
        }

    def problems(self, *branches: str) -> list[str]:
        return self.integrate.audit_repo(self.ws, self.entry(*branches))

    def test_commit_cherry_picked_into_base_is_reported(self) -> None:
        git(self.repo, 'switch', '-q', '-c', 'feature/a')
        commit(self.repo, 'a.txt', 'change\n', 'topic change')
        git(self.repo, 'switch', '-q', 'main')
        commit(self.repo, 'b.txt', 'advance\n', 'advance base')
        git(self.repo, 'cherry-pick', '--no-commit', 'feature/a')
        git(self.repo, 'commit', '-q', '-m', 'cherry-picked topic change')
        problems = self.problems('feature/a')
        self.assertTrue(any('already in main' in p for p in problems), problems)

    def test_same_patch_on_two_topics_is_reported(self) -> None:
        git(self.repo, 'switch', '-q', '-c', 'feature/a')
        commit(self.repo, 'a.txt', 'change\n', 'topic change')
        git(self.repo, 'switch', '-q', '-c', 'feature/b', 'main')
        git(self.repo, 'cherry-pick', '--no-commit', 'feature/a')
        git(self.repo, 'commit', '-q', '-m', 'same change, other branch')
        problems = self.problems('feature/a', 'feature/b')
        self.assertTrue(any('duplicate patch-id' in p for p in problems), problems)

    def test_stacked_topic_is_not_a_duplicate(self) -> None:
        git(self.repo, 'switch', '-q', '-c', 'feature/parent')
        commit(self.repo, 'parent.txt', 'one\n', 'parent change')
        git(self.repo, 'switch', '-q', '-c', 'feature/child')
        commit(self.repo, 'child.txt', 'two\n', 'child change')
        self.assertEqual(self.problems('feature/parent', 'feature/child'), [])

    def test_topic_cut_before_the_base_moved_is_reported(self) -> None:
        git(self.repo, 'branch', 'feature/old', self.base)
        git(self.repo, 'switch', '-q', 'feature/old')
        commit(self.repo, 'old.txt', 'old\n', 'old change')
        git(self.repo, 'switch', '-q', 'main')
        commit(self.repo, 'new.txt', 'new\n', 'advance base')
        problems = self.problems('feature/old')
        self.assertTrue(any('not based on main' in p for p in problems), problems)

    def test_fork_branch_missing_from_manifest_is_reported(self) -> None:
        git(self.repo, 'update-ref', 'refs/remotes/fork/stray', self.base)
        problems = self.problems('feature/absent')
        self.assertTrue(any('fork branches not in the manifest' in p for p in problems),
                        problems)
        self.assertTrue(any('stray' in p for p in problems), problems)

    def test_base_and_default_fork_branches_are_skipped(self) -> None:
        git(self.repo, 'switch', '-q', '-c', 'feature/a')
        commit(self.repo, 'a.txt', 'change\n', 'topic change')
        git(self.repo, 'update-ref', 'refs/remotes/fork/main', self.base)
        git(self.repo, 'update-ref', 'refs/remotes/fork/develop', self.base)
        git(self.repo, 'symbolic-ref', 'refs/remotes/fork/HEAD',
            'refs/remotes/fork/develop')
        git(self.repo, 'update-ref', 'refs/remotes/fork/leftover', self.base)
        problems = self.problems('feature/a')
        self.assertEqual(
            [p for p in problems if 'fork branches' in p],
            ['fork branches not in the manifest: 1: leftover'],
        )

    def test_clean_repo_has_no_problems(self) -> None:
        git(self.repo, 'switch', '-q', '-c', 'feature/a')
        commit(self.repo, 'a.txt', 'change\n', 'topic change')
        self.assertEqual(self.problems('feature/a'), [])


class ManifestDirtyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.integrate = load_integrate()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ws = Path(self.tmp.name)
        git(self.ws, 'init', '-q')
        git(self.ws, 'config', 'user.name', 'Test')
        git(self.ws, 'config', 'user.email', 'test@example.invalid')
        git(self.ws, 'config', 'commit.gpgsign', 'false')
        (self.ws / 'integration.json').write_text('{"repos": []}\n', encoding='utf-8')
        git(self.ws, 'add', 'integration.json')
        git(self.ws, 'commit', '-q', '-m', 'manifest')

    def test_clean_manifest_is_not_dirty(self) -> None:
        self.assertFalse(self.integrate.manifest_dirty(self.ws))

    def test_uncommitted_manifest_change_is_dirty(self) -> None:
        (self.ws / 'integration.json').write_text('{"repos": []}\n\n', encoding='utf-8')
        self.assertTrue(self.integrate.manifest_dirty(self.ws))

    def test_rebuild_refuses_a_dirty_manifest_without_the_flag(self) -> None:
        (self.ws / 'integration.json').write_text('{"repos": []}\n\n', encoding='utf-8')
        with self.assertRaisesRegex(self.integrate.Fail, 'allow-dirty-manifest'):
            self.integrate.cmd_rebuild(self.ws, {'repos': []}, [], False)

    def test_the_flag_allows_a_dirty_manifest(self) -> None:
        (self.ws / 'integration.json').write_text('{"repos": []}\n\n', encoding='utf-8')
        with mock.patch.object(self.integrate, 'select_repos', return_value=[]), \
                mock.patch.object(self.integrate, 'write_lock'):
            self.assertEqual(
                self.integrate.cmd_rebuild(self.ws, {'repos': []}, [], False,
                                           allow_dirty_manifest=True),
                0,
            )


class BuildGuardTest(unittest.TestCase):
    def setUp(self) -> None:
        self.integrate = load_integrate()

    def workspace(self, tmp: str) -> Path:
        ws = Path(tmp)
        (ws / 'work/builds').mkdir(parents=True)
        return ws

    @contextmanager
    def held_lock(self, ws: Path):
        # flock conflicts between separate open file descriptions, so a lock
        # held here blocks the probe even inside the same process.
        fd = os.open(ws / 'work/builds/.build.lock', os.O_RDWR | os.O_CREAT)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            os.write(fd, f'{os.getpid()}\n'.encode())
            yield
        finally:
            os.close(fd)

    def test_no_lock_means_no_build(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(self.integrate.build_in_progress(self.workspace(tmp)))

    def test_held_lock_stops_a_rebuild(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = self.workspace(tmp)
            with self.held_lock(ws):
                self.assertEqual(self.integrate.build_in_progress(ws), os.getpid())

    def test_the_builds_own_rebuild_may_pass_the_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = self.workspace(tmp)
            manifest = {'repos': []}
            with self.held_lock(ws), \
                    mock.patch.object(self.integrate, 'select_repos', return_value=[]), \
                    mock.patch.object(self.integrate, 'write_lock'):
                rc = self.integrate.cmd_rebuild(ws, manifest, [], False,
                                                allow_during_build=True)
                self.assertEqual(rc, 0)
                with self.assertRaises(self.integrate.Fail):
                    self.integrate.cmd_rebuild(ws, manifest, [], False)

    def test_unheld_lock_file_is_idle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = self.workspace(tmp)
            (ws / 'work/builds/.build.lock').write_text('4194305\n')
            self.assertIsNone(self.integrate.build_in_progress(ws))


if __name__ == '__main__':
    unittest.main()
