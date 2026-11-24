#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Build and deploy the Lidar lab OTA from the integration branches.

`build` rebuilds the per-repo `integration` branches (tools/integrate.py), checks
the lock, then builds the OTA from those worktrees: kernel (cached by its
integration head), UI bundle, boot images, audio engine, feature payloads and the
signed OTA bundle.  Every input that is not a repository is pinned in
tools/lab-build.json by workspace-relative path and sha256.

`deploy` installs a finished build over Wi-Fi.  It writes the device's inactive
boot slot and reboots the device; it therefore needs --yes and an explicit host.

Host-only build: `build` never talks to a device.

usage:
  tools/lab-build.py build [--version X.Y.Z] [--no-integrate] [--lock PATH]
                           [--kernel-prebuilt DIR]
  tools/lab-build.py deploy VERSION --host HOST --yes

`--lock PATH` skips `tools/integrate.py` and reads a hand-written lock instead.
`build` outputs to private/artifacts/builds/v<version>/ with provenance.json and
build.log; the version defaults to the highest existing lab version plus one
patch.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import lzma
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_REL = 'tools/lab-build.json'
MANIFEST_REL = 'integration.json'
LOCK_REL = 'private/integration/integration.lock.json'
INTEGRATE_REL = 'tools/integrate.py'

BOOT_SIZE = 16 * 1024 * 1024
VERSION_RE = re.compile(r'\d+\.\d+\.\d+')
VERSION_FULL_RE = re.compile(r'(\d+)\.(\d+)\.(\d+)')
KERNEL_DEFCONFIG = 'mt8167_arm64_defconfig'
KERNEL_DTB_TARGET = 'mediatek/libreecho-lidar.dtb'

# v0.2.37 checks that were left out because they are pinned to one fix:
DROPPED_CHECKS = (
    'platform pinned-commit ancestry (02ef8ad6 / 671a2caf9): the lock records '
    'the topic commits instead',
    'platform worktree HEAD equals 7011650f9: the lock records the head instead',
    'audio engine byte-identical to the v0.2.36 engine and different from the '
    'v0.2.35 engine: that pinned the loudness fix',
    'ramdisk Lidar Wi-Fi bring-up / wifi-radio gate strings: pinned to the radio '
    'bring-up fix',
    'web init assistant_services startup gate and reconciler topology string: '
    'pinned to those fixes',
    'audio profile lo_driver_gain=6, hp_driver_gain=6 and speaker_chain=lidar: '
    'pinned to the loudness change',
    'DTB strings board-thermal / ti,tmp112 / no uart-has-rtscts: pinned to the '
    'thermal and UART fixes; verify_lidar_dtb.py still validates the DTB',
    'UI bundle reused-from-v0236 flag: v0.2.37-specific bookkeeping',
)


class Fail(Exception):
    """A fatal, already-described build or deploy failure."""


# --------------------------------------------------------------------------
# small helpers


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def tree_sha256(path: Path) -> str:
    """Hash a directory: sorted relative paths plus file contents or link targets."""
    h = hashlib.sha256()
    root = path.resolve()
    for entry in sorted(root.rglob('*'), key=lambda p: p.relative_to(root).as_posix()):
        rel = entry.relative_to(root).as_posix()
        if entry.is_symlink():
            h.update(b'L\0' + rel.encode() + b'\0' + os.readlink(entry).encode() + b'\n')
        elif entry.is_file():
            h.update(b'F\0' + rel.encode() + b'\0' + sha256_file(entry).encode() + b'\n')
    return h.hexdigest()


def rel_to_ws(path: Path) -> str:
    """Workspace-relative path when possible, otherwise the absolute path."""
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def now_iso() -> str:
    return (datetime.datetime.now(datetime.timezone.utc)
            .replace(microsecond=0).isoformat().replace('+00:00', 'Z'))


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise Fail(f'cannot read JSON {rel_to_ws(path)}: {exc}')


