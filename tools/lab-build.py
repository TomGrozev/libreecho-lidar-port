#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Build and deploy a Lidar image with the product build.

`build` rebuilds the per-repo `integration` branches (tools/integrate.py),
checks the lock, refuses a dirty or missing integration worktree, and then runs
the product's own Lidar build from the integrated LibreEcho checkout:

    work/integration/LibreEcho/build/build.sh --target lidar --profile ota --no-publish

The product build is the only Lidar build; this tool supplies its environment
from `work/inputs`, `work/product-build` and the paths in `private/local.json`,
then copies the immutable product run into `work/builds/v<version>/` with
`SHA256SUMS` and `provenance.json`.

`deploy` installs a finished build over Wi-Fi.  It writes the device's inactive
boot slot and reboots the device; it therefore needs --yes and an explicit host
(or `device_host` in private/local.json).

`build` runs the product build inside the pinned `libreecho-build` container
image by default, so the host toolchain does not matter. `--no-container`
builds with the host toolchain instead; `LIBREECHO_BUILD_IMAGE` selects another
image. The cluster workflow runs `build --no-container` inside that image and
`ci-setup` first points `work` at the persistent `/lab-cache`.

`push` is the one command the maintainer runs from Coder: it pushes the topic
branches to each fork and the port's `main`, then dispatches the cluster
workflow. `fetch` downloads that run's public artifact, verifies `SHA256SUMS`
and installs it as `work/builds/v<version>/`. The artifact carries only the OTA
bundle and the records; the product run directory stays on the runner.

usage:
  tools/lab-build.py ci-setup --work-root /lab-cache [--workspace DIR]
  tools/lab-build.py build [--version X.Y.Z] [--no-integrate] [--lock PATH]
                           [--no-container] [--workspace DIR] [--rebuild]
                           [--stock-boot PATH] [--ota-signing-key PATH]
                           [--ota-public-key PATH]
  tools/lab-build.py push [--force] [--version X.Y.Z] [--workspace DIR]
  tools/lab-build.py fetch [RUN-ID|latest] [--workspace DIR]
  tools/lab-build.py deploy VERSION --host HOST --yes [--workspace DIR]

