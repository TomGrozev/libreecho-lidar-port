#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Unit tests for tools/workspace.py. Run with python3 tools/check.py."""

from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import workspace  # noqa: E402

# The sandbox git shim asks a grant server for every commit; tests run real git
# with signing pinned off, so drop the shim from PATH for child processes.
GIT_ENV = dict(
    os.environ,
    PATH=":".join(part for part in os.environ.get("PATH", "").split(":")
                  if "git-bot-identity" not in part),
    GIT_CONFIG_COUNT="3",
    GIT_CONFIG_KEY_0="commit.gpgsign", GIT_CONFIG_VALUE_0="false",
    GIT_CONFIG_KEY_1="user.name", GIT_CONFIG_VALUE_1="Test",
    GIT_CONFIG_KEY_2="user.email", GIT_CONFIG_VALUE_2="test@example.invalid",
)


def git(path: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(path), *args], check=True, capture_output=True, text=True,
        env=GIT_ENV,
    )


def git_out(path: Path, *args: str) -> str:
    return git(path, *args).stdout.strip()


def source_repo(root: Path, name: str, branches: list[str]) -> Path:
    """Create a bare repo with `main` plus the named branches."""
    work = root / name
    work.mkdir(parents=True)
    git(work, "init", "-q", "-b", "main")
    git(work, "config", "user.name", "Test")
    git(work, "config", "user.email", "test@example.invalid")
    git(work, "config", "commit.gpgsign", "false")
    (work / "README").write_text(f"{name}\n", encoding="utf-8")
    git(work, "add", "README")
    git(work, "commit", "-q", "-m", "base")
    for branch in branches:
        git(work, "switch", "-q", "-c", branch)
        (work / f"{branch.replace('/', '-')}.txt").write_text(branch + "\n", encoding="utf-8")
        git(work, "add", ".")
        git(work, "commit", "-q", "-m", branch)
    git(work, "switch", "-q", "main")
    bare = root / f"{name}.git"
    subprocess.run(
        ["git", "clone", "-q", "--bare", str(work), str(bare)], check=True,
        env=GIT_ENV,
    )
    return bare


def write_manifest(ws: Path, repos: list[dict]) -> None:
    (ws / "integration.json").write_text(
        json.dumps({"schema_version": 1, "integration_branch": "integration", "repos": repos}),
        encoding="utf-8",
    )


def entry(name: str, fork: Path, upstream: Path, base: str, topics: list[str]) -> dict:
    return {
        "name": name,
        "fork_url": str(fork),
        "upstream_url": str(upstream),
        "path": f"work/forks/{name}",
        "integration_path": f"work/integration/{name}",
        "base": base,
        "topics": [{"branch": branch} for branch in topics],
    }


class InitTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.fork = source_repo(root / "src", "alpha", ["feature/one", "feature/two"])
        self.upstream = source_repo(root / "src", "alpha-upstream", [])
        self.ws = root / "ws"
        self.ws.mkdir()

    def init(self) -> int:
        return workspace.main(
            ["init", "--workspace", str(self.ws), "--no-integrate", "--no-inputs",
             "--no-image"]
        )

    def test_clone_names_remotes_from_the_base_prefix(self) -> None:
        write_manifest(self.ws, [
            entry("alpha", self.fork, self.upstream, "upstream/main",
                  ["feature/one", "feature/two"]),
            entry("beta", self.fork, self.upstream, "upstream/main", ["feature/one"]),
        ])
        self.assertEqual(self.init(), 0)
        alpha = self.ws / "work/forks/alpha"
        beta = self.ws / "work/forks/beta"
        self.assertEqual(git_out(alpha, "remote", "get-url", "fork"), str(self.fork))
        self.assertEqual(git_out(alpha, "remote", "get-url", "upstream"),
                         str(self.upstream))
        self.assertEqual(git_out(beta, "remote", "get-url", "fork"), str(self.fork))
        self.assertEqual(git_out(beta, "remote", "get-url", "upstream"), str(self.upstream))
        self.assertNotIn("origin", git_out(beta, "remote").split())

    def test_a_base_without_a_remote_prefix_is_a_fork_branch(self) -> None:
        write_manifest(self.ws, [
            entry("linux", self.fork, self.upstream, "feature/one",
                  ["feature/two"]),
        ])
        self.assertEqual(self.init(), 0)
        alpha = self.ws / "work/forks/linux"
        self.assertEqual(
            git_out(alpha, "rev-parse", "--abbrev-ref", "feature/one@{upstream}"),
            "fork/feature/one",
        )
        self.assertEqual(git_out(alpha, "rev-parse", "feature/one"),
                         git_out(alpha, "rev-parse", "fork/feature/one"))

    def test_creates_tracking_branches_for_every_topic(self) -> None:
        write_manifest(self.ws, [
            entry("alpha", self.fork, self.upstream, "upstream/main",
                  ["feature/one", "feature/two"]),
        ])
        self.assertEqual(self.init(), 0)
        alpha = self.ws / "work/forks/alpha"
        for branch in ("feature/one", "feature/two"):
            self.assertEqual(
                git_out(alpha, "rev-parse", "--abbrev-ref", f"{branch}@{{upstream}}"),
                f"fork/{branch}",
            )

    def test_rerun_is_idempotent_and_keeps_existing_configuration(self) -> None:
        write_manifest(self.ws, [
            entry("alpha", self.fork, self.upstream, "upstream/main", ["feature/one"]),
        ])
        self.assertEqual(self.init(), 0)
        alpha = self.ws / "work/forks/alpha"
        git(alpha, "config", "--local", "workspace.marker", "kept")
        before = git_out(alpha, "remote", "-v")
        self.assertEqual(self.init(), 0)
        self.assertEqual(git_out(alpha, "config", "--get", "workspace.marker"), "kept")
        self.assertEqual(git_out(alpha, "remote", "-v"), before)

    def test_existing_clone_only_gains_missing_remotes(self) -> None:
        path = self.ws / "work/forks/alpha"
        path.parent.mkdir(parents=True)
        # A pre-existing clone with the fork as `origin` must keep that URL: init
        # adds the missing names, it does not rewrite or re-point remotes.
        subprocess.run(["git", "clone", "-q", str(self.fork), str(path)], check=True,
                       env=GIT_ENV)
        write_manifest(self.ws, [
            entry("alpha", self.fork, self.upstream, "upstream/main", ["feature/one"]),
        ])
        self.assertEqual(self.init(), 0)
        self.assertEqual(git_out(path, "remote", "get-url", "origin"), str(self.fork))
        self.assertIn("fork", git_out(path, "remote").split())
        # A branch the clone lacks is created from the fork remote.
        self.assertEqual(git_out(path, "rev-parse", "feature/one"),
                         git_out(str(self.fork), "rev-parse", "feature/one"))

    def test_rerun_fast_forwards_a_topic_branch(self) -> None:
        write_manifest(self.ws, [
            entry("alpha", self.fork, self.upstream, "upstream/main", ["feature/one"]),
        ])
        self.assertEqual(self.init(), 0)
        seed = Path(self.tmp.name) / "src/alpha"
        git(seed, "switch", "-q", "feature/one")
        (seed / "more.txt").write_text("more\n", encoding="utf-8")
        git(seed, "add", ".")
        git(seed, "commit", "-q", "-m", "more")
        git(seed, "push", "-q", str(self.fork), "feature/one")
        advanced = git_out(seed, "rev-parse", "HEAD")
        self.assertEqual(self.init(), 0)
        self.assertEqual(git_out(self.ws / "work/forks/alpha", "rev-parse", "feature/one"),
                         advanced)

    def test_sync_forks_resets_a_rewritten_unchecked_branch(self) -> None:
        write_manifest(self.ws, [
            entry("alpha", self.fork, self.upstream, "upstream/main", ["feature/one"]),
        ])
        self.assertEqual(self.init(), 0)
        alpha = self.ws / "work/forks/alpha"
        base = git_out(alpha, "rev-parse", "feature/one")
        tree = git_out(alpha, "rev-parse", "feature/one^{tree}")
        local = git_out(alpha, "commit-tree", tree, "-p", base, "-m", "local only")
        git(alpha, "update-ref", "refs/heads/feature/one", local)
        seed = Path(self.tmp.name) / "src/alpha"
        git(seed, "switch", "-q", "-C", "feature/one", "main")
        (seed / "rewritten.txt").write_text("rewritten\n", encoding="utf-8")
        git(seed, "add", ".")
        git(seed, "commit", "-q", "-m", "rewritten")
        git(seed, "push", "-q", "--force", str(self.fork), "feature/one")
        rewritten = git_out(seed, "rev-parse", "HEAD")
        # Without --sync-forks a diverged branch is kept, not discarded.
        self.assertEqual(self.init(), 0)
        self.assertEqual(git_out(alpha, "rev-parse", "feature/one"), local)
        self.assertEqual(workspace.main(
            ["init", "--workspace", str(self.ws), "--no-integrate", "--no-inputs",
             "--no-image", "--sync-forks"]), 0)
        self.assertEqual(git_out(alpha, "rev-parse", "feature/one"), rewritten)


