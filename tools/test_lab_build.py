#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Unit tests for tools/lab-build.py. Run with python3 tools/check.py."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
HEADS = {
    'LibreEcho': 'a' * 40,
    'LibreEcho-Platform': 'b' * 40,
    'LibreEcho-Linux': 'c' * 40,
    'LibreEcho-UI': 'd' * 40,
    'LibreEcho-Installer-Web': 'e' * 40,
}

# The sandbox git shim asks a grant server for every commit; tests run real git
# with signing pinned off, so drop the shim from PATH for child processes.
GIT_ENV = dict(
    os.environ,
    PATH=':'.join(part for part in os.environ.get('PATH', '').split(':')
                  if 'git-bot-identity' not in part),
    GIT_CONFIG_COUNT='3',
    GIT_CONFIG_KEY_0='commit.gpgsign', GIT_CONFIG_VALUE_0='false',
    GIT_CONFIG_KEY_1='user.name', GIT_CONFIG_VALUE_1='Test',
    GIT_CONFIG_KEY_2='user.email', GIT_CONFIG_VALUE_2='test@example.invalid',
)


def load_lab_build():
    spec = importlib.util.spec_from_file_location('lab_build', TOOLS / 'lab-build.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf-8')


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class FakeSource:
    def __init__(self, path: Path):
        self.path = path
        self.role = 'test'
        self.name = path.name
        self.entry = {'integration_path': str(path)}
        self.head = 'f' * 40
        self.dirty: list[str] = []

    def record(self) -> dict:
        return {'role': self.role, 'integration_path': str(self.path),
                'head': self.head, 'dirty': self.dirty}


class FakeLog:
    def __init__(self) -> None:
        self.runs: list[tuple[list[str], Path | None, dict | None]] = []

    def write(self, _text: str) -> None:
        pass

    def line(self, _kind: str, _text: str) -> None:
        pass

    def phase(self, _title: str) -> None:
        pass

    def run(self, cmd, cwd=None, env=None, step_log=None) -> int:
        self.runs.append(([str(item) for item in cmd], cwd, env))
        if step_log:
            Path(step_log).write_text(
                'building\nrun=' + str(env['_FAKE_RUN']) + '\n', encoding='utf-8')
        return 0

    def close(self) -> None:
        pass


class ReleaseTagTest(unittest.TestCase):
    def setUp(self) -> None:
        self.lab_build = load_lab_build()

    def lock(self) -> dict:
        return {'repos': {name: {'head': head} for name, head in HEADS.items()}}

    def test_tag_shape_and_product_commit(self) -> None:
        tag = self.lab_build.release_tag(self.lock(), '0.2.46')
        self.assertRegex(tag, r'^radar-puffin-build-[0-9a-f]{7}-'
                              r'[0-9a-f]{16}-[0-9a-f]{16}$')
        self.assertTrue(tag.startswith('radar-puffin-build-' + 'a' * 7))

    def test_tag_changes_with_version_and_source_set(self) -> None:
        first = self.lab_build.release_tag(self.lock(), '0.2.46')
        self.assertNotEqual(first, self.lab_build.release_tag(self.lock(), '0.2.47'))
        changed = self.lock()
        changed['repos']['LibreEcho-UI']['head'] = '9' * 40
        self.assertNotEqual(first, self.lab_build.release_tag(changed, '0.2.46'))

    def test_tag_requires_every_build_source(self) -> None:
        lock = self.lock()
        del lock['repos']['LibreEcho-Linux']
        with self.assertRaisesRegex(self.lab_build.Fail, 'LibreEcho-Linux'):
            self.lab_build.release_tag(lock, '0.2.46')


class NextVersionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.lab_build = load_lab_build()
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.builds = self.root / 'builds'
        self.builds.mkdir()

    def test_highest_build_plus_one_patch(self) -> None:
        for name in ('v0.2.9', 'v0.2.45', 'cache', 'v0.1.99'):
            (self.builds / name).mkdir()
        self.assertEqual(self.lab_build.next_version(self.builds), '0.2.46')

    def test_empty_builds_dir_needs_an_explicit_version(self) -> None:
        with self.assertRaisesRegex(self.lab_build.Fail, '--version'):
            self.lab_build.next_version(self.builds)

    def test_other_directories_are_not_scanned(self) -> None:
        (self.root / 'elsewhere/v9.9.9').mkdir(parents=True)
        with self.assertRaises(self.lab_build.Fail):
            self.lab_build.next_version(self.builds)


class SourceAttemptTest(unittest.TestCase):
    """A failed attempt is skipped; a successful build of the same sources reused."""

    SID = 'a' * 16

    def setUp(self) -> None:
        self.lab_build = load_lab_build()
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.builds = Path(self.temporary.name) / 'builds'
        self.builds.mkdir()

    def make_attempt(self, name: str, intact: bool, sid: str | None = None) -> Path:
        attempt = self.builds / name
        attempt.mkdir()
        output = attempt / 'run/boot.img'
        output.parent.mkdir()
        output.write_bytes(b'boot')
        digest = hashlib.sha256(output.read_bytes()).hexdigest()
        if not intact:
            digest = '0' * 64
        write_json(attempt / 'provenance.json', {
            'source_id': sid or self.SID,
            'outputs': {'run/boot.img': digest},
        })
        (attempt / 'SHA256SUMS').write_text('', encoding='utf-8')
        return attempt

    def test_failed_attempt_is_skipped(self) -> None:
        failed = self.make_attempt(f'20260101-000000-v0.2.99-{self.SID}', False)
        good = self.make_attempt(f'20260102-000000-v0.2.99-{self.SID}', True)
        self.assertEqual(self.lab_build.source_attempt(self.builds, self.SID), good)
        self.assertNotEqual(failed, good)

    def test_nothing_is_reused_without_a_matching_source_id(self) -> None:
        self.make_attempt('20260102-000000-v0.2.99-' + 'b' * 16, True, 'b' * 16)
        self.assertIsNone(self.lab_build.source_attempt(self.builds, self.SID))