`--lock PATH` skips `tools/integrate.py` and reads a hand-written lock instead.
The version defaults to the highest existing build under work/builds plus one
patch; the first build on an empty cache needs `--version` (the workflow asks
for it too). A successful attempt whose source id matches the lock is reused
unless `--rebuild` is passed; failed attempts stay under work/builds for
inspection and the five newest are kept.
"""

from __future__ import annotations

import argparse
import datetime
import fcntl
import hashlib
import json
import os
import re
import shlex
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
LOCK_REL = 'work/integration/integration.lock.json'
INTEGRATE_REL = 'tools/integrate.py'
LOCAL_REL = 'private/local.json'
WORK_REL = 'work'

# The cluster workflow and its artifact. `push` dispatches it; `fetch` reads it.
CI_WORKFLOW = 'lab-build.yml'
CI_ARTIFACT = 'libreecho-lidar-ota'
CI_SUMS_FILE = 'SHA256SUMS'
CI_PROVENANCE_FILE = 'provenance.json'

VERSION_FULL_RE = re.compile(r'(\d+)\.(\d+)\.(\d+)')
SOURCE_REPOS = ('LibreEcho', 'LibreEcho-Platform', 'LibreEcho-Linux', 'LibreEcho-UI')
DEFAULT_IMAGE_NAME = 'ghcr.io/tomgrozev/libreecho-build'
LOCAL_IMAGE = 'libreecho-build:local'
SOURCE_ID_RE = re.compile(r'^[0-9a-f]{16}$')
ATTEMPT_KEEP = 5


def set_workspace(root: Path) -> None:
    """Point every derived path at `root` (the repo checkout by default)."""
    global ROOT, INPUTS, PUBLIC_DEPS, AARCH64_ROOT, ARMHF_ROOT, MUSL_ROOT
    global BUILD_ROOT, MBEDTLS_VENV, OTA_GATE_PYTHON, BUILD_LOCK
    ROOT = root.resolve()
    INPUTS = ROOT / 'work/inputs'
    PUBLIC_DEPS = INPUTS / 'public-deps'
    AARCH64_ROOT = INPUTS / 'aarch64-root'
    ARMHF_ROOT = INPUTS / 'armhf-root'
    MUSL_ROOT = INPUTS / 'toolchain'
    BUILD_ROOT = ROOT / 'work/product-build'
    MBEDTLS_VENV = BUILD_ROOT / 'mbedtls-build-venv'
    OTA_GATE_PYTHON = BUILD_ROOT / 'ota-gate-python'
    BUILD_LOCK = ROOT / 'work/builds/.build.lock'


# Paths `tools/workspace.py init` stages; the product build reads them through
# the same variables the hosted release job sets.
INPUTS = ROOT / 'work/inputs'
PUBLIC_DEPS = INPUTS / 'public-deps'
AARCH64_ROOT = INPUTS / 'aarch64-root'
ARMHF_ROOT = INPUTS / 'armhf-root'
MUSL_ROOT = INPUTS / 'toolchain'
BUILD_ROOT = ROOT / 'work/product-build'
MBEDTLS_VENV = BUILD_ROOT / 'mbedtls-build-venv'
# The reviewed PyNaCl closure the product's OTA gate steps import; staged from
# the wheelhouse because the 3.11 in the build image carries no site packages.
OTA_GATE_PYTHON = BUILD_ROOT / 'ota-gate-python'
# The build lock: an fcntl.flock under work/builds, not a pid file, so a stale
# lock cannot outlive its build.
BUILD_LOCK = ROOT / 'work/builds/.build.lock'
CONTAINER_ID = 1000

# The product's whole-target contract fixes the five feature ids and their order.
FEATURE_ORDER = ('airplay2', 'tts', 'wakeword', 'stt', 'assistant')

LOCAL_INPUT_KEYS = ('stock_boot', 'ota_signing_key', 'ota_public_key')


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


def rel_to_ws(path: Path) -> str:
    """Workspace-relative path when possible, otherwise the absolute path."""
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def now_iso() -> str:
    return (datetime.datetime.now(datetime.UTC)
            .replace(microsecond=0).isoformat().replace('+00:00', 'Z'))


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise Fail(f'cannot read JSON {rel_to_ws(path)}: {exc}') from exc


def write_json(path: Path, doc: dict) -> None:
    path.write_text(json.dumps(doc, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def workspace_path(value: str) -> Path:
    path = Path(value).expanduser()
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
        return rc

    def close(self) -> None:
        self.handle.close()


# --------------------------------------------------------------------------
# private local inputs


def load_local(require_owner_inputs: bool = True,
               overrides: dict | None = None) -> dict:
    """Read private/local.json and resolve the local input paths it names.

    `overrides` maps a LOCAL_INPUT_KEYS name to an explicit path, winning over
    the file so a headless run need not write private/local.json.
    """
    overrides = {key: value for key, value in (overrides or {}).items() if value}
    path = ROOT / LOCAL_REL
    if not path.is_file() and not overrides:
        raise Fail(f'{LOCAL_REL} is missing; run `python3 tools/workspace.py keygen` '
                   f'and then `python3 tools/workspace.py doctor`')
    doc = read_json(path) if path.is_file() else {}
    missing = [key for key in LOCAL_INPUT_KEYS
               if key not in overrides and not str(doc.get(key) or '').strip()]
    if missing and require_owner_inputs:
        raise Fail(f'{LOCAL_REL} is missing {", ".join(missing)}; run '
                   f'`python3 tools/workspace.py keygen` to create the OTA key pair, '
                   f'set stock_boot to your boot_a backup, then run '
                   f'`python3 tools/workspace.py doctor`')
    resolved = {'device_host': str(doc.get('device_host') or '').strip()}
    for key in LOCAL_INPUT_KEYS:
        value = overrides.get(key) or str(doc.get(key) or '').strip()
        if not value:
            continue
        resolved[key] = workspace_path(value)
    if require_owner_inputs:
        for key in LOCAL_INPUT_KEYS:
            if not resolved[key].is_file():
                raise Fail(f'{LOCAL_REL}: {key} is missing: {rel_to_ws(resolved[key])}; '
                           f'run `python3 tools/workspace.py doctor`')
    return resolved


def local_input_record(local: dict) -> dict:
    """Identity of the private input files: paths and digests, never their contents."""
    record = {}
    for key in LOCAL_INPUT_KEYS:
        path = local[key]
        record[key] = {'path': rel_to_ws(path), 'sha256': sha256_file(path)}
    return record


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
                       f'{self.entry["integration_path"]}; run '
                       f'`python3 tools/workspace.py init`')
        try:
            actual = git(self.path, 'rev-parse', 'HEAD')
        except Fail as exc:
            raise Fail(f'{self.name}: {self.entry["integration_path"]} is not a '
                       f'git worktree ({exc})') from exc
        if self.head and actual != self.head:
            raise Fail(f'{self.name}: worktree HEAD {actual[:10]} does not match '
                       f'the lock {str(self.head)[:10]}; rerun without --lock')
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
# product build


def source_id(lock: dict) -> str:
    """The identity of the source set: sha256 over the four build heads.

    The version is deliberately not part of it: two builds of the same sources
    share this id, so a successful one can be reused.
    """
    heads = lock['repos']
    try:
        material = ''.join(heads[name]['head'] + '\n' for name in SOURCE_REPOS)
    except KeyError as exc:
        raise Fail(f'lock has no head for {exc.args[0]}') from exc
    return sha256_bytes(material.encode())[:16]


def release_tag(lock: dict, version: str) -> str:
    """The product dev release tag this build publishes under.

    `.github/workflows/build-release.yml:258-265` derives the tag as
    radar-puffin-build-<sha7>-<source_id>-<build_id>: sha7 is the product
    commit, source_id is the sha256 over the product, Platform, Linux and UI
    commit shas, and build_id hashes the CI run.  The lab has no run id, so
    build_id hashes a lab-unique string; build.sh:512 and the TAG grammar in
    ota_v3_product.py:30 pin the shape.
    """
    product = lock['repos']['LibreEcho']['head']
    # Python 3.11 (the interpreter in the build image) rejects a backslash
    # inside an f-string expression, so the version string is built first.
    version_material = f'lab:{version}\n'.encode()
    return (f'radar-puffin-build-{product[:7]}-'
            f'{source_id(lock)}-'
            f'{sha256_bytes(version_material)[:16]}')


def _pick(name: str, default: Path) -> str:
    value = os.environ.get(name)
    return value if value else str(default)


def product_env(local: dict, version: str, tag: str,
                sources: dict[str, Source], mbedtls_python: Path,
                ota_gate_python: Path | None) -> dict[str, str]:
    """The product build environment, mapped from work/inputs and local.json."""
    deps = PUBLIC_DEPS
    kernel_out = BUILD_ROOT / 'kernel'
    env = dict(os.environ)
    env.update({
        'LIBREECHO_BUILD_ROOT': str(BUILD_ROOT),
        'LIBREECHO_KERNEL_OUT': str(kernel_out),
        'LIBREECHO_PRIVATE_ROOT': str(ROOT / 'private'),
        'LIBREECHO_INPUTS_ROOT': str(deps),
        'LIBREECHO_PUBLIC_DEPS_ROOT': str(deps),
        'LIBREECHO_TOOLING_SRC': str(sources['platform'].path),
        'LIBREECHO_KERNEL_SRC': str(sources['linux'].path),
        'LIBREECHO_UI_SRC': str(sources['ui'].path),
        'LIBREECHO_PRODUCT_SRC': str(sources['libreecho'].path),
        'LIBREECHO_COMPONENT_CACHE_ROOT': str(BUILD_ROOT / 'component-cache'),
        'LIBREECHO_REUSE_COMPONENT_CACHE': '1',
        'LIBREECHO_UPDATE_CHANNEL': 'dev',
        'LIBREECHO_OTA_SIGNING_MODE': 'local',
        'LIBREECHO_OTA_FORMAT': 'v3',
        'LIBREECHO_SSH_ENABLED': os.environ.get('LIBREECHO_SSH_ENABLED', '0'),
        # Source offers and the production userdata tree need maintainer-private
        # tooling; the public source tree has no copy of it.
        'LIBREECHO_SOURCE_OFFERS': '0',
        'LIBREECHO_OTA_RELEASE': version,
        'LIBREECHO_TARGET_RELEASE_TAG': tag,
        'LIBREECHO_OTA_EXPECTED_PUBLIC_KEY_SHA256': sha256_file(local['ota_public_key']),
        'LIBREECHO_OTA_SIGNING_KEY': str(local['ota_signing_key']),
        'LIBREECHO_OTA_PUBLIC_KEY': str(local['ota_public_key']),
        'LIBREECHO_LIDAR_STOCK_BOOT': str(local['stock_boot']),

        'CROSS': str(ARMHF_ROOT / 'usr/bin/arm-linux-gnueabihf-'),
        'LIBREECHO_AARCH64_CROSS': str(AARCH64_ROOT / 'usr/bin/aarch64-linux-gnu-'),
        'LIBREECHO_CORE_RUNTIME_SYSROOT': str(ARMHF_ROOT / 'usr/arm-linux-gnueabihf'),
        'LIBREECHO_CORE_GCC_LIBDIR':
            str(ARMHF_ROOT / 'usr/lib/gcc-cross/arm-linux-gnueabihf/13'),
        'AUDIO_CC': str(MUSL_ROOT / 'usr/bin/armv7-alpine-linux-musleabihf-gcc'),
        'LIBREECHO_MUSL_CROSS_PREFIX':
            str(MUSL_ROOT / 'usr/bin/armv7-alpine-linux-musleabihf-'),
        'LIBREECHO_MUSL_SYSROOT': str(MUSL_ROOT),
        'LIBREECHO_OTA_MUSL_NATIVE_ROOT': str(MUSL_ROOT),
        'LIBREECHO_OTA_MUSL_SYSROOT': str(MUSL_ROOT),

        'LIBREECHO_BUSYBOX_SOURCE_ARCHIVE': str(deps / 'busybox-1.37.0.tar.bz2'),
        'LIBREECHO_MUSL_SOURCE_ARCHIVE': str(deps / 'musl-1.2.5.tar.gz'),
        'LIBREECHO_WPA_SUPPLICANT_SOURCE_ARCHIVE':
            str(deps / 'wpa_supplicant-2.10.tar.gz'),
        'LIBREECHO_LIBNL_SOURCE_ARCHIVE': str(deps / 'libnl-3.11.0.tar.gz'),
        'LIBREECHO_WIRELESS_TOOLS_SOURCE_ARCHIVE':
            str(deps / 'wireless-tools_30~pre9.orig.tar.gz'),
        'LIBREECHO_WIRELESS_REGDB_SOURCE_ARCHIVE':
            str(deps / 'wireless-regdb-2025.10.07.tar.xz'),
        'LIBREECHO_LIBSODIUM_SOURCE_ARCHIVE': str(deps / 'libsodium-1.0.18.tar.gz'),
        'LIBREECHO_ADBD_SOURCE': str(deps / 'aosp-system-core'),
        'LIBREECHO_ADBD_KERNEL_HEADERS':
            _pick('LIBREECHO_ADBD_KERNEL_HEADERS', INPUTS / 'kernel-uapi/include'),
        'LIBREECHO_OPUS_ARCHIVES_DIR': str(deps),
        'LIBREECHO_MBEDTLS_SOURCE_ARCHIVE': str(deps / 'mbedtls-3.6.7.tar.bz2'),
        'LIBREECHO_MBEDTLS_BUILD_PYTHON': str(mbedtls_python),

        'LIBREECHO_TTS_NORTHERN_MALE_MODEL': str(deps / 'northern-male.derived.onnx'),
        'LIBREECHO_TTS_FEMALE_MODEL': str(deps / 'southern-female.derived.onnx'),
        'LIBREECHO_TTS_TOKENS': str(deps / 'tts-tokens.txt'),
        'LIBREECHO_STT_MODEL_ROOT': str(deps),
        'LIBREECHO_WAKE_ORT_SOURCE': str(deps / 'onnxruntime-source'),
        'LIBREECHO_WAKE_TFLM_SOURCE': str(deps / 'tflite-micro-source'),
        'LIBREECHO_WAKE_TFLM_FLATBUFFERS_SOURCE': str(deps / 'flatbuffers-source'),
        'LIBREECHO_WAKE_TFLM_KISSFFT_SOURCE': str(deps / 'kissfft-source'),
        'LIBREECHO_WAKE_TFLM_PRINTF_SOURCE': str(deps / 'eyalroz-printf-source'),
        'LIBREECHO_WAKE_MWW_MODELS':
            str(deps / 'micro-wake-word-models-source/models/v2'),
        'LIBREECHO_ORT_BUILD': str(deps / 'neural/onnxruntime-build'),
        'LIBREECHO_ORT_PREFIX': str(deps / 'neural/onnxruntime-prefix'),
        'LIBREECHO_WAKE_FLATBUFFERS_PYTHON': str(deps / 'neural/flatbuffers-python'),
        'LIBREECHO_SHERPA_SOURCE': str(deps / 'sherpa-onnx-source'),
        'LIBREECHO_SHERPA_PREFIX': str(deps / 'neural/sherpa-onnx-prefix'),
        'LIBREECHO_ESPEAK_SOURCE': str(deps / 'espeak-ng-source'),
        'LIBREECHO_TTS_ESPEAK_DATA': str(deps / 'neural/espeak-ng-data'),
        'LIBREECHO_FLITE_SOURCE': str(deps / 'flite-source'),
        'LIBREECHO_FLITE_ROOT': str(deps / 'neural/flite-root'),
        'LIBREECHO_SPEEX_PREFIX': str(deps / 'neural/speexdsp-prefix'),

        'LIBREECHO_OTBR_SOURCE': _pick('LIBREECHO_OTBR_SOURCE',
                                       INPUTS / 'otbr/ot-br-posix'),
        'LIBREECHO_OTBR_DEPS': _pick('LIBREECHO_OTBR_DEPS', INPUTS / 'otbr/deps'),
    })
    if ota_gate_python is not None:
        existing_pythonpath = os.environ.get('PYTHONPATH')
        parts = [str(ota_gate_python)]
        if existing_pythonpath:
            parts.append(existing_pythonpath)
        env['PYTHONPATH'] = ':'.join(parts)
    return env


def product_args(config: dict) -> list[str]:
    values = config.get('values', {})
    return ['--target', values.get('target', 'lidar'),
            '--profile', values.get('profile', 'ota'),
            '--no-publish']


def run_dir_from_log(log_path: Path) -> Path:
    """The immutable product run build.sh reported at the end of its output."""
    try:
        text = log_path.read_text(encoding='utf-8', errors='replace')
    except OSError as exc:
        raise Fail(f'cannot read {rel_to_ws(log_path)}: {exc}') from exc
    runs = re.findall(r'^run=(.+)$', text, re.M)
    if not runs:
        raise Fail(f'{rel_to_ws(log_path)} has no `run=` line; the product build '
                   'did not finish')
    run = Path(runs[-1].strip())
    expected = (BUILD_ROOT / 'out/runs').resolve()
    try:
        run.resolve().relative_to(expected)
    except ValueError as exc:
        raise Fail(f'product run {run} is outside {rel_to_ws(expected)}') from exc
    if not run.is_dir():
        raise Fail(f'product run directory is missing: {run}')
    return run


def collect_run(run_dir: Path, build_dir: Path) -> Path:
    """Copy the immutable product run into the versioned build directory."""
    destination = build_dir / 'run'
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(run_dir, destination, symlinks=True)
    return destination


def write_build_identity(build_dir: Path, provenance: dict) -> dict:
    files = [path for path in sorted(build_dir.rglob('*'))
             if path.is_file() and path.name not in ('SHA256SUMS', 'provenance.json')]
    sums_path = build_dir / 'SHA256SUMS'
    sums_path.write_text(''.join(
        f'{sha256_file(path)}  {path.relative_to(build_dir).as_posix()}\n'
        for path in files), encoding='utf-8')
    outputs = {path.relative_to(build_dir).as_posix(): sha256_file(path)
               for path in files}
    provenance['outputs'] = outputs
    write_json(build_dir / 'provenance.json', provenance)
    return outputs


# --------------------------------------------------------------------------
# build command


def next_version(builds_dir: Path) -> str:
    """Highest version seen under work/builds, plus one patch.

    Both promoted builds (`vX.Y.Z`) and attempts (`<stamp>-vX.Y.Z-<source id>`)
    count, so a run whose sources were never promoted still advances the
    sequence.
    """
    found: list[tuple[int, int, int]] = []
    if builds_dir.is_dir():
        for entry in builds_dir.iterdir():
            for match in VERSION_FULL_RE.finditer(entry.name):
                found.append((int(match.group(1)), int(match.group(2)),
                              int(match.group(3))))
    if not found:
        raise Fail('no existing build version found under work/builds; '
                   'pass --version X.Y.Z')
    major, minor, patch = max(found)
    return f'{major}.{minor}.{patch + 1}'


ATTEMPT_RE = re.compile(r'^\d{8}-\d{6}-v\d+\.\d+\.\d+-[0-9a-f]{16}$')


def attempt_succeeded(attempt: Path) -> bool:
    """Whether an attempt or promoted build recorded every output intact."""
    provenance = attempt / 'provenance.json'
    if not provenance.is_file() or not (attempt / 'SHA256SUMS').is_file():
        return False
    try:
        doc = read_json(provenance)
    except Fail:
        return False
    outputs = doc.get('outputs') or {}
    if not outputs:
        return False
    for rel, digest in outputs.items():
        path = attempt / rel
        if not path.is_file() or sha256_file(path) != digest:
            return False
    return True


def source_attempt(builds_dir: Path, sid: str) -> Path | None:
    """A successful build or attempt of exactly these sources, newest first."""
    if not builds_dir.is_dir():
        return None
    candidates = [entry for entry in builds_dir.iterdir()
                  if entry.is_dir() and not entry.name.startswith('.')]
    for entry in sorted(candidates, key=lambda path: path.name, reverse=True):
        try:
            if read_json(entry / 'provenance.json').get('source_id') != sid:
                continue
        except Fail:
            continue
        if attempt_succeeded(entry):
            return entry
    return None


def prune_attempts(builds_dir: Path, keep: int = ATTEMPT_KEEP) -> None:
    attempts = sorted((entry for entry in builds_dir.glob('*')
                       if entry.is_dir() and ATTEMPT_RE.fullmatch(entry.name)),
                      key=lambda path: path.name)
    for old in attempts[:-keep] if keep else attempts:
        shutil.rmtree(old, ignore_errors=True)


def new_attempt(builds_dir: Path, version: str, sid: str) -> Path:
    stamp = time.strftime('%Y%m%d-%H%M%S', time.gmtime())
    return builds_dir / f'{stamp}-v{version}-{sid}'


def container_runtime() -> tuple[str, str] | None:
    """The installed container runtime: (name, executable) or None."""
    for name in ('podman', 'docker'):
        path = shutil.which(name)
        if path is not None:
            return name, path
    return None


def container_image() -> str:
    """The image `build` runs in.

    `LIBREECHO_BUILD_IMAGE` overrides; otherwise work/../tools/lab-build.json's
    build_image pins `name@digest`, falling back to the local build tag when
    the digest is null.
    """
    override = os.environ.get('LIBREECHO_BUILD_IMAGE')
    if override:
        return override
    try:
        config = read_json(ROOT / CONFIG_REL)
    except Fail:
        return LOCAL_IMAGE
    image = config.get('build_image') or {}
    digest = str(image.get('digest') or '').strip()
    name = image.get('name') or DEFAULT_IMAGE_NAME
    return f'{name}@{digest}' if digest else LOCAL_IMAGE


def container_enabled(args) -> bool:
    """Whether `build` should re-exec inside the container image."""
    if os.environ.get('LIBREECHO_CONTAINER') == '1':
        return False
    return not args.no_container


def container_git_identity() -> dict[str, str]:
    """The git identity for generated integration merges in the container.

    `tools/integrate.py` commits merges of existing topic commits, and those
    are generated, never pushed, so they carry a neutral build identity rather
    than the user's own. The image's HOME has no git config either way.
    """
    name = 'LibreEcho build'
    email = 'build@libreecho.invalid'
    return {'GIT_AUTHOR_NAME': name, 'GIT_AUTHOR_EMAIL': email,
            'GIT_COMMITTER_NAME': name, 'GIT_COMMITTER_EMAIL': email}


def container_argv(runtime: tuple[str, str], root: Path, image: str,
                   uid: int, gid: int, script_args: list[str],
                   git_identity: dict[str, str] | None = None,
                   image_id: str | None = None) -> list[str]:
    """The runtime argv that runs this tool inside the image at `root`."""
    name, path = runtime
    argv = [path, 'run', '--rm']
    if name == 'podman':
        # keep-id maps the host uid to the builder uid so the workspace stays
        # writable without running as root.
        argv += ['--userns=keep-id']
        home = '/home/builder'
    else:
        argv += ['--user', f'{uid}:{gid}']
        home = '/tmp'
    argv += ['--network=host',
             '-e', 'LIBREECHO_CONTAINER=1',
             '-e', f'HOME={home}',
             # The integration rebuild fetches the fork remotes. They are
             # ssh URLs and the image holds no key, so rewrite them to the
             # anonymous https form instead of mounting credentials.
             '-e', 'GIT_CONFIG_COUNT=1',
             '-e', 'GIT_CONFIG_KEY_0=url.https://github.com/.insteadOf',
             '-e', 'GIT_CONFIG_VALUE_0=git@github.com:',
             '-e', 'GIT_TERMINAL_PROMPT=0']
    for key, value in sorted((git_identity or {}).items()):
        argv += ['-e', f'{key}={value}']
    if image_id:
        # The inner build cannot resolve an image name; record the host's id.
        argv += ['-e', f'LIBREECHO_BUILD_IMAGE_ID={image_id}']
    # The product build reads these from its environment, so forward them by
    # name instead of baking their values into the command.
    for key in sorted(os.environ):
        if key.startswith('LIBREECHO_') and key != 'LIBREECHO_CONTAINER':
            argv += ['-e', key]
    argv += ['-v', f'{root}:{root}:Z',
             '-w', str(root),
             image, 'python3', str(root / 'tools/lab-build.py'),
             *script_args]
    return argv


def build_script_args(args) -> list[str]:
    """Reconstruct the `build` invocation from parsed args, in a stable order."""
    argv = ['build']
    if args.version:
        argv += ['--version', args.version]
    if args.no_integrate:
        argv += ['--no-integrate']
    if args.lock:
        argv += ['--lock', args.lock]
    if getattr(args, 'rebuild', False):
        argv += ['--rebuild']
    for flag, name in (('--stock-boot', 'stock_boot'),
                       ('--ota-signing-key', 'ota_signing_key'),
                       ('--ota-public-key', 'ota_public_key')):
        value = getattr(args, name, None)
        if value:
            argv += [flag, value]
    return argv


def run_in_container(args) -> int:
    """Re-exec `build` inside the build image and return its exit code."""
    image = container_image()
    runtime = container_runtime()
    if runtime is None:
        raise Fail('neither podman nor docker is installed; pass --no-container '
                   'to build with the host toolchain')
    name, path = runtime
    inspect = subprocess.run([path, 'image', 'inspect', '--format', '{{.Id}}', image],
                             capture_output=True, text=True)
    if inspect.returncode != 0:
        raise Fail(
            f'container image {image} is missing; pull the pinned digest '
            f'(`python3 tools/workspace.py init`) or build it from the '
            f'LibreEcho fork\'s build/container/Containerfile and tag it '
            f'{LOCAL_IMAGE}:\n'
            f'  {name} build --network=host -f build/container/Containerfile '
            f'-t {LOCAL_IMAGE} .\n'
            'or pass --no-container to build with the host toolchain')
    image_id = inspect.stdout.strip() or None
    argv = container_argv(runtime, ROOT, image, os.getuid(), os.getgid(),
                          build_script_args(args),
                          container_git_identity(), image_id=image_id)
    print(' '.join(shlex.quote(item) for item in argv))
    return subprocess.run(argv).returncode


def check_cross_tools() -> None:
    """Fail early when the cross binutils cannot load their host libraries.

    The musl toolchain binaries link against the host's libfl and libzstd, so
    an image without them fails inside make with an obscure "cannot open
    shared object file". Running one tool up front names the missing pieces.
    """
    tool = MUSL_ROOT / 'usr/bin/armv7-alpine-linux-musleabihf-ar'
    if not tool.is_file():
        return
    proc = subprocess.run([str(tool), '--version'], capture_output=True, text=True)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip().splitlines()
        raise Fail(
            f'{rel_to_ws(tool)} cannot run: {detail[0] if detail else "failed"}\n'
            'the host lacks a library the cross binutils link against; on '
            'ubuntu 24.04 they are packaged as libfl2 and libzstd1')


def ensure_mbedtls_venv() -> Path:
    """Return a venv for the pinned mbedTLS wheel closure.

    workspace.py stages one under work/inputs, but a venv belongs to the
    interpreter that created it, and that interpreter exists only on the host
    (or only in the image). Keep the build's own venv under work/product-build
    and restage it whenever it does not run here.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import workspace
    workspace.stage_mbedtls_venv(MBEDTLS_VENV, PUBLIC_DEPS / 'python-wheels')
    return MBEDTLS_VENV / 'bin/python'