class HookInstallTest(unittest.TestCase):
    def test_repo_is_pointed_at_the_versioned_hooks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            git(repo, "init", "-q")
            with contextlib.redirect_stdout(io.StringIO()):
                workspace.install_hooks(repo)
            self.assertEqual(git_out(repo, "config", "--local", "core.hooksPath"), ".githooks")

    def test_non_repo_is_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with contextlib.redirect_stdout(io.StringIO()):
                workspace.install_hooks(Path(tmp))


class DoctorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ws = Path(self.tmp.name)
        write_manifest(self.ws, [])

    def test_reports_missing_owner_file_work_tree_and_inputs(self) -> None:
        problems = "\n".join(workspace.collect_problems(self.ws))
        self.assertIn("private/local.json", problems)
        self.assertIn("work/integration/integration.lock.json", problems)
        self.assertIn("public-deps/SHA256SUMS", problems)

    def test_reports_missing_otbr_source_deps_and_kernel_uapi(self) -> None:
        problems = "\n".join(workspace.collect_problems(self.ws))
        self.assertIn(f"{workspace.OTBR_SOURCE_REL}: missing (OTBR source)", problems)
        self.assertIn(f"{workspace.OTBR_DEPS_REL}: missing (OTBR deps)", problems)
        self.assertIn(
            f"{workspace.KERNEL_UAPI_REL}/include/linux: missing "
            "(Linux UAPI headers)", problems)

    def test_reports_a_local_path_that_does_not_exist(self) -> None:
        keys = self.ws / "private/keys/ota-lab"
        keys.mkdir(parents=True)
        (keys / "ed25519-seed.hex").write_text("00" * 32 + "\n", encoding="ascii")
        (keys / "ed25519-public.hex").write_text("11" * 32 + "\n", encoding="ascii")
        (self.ws / "private/local.json").write_text(json.dumps({
            "ota_signing_key": "private/keys/ota-lab/ed25519-seed.hex",
            "ota_public_key": "private/keys/ota-lab/ed25519-public.hex",
            "stock_boot": "private/dumps/backup/boot_a.bin",
            "device_host": "",
        }), encoding="utf-8")
        problems = workspace.collect_problems(self.ws)
        self.assertTrue(any("stock_boot" in problem for problem in problems))
        self.assertFalse(any("ota_signing_key" in problem for problem in problems))
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(workspace.main(["doctor", "--workspace", str(self.ws)]), 1)


if __name__ == "__main__":
    unittest.main()