class LocalConfigTest(unittest.TestCase):
    def setUp(self) -> None:
        self.lab_build = load_lab_build()
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.local = self.root / 'private/local.json'
        self.patch = mock.patch.object(self.lab_build, 'ROOT', self.root)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_missing_file_points_at_keygen(self) -> None:
        with self.assertRaisesRegex(self.lab_build.Fail, 'workspace.py keygen'):
            self.lab_build.load_local()

    def test_missing_owner_entry_points_at_doctor(self) -> None:
        write_json(self.local, {'ota_signing_key': 'k',
                                'ota_public_key': 'p', 'stock_boot': ''})
        with self.assertRaisesRegex(self.lab_build.Fail, 'stock_boot.*doctor'):
            self.lab_build.load_local()

    def test_complete_file_resolves_workspace_relative_paths(self) -> None:
        (self.root / 'private').mkdir()
        for name in ('seed.hex', 'public.hex', 'boot_a.bin'):
            (self.root / 'private' / name).write_text(name, encoding='utf-8')
        write_json(self.local, {
            'ota_signing_key': 'private/seed.hex',
            'ota_public_key': 'private/public.hex',
            'stock_boot': 'private/boot_a.bin',
            'device_host': 'lidar.local:5555',
        })
        local = self.lab_build.load_local()
        self.assertEqual(local['stock_boot'], self.root / 'private/boot_a.bin')
        self.assertEqual(local['device_host'], 'lidar.local:5555')

    def test_deploy_reads_device_host_without_owner_files(self) -> None:
        write_json(self.local, {'device_host': 'lidar.local:5555'})
        local = self.lab_build.load_local(require_owner_inputs=False)
        self.assertEqual(local['device_host'], 'lidar.local:5555')


class ProductEnvTest(unittest.TestCase):
    def setUp(self) -> None:
        self.lab_build = load_lab_build()
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.stock = root / 'boot_a.bin'
        self.signing = root / 'seed.hex'
        self.public = root / 'public.hex'
        for path, data in ((self.stock, b'stock'),
                           (self.signing, b'seed'),
                           (self.public, b'public')):
            path.write_bytes(data)
        self.local = {'stock_boot': self.stock, 'ota_signing_key': self.signing,
                      'ota_public_key': self.public, 'device_host': ''}
        self.sources = {role: FakeSource(self.lab_build.ROOT / 'work/integration' / name)
                        for role, name in (('platform', 'LibreEcho-Platform'),
                                           ('linux', 'LibreEcho-Linux'),
                                           ('ui', 'LibreEcho-UI'),
                                           ('libreecho', 'LibreEcho'))}

    def test_local_and_work_paths_map_to_the_product_contract(self) -> None:
        env = self.lab_build.product_env(self.local, '0.2.46',
                                         'radar-puffin-build-test', self.sources,
                                         Path('/tmp/venv/bin/python'), None)
        self.assertEqual(env['LIBREECHO_LIDAR_STOCK_BOOT'], str(self.stock))
        self.assertEqual(env['LIBREECHO_OTA_SIGNING_KEY'], str(self.signing))
        self.assertEqual(env['LIBREECHO_OTA_PUBLIC_KEY'], str(self.public))
        self.assertEqual(env['LIBREECHO_OTA_EXPECTED_PUBLIC_KEY_SHA256'],
                         sha256(self.public))
        self.assertEqual(env['LIBREECHO_BUILD_ROOT'],
                         str(self.lab_build.ROOT / 'work/product-build'))
        self.assertEqual(env['LIBREECHO_KERNEL_OUT'],
                         str(self.lab_build.ROOT / 'work/product-build/kernel'))
        self.assertEqual(env['LIBREECHO_INPUTS_ROOT'],
                         str(self.lab_build.ROOT / 'work/inputs/public-deps'))
        self.assertEqual(env['LIBREECHO_TOOLING_SRC'], str(self.sources['platform'].path))
        self.assertEqual(env['LIBREECHO_KERNEL_SRC'], str(self.sources['linux'].path))
        self.assertEqual(env['LIBREECHO_UI_SRC'], str(self.sources['ui'].path))
        self.assertEqual(env['LIBREECHO_PRODUCT_SRC'],
                         str(self.sources['libreecho'].path))
        self.assertEqual(env['LIBREECHO_OTA_RELEASE'], '0.2.46')
        self.assertEqual(env['LIBREECHO_TARGET_RELEASE_TAG'],
                         'radar-puffin-build-test')
        self.assertEqual(env['LIBREECHO_OTA_FORMAT'], 'v3')
        self.assertNotIn('PYTHONPATH', env)

    def test_the_gate_wheel_closure_leads_pythonpath(self) -> None:
        gate = self.lab_build.ROOT / 'work/product-build/ota-gate-python'
        with mock.patch.dict('os.environ', {'PYTHONPATH': '/keep/me'}, clear=True):
            env = self.lab_build.product_env(self.local, '0.2.46',
                                             'radar-puffin-build-test', self.sources,
                                             Path('/tmp/venv/bin/python'), gate)
        self.assertEqual(env['PYTHONPATH'], f'{gate}:/keep/me')