def write_json(path: Path, doc: dict) -> None:
    path.write_text(json.dumps(doc, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def workspace_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def git(path: Path, *args: str) -> str:
    proc = subprocess.run(['git', '-C', str(path), *args], capture_output=True,
                          text=True, check=False)
    if proc.returncode != 0:
        raise Fail(f'git -C {rel_to_ws(path)} {" ".join(args)}: {proc.stderr.strip()}')
    return proc.stdout.strip()


# --------------------------------------------------------------------------
# build log


class BuildLog:
    def __init__(self, path: Path):
        self.path = path
        self.handle = open(path, 'a', encoding='utf-8')
        self.started = time.time()

    def write(self, text: str) -> None:
        sys.stdout.write(text)
        sys.stdout.flush()
        self.handle.write(text)
        self.handle.flush()

    def line(self, kind: str, text: str) -> None:
        self.write(f'{kind} {text}\n')

    def phase(self, title: str) -> None:
        self.write(f'\n== {title}\n')

    def run(self, cmd, cwd=None, env=None, step_log: Path | None = None,
            check: bool = True) -> int:
        printable = ' '.join(str(part) for part in cmd)
        self.line('$', printable)
        handle = open(step_log, 'a', encoding='utf-8') if step_log else None
        try:
            proc = subprocess.Popen([str(part) for part in cmd],
                                    cwd=str(cwd) if cwd else None, env=env,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, errors='replace')
            for line in proc.stdout:
                self.write(line)
                if handle:
                    handle.write(line)
            rc = proc.wait()
        finally:
            if handle:
                handle.close()
        if check and rc != 0:
            raise Fail(f'command failed ({rc}): {printable}')

    def capture(self, cmd, cwd=None, env=None, step_log: Path | None = None,
                check: bool = True) -> str:
        printable = ' '.join(str(part) for part in cmd)
        self.line('$', printable)
        proc = subprocess.run([str(part) for part in cmd],
                              cwd=str(cwd) if cwd else None, env=env,
                              capture_output=True, text=True, errors='replace',
                              check=False)
        output = proc.stdout + proc.stderr
        self.write(output)
        if step_log:
            with open(step_log, 'a', encoding='utf-8') as handle:
                handle.write(output)
        if check and proc.returncode != 0:
            raise Fail(f'command failed ({proc.returncode}): {printable}')
        return output

    def capture_status(self, cmd, cwd=None, env=None,
                       step_log: Path | None = None) -> tuple[int, str]:
        printable = ' '.join(str(part) for part in cmd)
        self.line('$', printable)
        proc = subprocess.run([str(part) for part in cmd],
                              cwd=str(cwd) if cwd else None, env=env,
                              capture_output=True, text=True, errors='replace',
                              check=False)
        output = proc.stdout + proc.stderr
        self.write(output)
        if step_log:
            with open(step_log, 'a', encoding='utf-8') as handle:
                handle.write(output)
        return proc.returncode, output

    def close(self) -> None:
        self.handle.close()


# --------------------------------------------------------------------------
# pinned inputs


class Inputs:
    def __init__(self, config: dict):
        self.config = config
        self.files = config.get('files', {})
        self.trees = config.get('trees', {})
        self.directories = config.get('directories', {})
        self.values = config.get('values', {})

    def path(self, name: str) -> Path:
        try:
            return workspace_path(self.files[name]['path'])
        except KeyError as exc:
            raise Fail(f'lab-build.json has no file input {name!r}') from exc

    def dir(self, name: str) -> Path:
        try:
            return workspace_path(self.directories[name])
        except KeyError as exc:
            raise Fail(f'lab-build.json has no directory input {name!r}') from exc

    def tree_path(self, name: str) -> Path:
        try:
            return workspace_path(self.trees[name]['path'])
        except KeyError as exc:
            raise Fail(f'lab-build.json has no tree input {name!r}') from exc

    def value(self, name: str) -> str:
        try:
            return self.values[name]
        except KeyError as exc:
            raise Fail(f'lab-build.json has no value {name!r}') from exc

    def verify(self, log: BuildLog) -> dict:
        """Fail unless every pinned file and tree matches its sha256."""
        record = {'files': {}, 'trees': {}}
        for name, spec in sorted(self.files.items()):
            path = self.path(name)
            if not path.is_file():
                raise Fail(f'pinned input {name} is missing: {spec["path"]}')
            actual = sha256_file(path)
            if actual != spec['sha256']:
                raise Fail(f'pinned input {name} changed: {spec["path"]} is {actual}, '
                           f'expected {spec["sha256"]}')
            record['files'][name] = {'path': spec['path'], 'sha256': actual,
                                     'size': path.stat().st_size}
        for name, spec in sorted(self.trees.items()):
            path = self.tree_path(name)
            if not path.is_dir():
                raise Fail(f'pinned tree {name} is missing: {spec["path"]}')
            actual = tree_sha256(path)
            if actual != spec['sha256']:
                raise Fail(f'pinned tree {name} changed: {spec["path"]} is {actual}, '
                           f'expected {spec["sha256"]}')
            record['trees'][name] = {'path': spec['path'], 'sha256': actual}
        for name in sorted(self.directories):
            path = self.dir(name)
            if not path.is_dir():
                raise Fail(f'input directory {name} is missing: {self.directories[name]}')
        log.line('PASS', f'{len(record["files"])} pinned files and '
                         f'{len(record["trees"])} pinned trees match lab-build.json')
        return record

    def input_manifest(self) -> dict:
        """file/tree/directory identity for provenance."""
        manifest = {'files': {}, 'trees': {}, 'directories': {}}
        for name, spec in sorted(self.files.items()):
            manifest['files'][name] = {'path': spec['path'], 'sha256': spec['sha256']}
        for name, spec in sorted(self.trees.items()):
            manifest['trees'][name] = {'path': spec['path'], 'sha256': spec['sha256']}
        for name, path in sorted(self.directories.items()):
            manifest['directories'][name] = {'path': path,
                                             'tree_sha256': tree_sha256(self.dir(name))}
        return manifest


# --------------------------------------------------------------------------
# lock and repositories


def repo_role(name: str) -> str | None:
    if name == 'LibreEcho':
        return 'libreecho'
    if name.endswith('Platform'):
        return 'platform'
    if name.endswith('UI'):
        return 'ui'
    if name.startswith('LibreEcho-Linux') or name == 'Linux':
        return 'linux'
    return None


class Source:
    def __init__(self, role: str, name: str, entry: dict):
        self.role = role
        self.name = name
        self.entry = entry
        self.path = workspace_path(entry['integration_path'])
        self.head = entry.get('head')
        self.dirty: list[str] = []
        self.clean = True

    def validate(self) -> None:
        if not self.path.is_dir():
            raise Fail(f'{self.name}: integration worktree missing: '
                       f'{self.entry["integration_path"]}')
        try:
            actual = git(self.path, 'rev-parse', 'HEAD')
        except Fail as exc:
            raise Fail(f'{self.name}: {self.entry["integration_path"]} is not a '
                       f'git worktree ({exc})') from exc
        if self.head and actual != self.head:
            raise Fail(f'{self.name}: worktree HEAD {actual[:10]} does not match '
                       f'the lock {str(self.head)[:10]}')
        self.head = actual
        status = git(self.path, 'status', '--porcelain', '--untracked-files=all')
        self.dirty = [line for line in status.splitlines() if line.strip()]
        self.clean = not self.dirty
        if not self.clean:
            raise Fail(f'{self.name}: worktree is dirty '
                       f'({self.entry["integration_path"]}): '
                       + ', '.join(self.dirty[:10]))

    def record(self) -> dict:
        return {
            'role': self.role,
            'integration_path': self.entry['integration_path'],
            'base_ref': self.entry.get('base_ref'),
            'base_sha': self.entry.get('base_sha'),
            'topics': self.entry.get('topics', []),
            'head': self.head,
            'dirty': self.dirty,
        }


def load_sources(lock: dict, log: BuildLog) -> dict[str, Source]:
    repos = lock.get('repos')
    if not isinstance(repos, dict) or not repos:
        raise Fail('lock has no repos')
    sources: dict[str, Source] = {}
    for name, entry in repos.items():
        role = repo_role(name)
        if role is None:
            continue
        if role in sources:
            raise Fail(f'lock has two {role} repos: {sources[role].name} and {name}')
        if not isinstance(entry, dict) or 'integration_path' not in entry:
            raise Fail(f'lock entry {name} has no integration_path')
        sources[role] = Source(role, name, entry)
    for role in ('platform', 'ui', 'linux', 'libreecho'):
        if role not in sources:
            raise Fail(f'the lock has no {role} repo (expected in the manifest)')
        sources[role].validate()
        log.line('PASS', f'{sources[role].name} @ {sources[role].head[:10]} '
                          f'({sources[role].entry["integration_path"]}) clean')
    return sources


# --------------------------------------------------------------------------
# kernel


class Kernel:
    def __init__(self, path: Path, mode: str, head: str | None, extra: dict | None = None):
        self.path = path
        self.mode = mode          # 'built' or 'prebuilt'
        self.head = head
        self.extra = extra or {}
        self.image = path / 'Image'
        self.config = path / 'config'
        self.dtb = path / 'libreecho-lidar.dtb'

    def validate(self) -> None:
        for path in (self.image, self.config, self.dtb):
            if not path.is_file():
                raise Fail(f'kernel input missing: {rel_to_ws(path)}')

    def record(self) -> dict:
        record = {
            'mode': self.mode,
            'path': rel_to_ws(self.path),
            'image_sha256': sha256_file(self.image),
            'dtb_sha256': sha256_file(self.dtb),
            'config_sha256': sha256_file(self.config),
        }
        if self.mode == 'built':
            record['linux_integration_head'] = self.head
        else:
            record['linux_integration_head'] = self.head
            record['warning'] = (
                'prebuilt kernel: NOT built from the integration Linux worktree. '
                'A lab build from the new integration kernel is untested on hardware.'
            )
        record.update(self.extra)
        return record


def commit_date(src: Path) -> str:
    text = git(src, 'log', '-1', '--format=%cs')
    return text.strip() or '1970-01-01'


def build_kernel(builder, sources: dict[str, Source]) -> Kernel:
    inputs = builder.inputs
    log = builder.log
    linux = sources['linux']
    cache_root = workspace_path(builder.config['kernel_cache_dir'])
    cache_root.mkdir(parents=True, exist_ok=True)
    cache = cache_root / linux.head
    toolchain_tree = inputs.trees['aarch64_cross']['sha256']
    wanted = {
        'head': linux.head,
        'toolchain_tree_sha256': toolchain_tree,
        'defconfig': KERNEL_DEFCONFIG,
        'dtb_target': KERNEL_DTB_TARGET,
    }
    meta_path = cache / 'meta.json'
    if meta_path.is_file():
        try:
            meta = read_json(meta_path)
        except Fail:
            meta = {}
        files_ok = all(meta.get('files', {}).get(name) == sha256_file(cache / name)
                       for name in ('Image', 'config', 'libreecho-lidar.dtb')
                       if (cache / name).is_file())
        if files_ok and all(meta.get(key) == value for key, value in wanted.items()):
            log.line('INFO', f'kernel cache hit for {linux.head[:10]} '
                             f'({rel_to_ws(cache)})')
            return Kernel(cache, 'built', linux.head, {
                'cache': 'hit',
                'toolchain_tree_sha256': toolchain_tree,
                'defconfig': KERNEL_DEFCONFIG,
                'dtb_target': KERNEL_DTB_TARGET,
                'build_timestamp': meta.get('build_timestamp'),
            })
        log.line('INFO', f'kernel cache stale for {linux.head[:10]}, rebuilding')

    prefix = inputs.tree_path('aarch64_cross') / 'usr/bin/aarch64-linux-gnu-'
    if not (prefix.parent / (prefix.name + 'gcc')).is_file():
        raise Fail(f'pinned aarch64 cross compiler missing under '
                   f'{rel_to_ws(prefix.parent)}')
    env = dict(os.environ)
    timestamp = f'{commit_date(linux.path)} 00:00:00 UTC'
    env.update({
        'KBUILD_BUILD_USER': 'libreecho',
        'KBUILD_BUILD_HOST': 'lab',
        'KBUILD_BUILD_TIMESTAMP': timestamp,
        # The pinned cross links its binutils/gcc against libraries shipped in its own
        # prefix, not the host's.
        'LD_LIBRARY_PATH': str(inputs.tree_path('aarch64_cross') / 'usr/lib/x86_64-linux-gnu'),
    })
    jobs = str(os.cpu_count() or 4)
    obj = Path(tempfile.mkdtemp(prefix='kbuild-', dir=str(cache_root)))
    step = builder.build_dir / 'kernel-build.log'
    try:
        log.phase(f'kernel from {linux.name} @ {linux.head[:10]}')
        log.run(['make', '-s', f'O={obj}', 'ARCH=arm64',
                 f'CROSS_COMPILE={prefix}', KERNEL_DEFCONFIG],
                cwd=linux.path, env=env, step_log=step)
        log.run(['make', '-s', f'O={obj}', 'ARCH=arm64', f'CROSS_COMPILE={prefix}',
                 f'-j{jobs}', 'Image', KERNEL_DTB_TARGET],
                cwd=linux.path, env=env, step_log=step)
        staged = Path(tempfile.mkdtemp(prefix='kinstall-', dir=str(cache_root)))
        shutil.copy2(obj / 'arch/arm64/boot/Image', staged / 'Image')
        shutil.copy2(obj / 'arch/arm64/boot/dts' / KERNEL_DTB_TARGET,
                     staged / 'libreecho-lidar.dtb')
        shutil.copy2(obj / '.config', staged / 'config')
        meta = dict(wanted)
        meta['build_timestamp'] = timestamp
        meta['files'] = {name: sha256_file(staged / name)
                         for name in ('Image', 'config', 'libreecho-lidar.dtb')}
        write_json(staged / 'meta.json', meta)
        if cache.exists():
            shutil.rmtree(cache)
        staged.rename(cache)
    finally:
        shutil.rmtree(obj, ignore_errors=True)
    log.line('PASS', f'kernel Image {meta["files"]["Image"][:16]} '
                     f'DTB {meta["files"]["libreecho-lidar.dtb"][:16]}')
    return Kernel(cache, 'built', linux.head, {
        'cache': 'miss',
        'toolchain_tree_sha256': toolchain_tree,
        'defconfig': KERNEL_DEFCONFIG,
        'dtb_target': KERNEL_DTB_TARGET,
        'build_timestamp': timestamp,
        'compiler': 'gcc (aarch64-cross)',
    })


def prebuilt_kernel(builder, sources: dict[str, Source], path: Path) -> Kernel:
    kernel = Kernel(path, 'prebuilt', sources['linux'].head, {
        'source': 'given with --kernel-prebuilt',
    })
    kernel.validate()
    builder.log.line('INFO', 'prebuilt kernel ' + rel_to_ws(path)
                     + ' (not rebuilt from the integration Linux worktree)')
    return kernel


# --------------------------------------------------------------------------
# build steps


def build_ui(builder, sources: dict[str, Source]) -> tuple[Path, str]:
    inputs = builder.inputs
    log = builder.log
    platform = sources['platform'].path
    ui_source = sources['ui'].path
    tools = platform / 'tools/mt8163-arm32'
    comp = builder.build_dir / 'components/ui'
    comp.mkdir(parents=True, exist_ok=True)
    (comp / 'logs').mkdir(parents=True, exist_ok=True)
    armhf_root = inputs.path('armhf_strip').parents[2]
    host_libs = inputs.dir('armhf_host_libs')
    musl_root = inputs.dir('musl_toolchain')
    env = dict(os.environ)
    env['LD_LIBRARY_PATH'] = str(host_libs)
    log.phase(f'UI bundle from {sources["ui"].name} @ {sources["ui"].head[:10]}')
    log.run([tools / 'mbedtls/build_mbedtls.sh',
             '--archive', inputs.path('mbedtls_archive'),
             '--output', comp / 'mbedtls-arm32',
             '--cc', armhf_root / 'usr/bin/arm-linux-gnueabihf-gcc',
             '--python', inputs.path('mbedtls_python'),
             '--jobs', str(os.cpu_count() or 4)],
            env=env, step_log=comp / 'logs/mbedtls-build.log')
    ui_cross = f'{inputs.path("armhf_gcc").parent}/arm-linux-gnueabihf-'
    build_env = dict(env)
    build_env.update({
        'LIBREECHO_UI_CROSS_COMPILE': ui_cross,
        'LIBREECHO_UI_MBEDTLS_ROOT': str(comp / 'mbedtls-arm32'),
        'LIBREECHO_OPUS_ARCHIVES_DIR': str(inputs.dir('opus_archives')),
        'LIBREECHO_OPUS_CC': ui_cross + 'gcc',
        'LIBREECHO_OPUS_AR': ui_cross + 'ar',
        'LIBREECHO_OPUS_HOST': 'arm-linux-gnueabihf',
        'LIBREECHO_UI_MUSL_NATIVE_ROOT': str(musl_root),
        'LIBREECHO_UI_MUSL_SYSROOT': str(musl_root),
        'LIBREECHO_UI_MUSL_CC': str(inputs.path('musl_gcc')),
        'LIBREECHO_UI_MUSL_NATIVE_LIB': str(musl_root / 'usr/lib'),
    })
    (comp / 'logs').mkdir(parents=True, exist_ok=True)
    log.run([tools / 'ui/build_ui_bundle.sh', ui_source, comp / 'ui-bundle/bundle'],
            env=build_env, step_log=comp / 'logs/ui-build.log')
    bundle = comp / 'ui-bundle/bundle'
    manifest = bundle / 'share/libreecho/ui-manifest.txt'
    if not manifest.is_file():
        raise Fail(f'UI bundle has no manifest: {rel_to_ws(manifest)}')
    fields = {}
    for line in manifest.read_text(encoding='utf-8').splitlines():
        if '=' in line:
            key, value = line.split('=', 1)
            fields[key] = value
    if fields.get('source_commit') != sources['ui'].head:
        raise Fail(f'UI bundle source_commit {fields.get("source_commit")} does not '
                   f'match {sources["ui"].name} {sources["ui"].head}')
    if fields.get('source_diff_sha256') != inputs.value('empty_tree_sha256'):
        raise Fail('UI bundle source_diff_sha256 is not a clean tree: '
                   f'{fields.get("source_diff_sha256")}')
    manifest_sha = sha256_file(manifest)
    log.line('PASS', f'UI bundle manifest {manifest_sha[:16]} '
                     f'(source_commit {sources["ui"].head[:10]}, clean tree)')
    return bundle, manifest_sha


def build_images(builder, sources: dict[str, Source], kernel: Kernel,
                 bundle: Path) -> Path:
    inputs = builder.inputs
    log = builder.log
    platform = sources['platform'].path
    lidar = platform / 'tools/mt8167-arm64'
    out = builder.build_dir / 'images'
    out.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env['PATH'] = str(inputs.path('qemu_arm').parent) + os.pathsep + env.get('PATH', '')
    shared_kernel = [
        '--stock-boot', inputs.path('stock_boot'),
        '--kernel-image', kernel.image,
        '--kernel-config', kernel.config,
        '--dtb', kernel.dtb,
        '--expected-dtb-sha256', sha256_file(kernel.dtb),
    ]
    build_common = [
        *shared_kernel,
        '--adbd', inputs.path('adbd'),
        '--adbd-source-metadata', inputs.path('adbd_source'),
        '--busybox', inputs.path('busybox'),
        '--expected-busybox-sha256', sha256_file(inputs.path('busybox')),
        '--musl-loader', inputs.path('musl_loader'),
        '--expected-musl-loader-sha256', sha256_file(inputs.path('musl_loader')),
        '--update-channel', 'dev',
        '--bootctl', inputs.path('bootctl'),
        '--update-verifier', inputs.path('update_verify'),
        '--ota-public-key', inputs.path('ota_public_key'),
        '--wifi-patch', inputs.path('wifi_patch'),
        '--wifi-licence', inputs.path('wifi_licence'),
        '--wpa-supplicant', inputs.path('wpa_supplicant'),
        '--tinyplay', inputs.path('tinyplay'),
        '--tinycap', inputs.path('tinycap'),
        '--tinymix', inputs.path('tinymix'),
        '--ui-bundle', bundle,
        '--ui-source', sources['ui'].path,
        '--expected-ui-commit', sources['ui'].head,
        '--expected-ui-diff-sha256', inputs.value('empty_tree_sha256'),
    ]
    verify_common = [
        *shared_kernel,
        '--expected-busybox-sha256', sha256_file(inputs.path('busybox')),
        '--expected-musl-loader-sha256', sha256_file(inputs.path('musl_loader')),
        '--update-channel', 'dev',
        '--expected-bootctl-sha256', sha256_file(inputs.path('bootctl')),
        '--expected-update-verifier-sha256', sha256_file(inputs.path('update_verify')),
        '--expected-ota-public-key-sha256', sha256_file(inputs.path('ota_public_key')),
        '--expected-ui-manifest-sha256',
        sha256_file(bundle / 'share/libreecho/ui-manifest.txt'),
        '--expected-ui-commit', sources['ui'].head,
        '--expected-ui-diff-sha256', inputs.value('empty_tree_sha256'),
        '--expected-wpa-supplicant-sha256', sha256_file(inputs.path('wpa_supplicant')),
        '--expected-tinyplay-sha256', sha256_file(inputs.path('tinyplay')),
        '--expected-tinycap-sha256', sha256_file(inputs.path('tinycap')),
        '--expected-tinymix-sha256', sha256_file(inputs.path('tinymix')),
    ]
    mdns = ['--mdns-runtime', inputs.dir('mdns_runtime')]
    specs = (
        ('dev', 'development', 'diagnostic', []),
        ('v2', 'ota', 'production', mdns),
    )
    log.phase('boot images')
    for name, image_profile, service_profile, extra in specs:
        image = out / f'boot-lidar-{name}.img'
        log.line('INFO', f'image {name}: {image_profile}/{service_profile}')
        log.run([sys.executable, lidar / 'build_recovery_image.py', *build_common,
                 '--image-profile', image_profile,
                 '--service-profile', service_profile,
                 '--feature-policy', 'preserve',
                 '--cmdline-append', f'libreecho.lab=p6-{name}',
                 *extra, '--output', image],
                env=env, step_log=out / 'build.log')
    builds = sorted(out.glob('boot-lidar-*.img'))
    (out / 'SHA256SUMS').write_text(''.join(
        f'{sha256_file(path)}  {path.name}\n' for path in builds), encoding='utf-8')
    log.phase('boot image verification')
    mdns_pin = ['--expected-mdns-runtime-manifest-sha256',
                (inputs.dir('mdns_runtime') / 'manifest.sha256').read_text().strip()]
    for name, image_profile, service_profile, extra in specs:
        extra_verify = mdns_pin if extra else []
        log.run([sys.executable, lidar / 'verify_recovery_image.py', *verify_common,
                 '--ramdisk', out / f'boot-lidar-{name}.ramdisk.cpio.xz',
                 '--manifest', out / f'boot-lidar-{name}.manifest.json',
                 '--boot-image', out / f'boot-lidar-{name}.img',
                 '--expected-boot-sha256', sha256_file(out / f'boot-lidar-{name}.img'),
                 '--cmdline-append', f'libreecho.lab=p6-{name}',
                 '--image-profile', image_profile,
                 '--service-profile', service_profile,
                 '--feature-policy', 'preserve',
                 *extra_verify],
                env=env, step_log=out / 'verify.log')
    log.line('PASS', 'three recovery images built and verified')
    return out


def build_engine(builder, sources: dict[str, Source]) -> Path:
    inputs = builder.inputs
    log = builder.log
    src = sources['platform'].path / 'tools/mt8163-arm32/airplay'
    tiny = inputs.dir('tinyalsa')
    out = builder.build_dir / 'engine'
    out.mkdir(parents=True, exist_ok=True)
    sources_c = ['audio_engine.c', 'aec_reference.c', 'audio_sink.c',
                 'audio_timing.c', 'audio_visualizer.c', 'playback_status.c']
    log.phase(f'audio engine from {sources["platform"].name} @ '
              f'{sources["platform"].head[:10]}')
    log.run([inputs.path('armhf_gcc'), '-O2', '-std=c99', '-Wall',
             f'-I{src}', f'-I{tiny / "include"}',
             '-o', out / 'libreecho-audio-engine',
             *[src / name for name in sources_c],
             f'-L{tiny / "src"}', '-ltinyalsa', '-ldl', '-lm'],
            step_log=out / 'build.log')
    env = dict(os.environ)
    env['LD_LIBRARY_PATH'] = str(inputs.dir('armhf_host_libs'))
    log.run([inputs.path('armhf_strip'), '--strip-unneeded',
             out / 'libreecho-audio-engine'], env=env, step_log=out / 'build.log')
    tracked = [src / 'audio_engine.c', src / 'test_airplay_session_dsp.py']
    (out / 'sources.sha256').write_text(
        ''.join(f'{sha256_file(path)}  {rel_to_ws(path)}\n' for path in tracked),
        encoding='utf-8')
    engine_sha = sha256_file(out / 'libreecho-audio-engine')
    log.line('PASS', f'audio engine {engine_sha[:16]}')
    return out / 'libreecho-audio-engine'


def build_airplay2(builder, sources: dict[str, Source], engine: Path) -> tuple[Path, Path]:
    inputs = builder.inputs
    log = builder.log
    stage = builder.build_dir / 'features/airplay2'
    stage.mkdir(parents=True, exist_ok=True)
    shutil.copytree(inputs.dir('airplay2_base_root'), stage / 'root', symlinks=True)
    shutil.copy2(inputs.path('sendspind'), stage / 'root/usr/local/sbin/libreecho-sendspind')
    shutil.copy2(engine, stage / 'root/usr/local/sbin/libreecho-audio-engine')
    log.phase('airplay2 payload')
    package = sources['libreecho'].path / 'build/package_feature_payload.sh'
    log.run(['bash', package, 'airplay2', stage / 'root',
             stage / 'probe.payload.squashfs', stage / 'probe.manifest.json'],
            step_log=stage / 'package.log')
    payload = stage / 'probe.payload.squashfs'
    identity = stage / 'probe.manifest.json'
    log.line('PASS', f'airplay2 payload {sha256_file(payload)[:16]} '
                     f'manifest {sha256_file(identity)[:16]}')
    return payload, identity


def stage_wakeword(builder) -> tuple[Path, Path]:
    inputs = builder.inputs
    builder.log.line('PASS', f'wakeword payload '
                             f'{inputs.files["wakeword_payload"]["sha256"][:16]} '
                             f'(pinned prebuilt)')
    return inputs.path('wakeword_payload'), inputs.path('wakeword_manifest')


# The product's whole-target contract fixes the five feature ids and their order.
FEATURE_ORDER = ('airplay2', 'tts', 'wakeword', 'stt', 'assistant')


def release_tag(lock: dict, version: str) -> str:
    """The product dev release tag this lab build publishes under.

    `.github/workflows/build-release.yml:258-265` derives the tag as
    radar-puffin-build-<sha7>-<source_id>-<build_id>: sha7 is the product
    commit, source_id is the sha256 over the product, Platform, Linux and UI
    commit shas, and build_id hashes the CI run.  The lab has no run id, so
    build_id hashes a lab-unique string; build.sh:512 and the TAG grammar in
    ota_v3_product.py:30 pin the shape.
    """
    heads = {name: entry['head'] for name, entry in lock['repos'].items()}
    try:
        product = heads['LibreEcho']
        material = ''.join(
            heads[name] + '\n' for name in
            ('LibreEcho', 'LibreEcho-Platform', 'LibreEcho-Linux', 'LibreEcho-UI'))
    except KeyError as exc:
        raise Fail(f'lock has no head for {exc.args[0]}') from exc
    return (f'radar-puffin-build-{product[:7]}-'
            f'{sha256_bytes(material.encode())[:16]}-'
            f'{sha256_bytes(f"lab:{version}\n".encode())[:16]}')


def write_catalog(builder, airplay2: tuple[Path, Path],
                  wakeword: tuple[Path, Path]) -> Path:
    """Write the product's CI candidate-catalog shape (plan-target-manifest.py:22-46).

    The catalog names each payload by the basename its feature manifest records,
    so the product pipeline can cross-check the pair; the pipeline derives the
    published content-addressed asset names itself.
    """
    inputs = builder.inputs
    log = builder.log
    base = read_json(inputs.path('feature_catalog'))
    base_features = base.get('features')
    if not isinstance(base_features, dict) or set(base_features) != set(FEATURE_ORDER):
        raise Fail('base feature catalog must name exactly the five product features')
    sources = {'airplay2': airplay2, 'wakeword': wakeword}
    for feature in FEATURE_ORDER:
        if feature in sources:
            continue
        entry = base_features[feature]
        pair = []
        for key in ('payload', 'manifest'):
            path = Path(entry[key])
            if not path.is_absolute():
                path = inputs.path('feature_catalog').parent / path
            if not path.is_file():
                raise Fail(f'catalog {feature} {key} is missing: {entry[key]}')
            pair.append(path)
        sources[feature] = tuple(pair)

    catalog = {'board': 'lidar', 'features': {}}
    for feature in FEATURE_ORDER:
        payload, manifest = sources[feature]
        identity = read_json(manifest)
        filename = identity.get('payload', {}).get('filename')
        if not isinstance(filename, str) or not filename or Path(filename).name != filename:
            raise Fail(f'{feature} manifest does not name a plain payload file')
        stage = builder.build_dir / 'ota/catalog' / feature
        stage.mkdir(parents=True, exist_ok=True)
        staged_payload = stage / filename
        staged_manifest = stage / 'manifest.json'
        shutil.copy2(payload, staged_payload)
        shutil.copy2(manifest, staged_manifest)
        catalog['features'][feature] = {
            'payload': {'path': str(staged_payload),
                        'sha256': sha256_file(staged_payload),
                        'size': staged_payload.stat().st_size},
            'manifest': {'path': str(staged_manifest),
                         'sha256': sha256_file(staged_manifest),
                         'size': staged_manifest.stat().st_size},
        }
    out = builder.build_dir / 'ota/feature-candidate-catalog.json'
    write_json(out, catalog)
    log.line('PASS', 'feature candidate catalog written (product v3 shape)')
    return out


def create_ota(builder, version: str, tag: str, catalog: Path,
               sources: dict[str, Source]) -> tuple[Path, str, Path]:
    """Run the product's plan and signing scripts over the lab-built payloads."""
    inputs = builder.inputs
    log = builder.log
    out = builder.build_dir / 'ota'
    run = out / 'run'
    run.mkdir(parents=True, exist_ok=False)
    shutil.copy2(builder.build_dir / 'images/boot-lidar-v2.img', run / 'boot.img')
    pipeline = sources['libreecho'].path / 'build' / 'ci'
    log.phase('product v3 target plan')
    log.run([sys.executable, '-B', pipeline / 'plan-target-manifest.py',
             '--target', 'lidar', '--candidate-catalog', catalog,
             '--boot-image', run / 'boot.img', '--release', tag,
             '--version', version, '--update-channel', 'dev', '--config-schema', '1',
             '--output', run / 'target.manifest',
             '--asset-output-dir', run / 'ota-assets'],
            step_log=run / 'plan.log')
    log.phase('signed OTA')
    tarball = out / f'libreecho-{tag}.ota.tar'
    log.run([sys.executable, '-B', pipeline / 'ota_v3_product.py',
             '--run', run,
             '--signing-key', inputs.path('ota_signing_key'),
             '--public-key', inputs.path('ota_public_key'),
             '--expected-key-sha256', inputs.files['ota_public_key']['sha256'],
             '--output', tarball],
            step_log=run / 'sign.log')
    transaction = read_json(run / 'feature-plan.json').get('transaction_id')
    if not isinstance(transaction, str) or not transaction:
        raise Fail('feature-plan.json has no transaction id')
    log.line('PASS', f'OTA {sha256_file(tarball)[:16]} tx {transaction}')
    return tarball, transaction, run


# --------------------------------------------------------------------------
# verification


def cpio_members(xz_path: Path) -> dict[str, tuple[int, bytes]]:
    """Read a newc cpio archive compressed with xz: name -> (mode, body)."""
    raw = lzma.decompress(xz_path.read_bytes())
    members: dict[str, tuple[int, bytes]] = {}
    pos = 0
    while True:
        if raw[pos:pos + 6] not in (b'070701', b'070702'):
            raise Fail(f'{rel_to_ws(xz_path)}: not a newc cpio archive at {pos}')
        fields = [int(raw[pos + 6 + 8 * i:pos + 14 + 8 * i], 16) for i in range(13)]
        mode, filesize, namesize = fields[1], fields[6], fields[11]
        name_end = pos + 110 + namesize
        name = raw[pos + 110:name_end - 1].decode('ascii', 'replace')
        data_start = name_end + (-name_end % 4)
        body = raw[data_start:data_start + filesize]
        pos = data_start + filesize
        pos += -pos % 4
        if name == 'TRAILER!!!':
            break
        name = name.lstrip('./').lstrip('/')
        members[name] = (mode, body)
    return members


def find_member(members: dict[str, tuple[int, bytes]], suffix: str
                ) -> tuple[int, bytes] | None:
    for name, body in members.items():
        if name == suffix or name.endswith('/' + suffix):
            return body
    return None


def member_sha(members: dict[str, tuple[int, bytes]], suffix: str) -> str | None:
    found = find_member(members, suffix)
    return sha256_bytes(found[1]) if found else None


def unsquashfs_sha(builder, archive: Path, member: str) -> str:
    proc = subprocess.run(['unsquashfs', '-cat', str(archive), member],
                          capture_output=True, check=False)
    if proc.returncode != 0:
        raise Fail(f'unsquashfs -cat {rel_to_ws(archive)} {member} failed: '
                   f'{proc.stderr.decode(errors="replace").strip()}')
    return sha256_bytes(proc.stdout)


def verify(builder, version: str, tag: str, sources: dict[str, Source],
           kernel: Kernel, bundle: Path, engine: Path, airplay2: tuple[Path, Path],
           wakeword: tuple[Path, Path], tarball: Path, run: Path) -> list[dict]:
    inputs = builder.inputs
    log = builder.log
    images = builder.build_dir / 'images'
    checks: list[dict] = []

    def check(name: str, ok: bool, detail: str = '') -> None:
        checks.append({'check': name, 'ok': bool(ok), 'detail': detail})
        log.line('PASS' if ok else 'FAIL', name + (f' ({detail})' if detail else ''))

    log.phase('verification')
    boot = images / 'boot-lidar-v2.img'
    for name in ('dev', 'v2'):
        image = images / f'boot-lidar-{name}.img'
        check(f'boot-lidar-{name}.img is 16 MiB',
              image.stat().st_size == BOOT_SIZE, f'{image.stat().st_size} bytes')
        with open(image, 'rb') as handle:
            magic = handle.read(8)
        check(f'boot-lidar-{name}.img has the ANDROID! magic', magic == b'ANDROID!')

    members = cpio_members(images / 'boot-lidar-v2.ramdisk.cpio.xz')
    key_entry = find_member(members, 'ota-public-key.hex')
    key_text = key_entry[1].decode('ascii', 'replace') if key_entry else ''
    want_key = inputs.path('ota_public_key').read_text(encoding='ascii').strip()
    check('ramdisk carries the lab OTA public key',
          key_text.strip() == want_key, key_text.strip()[:16])
    target_entry = find_member(members, 'etc/libreecho/target')
    target_text = target_entry[1].decode('ascii', 'replace') if target_entry else ''
    first_line = target_text.splitlines()[0] if target_text else ''
    check('ramdisk target identity is target_id=lidar', first_line == 'target_id=lidar',
          first_line)
    esphomed = member_sha(members, 'usr/local/sbin/libreecho-esphomed')
    bundle_esphomed = sha256_file(bundle / 'sbin/libreecho-esphomed')
    check('ramdisk esphomed matches the UI bundle', esphomed == bundle_esphomed,
          str(esphomed)[:16] if esphomed else 'missing')

    ui_fields = {}
    for line in (bundle / 'share/libreecho/ui-manifest.txt').read_text(
            encoding='utf-8').splitlines():
        if '=' in line:
            key, value = line.split('=', 1)
            ui_fields[key] = value
    check('UI manifest source_commit is the lock UI head',
          ui_fields.get('source_commit') == sources['ui'].head,
          str(ui_fields.get('source_commit'))[:10])
    check('UI manifest source_diff_sha256 is the clean tree',
          ui_fields.get('source_diff_sha256') == inputs.value('empty_tree_sha256'))

    manifest = read_json(images / 'boot-lidar-v2.manifest.json')
    inputs_block = manifest.get('inputs', {})
    check('image manifest kernel Image matches the build kernel',
          inputs_block.get('kernel_image', {}).get('sha256') == sha256_file(kernel.image))
    check('image manifest DTB matches the build DTB',
          inputs_block.get('dtb', {}).get('sha256') == sha256_file(kernel.dtb))
    check('image manifest is the ota/production image',
          manifest.get('image_profile') == 'ota'
          and manifest.get('service_profile') == 'production')

    dtb_log = builder.build_dir / 'verify-lidar-dtb.log'
    rc, output = log.capture_status(
        [sys.executable,
         sources['platform'].path / 'tools/mt8167-arm64/verify_lidar_dtb.py', kernel.dtb],
        step_log=dtb_log)
    check('verify_lidar_dtb.py passes', rc == 0,
          output.strip().splitlines()[-1] if output.strip() else '')

    image_log = (images / 'verify.log').read_text(encoding='utf-8', errors='replace')
    contract = image_log.count('lidar_recovery_image_contract=PASS')
    check('lidar_recovery_image_contract=PASS for dev, v2', contract == 2,
          f'{contract}/2')

    qemu = inputs.path('qemu_arm')
    verifier = inputs.path('update_verify')
    musl_lib = inputs.dir('musl_toolchain_lib')
    run_manifest = run / 'target.manifest'
    plan = read_json(run / 'feature-plan.json')
    check('target plan board is lidar', plan.get('board') == 'lidar',
          str(plan.get('board')))
    check('target plan version is the build version', plan.get('version') == version,
          str(plan.get('version')))

    with tarfile.open(tarball) as archive:
        names = [member.name for member in archive.getmembers()]
        check('OTA tar holds manifest, manifest.sig and boot.img',
              names == ['manifest', 'manifest.sig', 'boot.img'], ','.join(names))
        tar_manifest = archive.extractfile('manifest').read()
        tar_signature = archive.extractfile('manifest.sig').read()
        tar_boot = archive.extractfile('boot.img').read()
    check('OTA tar manifest is the run target.manifest',
          tar_manifest == run_manifest.read_bytes())
    check('OTA tar boot.img matches the built v2 image', tar_boot == boot.read_bytes())

    verify_dir = builder.build_dir / 'verify'
    verify_dir.mkdir(parents=True, exist_ok=True)
    gen_manifest = verify_dir / 'manifest'
    gen_signature = verify_dir / 'manifest.sig'
    gen_manifest.write_bytes(tar_manifest)
    gen_signature.write_bytes(tar_signature)

    def signature_ok(key_path: Path) -> bool:
        return subprocess.run([str(qemu), '-L', str(musl_lib), str(verifier),
                               str(key_path), str(gen_manifest), str(gen_signature)],
                              capture_output=True, check=False).returncode == 0

    check('OTA signature verifies with the lab key',
          signature_ok(inputs.path('ota_public_key')))
    old_key = builder.build_dir / 'verify/old-key.hex'
    old_key.write_text(inputs.value('old_ota_public_key') + '\n', encoding='ascii')
    check('OTA signature is rejected with the old key', not signature_ok(old_key))

    manifest_lines = tar_manifest.decode('ascii')
    check(f'OTA manifest release={tag}',
          f'\nrelease={tag}\n' in '\n' + manifest_lines + '\n', tag)
    check(f'OTA manifest version={version}',
          f'\nversion={version}\n' in '\n' + manifest_lines + '\n')
    check('OTA manifest transaction id is the plan transaction',
          f'\ntransaction_id={plan.get("transaction_id")}\n'
          in '\n' + manifest_lines + '\n', str(plan.get('transaction_id')))
    boot_line = re.search(r'^boot_sha256=(\S+)$', manifest_lines, re.M)
    check('OTA manifest boot_sha256 is the v2 image',
          bool(boot_line) and boot_line.group(1) == sha256_file(boot))

    assets = run / 'ota-assets'
    records = plan.get('features', [])
    order = [record.get('feature_id') for record in records]
    check('target plan names the five product features in order',
          order == list(FEATURE_ORDER), ','.join(str(item) for item in order))
    if order != list(FEATURE_ORDER):
        raise Fail('target plan does not name the five product features in order')
    by_feature = {record['feature_id']: record for record in records}
    for feature in FEATURE_ORDER:
        record = by_feature.get(feature, {})
        payload = assets / str(record.get('asset'))
        identity_path = assets / str(record.get('manifest_asset'))
        check(f'OTA {feature} payload matches the plan',
              payload.is_file() and sha256_file(payload) == record.get('sha256')
              and payload.stat().st_size == record.get('size'))
        check(f'OTA {feature} manifest matches the plan',
              identity_path.is_file()
              and sha256_file(identity_path) == record.get('manifest_sha256')
              and identity_path.stat().st_size == record.get('manifest_size'))

    airplay2_payload = assets / by_feature['airplay2']['asset']
    airplay2_manifest = assets / by_feature['airplay2']['manifest_asset']
    wake_payload = assets / by_feature['wakeword']['asset']
    wake_identity = assets / by_feature['wakeword']['manifest_asset']
    check('OTA airplay2 payload is the built payload',
          sha256_file(airplay2_payload) == sha256_file(airplay2[0]))
    check('OTA airplay2 manifest is the built manifest',
          sha256_file(airplay2_manifest) == sha256_file(airplay2[1]))
    check('airplay2 payload carries the pinned sendspind',
          unsquashfs_sha(builder, airplay2[0], 'usr/local/sbin/libreecho-sendspind')
          == inputs.files['sendspind']['sha256'])
    engine_sha = sha256_file(engine)
    check('airplay2 payload engine is the fresh build',
          unsquashfs_sha(builder, airplay2[0], 'usr/local/sbin/libreecho-audio-engine')
          == engine_sha)
    engine_record = (builder.build_dir / 'engine/sources.sha256').read_text(encoding='utf-8')
    recorded = {}
    for line in engine_record.splitlines():
        if '  ' in line:
            digest, path = line.split('  ', 1)
            recorded[path] = digest
    audio_engine_src = sources['platform'].path / 'tools/mt8163-arm32/airplay/audio_engine.c'
    check('engine source hash recorded for audio_engine.c',
          recorded.get(rel_to_ws(audio_engine_src)) == sha256_file(audio_engine_src))

    check('OTA wakeword payload is the pinned payload',
          sha256_file(wake_payload) == inputs.files['wakeword_payload']['sha256'])
    check('OTA wakeword manifest is the pinned manifest',
          sha256_file(wake_identity) == inputs.files['wakeword_manifest']['sha256'])
    check('OTA wakeword waked is the pinned waked',
          unsquashfs_sha(builder, wake_payload, 'usr/local/sbin/libreecho-waked')
          == inputs.files['wakeword_waked']['sha256'])
    identity = read_json(wake_identity)
    check('wakeword manifest identifies its payload',
          identity.get('payload', {}).get('sha256')
          == inputs.files['wakeword_payload']['sha256']
          and identity.get('feature_id') == 'wakeword'
          and identity.get('schema_version') == 1)
    check('OTA manifest wakeword daemon hash',
          f'\nfeature_wakeword_daemon_sha256='
          f'{inputs.files["wakeword_waked"]["sha256"]}\n' in '\n' + manifest_lines + '\n')
    check('OTA manifest airplay2 daemon hash is the engine',
          f'\nfeature_airplay2_daemon_sha256={engine_sha}\n' in '\n' + manifest_lines + '\n')

    release_check = sources['libreecho'].path / 'tools/check-release-components.py'
    release_log = builder.build_dir / 'check-release-components.log'
    rc, output = log.capture_status(
        [sys.executable, '-B', release_check, '--target', 'lidar',
         '--artifacts', tarball, '--artifacts', boot],
        step_log=release_log)
    check('check-release-components --target lidar passes', rc == 0,
          output.strip().splitlines()[-1] if output.strip() else '')

    return checks


# --------------------------------------------------------------------------
# build driver


def next_version(builds_dir: Path) -> str:
    found: list[tuple[int, int, int]] = []
    roots = [ROOT / builds_dir, ROOT / 'private/artifacts/phase-07',
             ROOT / 'private/lab/phase-07']
    for root in roots:
        if not root.is_dir():
            continue
        for entry in root.iterdir():
            for match in VERSION_FULL_RE.finditer(entry.name):
                found.append((int(match.group(1)), int(match.group(2)),
                              int(match.group(3))))
    if not found:
        raise Fail('no existing lab OTA version found; pass --version X.Y.Z')
    major, minor, patch = max(found)
    return f'{major}.{minor}.{patch + 1}'


def deliverable_files(build_dir: Path) -> list[Path]:
    patterns = (
        'images/boot-lidar-*.img', 'images/boot-lidar-*.manifest.json',
        'images/boot-lidar-*.ramdisk.cpio.xz', 'images/SHA256SUMS',
        'ota/*.ota.tar', 'ota/feature-candidate-catalog.json',
        'ota/run/target.manifest', 'ota/run/feature-plan.json',
        'ota/run/feature-assets.json', 'ota/run/ota-assets/*',
        'features/airplay2/probe.payload.squashfs',
        'features/airplay2/probe.manifest.json',
        'engine/libreecho-audio-engine', 'engine/sources.sha256',
        'check-release-components.log', 'verify-lidar-dtb.log',
    )
    files: list[Path] = []
    for pattern in patterns:
        files.extend(sorted(build_dir.glob(pattern)))
    return files


def cmd_build(args) -> int:
    config = read_json(ROOT / CONFIG_REL)
    if config.get('schema_version') != 1:
        raise Fail(f'{CONFIG_REL}: unsupported schema_version '
                   f'{config.get("schema_version")}')
    builds_dir = workspace_path(config['builds_dir'])
    version = args.version or next_version(Path(config['builds_dir']))
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise Fail(f'version {version!r} is not MAJOR.MINOR.PATCH')
    build_dir = builds_dir / f'v{version}'
    if build_dir.exists() and any(build_dir.iterdir()):
        raise Fail(f'{rel_to_ws(build_dir)} already exists and is not empty')
    build_dir.mkdir(parents=True, exist_ok=True)
    log = BuildLog(build_dir / 'build.log')
    try:
        log.phase(f'lab OTA v{version}')
        inputs = Inputs(config)
        if args.lock:
            lock_path = workspace_path(args.lock)
        else:
            lock_path = ROOT / LOCK_REL
        if not args.no_integrate:
            integrate = ROOT / INTEGRATE_REL
            if not integrate.is_file():
                raise Fail(f'{INTEGRATE_REL} is missing; use --no-integrate with --lock')
            log.phase('integration rebuild')
            log.run([sys.executable, integrate, 'rebuild', '--only-in-ota'], cwd=ROOT)
            log.run([sys.executable, integrate, 'check-lock'], cwd=ROOT)
        log.phase('lock')
        lock = read_json(lock_path)
        if lock.get('schema_version') != 1:
            raise Fail(f'{rel_to_ws(lock_path)}: unsupported schema_version')
        log.line('INFO', f'lock {rel_to_ws(lock_path)} generated '
                         f'{lock.get("generated")}')
        sources = load_sources(lock, log)
        inputs.verify(log)
        builder = Builder(build_dir, log, inputs, config)

        if args.kernel_prebuilt:
            kernel = prebuilt_kernel(builder, sources,
                                     workspace_path(args.kernel_prebuilt))
        else:
            kernel = build_kernel(builder, sources)
        kernel.validate()

        bundle, bundle_sha = build_ui(builder, sources)
        images = build_images(builder, sources, kernel, bundle)
        engine = build_engine(builder, sources)
        airplay2 = build_airplay2(builder, sources, engine)
        wakeword = stage_wakeword(builder)
        catalog = write_catalog(builder, airplay2, wakeword)
        tag = release_tag(lock, version)
        tarball, transaction, run = create_ota(builder, version, tag, catalog, sources)

        checks = verify(builder, version, tag, sources, kernel, bundle, engine,
                        airplay2, wakeword, tarball, run)

        deliverables = deliverable_files(build_dir)
        sums_path = build_dir / 'SHA256SUMS'
        sums_path.write_text(''.join(
            f'{sha256_file(path)}  {path.relative_to(build_dir).as_posix()}\n'
            for path in deliverables), encoding='utf-8')
        rc, output = log.capture_status(['sha256sum', '--quiet', '-c',
                                         sums_path.name], cwd=build_dir)
        checks.append({'check': 'SHA256SUMS matches the deliverables',
                       'ok': rc == 0, 'detail': output.strip()[:120]})
        log.line('PASS' if rc == 0 else 'FAIL', 'SHA256SUMS matches the deliverables')
        failures = [item for item in checks if not item['ok']]
        outputs = {path.relative_to(build_dir).as_posix(): sha256_file(path)
                   for path in deliverables}

        provenance = {
            'schema_version': 1,
            'generated': now_iso(),
            'version': version,
            'release': tag,
            'build_dir': rel_to_ws(build_dir),
            'tool': {'path': rel_to_ws(Path(__file__)), 'sha256': sha256_file(Path(__file__))},
            'config': {'path': CONFIG_REL, 'sha256': sha256_file(ROOT / CONFIG_REL)},
            'manifest': {'path': MANIFEST_REL,
                         'sha256': sha256_file(ROOT / MANIFEST_REL)
                         if (ROOT / MANIFEST_REL).is_file() else None},
            'lock': {'path': rel_to_ws(lock_path),
                     'sha256': sha256_file(lock_path),
                     'generated': lock.get('generated'),
                     'document': lock},
            'sources': {role: source.record() for role, source in sources.items()},
            'kernel': kernel.record(),
            'ui': {'head': sources['ui'].head, 'bundle_manifest_sha256': bundle_sha},
            'inputs': inputs.input_manifest(),
            'ota': {'transaction_id': transaction,
                    'release': tag,
                    'bundle': tarball.relative_to(build_dir).as_posix(),
                    'run_dir': run.relative_to(build_dir).as_posix(),
                    'bundle_sha256': sha256_file(tarball)},
            'outputs': outputs,
            'verification': {'checks': checks, 'failed': len(failures),
                             'dropped_checks': list(DROPPED_CHECKS)},
            'log_files': [path.relative_to(build_dir).as_posix()
                          for path in sorted(build_dir.rglob('*.log'))],
            'notes': [
                'Built from the integration worktrees named in the lock; no topic '
                'branch or fork checkout was used.',
                'A build from the new integration kernel is untested on hardware.'
                if kernel.mode == 'built' else
                'Kernel is a pinned prebuilt: it was NOT built from the '
                'integration Linux worktree and is untested on hardware.',
            ],
        }
        write_json(build_dir / 'provenance.json', provenance)
        log.phase('result')
        log.line('INFO', f'build {rel_to_ws(build_dir)}')
        log.line('INFO', f'kernel {kernel.mode} Image {sha256_file(kernel.image)[:16]} '
                         f'DTB {sha256_file(kernel.dtb)[:16]}')
        log.line('INFO', f'ota tx {transaction} '
                         f'bundle {sha256_file(tarball)[:16]}')
        log.line('INFO', f'verification: {len(checks) - len(failures)} passed, '
                         f'{len(failures)} failed')
        if failures:
            log.line('FAIL', 'build finished with failing checks; see '
                             f'{rel_to_ws(build_dir / "build.log")}')
            return 1
        return 0
    finally:
        log.close()


class Builder:
    """Bag of paths the build steps need."""

    def __init__(self, build_dir: Path, log: BuildLog, inputs: Inputs, config: dict):
        self.build_dir = build_dir
        self.log = log
        self.inputs = inputs
        self.config = config


# --------------------------------------------------------------------------
# deploy


class Adb:
    def __init__(self, binary: Path, host: str, log: BuildLog, out_dir: Path):
        self.binary = str(binary)
        self.host = host
        self.log = log
        self.out_dir = out_dir
        self.out_dir.mkdir(parents=True, exist_ok=True)

    def run(self, *args: str, timeout: int = 120, step_log: str | None = None) -> str:
        cmd = [self.binary, '-s', self.host, *args]
        proc = subprocess.run(cmd, capture_output=True, text=True, errors='replace',
                              timeout=timeout, check=False)
        output = proc.stdout + proc.stderr
        if step_log:
            (self.out_dir / step_log).write_text(output, encoding='utf-8')
        return output

    def connect(self) -> None:
        proc = subprocess.run([self.binary, 'connect', self.host], capture_output=True,
                              text=True, timeout=20, check=False)
        (self.out_dir / 'connect.log').write_text(proc.stdout + proc.stderr,
                                                  encoding='utf-8')

    def shell(self, command: str, timeout: int = 120,
              step_log: str | None = None) -> str:
        return self.run('shell',
                        'export PATH=/sbin:/usr/sbin:/usr/local/sbin:$PATH; ' + command,
                        timeout=timeout, step_log=step_log)

    def push(self, local: Path, remote: str, timeout: int = 900) -> None:
        output = self.run('push', str(local), remote, timeout=timeout)
        self.log.line('INFO', f'push {local.name}: {output.strip().splitlines()[-1]}')


def slot_of(adb: Adb) -> str:
    output = adb.shell("tr ' ' '\\n' < /proc/cmdline | "
                       "sed -n 's/^androidboot.slot_suffix=_//p'", timeout=20)
    for line in output.splitlines():
        line = line.strip()
        if line in ('a', 'b'):
            return line
    return ''


def reconnect(adb: Adb, seconds: int) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        adb.connect()
        if 'device' in adb.run('get-state', timeout=15):
            return True
        time.sleep(5)
    return False


def cmd_deploy(args) -> int:
    config = read_json(ROOT / CONFIG_REL)
    inputs = Inputs(config)
    version = args.version
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise Fail(f'version {version!r} is not MAJOR.MINOR.PATCH')
    build_dir = workspace_path(config['builds_dir']) / f'v{version}'
    provenance = read_json(build_dir / 'provenance.json')
    if provenance.get('version') != version:
        raise Fail(f'{rel_to_ws(build_dir)} provenance is for '
                   f'{provenance.get("version")}, not {version}')
    host = args.host or os.environ.get('LAB_DEVICE_HOST') or os.environ.get('LIDAR_WIFI')
    if not host:
        raise Fail('no device host: pass --host HOST or set LAB_DEVICE_HOST')
    banner = (
        '\n'
        '!!!!! DEPLOY WRITES THE DEVICE AND REBOOTS IT !!!!!\n'
        f'Build v{version} will be installed on {host}:\n'
        '  - pushes the signed OTA bundle and its content-addressed feature assets\n'
        '    into /data/libreecho/update/asset-cache/ and assembles the generation\n'
        '    on the device (offline: every asset is already cached),\n'
        '  - runs `libreecho-update install` (writes the INACTIVE boot slot),\n'
        '  - reboots the device and waits for the new slot to confirm.\n'
        f'provenance: {rel_to_ws(build_dir / "provenance.json")}\n'
        'Re-run with --yes to proceed.\n'
    )
    print(banner)
    if not args.yes:
        return 2
    for rel, digest in sorted(provenance['outputs'].items()):
        path = build_dir / rel
        if not path.is_file() or sha256_file(path) != digest:
            raise Fail(f'built file changed or missing: {rel}')
    print('local deliverables match provenance.json\n')

    log = BuildLog(build_dir / 'deploy.log')
    try:
        adb_binary = inputs.path('adb')
        if not adb_binary.is_file():
            found = shutil.which('adb')
            if not found:
                raise Fail('adb not found (pinned path and PATH)')
            adb_binary = Path(found)
        out = build_dir / 'deploy'
        adb = Adb(adb_binary, host, log, out)
        log.phase(f'deploy v{version} to {host}')
        adb.connect()
        log.write(adb.run('devices', '-l', step_log='devices.log'))
        start = slot_of(adb)
        if not start:
            raise Fail('no Wi-Fi adb connection to the device')
        target = 'b' if start == 'a' else 'a'
        txn = provenance['ota']['transaction_id']
        run = build_dir / provenance['ota']['run_dir']
        tarball = build_dir / provenance['ota']['bundle']
        inventory = read_json(run / 'feature-assets.json').get('assets', [])
        if len(inventory) != 2 * len(FEATURE_ORDER):
            raise Fail(f'{rel_to_ws(run)} lists {len(inventory)} assets, '
                       f'expected {2 * len(FEATURE_ORDER)}')
        # The device assembles the generation from the signed manifest and the
        # content-addressed cache, so it needs the control members as files.
        incoming = build_dir / 'ota/incoming'
        incoming.mkdir(parents=True, exist_ok=True)
        with tarfile.open(tarball) as archive:
            (incoming / 'manifest').write_bytes(archive.extractfile('manifest').read())
            (incoming / 'manifest.sig').write_bytes(
                archive.extractfile('manifest.sig').read())
        log.line('INFO', f'start slot {start}; target slot {target}; tx {txn}')
        adb.shell('uname -a; tr " " "\\n" < /proc/cmdline; '
                  'cat /proc/sys/kernel/random/boot_id; libreecho-bootctl status; '
                  'libreecho-update status; '
                  'echo current=$(cat /data/libreecho/update/current 2>/dev/null)',
                  step_log='state-before.log')
        adb.shell('mkdir -p /data/libreecho/update/asset-cache '
                  '/data/libreecho/incoming/local-manifest')
        adb.push(incoming / 'manifest',
                 '/data/libreecho/incoming/local-manifest/manifest')
        adb.push(incoming / 'manifest.sig',
                 '/data/libreecho/incoming/local-manifest/manifest.sig')
        for item in inventory:
            adb.push(run / 'ota-assets' / item['name'],
                     f'/data/libreecho/update/asset-cache/{item["sha256"]}.part')
        assemble = adb.shell(
            'libreecho-update-fetch assemble-generation '
            '/data/libreecho/incoming/local-manifest/manifest '
            '/data/libreecho/incoming/local-manifest/manifest.sig; '
            'echo assemble_rc=$?', timeout=1800, step_log='assemble.log')
        log.write(assemble)
        if 'assemble_rc=0' not in assemble:
            raise Fail('libreecho-update-fetch assemble-generation failed; '
                       'see deploy/assemble.log')
        # Assembly reclaims every regular file in incoming/ (libreecho-generation
        # reclaim-incoming), so the bundle can only be pushed once it has finished.
        adb.push(tarball, '/data/libreecho/incoming/local-install.ota.tar')
        install = adb.shell(
            'libreecho-update install /data/libreecho/incoming/local-install.ota.tar; '
            'echo install_rc=$?\n'
            'sync; libreecho-bootctl status', timeout=1800, step_log='install.log')
        log.write(install)
        if 'install_rc=0' not in install:
            raise Fail('libreecho-update install failed; see deploy/install.log')
        adb.shell('reboot', timeout=20)
        log.line('INFO', 'reboot requested')
        if not reconnect(adb, 1200):
            raise Fail('no adb after reboot')
        log.line('INFO', f'adb back on slot {slot_of(adb)}')
        deadline = time.time() + 1200
        confirmed = False
        while time.time() < deadline:
            state = adb.shell('tr " " "\\n" < /proc/cmdline; libreecho-update status', 20)
            with open(out / 'polls.log', 'a', encoding='utf-8') as handle:
                handle.write(f'== {now_iso()}\n{state}')
            slot = ''
            for line in state.splitlines():
                if line.startswith('androidboot.slot_suffix=_'):
                    slot = line.split('=', 1)[1]
            fields = dict(line.split('=', 1) for line in state.splitlines() if '=' in line)
            if slot == target and fields.get('state') == 'installed' \
                    and fields.get('generation') == txn \
                    and fields.get('current') == txn:
                (out / 'state-after.log').write_text(state, encoding='utf-8')
                log.line('PASS', f'CONFIRMED slot {slot} state installed tx {txn}')
                confirmed = True
                break
            time.sleep(15)
        if not confirmed:
            raise Fail('new slot did not confirm within 20 minutes; see deploy/polls.log')
        want_boot = sha256_file(build_dir / 'images/boot-lidar-v2.img')
        post = adb.shell(
            'for p in 10 11; do printf "mmcblk0p%s " $p; '
            'dd if=/dev/mmcblk0p$p bs=4096 count=4096 2>/dev/null | sha256sum; done\n'
            'echo "== services"\n'
            'ps | grep -E "libreecho-(web|airplayd|btd|timed|micd|waked|esphomed|'
            'audiod|sendspind)" | grep -v grep\n'
            'echo "== uname"; uname -a; echo "== pstore"; ls /sys/fs/pstore 2>/dev/null',
            timeout=180, step_log='post-check.log')
        log.write(post)
        readback = re.findall(r'^mmcblk0p1[01] ([0-9a-f]{64})', post, re.M)
        boot_matches = want_boot in readback
        log.line('PASS' if boot_matches else 'WARN',
                 f'slot boot readback {"matches" if boot_matches else "does not match"} '
                 f'{want_boot[:16]}')
        log.line('INFO', f'deploy logs: {rel_to_ws(out)}')
        return 0 if boot_matches else 1
    finally:
        log.close()


# --------------------------------------------------------------------------


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description='Build and deploy the Lidar lab OTA from the integration branches.',
        allow_abbrev=False)
    sub = parser.add_subparsers(dest='command', required=True)
    build = sub.add_parser('build', help='rebuild integration and build the OTA',
                           allow_abbrev=False)
    build.add_argument('--version', help='OTA version MAJOR.MINOR.PATCH '
                                         '(default: highest lab version + 1 patch)')
    build.add_argument('--no-integrate', action='store_true',
                       help='do not run tools/integrate.py rebuild/check-lock')
    build.add_argument('--lock', help='read this lock instead of '
                                      'private/integration/integration.lock.json '
                                      '(implies --no-integrate)')
    build.add_argument('--kernel-prebuilt', metavar='DIR',
                       help='use DIR/{Image,config,libreecho-lidar.dtb} instead of '
                            'building the kernel from the integration worktree')
    deploy = sub.add_parser('deploy', help='install a built OTA on the device',
                            allow_abbrev=False)
    deploy.add_argument('version', help='built version, e.g. 0.2.38')
    deploy.add_argument('--host', help='device adb host:port (or $LAB_DEVICE_HOST)')
    deploy.add_argument('--yes', action='store_true',
                        help='confirm writing the inactive boot slot and rebooting')
    args = parser.parse_args(argv)
    try:
        if args.command == 'build':
            if args.lock:
                args.no_integrate = True
            return cmd_build(args)
        return cmd_deploy(args)
    except Fail as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1
    except subprocess.TimeoutExpired as exc:
        print(f'ERROR: command timed out: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