def ensure_ota_gate_python() -> Path | None:
    """Stage the reviewed PyNaCl closure the product's OTA steps import.

    plan-target-manifest.py imports ota_v2_product.py, which imports nacl at
    module level, so the OTA pipeline cannot plan a manifest without it. The
    hosted job pip-installs build/inputs/reviewed/python-wheels onto its 3.11
    runner; the build image ships a bare 3.11. Install the same closure from
    the staged wheelhouse and hand it to the build through PYTHONPATH, so no
    wheel is baked into the image. Returns None when this interpreter imports
    nacl already and needs no help.
    """
    if subprocess.run([sys.executable, '-c', 'import nacl'],
                      capture_output=True).returncode == 0:
        return None
    wheelhouse = PUBLIC_DEPS / 'python-wheels'
    requirements = wheelhouse / 'requirements.txt'
    if not requirements.is_file():
        raise Fail(f'missing product gate requirements: {rel_to_ws(requirements)}')
    if OTA_GATE_PYTHON.exists():
        shutil.rmtree(OTA_GATE_PYTHON)
    OTA_GATE_PYTHON.mkdir(parents=True)
    proc = subprocess.run(
        [sys.executable, '-m', 'pip', 'install',
         '--disable-pip-version-check', '--no-index',
         '--find-links', str(wheelhouse), '--require-hashes',
         '--requirement', str(requirements), '--target', str(OTA_GATE_PYTHON)],
        capture_output=True, text=True)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip().splitlines()
        raise Fail('cannot stage the product gate wheel closure: '
                   f'{detail[-1] if detail else "pip failed"}')
    return OTA_GATE_PYTHON