class ContainerTest(unittest.TestCase):
    """The build re-execs inside the pinned image unless told otherwise."""

    def setUp(self) -> None:
        self.lab_build = load_lab_build()
        self.root = Path('/workspace/libreecho')

    def test_podman_argv_runs_the_build_inside_the_workspace(self) -> None:
        with mock.patch.dict('os.environ', {}, clear=True):
            argv = self.lab_build.container_argv(
                ('podman', '/usr/bin/podman'), self.root, 'libreecho-build',
                1000, 1000, ['--version', '0.2.99'])
        self.assertEqual(argv[:3], ['/usr/bin/podman', 'run', '--rm'])
        self.assertIn('--userns=keep-id', argv)
        self.assertIn('--network=host', argv)
        self.assertIn(f'{self.root}:{self.root}:Z', argv)
        self.assertIn('LIBREECHO_CONTAINER=1', argv)
        self.assertIn('HOME=/home/builder', argv)
        self.assertEqual(argv[argv.index('-w') + 1], str(self.root))
        self.assertEqual(argv[-4:], ['python3',
                                     str(self.root / 'tools/lab-build.py'),
                                     '--version', '0.2.99'])

    def test_docker_argv_maps_the_host_user_instead_of_userns(self) -> None:
        with mock.patch.dict('os.environ', {}, clear=True):
            argv = self.lab_build.container_argv(
                ('docker', '/usr/bin/docker'), self.root, 'libreecho-build',
                1000, 1000, [])
        self.assertEqual(argv[argv.index('--user') + 1], '1000:1000')
        self.assertNotIn('--userns=keep-id', argv)
        self.assertIn('HOME=/tmp', argv)
        self.assertEqual(argv[-2:], ['python3',
                                     str(self.root / 'tools/lab-build.py')])

    def test_image_name_from_environment(self) -> None:
        with mock.patch.dict('os.environ',
                             {'LIBREECHO_BUILD_IMAGE': 'lab-image'}, clear=True):
            self.assertEqual(self.lab_build.container_image(), 'lab-image')

    def test_image_pin_uses_the_digest_or_the_local_tag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_json(root / 'tools/lab-build.json', {
                'schema_version': 1,
                'build_image': {'name': 'ghcr.io/x/build', 'digest': 'sha256:abc'},
            })
            with mock.patch.object(self.lab_build, 'ROOT', root), \
                    mock.patch.dict('os.environ', {}, clear=True):
                self.assertEqual(self.lab_build.container_image(),
                                 'ghcr.io/x/build@sha256:abc')
            write_json(root / 'tools/lab-build.json', {
                'schema_version': 1,
                'build_image': {'name': 'ghcr.io/x/build', 'digest': None},
            })
            with mock.patch.object(self.lab_build, 'ROOT', root), \
                    mock.patch.dict('os.environ', {}, clear=True):
                self.assertEqual(self.lab_build.container_image(),
                                 self.lab_build.LOCAL_IMAGE)

    def test_host_libreecho_variables_are_forwarded_by_name(self) -> None:
        with mock.patch.dict('os.environ',
                             {'LIBREECHO_BUILD_IMAGE': 'lab-image',
                              'LIBREECHO_EXTRA': 'value'}, clear=True):
            argv = self.lab_build.container_argv(
                ('podman', '/usr/bin/podman'), self.root, 'lab-image', 1000, 1000, [])
        names = [argv[index + 1] for index, item in enumerate(argv) if item == '-e']
        self.assertIn('LIBREECHO_EXTRA', names)
        self.assertIn('LIBREECHO_BUILD_IMAGE', names)
        self.assertEqual(names.count('LIBREECHO_CONTAINER=1'), 1)

    def test_build_lock_refuses_a_concurrent_build(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            lock = Path(tmp) / '.build.lock'
            with mock.patch.object(self.lab_build, 'BUILD_LOCK', lock), \
                    mock.patch.dict('os.environ', {}, clear=True):
                handle = self.lab_build.open_build_lock()
                try:
                    self.assertEqual(lock.read_text().strip(), str(os.getpid()))
                    with self.assertRaises(self.lab_build.Fail) as caught:
                        self.lab_build.open_build_lock()
                    self.assertIn('another lab build', str(caught.exception))
                finally:
                    self.lab_build.close_build_lock(handle)

    def test_build_lock_is_released_by_closing_the_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            lock = Path(tmp) / '.build.lock'
            with mock.patch.object(self.lab_build, 'BUILD_LOCK', lock), \
                    mock.patch.dict('os.environ', {}, clear=True):
                handle = self.lab_build.open_build_lock()
                self.lab_build.close_build_lock(handle)
                # A dead owner's lock is gone with its file handle, so the
                # next build takes it over without waiting.
                again = self.lab_build.open_build_lock()
                self.lab_build.close_build_lock(again)

    def test_mbedtls_venv_is_staged_under_the_build_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            venv = Path(tmp) / 'mbedtls-build-venv'
            calls = []
            fake = SimpleNamespace(
                stage_mbedtls_venv=lambda path, wheels: calls.append((path, wheels)))
            with mock.patch.dict('sys.modules', {'workspace': fake}), \
                    mock.patch.object(self.lab_build, 'MBEDTLS_VENV', venv), \
                    mock.patch.object(self.lab_build, 'PUBLIC_DEPS',
                                      Path(tmp) / 'public-deps'):
                python = self.lab_build.ensure_mbedtls_venv()
        self.assertEqual(python, venv / 'bin/python')
        self.assertEqual(calls, [(venv, Path(tmp) / 'public-deps' / 'python-wheels')])

    def test_cross_tool_preflight_names_the_missing_library(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tool = Path(tmp) / 'usr/bin/armv7-alpine-linux-musleabihf-ar'
            tool.parent.mkdir(parents=True)
            tool.write_text('')
            failed = subprocess.CompletedProcess(
                [str(tool)], 127, '',
                'libfl.so.2: cannot open shared object file: No such file\n')
            with mock.patch.object(self.lab_build, 'MUSL_ROOT', Path(tmp)), \
                    mock.patch.object(self.lab_build.subprocess, 'run',
                                      return_value=failed):
                with self.assertRaises(self.lab_build.Fail) as caught:
                    self.lab_build.check_cross_tools()
        self.assertIn('libfl.so.2', str(caught.exception))
        self.assertIn('libfl2', str(caught.exception))

    def test_cross_tool_preflight_skips_unstaged_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(self.lab_build, 'MUSL_ROOT', Path(tmp)):
            self.lab_build.check_cross_tools()

    def test_reexec_passes_the_subcommand_first(self) -> None:
        args = SimpleNamespace(version='0.2.99', no_integrate=True, lock=None)
        self.assertEqual(self.lab_build.build_script_args(args),
                         ['build', '--version', '0.2.99', '--no-integrate'])

    def test_integration_merges_use_a_neutral_identity(self) -> None:
        with mock.patch.dict('os.environ', {}, clear=True):
            identity = self.lab_build.container_git_identity()
            argv = self.lab_build.container_argv(
                ('podman', '/usr/bin/podman'), self.root, 'libreecho-build',
                1000, 1000, [], identity)
        passed = [argv[index + 1] for index, item in enumerate(argv) if item == '-e']
        self.assertIn('GIT_AUTHOR_NAME=LibreEcho build', passed)
        self.assertIn('GIT_COMMITTER_EMAIL=build@libreecho.invalid', passed)
        self.assertNotIn('GIT_AUTHOR_NAME=Tom Grozev', passed)

    def test_ssh_remotes_are_rewritten_for_credential_free_fetch(self) -> None:
        with mock.patch.dict('os.environ', {}, clear=True):
            argv = self.lab_build.container_argv(
                ('podman', '/usr/bin/podman'), self.root, 'libreecho-build',
                1000, 1000, [])
        passed = [argv[index + 1] for index, item in enumerate(argv) if item == '-e']
        self.assertIn('GIT_CONFIG_KEY_0=url.https://github.com/.insteadOf', passed)
        self.assertIn('GIT_CONFIG_VALUE_0=git@github.com:', passed)
        self.assertIn('GIT_CONFIG_COUNT=1', passed)

    def test_guard_does_not_reexec_inside_the_container(self) -> None:
        with mock.patch.dict('os.environ', {'LIBREECHO_CONTAINER': '1'}, clear=True):
            self.assertFalse(self.lab_build.container_enabled(
                SimpleNamespace(no_container=False)))

    def test_guard_reexecs_on_the_host_unless_disabled(self) -> None:
        with mock.patch.dict('os.environ', {}, clear=True):
            self.assertTrue(self.lab_build.container_enabled(
                SimpleNamespace(no_container=False)))
            self.assertFalse(self.lab_build.container_enabled(
                SimpleNamespace(no_container=True)))


class BuildCommandTest(unittest.TestCase):
    """cmd_build hands build.sh the mapped local.json and work/ environment."""

    def setUp(self) -> None:
        self.lab_build = load_lab_build()
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        # The host steps read work/inputs, which only a real workspace has;
        # CI checks out the bare port repo.
        overlay = mock.patch.multiple(
            self.lab_build,
            ROOT=self.root,
            BUILD_ROOT=self.root / 'work/product-build',
            ensure_mbedtls_venv=mock.Mock(return_value=Path('/venv/bin/python')),
            ensure_ota_gate_python=mock.Mock(return_value=Path('/gate/bin/python')),
            check_cross_tools=mock.Mock(),
        )
        overlay.start()
        self.addCleanup(overlay.stop)

        self.product = self.root / 'work/integration/LibreEcho'
        (self.product / 'build').mkdir(parents=True)
        (self.product / 'build/build.sh').write_text('#!/bin/sh\n', encoding='utf-8')
        write_json(self.root / 'tools/lab-build.json', {
            'schema_version': 1,
            'builds_dir': 'work/builds',
            'values': {'target': 'lidar', 'profile': 'ota'},
        })
        write_json(self.root / 'integration.json', {'repos': []})
        private = self.root / 'private'
        private.mkdir()
        self.stock = private / 'boot_a.bin'
        self.signing = private / 'seed.hex'
        self.public = private / 'public.hex'
        self.stock.write_bytes(b'stock')
        self.signing.write_bytes(b'seed-secret')
        self.public.write_bytes(b'public')
        write_json(private / 'local.json', {
            'ota_signing_key': 'private/seed.hex',
            'ota_public_key': 'private/public.hex',
            'stock_boot': 'private/boot_a.bin',
            'device_host': 'lidar.local:5555',
        })
        write_json(self.root / 'lock.json', {
            'schema_version': 1,
            'generated': '2026-11-26T00:00:00Z',
            'repos': {name: {'head': head,
                             'integration_path': f'work/integration/{name}'}
                      for name, head in HEADS.items()},
        })
        self.run_dir = self.root / 'work/product-build/out/runs/run-1'
        self.run_dir.mkdir(parents=True)
        (self.run_dir / 'boot.img').write_bytes(b'boot')
        (self.run_dir / 'libreecho-run-1.ota.tar').write_bytes(b'ota')
        write_json(self.run_dir / 'manifest.json', {'target': 'lidar'})
        write_json(self.run_dir / 'feature-plan.json',
                   {'transaction_id': 'txn-test', 'release': 'radar-puffin-build-test'})

        self.log = FakeLog()
        self.log.runs_env = None
        self.lab_build.BuildLog = mock.Mock(return_value=self.log)
        sources = {role: FakeSource(self.root / f'work/integration/{name}')
                   for role, name in (('platform', 'LibreEcho-Platform'),
                                      ('linux', 'LibreEcho-Linux'),
                                      ('ui', 'LibreEcho-UI'),
                                      ('libreecho', 'LibreEcho'))}
        self.sources = sources
        self.lab_build.load_sources = mock.Mock(return_value=sources)

    def run_build(self, rebuild: bool = False) -> int:
        original_run = self.log.run
        run_dir = self.run_dir

        def run(cmd, cwd=None, env=None, step_log=None) -> int:
            env = dict(env or {})
            env['_FAKE_RUN'] = run_dir
            return original_run(cmd, cwd=cwd, env=env, step_log=step_log)

        self.log.run = run
        args = SimpleNamespace(version='0.2.99', no_integrate=True,
                               lock='lock.json', no_container=True,
                               rebuild=rebuild, stock_boot=None,
                               ota_signing_key=None, ota_public_key=None)
        return self.lab_build.cmd_build(args)

    def test_environment_and_outputs(self) -> None:
        self.assertEqual(self.run_build(), 0)
        command, cwd, env = self.log.runs[0]
        self.assertEqual(command[0], str(self.product / 'build/build.sh'))
        self.assertEqual(command[1:], ['--target', 'lidar', '--profile', 'ota',
                                       '--no-publish'])
        self.assertEqual(cwd, self.product)
        self.assertEqual(env['LIBREECHO_LIDAR_STOCK_BOOT'], str(self.stock))
        self.assertEqual(env['LIBREECHO_OTA_SIGNING_KEY'], str(self.signing))
        self.assertEqual(env['LIBREECHO_OTA_EXPECTED_PUBLIC_KEY_SHA256'],
                         sha256(self.public))
        self.assertEqual(env['LIBREECHO_BUILD_ROOT'],
                         str(self.root / 'work/product-build'))
        self.assertEqual(env['LIBREECHO_INPUTS_ROOT'],
                         str(self.lab_build.PUBLIC_DEPS))
        self.assertTrue(env['LIBREECHO_TARGET_RELEASE_TAG'].startswith(
            'radar-puffin-build-'))

        build_dir = self.root / 'work/builds/v0.2.99'
        self.assertTrue((build_dir / 'run/boot.img').is_file())
        sums = (build_dir / 'SHA256SUMS').read_text(encoding='utf-8')
        self.assertIn('run/boot.img', sums)
        provenance = json.loads((build_dir / 'provenance.json').read_text(encoding='utf-8'))
        self.assertEqual(provenance['local']['ota_signing_key']['sha256'],
                         sha256(self.signing))
        self.assertEqual(provenance['lock']['heads']['LibreEcho'], 'a' * 40)
        self.assertEqual(provenance['ota']['transaction_id'], 'txn-test')
        self.assertNotIn('seed-secret',
                         (build_dir / 'provenance.json').read_text(encoding='utf-8'))

    def test_same_sources_are_reused_unless_rebuild_is_asked(self) -> None:
        self.assertEqual(self.run_build(), 0)
        self.assertEqual(len(self.log.runs), 1)
        build_dir = self.root / 'work/builds/v0.2.99'
        stamp = (build_dir / 'provenance.json').read_text(encoding='utf-8')
        self.assertEqual(self.run_build(), 0)
        # No second build.sh run, and the promoted build is untouched.
        self.assertEqual(len(self.log.runs), 1)
        self.assertEqual(
            (build_dir / 'provenance.json').read_text(encoding='utf-8'), stamp)
        with self.assertRaisesRegex(self.lab_build.Fail, 'already exists'):
            self.run_build(rebuild=True)


class DeployChecksTest(unittest.TestCase):
    def setUp(self) -> None:
        self.lab_build = load_lab_build()
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.build_dir = Path(self.temporary.name)

    def test_host_precedence(self) -> None:
        with mock.patch.dict('os.environ', {'LAB_DEVICE_HOST': 'env-host:5555'},
                             clear=False):
            local = {'device_host': 'local-host:5555'}
            self.assertEqual(self.lab_build.device_host(
                SimpleNamespace(host='flag-host:5555'), local), 'flag-host:5555')
            self.assertEqual(self.lab_build.device_host(
                SimpleNamespace(host=None), local), 'local-host:5555')
            self.assertEqual(self.lab_build.device_host(
                SimpleNamespace(host=None), {}), 'env-host:5555')

    def test_deliverable_digest_mismatch_is_refused(self) -> None:
        artifact = self.build_dir / 'run/boot.img'
        artifact.parent.mkdir()
        artifact.write_bytes(b'boot')
        provenance = {'outputs': {'run/boot.img': sha256(artifact)}}
        self.lab_build.verify_deliverables(self.build_dir, provenance)
        artifact.write_bytes(b'tampered')
        with self.assertRaisesRegex(self.lab_build.Fail, 'run/boot.img'):
            self.lab_build.verify_deliverables(self.build_dir, provenance)


class CiSetupTest(unittest.TestCase):
    """`work` is a symlink to the runner cache, so every derived path follows it."""

    def setUp(self) -> None:
        self.lab_build = load_lab_build()
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.cache = self.root / 'lab-cache'

    def test_work_symlink_redirects_build_paths(self) -> None:
        self.assertEqual(self.lab_build.main(
            ['ci-setup', '--work-root', str(self.cache),
             '--workspace', str(self.root)]), 0)
        self.assertTrue((self.root / 'work').is_symlink())
        (self.root / 'work/builds').mkdir(parents=True)
        self.assertTrue((self.cache / 'builds').is_dir())

    def test_existing_symlink_is_accepted(self) -> None:
        (self.root / 'work').symlink_to(self.cache)
        self.assertEqual(self.lab_build.main(
            ['ci-setup', '--work-root', str(self.cache),
             '--workspace', str(self.root)]), 0)

    def test_real_work_directory_with_content_is_refused(self) -> None:
        (self.root / 'work/builds').mkdir(parents=True)
        self.assertEqual(self.lab_build.main(
            ['ci-setup', '--work-root', str(self.cache),
             '--workspace', str(self.root)]), 1)
        self.assertFalse((self.root / 'work').is_symlink())


def run_git(path: Path, *args: str) -> str:
    proc = subprocess.run(['git', '-C', str(path), *args], check=True,
                          capture_output=True, text=True, env=GIT_ENV)
    return proc.stdout.strip()


def configure_repo(path: Path) -> None:
    run_git(path, 'config', 'user.name', 'Test')
    run_git(path, 'config', 'user.email', 'test@example.invalid')
    run_git(path, 'config', 'commit.gpgsign', 'false')


def init_repo(path: Path) -> None:
    path.mkdir(parents=True)
    run_git(path, 'init', '-q', '-b', 'main')
    configure_repo(path)
    (path / 'README').write_text('base\n', encoding='utf-8')
    run_git(path, 'add', 'README')
    run_git(path, 'commit', '-q', '-m', 'base')


def commit_file(path: Path, name: str, text: str, message: str) -> str:
    (path / name).write_text(text, encoding='utf-8')
    run_git(path, 'add', name)
    run_git(path, 'commit', '-q', '-m', message)
    return run_git(path, 'rev-parse', 'HEAD')


FAKE_GH = '''#!/usr/bin/env python3
import json
import os
import shutil
import sys

args = sys.argv[1:]
log = os.environ.get("GH_LOG")
if log:
    with open(log, "a", encoding="utf-8") as handle:
        handle.write(" ".join(args) + "\\n")
if args[:2] == ["workflow", "run"]:
    state = os.environ.get("GH_STATE")
    if state:
        open(state, "w", encoding="utf-8").write("1")
elif args[:2] == ["run", "list"]:
    state = os.environ.get("GH_STATE")
    if state and os.path.exists(state):
        print(json.dumps([{"databaseId": 2, "url": "https://example.invalid/run/2"}]))
    elif "--status" in args:
        print(json.dumps([{"databaseId": 42}]))
    else:
        print(json.dumps([{"databaseId": 1, "url": "https://example.invalid/run/1"}]))
elif args[:2] == ["run", "download"]:
    destination = args[args.index("-D") + 1]
    shutil.copytree(os.environ["GH_ARTIFACT_SRC"], destination, dirs_exist_ok=True)
'''


def fake_gh(bin_dir: Path) -> Path:
    bin_dir.mkdir(parents=True, exist_ok=True)
    path = bin_dir / 'gh'
    path.write_text(FAKE_GH, encoding='utf-8')
    path.chmod(0o755)
    return path


class PushTest(unittest.TestCase):
    """push is fast-forward only unless --force leases the fetched head."""

    def setUp(self) -> None:
        self.lab_build = load_lab_build()
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.ws = self.root / 'ws'
        init_repo(self.ws)
        self.port_bare = self.root / 'remotes/port.git'
        subprocess.run(['git', 'clone', '-q', '--bare', str(self.ws),
                        str(self.port_bare)], check=True, env=GIT_ENV)
        run_git(self.ws, 'remote', 'add', 'origin', str(self.port_bare))

        self.fork_bare = self.root / 'remotes/alpha.git'
        self.fork_bare.parent.mkdir(parents=True, exist_ok=True)
        run_git(self.ws, 'init', '-q', '--bare', str(self.fork_bare))
        seed = self.root / 'alpha-seed'
        init_repo(seed)
        run_git(seed, 'switch', '-q', '-c', 'feature/one')
        commit_file(seed, 'one.txt', 'one\n', 'feature one')
        run_git(seed, 'push', '-q', str(self.fork_bare), 'main', 'feature/one')
        self.fork = self.ws / 'work/forks/alpha'
        subprocess.run(['git', 'clone', '-q', str(self.fork_bare), str(self.fork)],
                       check=True, env=GIT_ENV)
        configure_repo(self.fork)
        run_git(self.fork, 'switch', '-q', 'feature/one')
        write_json(self.ws / 'integration.json', {
            'schema_version': 1, 'repos': [{
                'name': 'alpha', 'fork_url': str(self.fork_bare), 'path': 'work/forks/alpha',
                'integration_path': 'work/integration/alpha', 'base': 'main',
                'topics': [{'branch': 'feature/one'}],
            }]})
        self.bin = self.root / 'bin'
        fake_gh(self.bin)
        self.log = self.root / 'gh.log'
        self.env = mock.patch.dict('os.environ', {
            'PATH': f'{self.bin}:{os.environ["PATH"]}',
            'GH_LOG': str(self.log),
            'GH_STATE': str(self.root / 'gh.state'),
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        self.patch = mock.patch.object(self.lab_build, 'ROOT', self.ws)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def push(self, force: bool = False) -> int:
        return self.lab_build.cmd_push(
            SimpleNamespace(force=force, version=None, workspace=str(self.ws)))

    def fork_sha(self, branch: str) -> str:
        return run_git(self.fork_bare, 'rev-parse', f'refs/heads/{branch}')

    def test_fast_forward_updates_the_fork_and_dispatches(self) -> None:
        local = commit_file(self.fork, 'local.txt', 'local\n', 'local change')
        self.assertEqual(self.push(), 0)
        self.assertEqual(self.fork_sha('feature/one'), local)
        self.assertEqual(run_git(self.port_bare, 'rev-parse', 'refs/heads/main'),
                         run_git(self.ws, 'rev-parse', 'main'))
        dispatched = self.log.read_text(encoding='utf-8')
        self.assertIn('workflow run lab-build.yml --ref main', dispatched)

    def test_diverged_branch_is_refused_without_force(self) -> None:
        local = commit_file(self.fork, 'local.txt', 'local\n', 'local change')
        other = self.root / 'other'
        subprocess.run(['git', 'clone', '-q', str(self.fork_bare), str(other)],
                       check=True, env=GIT_ENV)
        configure_repo(other)
        run_git(other, 'switch', '-q', 'feature/one')
        remote = commit_file(other, 'remote.txt', 'remote\n', 'remote change')
        run_git(other, 'push', '-q', 'origin', 'feature/one')
        self.assertNotEqual(local, remote)
        with self.assertRaisesRegex(self.lab_build.Fail, 'diverged.*--force'):
            self.push()
        self.assertEqual(self.fork_sha('feature/one'), remote)
        self.assertFalse(self.log.exists())

    def test_force_leases_the_fetched_head(self) -> None:
        local = commit_file(self.fork, 'local.txt', 'local\n', 'local change')
        other = self.root / 'other'
        subprocess.run(['git', 'clone', '-q', str(self.fork_bare), str(other)],
                       check=True, env=GIT_ENV)
        configure_repo(other)
        run_git(other, 'switch', '-q', 'feature/one')
        remote = commit_file(other, 'remote.txt', 'remote\n', 'remote change')
        run_git(other, 'push', '-q', 'origin', 'feature/one')
        calls: list[list[str]] = []
        real_run = subprocess.run

        def spy(*args, **kwargs):
            calls.append([str(part) for part in args[0]])
            return real_run(*args, **kwargs)

        with mock.patch.object(self.lab_build.subprocess, 'run', side_effect=spy):
            self.assertEqual(self.push(force=True), 0)
        self.assertEqual(self.fork_sha('feature/one'), local)
        self.assertNotEqual(local, remote)
        pushes = [call for call in calls if 'push' in call]
        self.assertTrue(any(f'--force-with-lease=refs/heads/feature/one:{remote}' in call
                            for call in pushes), pushes)

    def test_dirty_port_tree_is_refused(self) -> None:
        (self.ws / 'README').write_text('changed\n', encoding='utf-8')
        with self.assertRaisesRegex(self.lab_build.Fail, 'uncommitted changes'):
            self.push()

    def test_push_argv_only_leases_when_asked(self) -> None:
        plain = self.lab_build.push_argv(Path('/repo'), 'fork', 'feat/x')
        self.assertNotIn('--force', ' '.join(plain))
        leased = self.lab_build.push_argv(Path('/repo'), 'fork', 'feat/x', 'a' * 40)
        self.assertIn(f'--force-with-lease=refs/heads/feat/x:{"a" * 40}', leased)


class FetchTest(unittest.TestCase):
    """fetch downloads the public artifact, verifies SHA256SUMS and installs it."""

    def setUp(self) -> None:
        self.lab_build = load_lab_build()
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        write_json(self.root / 'tools/lab-build.json', {
            'schema_version': 1, 'builds_dir': 'work/builds',
        })
        self.artifact = self.root / 'artifact'
        self.artifact.mkdir()
        build = self.root / 'build-tree'
        run = build / 'run'
        (run / 'ota-assets').mkdir(parents=True)
        (run / 'boot.img').write_bytes(b'boot')
        names = [f'asset-{index}.bin'
                 for index in range(2 * len(self.lab_build.FEATURE_ORDER))]
        for name in names:
            (run / 'ota-assets' / name).write_bytes(name.encode())
        write_json(run / 'feature-assets.json', {'assets': [
            {'name': name, 'sha256': hashlib.sha256(name.encode()).hexdigest(),
             'size': len(name)}
            for name in names]})
        write_json(run / 'manifest.json', {'schema': 1})
        bundle = run / 'libreecho-test.ota.tar'
        with tarfile.open(bundle, 'w') as archive:
            for member, payload in (('manifest', b'{}'), ('manifest.sig', b'sig')):
                info = tarfile.TarInfo(member)
                info.size = len(payload)
                archive.addfile(info, io.BytesIO(payload))
        (build / 'build.sh.log').write_text('run=\n', encoding='utf-8')
        provenance = {
            'version': '1.2.3',
            'ota': {'run_dir': 'run', 'bundle': 'run/libreecho-test.ota.tar',
                    'bundle_sha256': hashlib.sha256(bundle.read_bytes()).hexdigest()},
        }
        self.lab_build.write_build_identity(build, provenance)
        self.build = build
        self.bin = self.root / 'bin'
        fake_gh(self.bin)
        self.env = mock.patch.dict('os.environ', {
            'PATH': f'{self.bin}:{os.environ["PATH"]}',
            'GH_ARTIFACT_SRC': str(self.artifact),
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        for key in ('GH_LOG', 'GH_STATE'):
            os.environ.pop(key, None)
        self.patch = mock.patch.object(self.lab_build, 'ROOT', self.root)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def publish(self, sums: str | None = None) -> None:
        # CI uploads the whole build directory: the deploy closure plus records.
        sums_text = sums if sums is not None else (self.build / 'SHA256SUMS').read_text(
            encoding='utf-8')
        (self.build / 'SHA256SUMS').write_text(sums_text, encoding='utf-8')
        # Rewrite provenance outputs for a tampered SHA256SUMS so deploy sees the
        # digest the artifact claims rather than the real one.
        if sums is not None:
            provenance = json.loads((self.build / 'provenance.json').read_text(
                encoding='utf-8'))
            provenance['outputs'] = dict(
                line.split('  ', 1)[::-1] for line in sums_text.splitlines() if line)
            write_json(self.build / 'provenance.json', provenance)
        shutil.copytree(self.build, self.artifact, dirs_exist_ok=True)

    def test_verify_and_install(self) -> None:
        self.publish()
        self.assertEqual(self.lab_build.cmd_fetch(SimpleNamespace(run='42')), 0)
        destination = self.root / 'work/builds/v1.2.3'
        self.assertEqual((destination / 'run/boot.img').read_bytes(), b'boot')
        self.assertTrue((destination / 'SHA256SUMS').is_file())
        self.assertTrue((destination / 'provenance.json').is_file())

    def test_fetched_build_passes_deploy_preflight(self) -> None:
        self.publish()
        self.assertEqual(self.lab_build.cmd_fetch(SimpleNamespace(run='42')), 0)
        destination = self.root / 'work/builds/v1.2.3'
        provenance = json.loads((destination / 'provenance.json').read_text(
            encoding='utf-8'))
        self.lab_build.verify_deliverables(destination, provenance)
        run = destination / provenance['ota']['run_dir']
        assets = json.loads((run / 'feature-assets.json').read_text(
            encoding='utf-8'))['assets']
        self.assertEqual(len(assets), 2 * len(self.lab_build.FEATURE_ORDER))
        for item in assets:
            self.assertTrue((run / 'ota-assets' / item['name']).is_file())
        with tarfile.open(destination / provenance['ota']['bundle']) as archive:
            self.assertIsNotNone(archive.extractfile('manifest'))

    def test_latest_resolves_the_newest_successful_run(self) -> None:
        self.publish()
        self.assertEqual(self.lab_build.cmd_fetch(SimpleNamespace(run='latest')), 0)
        self.assertTrue((self.root / 'work/builds/v1.2.3').is_dir())

    def test_checksum_mismatch_is_refused(self) -> None:
        self.publish(sums='0' * 64 + '  run/boot.img\n')
        with self.assertRaisesRegex(self.lab_build.Fail, 'does not match'):
            self.lab_build.cmd_fetch(SimpleNamespace(run='42'))
        self.assertFalse((self.root / 'work/builds/v1.2.3').exists())

    def test_artifact_without_a_bundle_is_refused(self) -> None:
        self.publish()
        for bundle in (self.artifact / 'run').glob('*.ota.tar'):
            bundle.unlink()
        with self.assertRaisesRegex(self.lab_build.Fail, 'missing from the fetched build'):
            self.lab_build.cmd_fetch(SimpleNamespace(run='42'))


class WorkflowPinTest(unittest.TestCase):
    """The workflow's container image and the tool's pin cannot drift apart."""

    def test_workflow_runs_the_pinned_build_image(self) -> None:
        config = json.loads((ROOT / 'tools/lab-build.json').read_text(encoding='utf-8'))
        image = config['build_image']
        pinned = f'{image["name"]}@{image["digest"]}'
        workflow = (ROOT / '.github/workflows/lab-build.yml').read_text(encoding='utf-8')
        self.assertIn(f'image: {pinned}', workflow)
        self.assertIn('runs-on: arc-libreecho', workflow)
        self.assertIn('workflow_dispatch:', workflow)
        self.assertNotIn('pull_request:', workflow)


if __name__ == '__main__':
    unittest.main()