def open_build_lock():
    """Claim the workspace for this build with a non-blocking flock.

    Two builds share work/integration and work/product-build, so a second one
    corrupts the first: files change under a running compiler and it fails in
    ways that vanish on a rerun. flock ties the lock to the open file, so a
    killed build can never leave a stale lock behind.
    """
    BUILD_LOCK.parent.mkdir(parents=True, exist_ok=True)
    handle = open(BUILD_LOCK, 'a+', encoding='utf-8')
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.seek(0)
        pid = handle.read().strip() or '?'
        handle.close()
        raise Fail(f'another lab build is running (pid {pid}); '
                   'wait for it to finish or stop it') from None
    handle.seek(0)
    handle.truncate()
    handle.write(f'{os.getpid()}\n')
    handle.flush()
    return handle


def close_build_lock(handle) -> None:
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()


def cmd_build(args) -> int:
    if os.environ.get('LIBREECHO_CONTAINER') == '1':
        # The host process that started this container holds the build lock.
        return run_build(args)
    lock = open_build_lock()
    try:
        if container_enabled(args):
            return run_in_container(args)
        return run_build(args)
    finally:
        close_build_lock(lock)


def run_build(args) -> int:
    config = read_json(ROOT / CONFIG_REL)
    if config.get('schema_version') != 1:
        raise Fail(f'{CONFIG_REL}: unsupported schema_version '
                   f'{config.get("schema_version")}')
    builds_dir = workspace_path(config['builds_dir'])
    builds_dir.mkdir(parents=True, exist_ok=True)
    version = args.version or next_version(builds_dir)
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise Fail(f'version {version!r} is not MAJOR.MINOR.PATCH')
    out_dir = builds_dir / f'v{version}'
    staging = builds_dir / f'.staging-{os.getpid()}'
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    log = BuildLog(staging / 'build.log')
    attempt = None
    try:
        log.phase(f'lab build v{version}')
        local = load_local(overrides={
            'stock_boot': args.stock_boot,
            'ota_signing_key': args.ota_signing_key,
            'ota_public_key': args.ota_public_key,
        })

        if args.lock:
            lock_path = workspace_path(args.lock)
        else:
            lock_path = ROOT / LOCK_REL
        if not args.no_integrate:
            integrate = ROOT / INTEGRATE_REL
            if not integrate.is_file():
                raise Fail(f'{INTEGRATE_REL} is missing; use --no-integrate with --lock')
            log.phase('integration rebuild')
            log.run([sys.executable, integrate, 'rebuild', '--only-in-ota',
                     '--allow-during-build'], cwd=ROOT)
            log.run([sys.executable, integrate, 'check-lock'], cwd=ROOT)

        log.phase('lock')
        lock = read_json(lock_path)
        if lock.get('schema_version') != 1:
            raise Fail(f'{rel_to_ws(lock_path)}: unsupported schema_version')
        log.line('INFO', f'lock {rel_to_ws(lock_path)} generated '
                         f'{lock.get("generated")}')
        sid = source_id(lock)
        if not args.rebuild:
            reuse = source_attempt(builds_dir, sid)
            if reuse is not None:
                log.line('PASS', f'reusing {rel_to_ws(reuse)}: same source id '
                                 f'{sid}, every recorded output intact')
                print(f'reused {rel_to_ws(reuse)} (pass --rebuild to build again)')
                log.close()
                shutil.rmtree(staging, ignore_errors=True)
                return 0
        if out_dir.exists() and any(out_dir.iterdir()):
            raise Fail(f'{rel_to_ws(out_dir)} already exists and is not empty')
        attempt = new_attempt(builds_dir, version, sid)
        staging.rename(attempt)
        log.line('INFO', f'attempt {rel_to_ws(attempt)}')
        image_ref = container_image()
        image_id = os.environ.get('LIBREECHO_BUILD_IMAGE_ID')
        log.line('INFO', f'image {image_ref} {image_id or "(host toolchain)"}')
        sources = load_sources(lock, log)

        tag = release_tag(lock, version)
        log.phase('mbedtls build venv')
        mbedtls_python = ensure_mbedtls_venv()
        log.phase('product gate python')
        ota_gate_python = ensure_ota_gate_python()
        env = product_env(local, version, tag, sources, mbedtls_python,
                          ota_gate_python)
        product_dir = sources['libreecho'].path
        build_sh = product_dir / 'build/build.sh'
        if not build_sh.is_file():
            raise Fail(f'product build script missing: {rel_to_ws(build_sh)}')

        log.phase(f'product build v{version} ({tag})')
        check_cross_tools()
        step_log = attempt / 'build.sh.log'
        log.run([str(build_sh), *product_args(config)], cwd=product_dir,
                env=env, step_log=step_log)
        run = run_dir_from_log(step_log)
        log.line('PASS', f'product run {rel_to_ws(run)}')

        collect_run(run, attempt)
        bundle = next(iter(sorted((attempt / 'run').glob('libreecho-*.ota.tar'))),
                      None)
        if bundle is None:
            raise Fail(f'product run {rel_to_ws(run)} has no signed OTA bundle')
        plan = read_json(attempt / 'run/feature-plan.json')
        manifest_path = attempt / 'run/manifest.json'
        provenance = {
            'schema_version': 1,
            'generated': now_iso(),
            'version': version,
            'release': tag,
            'source_id': sid,
            'build_dir': rel_to_ws(out_dir),
            'attempt': attempt.name,
            'image': {'ref': image_ref, 'id': image_id},
            'tool': {'path': rel_to_ws(Path(__file__)),
                     'sha256': sha256_file(Path(__file__))},
            'config': {'path': CONFIG_REL,
                       'sha256': sha256_file(ROOT / CONFIG_REL)},
            'manifest': {'path': MANIFEST_REL,
                         'sha256': sha256_file(ROOT / MANIFEST_REL)
                         if (ROOT / MANIFEST_REL).is_file() else None},
            'lock': {'path': rel_to_ws(lock_path),
                     'sha256': sha256_file(lock_path),
                     'generated': lock.get('generated'),
                     'heads': {name: entry.get('head')
                               for name, entry in lock['repos'].items()}},
            'sources': {role: source.record() for role, source in sources.items()},
            'local': local_input_record(local),
            'product': {
                'build_root': rel_to_ws(BUILD_ROOT),
                'run': 'run',
                'manifest': 'run/manifest.json',
                'manifest_sha256': sha256_file(manifest_path)
                if manifest_path.is_file() else None,
                'transaction_id': plan.get('transaction_id'),
                'release': plan.get('release'),
            },
            'ota': {
                'transaction_id': plan.get('transaction_id'),
                'release': tag,
                'run_dir': 'run',
                'bundle': bundle.relative_to(attempt).as_posix(),
                'bundle_sha256': sha256_file(bundle),
            },
            'log_files': [path.relative_to(attempt).as_posix()
                          for path in sorted(attempt.rglob('*.log'))],
        }
        log.phase('result')
        log.line('INFO', f'attempt {rel_to_ws(attempt)}')
        log.line('INFO', f'ota {plan.get("transaction_id")} '
                         f'bundle {sha256_file(bundle)[:16]}')
        outputs = write_build_identity(attempt, provenance)
        attempt.rename(out_dir)
        prune_attempts(builds_dir)
        log.line('INFO', f'build {rel_to_ws(out_dir)}')
        print(f'{len(outputs)} files recorded in SHA256SUMS and provenance.json')
        return 0
    finally:
        log.close()


# --------------------------------------------------------------------------
# cluster workflow: setup, push, fetch


def cmd_ci_setup(args) -> int:
    """Point `work` at the persistent cache the runner mounts."""
    work_root = Path(args.work_root).expanduser().resolve()
    work_root.mkdir(parents=True, exist_ok=True)
    link = ROOT / WORK_REL
    if link.is_symlink():
        target = Path(os.readlink(link))
        if not target.is_absolute():
            target = link.parent / target
        if target.resolve() != work_root:
            raise Fail(f'{WORK_REL} already points at {target}; expected {work_root}')
    elif link.exists():
        if not link.is_dir():
            raise Fail(f'{WORK_REL} exists and is not a directory')
        if any(link.iterdir()):
            raise Fail(f'{WORK_REL} is a real directory with content; the cluster build '
                       f'needs it to be a symlink to {work_root}')
        link.rmdir()
        link.symlink_to(work_root)
    else:
        link.symlink_to(work_root)
    print(f'{WORK_REL} -> {work_root}')
    return 0


def require_tool(name: str, hint: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise Fail(f'{name} is not installed; {hint}')
    return path


def git_rev(path: Path, revish: str) -> str | None:
    proc = subprocess.run(['git', '-C', str(path), 'rev-parse', '--verify', '--quiet',
                           revish], capture_output=True, text=True)
    return proc.stdout.strip() if proc.returncode == 0 else None


def git_tracked_changes(path: Path) -> list[str]:
    text = git(path, 'status', '--porcelain', '--untracked-files=no')
    return [line for line in text.splitlines() if line.strip()]


def is_ancestor(path: Path, older: str, newer: str) -> bool:
    proc = subprocess.run(['git', '-C', str(path), 'merge-base', '--is-ancestor',
                           older, newer], capture_output=True, text=True)
    return proc.returncode == 0


def fetch_remote_branch(repo: Path, remote: str, branch: str) -> str | None:
    """Fetch `remote/branch` into its tracking ref; None when it does not exist."""
    proc = subprocess.run(
        ['git', '-C', str(repo), 'fetch', '--no-tags', remote,
         f'+refs/heads/{branch}:refs/remotes/{remote}/{branch}'],
        capture_output=True, text=True)
    if proc.returncode != 0:
        if "couldn't find remote ref" in proc.stderr or 'no such remote ref' in proc.stderr:
            return None
        raise Fail(f'git fetch {remote} {branch}: {proc.stderr.strip() or "failed"}')
    return git_rev(repo, f'refs/remotes/{remote}/{branch}')


def push_argv(repo: Path, remote: str, branch: str, lease: str | None = None) -> list[str]:
    argv = ['git', '-C', str(repo), 'push', remote]
    if lease:
        # Lease against the remote head we just fetched, so a concurrent push
        # is not overwritten even when the owner asked for --force.
        argv.append(f'--force-with-lease=refs/heads/{branch}:{lease}')
    argv.append(f'refs/heads/{branch}:refs/heads/{branch}')
    return argv


def push_one(repo: Path, remote: str, branch: str, force: bool) -> bool:
    """Push one branch; fast-forward only unless `force` leases the fetched head."""
    local = git_rev(repo, f'refs/heads/{branch}')
    if local is None:
        raise Fail(f'{rel_to_ws(repo)} has no branch {branch}')
    remote_sha = fetch_remote_branch(repo, remote, branch)
    if remote_sha == local:
        print(f'up to date: {branch} -> {remote}')
        return False
    lease = None
    if remote_sha is not None:
        if is_ancestor(repo, local, remote_sha):
            raise Fail(f'{branch} is behind {remote}/{branch}; fetch and merge it first')
        if not is_ancestor(repo, remote_sha, local):
            if not force:
                raise Fail(f'{branch} has diverged from {remote}/{branch} '
                           f'({remote_sha[:10]}); rerun with --force to lease that head')
            lease = remote_sha
        elif force:
            lease = remote_sha
    argv = push_argv(repo, remote, branch, lease)
    print('$ ' + ' '.join(argv))
    proc = subprocess.run(argv, capture_output=True, text=True)
    if proc.returncode != 0:
        raise Fail(f'git push {remote} {branch}: {proc.stderr.strip() or "failed"}')
    return True


def gh_json(gh: str, *args: str):
    proc = subprocess.run([gh, *args], capture_output=True, text=True)
    if proc.returncode != 0:
        raise Fail(f'gh {" ".join(args)}: {proc.stderr.strip() or "failed"}')
    try:
        return json.loads(proc.stdout or '[]')
    except ValueError as exc:
        raise Fail(f'gh {" ".join(args)} printed no JSON: {exc}') from exc


def latest_run(gh: str) -> tuple[object, str | None]:
    runs = gh_json(gh, 'run', 'list', '--workflow', CI_WORKFLOW, '--branch', 'main',
                   '--limit', '5', '--json', 'databaseId,url')
    if not isinstance(runs, list) or not runs:
        return None, None
    return runs[0].get('databaseId'), runs[0].get('url')


def dispatch_workflow(version: str | None) -> None:
    gh = require_tool('gh', 'install the GitHub CLI and run `gh auth login`')
    before, _ = latest_run(gh)
    argv = [gh, 'workflow', 'run', CI_WORKFLOW, '--ref', 'main']
    if version:
        argv += ['-f', f'version={version}']
    print('$ ' + ' '.join(argv))
    proc = subprocess.run(argv, capture_output=True, text=True)
    if proc.returncode != 0:
        raise Fail(f'gh workflow run: {proc.stderr.strip() or "failed"}')
    deadline = time.time() + 30
    while time.time() < deadline:
        time.sleep(1)
        run_id, url = latest_run(gh)
        if run_id is not None and run_id != before:
            print(f'run: {url or run_id}')
            return
    print(f'dispatched {CI_WORKFLOW}; see the repository Actions page')


def cmd_push(args) -> int:
    if args.version and not re.fullmatch(r'\d+\.\d+\.\d+', args.version):
        raise Fail(f'version {args.version!r} is not MAJOR.MINOR.PATCH')
    manifest = read_json(ROOT / MANIFEST_REL)
    dirty = git_tracked_changes(ROOT)
    if dirty:
        raise Fail('the port repository has uncommitted changes; commit or stash them '
                   'first:\n  ' + '\n  '.join(dirty[:10]))
    branch = git(ROOT, 'rev-parse', '--abbrev-ref', 'HEAD')
    if branch != 'main':
        raise Fail(f'the port repository is on {branch!r}; run push from main')
    for entry in manifest.get('repos', []):
        repo = workspace_path(entry['path'])
        if not repo.is_dir():
            raise Fail(f'{entry["path"]} is missing; run `python3 tools/workspace.py init`')
        dirty = git_tracked_changes(repo)
        if dirty:
            raise Fail(f'{entry["path"]} has uncommitted changes; commit or stash them '
                       f'first:\n  ' + '\n  '.join(dirty[:10]))
        remotes = git(repo, 'remote').split()
        remote = 'fork' if 'fork' in remotes else 'origin'
        if remote not in remotes:
            raise Fail(f'{entry["path"]} has neither a fork nor an origin remote')
        for topic in entry.get('topics', []):
            push_one(repo, remote, topic['branch'], args.force)
    remotes = git(ROOT, 'remote').split()
    if 'origin' not in remotes:
        raise Fail('the port repository has no origin remote')
    push_one(ROOT, 'origin', 'main', args.force)
    print(f'pushed; dispatching {CI_WORKFLOW}')
    dispatch_workflow(args.version)
    return 0


# --------------------------------------------------------------------------
# fetch a CI build into work/builds


def find_artifact_file(root: Path, pattern: str) -> Path:
    matches = [path for path in sorted(root.rglob(pattern)) if path.is_file()]
    if len(matches) != 1:
        raise Fail(f'artifact {CI_ARTIFACT}: expected one {pattern}, found {len(matches)}')
    return matches[0]


def verify_sha256sums(root: Path) -> int:
    sums = root / CI_SUMS_FILE
    if not sums.is_file():
        raise Fail(f'{rel_to_ws(root)} has no {CI_SUMS_FILE}')
    count = 0
    for number, line in enumerate(sums.read_text(encoding='utf-8').splitlines(), 1):
        digest, separator, name = line.partition('  ')
        if not separator or not name:
            raise Fail(f'{CI_SUMS_FILE}:{number}: malformed line')
        path = root / name
        if not path.is_file():
            raise Fail(f'{name} is missing from the fetched build')
        actual = sha256_file(path)
        if actual != digest:
            raise Fail(f'{name}: sha256 {actual} does not match {CI_SUMS_FILE}')
        count += 1
    if not count:
        raise Fail(f'{CI_SUMS_FILE} is empty')
    return count


def download_artifact(run: str, destination: Path) -> str:
    gh = require_tool('gh', 'install the GitHub CLI and run `gh auth login`')
    spec = run
    if run == 'latest':
        runs = gh_json(gh, 'run', 'list', '--workflow', CI_WORKFLOW,
                       '--status', 'success', '--limit', '1',
                       '--json', 'databaseId')
        if not runs:
            raise Fail(f'no successful {CI_WORKFLOW} run found')
        spec = str(runs[0]['databaseId'])
    argv = [gh, 'run', 'download', spec, '-n', CI_ARTIFACT, '-D', str(destination)]
    print('$ ' + ' '.join(argv))
    proc = subprocess.run(argv, capture_output=True, text=True)
    if proc.returncode != 0:
        raise Fail(f'gh run download {spec}: {proc.stderr.strip() or "failed"}')
    return spec


def cmd_fetch(args) -> int:
    config = read_json(ROOT / CONFIG_REL)
    builds_dir = workspace_path(config['builds_dir'])
    temporary = Path(tempfile.mkdtemp(prefix='lab-fetch-'))
    try:
        download = temporary / 'download'
        spec = download_artifact(args.run, download)
        provenance = read_json(find_artifact_file(download, CI_PROVENANCE_FILE))
        version = str(provenance.get('version') or '')
        if not re.fullmatch(r'\d+\.\d+\.\d+', version):
            raise Fail(f'{CI_PROVENANCE_FILE}: version {version!r} is not MAJOR.MINOR.PATCH')
        destination = builds_dir / f'v{version}'
        if destination.exists() and any(destination.iterdir()):
            raise Fail(f'{rel_to_ws(destination)} already exists and is not empty')
        # Everything the artifact holds sits below its provenance file.
        root = find_artifact_file(download, CI_PROVENANCE_FILE).parent
        staging = builds_dir / f'.fetch-{os.getpid()}'
        if staging.exists():
            shutil.rmtree(staging)
        try:
            shutil.copytree(root, staging, dirs_exist_ok=True)
            count = verify_sha256sums(staging)
            if destination.exists():
                destination.rmdir()
            destination.parent.mkdir(parents=True, exist_ok=True)
            staging.rename(destination)
        finally:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)
        print(f'fetched run {spec}: build v{version} at {rel_to_ws(destination)} '
              f'({count} files verified)')
        return 0
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


# --------------------------------------------------------------------------
# deploy


class Adb:
    def __init__(self, binary: str, host: str, log: BuildLog, out_dir: Path):
        self.binary = binary
        self.host = host
        self.log = log
        self.out_dir = out_dir
        self.out_dir.mkdir(parents=True, exist_ok=True)

    def run(self, *args: str, timeout: int = 120, step_log: str | None = None) -> str:
        cmd = [self.binary, '-s', self.host, *args]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  errors='replace', timeout=timeout, check=False)
        except subprocess.TimeoutExpired:
            # Right after a reboot adbd accepts the connection before it can
            # run a shell. Returning empty output lets the callers retry or
            # report a missing rc line, instead of killing a deploy that has
            # already written the slot.
            return ''
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

    def push(self, local: Path, remote: str, timeout: int = 3600) -> None:
        # The TTS payload is 160 MB and Wi-Fi adb delivers 0.1-0.4 MB/s, so a
        # single push can legitimately run for half an hour; the old 900 s cap
        # failed mid-transfer on a working link.
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


def device_host(args, local: dict) -> str:
    return (args.host or local.get('device_host')
            or os.environ.get('LAB_DEVICE_HOST') or os.environ.get('LIDAR_WIFI')
            or '')


def verify_deliverables(build_dir: Path, provenance: dict) -> None:
    for rel, digest in sorted(provenance['outputs'].items()):
        path = build_dir / rel
        if not path.is_file() or sha256_file(path) != digest:
            raise Fail(f'built file changed or missing: {rel}')


def asset_cached(adb: Adb, remote: str, sha256: str, size: int) -> bool:
    """True when the device already holds an asset's exact bytes.

    A failed push leaves a truncated .part behind and the cache also keeps
    earlier generations, so compare size and SHA-256 before sending 218 MB of
    payloads over Wi-Fi again.
    """
    got = adb.shell(f'stat -c %s {remote} 2>/dev/null', timeout=60).strip()
    if got != str(size):
        return False
    digest = adb.shell(f'sha256sum {remote} 2>/dev/null', timeout=900).split()
    return bool(digest) and digest[0] == sha256


def cmd_deploy(args) -> int:
    config = read_json(ROOT / CONFIG_REL)
    version = args.version
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise Fail(f'version {version!r} is not MAJOR.MINOR.PATCH')
    build_dir = workspace_path(config['builds_dir']) / f'v{version}'
    provenance = read_json(build_dir / 'provenance.json')
    if provenance.get('version') != version:
        raise Fail(f'{rel_to_ws(build_dir)} provenance is for '
                   f'{provenance.get("version")}, not {version}')
    local = load_local(require_owner_inputs=False)
    host = device_host(args, local)
    if not host:
        raise Fail('no device host: pass --host HOST, set device_host in '
                   'private/local.json, or set LAB_DEVICE_HOST')
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
    verify_deliverables(build_dir, provenance)
    print('local deliverables match provenance.json\n')

    log = BuildLog(build_dir / 'deploy.log')
    try:
        adb_binary = shutil.which('adb')
        if not adb_binary:
            raise Fail('adb not found on PATH')
        out = build_dir / 'deploy'
        adb = Adb(adb_binary, host, log, out)
        log.phase(f'deploy v{version} to {host}')
        adb.connect()
        log.write(adb.run('devices', '-l', step_log='devices.log'))
        start = slot_of(adb)
        if not start:
            raise Fail('no Wi-Fi adb connection to the device')
        target = 'b' if start == 'a' else 'a'
        run = build_dir / provenance['ota']['run_dir']
        txn = provenance['ota']['transaction_id']
        tarball = build_dir / provenance['ota']['bundle']
        inventory = read_json(run / 'feature-assets.json').get('assets', [])
        if len(inventory) != 2 * len(FEATURE_ORDER):
            raise Fail(f'{rel_to_ws(run)} lists {len(inventory)} assets, '
                       f'expected {2 * len(FEATURE_ORDER)}')
        # The device assembles the generation from the signed manifest and the
        # content-addressed cache, so it needs the control members as files.
        incoming = build_dir / 'deploy/incoming'
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
            remote = f'/data/libreecho/update/asset-cache/{item["sha256"]}.part'
            if asset_cached(adb, remote, item['sha256'], item['size']):
                log.line('INFO', f'cached {item["name"]}')
                continue
            adb.push(run / 'ota-assets' / item['name'], remote)
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
        if not asset_cached(adb, '/data/libreecho/incoming/local-install.ota.tar',
                            provenance['ota']['bundle_sha256'],
                            tarball.stat().st_size):
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
        # adbd can accept the connection before it can run a shell (the deploy
        # this guards died exactly there and reported failure for a good slot).
        deadline = time.time() + 300
        slot = slot_of(adb)
        while not slot and time.time() < deadline:
            time.sleep(5)
            slot = slot_of(adb)
        if not slot:
            raise Fail('no shell after reboot; see deploy/connect.log')
        log.line('INFO', f'adb back on slot {slot}')
        deadline = time.time() + 1200
        confirmed = False
        while time.time() < deadline:
            state = adb.shell('tr " " "\\n" < /proc/cmdline; libreecho-update status; '
                              'echo current=$(cat /data/libreecho/update/current 2>/dev/null)',
                              20)
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
        want_boot = sha256_file(run / 'boot.img')
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
        description='Build and deploy a Lidar image with the product build.',
        allow_abbrev=False)
    sub = parser.add_subparsers(dest='command', required=True)
    build = sub.add_parser('build', help='rebuild integration and run the product build',
                           allow_abbrev=False)
    build.add_argument('--version', help='build version MAJOR.MINOR.PATCH '
                                         '(default: highest build under work/builds + 1 patch)')
    build.add_argument('--no-integrate', action='store_true',
                       help='do not run tools/integrate.py rebuild/check-lock')
    build.add_argument('--lock', help='read this lock instead of '
                                      'work/integration/integration.lock.json '
                                      '(implies --no-integrate)')
    build.add_argument('--no-container', action='store_true',
                       help='build with the host toolchain instead of the '
                            'libreecho-build container image')
    build.add_argument('--workspace', help='workspace root (default: this checkout)')
    build.add_argument('--rebuild', action='store_true',
                       help='build even when a successful build of the same '
                            'sources exists')
    build.add_argument('--stock-boot',
                       help='stock boot_a image (overrides private/local.json)')
    build.add_argument('--ota-signing-key',
                       help='ed25519 OTA signing seed (overrides private/local.json)')
    build.add_argument('--ota-public-key',
                       help='ed25519 OTA public key (overrides private/local.json)')
    deploy = sub.add_parser('deploy', help='install a built OTA on the device',
                            allow_abbrev=False)
    deploy.add_argument('version', help='built version, e.g. 0.2.46')
    deploy.add_argument('--host', help='device adb host:port '
                                       '(or device_host in private/local.json)')
    deploy.add_argument('--yes', action='store_true',
                        help='confirm writing the inactive boot slot and rebooting')
    deploy.add_argument('--workspace', help='workspace root (default: this checkout)')
    ci_setup = sub.add_parser('ci-setup',
                              help='point work/ at the cluster runner cache',
                              allow_abbrev=False)
    ci_setup.add_argument('--work-root', required=True,
                          help='persistent work tree, e.g. /lab-cache')
    ci_setup.add_argument('--workspace', help='workspace root (default: this checkout)')
    push = sub.add_parser('push', help='push the forks and dispatch the cluster build',
                          allow_abbrev=False)
    push.add_argument('--force', action='store_true',
                      help='allow a rewritten branch with --force-with-lease')
    push.add_argument('--version', help='version for the workflow input '
                                        '(default: the next patch on the cache)')
    push.add_argument('--workspace', help='workspace root (default: this checkout)')
    fetch = sub.add_parser('fetch', help='download and verify a cluster build',
                           allow_abbrev=False)
    fetch.add_argument('run', nargs='?', default='latest',
                       help='workflow run id (default: the latest successful run)')
    fetch.add_argument('--workspace', help='workspace root (default: this checkout)')
    args = parser.parse_args(argv)
    try:
        if args.workspace:
            set_workspace(Path(args.workspace))
        if args.command == 'build':
            if args.lock:
                args.no_integrate = True
            return cmd_build(args)
        if args.command == 'ci-setup':
            return cmd_ci_setup(args)
        if args.command == 'push':
            return cmd_push(args)
        if args.command == 'fetch':
            return cmd_fetch(args)
        return cmd_deploy(args)
    except Fail as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1
    except subprocess.TimeoutExpired as exc:
        print(f'ERROR: command timed out: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
