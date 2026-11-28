#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Prepare the gitignored `work/` tree and the private inputs under `private/`.

The published repo holds code only. Everything a build needs on disk is
regenerated or supplied here: the fork clones named by `integration.json`, the
integration branches, the product's public build inputs, and the private
signing key and stock boot image.

Commands:
  init [--no-integrate] [--no-inputs]
                           install the versioned git hooks, clone missing forks,
                           rebuild integration, fetch the public build inputs into
                           work/inputs/
  keygen                   create the ed25519 OTA signing key pair named by
                           private/local.json
  doctor                   report what a build still needs; exits 1 when
                           anything is missing

Paths are resolved against the workspace root (the parent of tools/). Override
with --workspace or LIBREECHO_WORKSPACE.
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

from integrate import Fail, is_git_repo, load_json, load_manifest, sha256_file, workspace_from

FORK_REMOTE = "fork"
UPSTREAM_REMOTE = "upstream"
LOCAL_JSON = "private/local.json"
LOCAL_EXAMPLE = "tools/local.example.json"
LOCK_REL = "work/integration/integration.lock.json"
INPUTS_REL = "work/inputs"
PRODUCT_REL = "work/integration/LibreEcho"
PRODUCT_BUILD_REL = "work/integration/LibreEcho/build"
PLATFORM_REL = "work/integration/LibreEcho-Platform"

LAB_BUILD_CONFIG_REL = "tools/lab-build.json"
CONTAINERFILE_REL = "work/integration/LibreEcho/build/container/Containerfile"
BUILD_IMAGE_NAME = "ghcr.io/tomgrozev/libreecho-build"
LOCAL_BUILD_IMAGE = "libreecho-build:local"
MIN_FREE_DISK = 20 * 1024 ** 3

PUBLIC_DEPS_REL = "work/inputs/public-deps"
AARCH64_DEBS_REL = "work/inputs/aarch64-debs"
AARCH64_ROOT_REL = "work/inputs/aarch64-root"
ARMHF_DEBS_REL = "work/inputs/armhf-debs"
ARMHF_ROOT_REL = "work/inputs/armhf-root"
MUSL_ROOT_REL = "work/inputs/toolchain"
KEYGEN_VENV_REL = "work/tools/keygen-venv"

# Paths `tools/lab-build.py:product_env` hands to the product build.
OTBR_LOCK_REL = "tools/mt8163-arm32/otbr/SOURCE.lock"
OTBR_ARCHIVES_REL = "work/inputs/otbr/archives"
OTBR_SOURCE_REL = "work/inputs/otbr/ot-br-posix"
OTBR_DEPS_REL = "work/inputs/otbr/deps"
OTBR_DEPS_RECEIPT = "SOURCE_LOCK_SHA256"
OTBR_DEPS_LIBS = ("libexpat.a", "libdaemon.a", "libdbus-1.a",
                  "libavahi-common.a", "libavahi-client.a")
KERNEL_UAPI_REL = "work/inputs/kernel-uapi"
KERNEL_UAPI_OUT_REL = "work/inputs/kernel-uapi-out"
KERNEL_UAPI_TREES = ("linux", "asm", "asm-generic")
LINUX_REL = "work/integration/LibreEcho-Linux"

NEURAL_REL = "work/inputs/public-deps/neural"
NEURAL_MANIFEST = "NEURAL_DEPENDENCY_MANIFEST"
NEURAL_REQUIRED = (
    "onnxruntime-prefix/include/onnxruntime_cxx_api.h",
    "onnxruntime-build/libonnxruntime_session.a",
    "onnxruntime-build/_deps/onnx-build/libonnx.a",
    "onnxruntime-prefix/lib/libonnxruntime.a",
    "onnxruntime-prefix/lib/libre2.a",
    "sherpa-onnx-prefix/lib/libsherpa-onnx-core.a",
    "flatbuffers-python/flatbuffers/__init__.py",
    "speexdsp-prefix/lib/libspeexdsp.a",
    "flite-root/build/arm-linux-gnueabihf/lib/libflite.a",
    "espeak-ng-data/phontab",
    "espeak-ng-data/phonindex",
)
TTS_SPEC_REL = "work/integration/LibreEcho/build/inputs/tts-voice-metadata.json"
TTS_DERIVE_REL = "work/integration/LibreEcho/build/ci/derive-tts-model.py"

AARCH64_RECEIPT = ".libreecho-aarch64-toolchain-receipt.json"
ARMHF_RECEIPT = ".libreecho-armhf-toolchain-receipt.json"

# build/ci/build-public-toolchain.sh clones this musl-cross-make commit, and the
# release workflow records it beside the built toolchain as its identity.
MUSL_TOOLCHAIN_COMMIT = "227df8b99103f9c59f6570babf892978e293082f"

# The reviewed wheel closure is CPython 3.11/Linux x86_64; the release workflow
# refuses any other interpreter before installing it.
MBEDTLS_VERSIONS = {"jinja2": "3.1.6", "jsonschema": "4.25.1"}
LOCAL_PATH_KEYS = ("ota_signing_key", "ota_public_key", "stock_boot")
DEFAULT_SIGNING_KEY = "private/keys/ota-lab/ed25519-seed.hex"
DEFAULT_PUBLIC_KEY = "private/keys/ota-lab/ed25519-public.hex"
HOST_TOOLS = ("git", "curl", "make", "dpkg-deb", "rsync")

KEYGEN_SOURCE = """\
import os
import sys
from nacl.signing import SigningKey

key = SigningKey.generate()


def write(path, text, mode):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(descriptor, "w", encoding="ascii") as stream:
        stream.write(text)


write(sys.argv[1], key.encode().hex() + "\\n", 0o600)
write(sys.argv[2], key.verify_key.encode().hex() + "\\n", 0o644)
"""


def rel(ws, path):
    try:
        return str(Path(path).relative_to(ws))
    except ValueError:
        return str(path)


def run(cmd, env=None, capture=False, cwd=None):
    proc = subprocess.run(
        [str(part) for part in cmd],
        text=True,
        capture_output=capture,
        env=env,
        cwd=cwd,
    )
    if proc.returncode != 0:
        detail = ((proc.stderr or "") + (proc.stdout or "")).strip() if capture else ""
        command = " ".join(str(part) for part in cmd)
        raise Fail(f"{command[:160]}: {detail or f'exit {proc.returncode}'}")
    return proc


def git_out(repo, *args):
    proc = subprocess.run(
        ["git", "-C", str(repo), *args], text=True, capture_output=True
    )
    if proc.returncode != 0:
        raise Fail(f"git {' '.join(args)}: {proc.stderr.strip() or 'failed'}")
    return proc.stdout.strip()


def rev(repo, revish):
    proc = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--verify", "--quiet", revish],
        text=True,
        capture_output=True,
    )
    return proc.stdout.strip() if proc.returncode == 0 else None


def remotes(repo):
    return git_out(repo, "remote").split()


def add_remote_if_missing(repo, name, url):
    if name in remotes(repo):
        return False
    run(["git", "-C", str(repo), "remote", "add", name, url])
    return True


def base_is_fork_branch(entry):
    """A base without an `upstream/` prefix is a branch the fork carries.

    It is checked out locally tracking `fork/<base>`, exactly like a topic, so
    the integration rebuild sees an ordinary local ref.
    """
    return not entry["base"].startswith(UPSTREAM_REMOTE + "/")


def ensure_tracking_branch(path, entry, branch):
    if rev(path, f"refs/remotes/{FORK_REMOTE}/{branch}") is None:
        raise Fail(f"{entry['name']}: fork has no branch {branch!r}")
    if rev(path, f"refs/heads/{branch}") is None:
        run(["git", "-C", path, "branch", "--track", branch,
             f"{FORK_REMOTE}/{branch}"])


# --------------------------------------------------------------------------
# init: forks, integration, public inputs


def clone_fork(ws, entry):
    path = ws / entry["path"]
    if path.exists():
        raise Fail(f"{entry['path']} exists but is not a git repository")
    print(f"clone {entry['name']} -> {entry['path']}")
    path.parent.mkdir(parents=True, exist_ok=True)
    run(["git", "clone", "--origin", FORK_REMOTE, entry["fork_url"], path])
    add_remote_if_missing(path, UPSTREAM_REMOTE, entry["upstream_url"])
    run(["git", "-C", path, "fetch", FORK_REMOTE])
    run(["git", "-C", path, "fetch", UPSTREAM_REMOTE])
    for topic in entry["topics"]:
        ensure_tracking_branch(path, entry, topic["branch"])
    if base_is_fork_branch(entry):
        ensure_tracking_branch(path, entry, entry["base"])


def ensure_remotes(ws, entry):
    path = ws / entry["path"]
    for name, url in ((FORK_REMOTE, entry["fork_url"]),
                      (UPSTREAM_REMOTE, entry["upstream_url"])):
        if add_remote_if_missing(path, name, url):
            print(f"{entry['path']}: added remote {name}")


def checked_out_branches(path):
    """Branches some worktree of `path` has checked out."""
    out = git_out(path, "worktree", "list", "--porcelain")
    return {
        line.split(" ", 1)[1]
        for line in out.splitlines()
        if line.startswith("branch refs/heads/")
    }


def is_ancestor(path, older, newer):
    proc = subprocess.run(
        ["git", "-C", str(path), "merge-base", "--is-ancestor", older, newer],
        capture_output=True,
    )
    return proc.returncode == 0


def sync_fork_branches(path, entry, force):
    """Bring the cached clone's manifest branches up to the fork remote.

    A reused `work/forks` clone keeps the topic branches it was cloned with,
    so without this a cluster build would rebuild stale sources. Local commits
    the fork does not have are never discarded; `force` only resets an
    unchecked branch whose fork history was rewritten.
    """
    run(["git", "-C", path, "fetch", "--prune", "--no-tags", FORK_REMOTE])
    branches = [topic["branch"] for topic in entry["topics"]]
    if base_is_fork_branch(entry) and entry["base"] not in branches:
        branches.insert(0, entry["base"])
    checked = checked_out_branches(path)
    head_branch = git_out(path, "rev-parse", "--abbrev-ref", "HEAD")
    for branch in branches:
        remote = rev(path, f"refs/remotes/{FORK_REMOTE}/{branch}")
        if remote is None:
            raise Fail(f"{entry['name']}: fork has no branch {branch!r}")
        local = rev(path, f"refs/heads/{branch}")
        if local is None:
            run(["git", "-C", path, "branch", "--track", branch,
                 f"{FORK_REMOTE}/{branch}"])
            print(f"   {branch}: created from {FORK_REMOTE}/{branch}")
        elif local == remote:
            continue
        elif is_ancestor(path, local, remote):
            if branch == head_branch and branch in checked:
                if git_out(path, "status", "--porcelain"):
                    raise Fail(f"{branch} is checked out and dirty in {entry['path']}")
                run(["git", "-C", path, "merge", "--ff-only", remote])
            elif branch in checked:
                print(f"   warning: {branch} is checked out in a linked worktree; "
                      f"left at {local[:10]}", file=sys.stderr)
                continue
            else:
                run(["git", "-C", path, "update-ref", f"refs/heads/{branch}",
                     remote, local])
            print(f"   {branch}: fast-forwarded to {remote[:10]}")
        elif is_ancestor(path, remote, local):
            print(f"   {branch}: local commits not on the fork; left as is")
        elif force and branch not in checked:
            run(["git", "-C", path, "branch", "-f", branch,
                 f"{FORK_REMOTE}/{branch}"])
            print(f"   {branch}: reset to the fork")
        else:
            print(f"   warning: {branch} diverged from the fork; left as is "
                  f"(init --sync-forks resets an unchecked branch)", file=sys.stderr)


def sums_ok(root):
    sums = root / "SHA256SUMS"
    if not sums.is_file():
        return False
    for line in sums.read_text(encoding="utf-8").splitlines():
        digest, sep, name = line.partition("  ")
        if not sep or not name:
            return False
        path = root / name
        if not path.is_file() or sha256_file(path) != digest:
            return False
    return True


def stage_public_deps(ws, ci, inputs, deps, lock, patches):
    for required in (inputs / "public-inputs.json", lock):
        if not required.is_file():
            raise Fail(f"missing public input descriptor: {rel(ws, required)}")
    if not patches.is_dir():
        raise Fail(f"missing Platform sendspin patch directory: {rel(ws, patches)}")
    if sums_ok(deps):
        print("inputs: public deps present and verified")
        return
    if deps.exists():
        shutil.rmtree(deps)
    print("inputs: fetching public deps")
    run([sys.executable, ci / "fetch-public-deps.py", inputs / "public-inputs.json",
         "--allow-generated", "--output", deps,
         "--source-lock", lock, "--patch-dir", patches])
    if not sums_ok(deps):
        raise Fail("public deps failed their SHA256SUMS check")
    print("inputs: public deps fetched and verified")


def stage_toolchain(script, lock, debs, prefix, receipt_name, label):
    if (prefix / receipt_name).is_file():
        verify = subprocess.run(
            [sys.executable, str(script), "verify", "--lock", str(lock),
             "--archives", str(debs), "--prefix", str(prefix)],
            text=True, capture_output=True,
        )
        if verify.returncode == 0:
            print(f"inputs: {label} present and verified")
            return
        print(f"inputs: {label} failed verification; restaging")
    if prefix.exists():
        shutil.rmtree(prefix)
    run([sys.executable, script, "fetch", "--lock", lock, "--archives", debs])
    for step in ("stage", "verify"):
        run([sys.executable, script, step, "--lock", lock,
             "--archives", debs, "--prefix", prefix])
    print(f"inputs: {label} staged and verified")


def stage_musl(ws, script, root):
    commit_file = root / "TOOLCHAIN_SOURCE_COMMIT"
    if (
        (root / "bin" / "arm-linux-musleabihf-gcc").is_file()
        and commit_file.is_file()
        and commit_file.read_text(encoding="utf-8").strip() == MUSL_TOOLCHAIN_COMMIT
    ):
        print("inputs: ARM32 musl toolchain present")
        return
    tmp = ws / INPUTS_REL / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, RUNNER_TEMP=str(tmp))
    print("inputs: building the ARM32 musl toolchain (several minutes)")
    run([script, root], env=env)
    commit_file.write_text(MUSL_TOOLCHAIN_COMMIT + "\n", encoding="utf-8")


def mbedtls_check_source():
    pairs = ", ".join(f"({name!r}, {version!r})" for name, version in MBEDTLS_VERSIONS.items())
    return (
        "import importlib.metadata as metadata\n"
        "import sys\n"
        "if sys.version_info[:2] != (3, 11):\n"
        "    raise SystemExit(1)\n"
        f"for module, expected in ({pairs},):\n"
        "    if metadata.version(module) != expected:\n"
        "        raise SystemExit(1)\n"
    )


def mbedtls_ready(venv):
    python = venv / "bin" / "python"
    if not python.is_file():
        return False
    proc = subprocess.run(
        [str(python), "-c", mbedtls_check_source()], text=True, capture_output=True
    )
    return proc.returncode == 0


def find_python311():
    candidates = []
    if sys.version_info[:2] == (3, 11):
        candidates.append(sys.executable)
    found = shutil.which("python3.11")
    if found:
        candidates.append(found)
    for candidate in candidates:
        proc = subprocess.run(
            [candidate, "-c",
             "import sys; raise SystemExit(sys.version_info[:2] != (3, 11))"],
            capture_output=True,
        )
        if proc.returncode == 0:
            return candidate
    raise Fail(
        "CPython 3.11 is required for the pinned wheel closure; install python3.11"
    )


def stage_mbedtls_venv(venv, wheelhouse):
    if mbedtls_ready(venv):
        print("inputs: mbedTLS build venv present")
        return
    requirements = wheelhouse / "mbedtls-build-requirements.txt"
    if not requirements.is_file():
        raise Fail(f"missing mbedTLS build requirements: {requirements}")
    python = find_python311()
    if venv.exists():
        shutil.rmtree(venv)
    run([python, "-m", "venv", venv])
    run([venv / "bin" / "python", "-m", "pip", "install",
         "--disable-pip-version-check", "--no-index",
         "--find-links", wheelhouse, "--require-hashes",
         "--requirement", requirements])
    if not mbedtls_ready(venv):
        raise Fail("mbedTLS build venv does not match the pinned requirements")


def otbr_source_ready(source):
    """True when the checkout is usable by Platform otbr/build_otbr.sh.

    That script compiles third_party out of submodules, so a plain checkout
    (empty submodule directories) is not a ready source.
    """
    if not is_git_repo(source):
        return False
    proc = subprocess.run(
        ["git", "-C", str(source), "submodule", "status", "--recursive"],
        text=True, capture_output=True,
    )
    if proc.returncode != 0:
        return False
    # Uninitialized submodules are listed with a leading '-'.
    return not any(line.startswith("-") for line in proc.stdout.splitlines())


def stage_otbr_source(ws, platform):
    source = ws / OTBR_SOURCE_REL
    lock_path = platform / OTBR_LOCK_REL
    lock = load_json(lock_path)
    commit = lock["commit"]
    if source.exists() and not is_git_repo(source):
        raise Fail(f"{OTBR_SOURCE_REL} exists but is not a git repository")
    if not source.exists():
        print(f"inputs: cloning ot-br-posix at {commit[:12]}")
        source.parent.mkdir(parents=True, exist_ok=True)
        # --no-checkout skips the default branch; the checkout below always
        # lands on the pinned commit.
        run(["git", "clone", "--no-checkout", lock["repository"], source])
        run(["git", "-C", source, "checkout", "--detach", commit])
    if rev(source, "HEAD") != commit:
        run(["git", "-C", source, "fetch", "origin", commit])
        run(["git", "-C", source, "checkout", "--detach", commit])
    run(["git", "-C", source, "submodule", "sync", "--recursive"])
    run(["git", "-C", source, "submodule", "update", "--init", "--recursive"])
    if rev(source, "HEAD") != commit:
        raise Fail(f"{OTBR_SOURCE_REL}: HEAD is not the SOURCE.lock commit {commit}")
    if not otbr_source_ready(source):
        raise Fail(f"{OTBR_SOURCE_REL}: third_party submodules are not initialized")
    print("inputs: ot-br-posix source present and verified")


def fetch_pinned_archive(dependency, archives):
    name = dependency["source_url"].rsplit("/", 1)[-1]
    target = archives / name
    expected = dependency["source_sha256"]
    if target.is_file() and sha256_file(target) == expected:
        return
    if target.exists():
        target.unlink()
    print(f"inputs: fetching {name}")
    run(["curl", "-fL", "--retry", "3", "--output", target,
         dependency["source_url"]])
    if sha256_file(target) != expected:
        target.unlink(missing_ok=True)
        raise Fail(f"{name}: sha256 mismatch (expected {expected})")


def stage_otbr_deps(ws, platform):
    deps = ws / OTBR_DEPS_REL
    lock_path = platform / OTBR_LOCK_REL
    lock = load_json(lock_path)
    digest = sha256_file(lock_path)
    receipt = deps / OTBR_DEPS_RECEIPT
    if (
        receipt.is_file()
        and receipt.read_text(encoding="utf-8").strip() == digest
        and all((deps / "lib" / lib).is_file() for lib in OTBR_DEPS_LIBS)
    ):
        print("inputs: OTBR deps present and verified")
        return
    archives = ws / OTBR_ARCHIVES_REL
    archives.mkdir(parents=True, exist_ok=True)
    for dependency in lock["dependencies"]:
        fetch_pinned_archive(dependency, archives)
    if deps.exists():
        shutil.rmtree(deps)
    print("inputs: building OTBR deps (several minutes)")
    # build_otbr_deps.sh finds the cross compiler's host libraries itself but
    # expects the target sysroot in the flags; the staged Ubuntu compiler's
    # built-in sysroot is /, which on a non-Debian host has no armhf libc.
    sysroot = f"--sysroot={ws / ARMHF_ROOT_REL}"
    run(
        [platform / "tools/mt8163-arm32/otbr/build_otbr_deps.sh", deps],
        env=dict(
            os.environ,
            OTBR_DEPS_ARCHIVES=str(archives),
            ARM_CC=str(ws / ARMHF_ROOT_REL / "usr/bin/arm-linux-gnueabihf-gcc"),
            ARM_CXX=str(ws / ARMHF_ROOT_REL / "usr/bin/arm-linux-gnueabihf-g++"),
            CFLAGS=f"-O2 {sysroot}",
            CXXFLAGS=f"-O2 {sysroot}",
            LDFLAGS=sysroot,
        ),
    )
    for lib in OTBR_DEPS_LIBS:
        if not (deps / "lib" / lib).is_file():
            raise Fail(f"{OTBR_DEPS_REL}/lib/{lib} was not built")
    receipt.write_text(digest + "\n", encoding="utf-8")
    print("inputs: OTBR deps built and verified")


def stage_kernel_uapi(ws):
    root = ws / KERNEL_UAPI_REL
    include = root / "include"
    if all((include / tree).is_dir() for tree in KERNEL_UAPI_TREES):
        print("inputs: kernel UAPI headers present")
        return
    source = ws / LINUX_REL
    if not (source / "Makefile").is_file():
        raise Fail(f"{LINUX_REL} is missing; run `tools/integrate.py rebuild` first")
    out = ws / KERNEL_UAPI_OUT_REL
    for path in (root, out):
        if path.exists():
            shutil.rmtree(path)
    print("inputs: exporting kernel UAPI headers")
    # headers_install is standalone (no kernel build); this mirrors the
    # "Export Linux UAPI headers" step in the product release workflow.
    run(["make", "-C", source, f"O={out}", "ARCH=arm", "headers_install",
         f"INSTALL_HDR_PATH={root}"])
    for tree in KERNEL_UAPI_TREES:
        if not (include / tree).is_dir():
            raise Fail(f"kernel UAPI export is missing include/{tree}")


def stage_neural_deps(ws):
    deps = ws / PUBLIC_DEPS_REL
    neural = ws / NEURAL_REL
    manifest = neural / NEURAL_MANIFEST
    if manifest.is_file() and all((neural / path).exists() for path in NEURAL_REQUIRED):
        print("inputs: public neural deps present and verified")
        return
    script = ws / PRODUCT_BUILD_REL / "ci/build-public-neural-deps.sh"
    if not script.is_file():
        raise Fail(f"neural dependency builder is missing: {rel(ws, script)}")
    tmp = ws / INPUTS_REL / "tmp/neural"
    tmp.mkdir(parents=True, exist_ok=True)
    cross = ws / ARMHF_ROOT_REL / "usr/bin/arm-linux-gnueabihf-"
    env = dict(
        os.environ,
        RUNNER_TEMP=str(tmp),
        LIBREECHO_NEURAL_CROSS=str(cross),
        JOBS=os.environ.get("JOBS") or str(os.cpu_count() or 2),
    )
    print("inputs: building the public neural dependency closure (several minutes)")
    run([script, deps, ws / ARMHF_ROOT_REL], env=env)
    missing = [path for path in NEURAL_REQUIRED if not (neural / path).exists()]
    if missing:
        raise Fail(f"neural dependency output is incomplete: {missing[0]}")
    print("inputs: public neural deps built and verified")


def tts_ready(ws):
    spec_path = ws / TTS_SPEC_REL
    if not spec_path.is_file():
        return False
    spec = load_json(spec_path)
    for voice in spec.get("voices", {}).values():
        output = ws / PUBLIC_DEPS_REL / voice["output_file"]
        if not output.is_file() or sha256_file(output) != voice["reviewed_sha256"]:
            return False
    return True


def stage_tts_models(ws):
    if tts_ready(ws):
        print("inputs: reviewed TTS voice models present and verified")
        return
    script = ws / TTS_DERIVE_REL
    if not script.is_file():
        raise Fail(f"TTS derivation script is missing: {rel(ws, script)}")
    print("inputs: deriving reviewed TTS voice models")
    run([sys.executable, script, "--deps-root", ws / PUBLIC_DEPS_REL])
    if not tts_ready(ws):
        raise Fail("TTS derivation did not reproduce the reviewed hashes")


def build_image_config(ws):
    """The image pin from tools/lab-build.json: (name, digest-or-None)."""
    path = ws / LAB_BUILD_CONFIG_REL
    if not path.is_file():
        raise Fail(f"{LAB_BUILD_CONFIG_REL}: missing")
    config = load_json(path)
    image = config.get("build_image") or {}
    name = image.get("name") or BUILD_IMAGE_NAME
    digest = image.get("digest")
    if isinstance(digest, str) and digest.strip():
        return name, digest.strip()
    return name, None


def pinned_image_ref(name, digest):
    return f"{name}@{digest}" if digest else LOCAL_BUILD_IMAGE


def ensure_build_image(ws, build):
    """Pull the pinned image, or build it locally when there is no digest.

    The image carries the ubuntu-24.04 CI host baseline; the product's public
    inputs and toolchains are still staged separately.
    """
    if shutil.which("podman") is None:
        raise Fail("podman is required to prepare the build image")
    name, digest = build_image_config(ws)
    if build or not digest:
        containerfile = ws / CONTAINERFILE_REL
        if not containerfile.is_file():
            raise Fail(
                f"{CONTAINERFILE_REL} is missing; run `tools/integrate.py rebuild` first")
        print(f"image: building {LOCAL_BUILD_IMAGE} from {CONTAINERFILE_REL}")
        run(["podman", "build", "--network=host", "-f", containerfile,
             "-t", LOCAL_BUILD_IMAGE, ws / PRODUCT_REL])
    else:
        ref = pinned_image_ref(name, digest)
        print(f"image: pulling {ref}")
        run(["podman", "pull", ref])


def fetch_inputs(ws):
    build = ws / PRODUCT_BUILD_REL
    if not build.is_dir():
        raise Fail(
            f"{PRODUCT_BUILD_REL} is missing; run `tools/integrate.py rebuild` first"
        )
    ci = build / "ci"
    inputs = build / "inputs"
    platform_sendspin = ws / PLATFORM_REL / "tools/mt8163-arm32/sendspin"
    deps = ws / PUBLIC_DEPS_REL
    stage_public_deps(
        ws, ci, inputs, deps,
        platform_sendspin / "SOURCE.lock",
        platform_sendspin / "patches",
    )
    stage_toolchain(
        ci / "aarch64_toolchain.py", inputs / "aarch64-cross-toolchain.lock.json",
        ws / AARCH64_DEBS_REL, ws / AARCH64_ROOT_REL, AARCH64_RECEIPT,
        "aarch64 kernel cross",
    )
    stage_toolchain(
        ci / "armhf_toolchain.py", inputs / "armhf-cross-toolchain.lock.json",
        ws / ARMHF_DEBS_REL, ws / ARMHF_ROOT_REL, ARMHF_RECEIPT,
        "ARMHF userspace cross",
    )
    stage_musl(ws, ci / "build-public-toolchain.sh", ws / MUSL_ROOT_REL)
    platform = ws / PLATFORM_REL
    stage_otbr_source(ws, platform)
    stage_otbr_deps(ws, platform)
    stage_kernel_uapi(ws)
    stage_neural_deps(ws)
    stage_tts_models(ws)


def install_hooks(ws):
    """Point the port repo at the versioned hooks; skip outside a git checkout."""
    proc = subprocess.run(
        ["git", "-C", str(ws), "rev-parse", "--git-dir"],
        text=True, capture_output=True,
    )
    if proc.returncode != 0:
        print("skip: git hooks (workspace is not a git repository)")
        return
    run(["git", "-C", str(ws), "config", "core.hooksPath", ".githooks"])


def cmd_init(ws, args):
    install_hooks(ws)
    manifest = load_manifest(ws)
    for entry in manifest["repos"]:
        path = ws / entry["path"]
        if path.exists():
            if not is_git_repo(path):
                raise Fail(f"{entry['path']} exists but is not a git repository")
            ensure_remotes(ws, entry)
            sync_fork_branches(path, entry, args.sync_forks)
        else:
            clone_fork(ws, entry)
    if args.no_integrate:
        print("skip: integration rebuild (--no-integrate)")
    else:
        run([sys.executable, ws / "tools" / "integrate.py", "rebuild",
             "--workspace", ws])
    if args.no_image:
        print("skip: build image (--no-image)")
    else:
        ensure_build_image(ws, args.build_image)
    if args.no_inputs:
        print("skip: public inputs (--no-inputs)")
    else:
        fetch_inputs(ws)
    return 0


# --------------------------------------------------------------------------
# keygen


def ensure_local_json(ws):
    path = ws / LOCAL_JSON
    if path.is_file():
        return path
    example = ws / LOCAL_EXAMPLE
    if not example.is_file():
        raise Fail(f"{LOCAL_EXAMPLE} is missing")
    path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(example, path)
    path.chmod(0o600)
    print(f"wrote {LOCAL_JSON} from {LOCAL_EXAMPLE}; fill in the local input paths")
    return path


def resolve_local_path(ws, doc, key, default):
    value = doc.get(key) or default
    if not value:
        raise Fail(f"{LOCAL_JSON}: {key} is empty and has no default")
    path = Path(value).expanduser()
    return path if path.is_absolute() else ws / path


def nacl_importable(python):
    if not Path(python).is_file():
        return False
    proc = subprocess.run(
        [str(python), "-c", "import nacl.signing"], capture_output=True
    )
    return proc.returncode == 0


def wheelhouse_dir(ws):
    for candidate in (
        ws / PUBLIC_DEPS_REL / "python-wheels",
        ws / PRODUCT_BUILD_REL / "inputs" / "reviewed" / "python-wheels",
    ):
        if (candidate / "requirements.txt").is_file():
            return candidate
    raise Fail("reviewed Python wheelhouse not found; run `workspace.py init` first")


def python_with_nacl(ws):
    venv = ws / KEYGEN_VENV_REL
    python = venv / "bin" / "python"
    if nacl_importable(python):
        return python
    try:
        wheelhouse = wheelhouse_dir(ws)
    except Fail:
        wheelhouse = None
    if wheelhouse is None:
        for candidate in (sys.executable, shutil.which("python3.11")):
            if candidate and nacl_importable(candidate):
                return candidate
        raise Fail(
            "PyNaCl is not available; run `workspace.py init` to fetch the reviewed wheelhouse"
        )
    if venv.exists():
        shutil.rmtree(venv)
    run([find_python311(), "-m", "venv", venv])
    run([python, "-m", "pip", "install", "--disable-pip-version-check",
         "--no-index", "--find-links", wheelhouse, "--require-hashes",
         "--requirement", wheelhouse / "requirements.txt"])
    return python


def cmd_keygen(ws):
    local_path = ensure_local_json(ws)
    doc = load_json(local_path)
    seed = resolve_local_path(ws, doc, "ota_signing_key", DEFAULT_SIGNING_KEY)
    public = resolve_local_path(ws, doc, "ota_public_key", DEFAULT_PUBLIC_KEY)
    for path in (seed, public):
        if path.exists():
            raise Fail(f"refusing to overwrite {rel(ws, path)}; move it aside first")
    python = python_with_nacl(ws)
    seed.parent.mkdir(parents=True, exist_ok=True)
    public.parent.mkdir(parents=True, exist_ok=True)
    run([python, "-c", KEYGEN_SOURCE, seed, public])
    print(f"wrote {rel(ws, seed)} (mode 600) and {rel(ws, public)}")
    return 0


# --------------------------------------------------------------------------
# doctor


def collect_problems(ws):
    problems = []

    local_path = ws / LOCAL_JSON
    local = None
    if not local_path.is_file():
        problems.append(f"{LOCAL_JSON}: missing (run `workspace.py keygen`)")
    else:
        try:
            local = load_json(local_path)
        except Fail as exc:
            problems.append(str(exc))
        else:
            if not isinstance(local, dict):
                problems.append(f"{LOCAL_JSON}: expected a JSON object")
                local = None
    if local is not None:
        for key in LOCAL_PATH_KEYS:
            value = local.get(key)
            if not value:
                problems.append(f"local.json: {key} is empty")
            elif not resolve_local_path(ws, local, key, None).exists():
                problems.append(f"local.json: {key} points at a missing path: {value}")
        # gh is only needed once the owner starts using the cluster artifacts,
        # so a desktop-only build must not fail on it.
        if shutil.which("gh") is None:
            print("note: gh missing (needed for cluster artifact push/fetch)")

    manifest = None
    try:
        manifest = load_manifest(ws)
    except Fail as exc:
        problems.append(str(exc))
    if manifest is not None:
        for entry in manifest["repos"]:
            path = ws / entry["path"]
            if not is_git_repo(path):
                problems.append(f"{entry['path']}: clone missing")
                continue
            names = remotes(path)
            if FORK_REMOTE not in names:
                problems.append(f"{entry['path']}: remote {FORK_REMOTE!r} missing")
            if UPSTREAM_REMOTE not in names:
                problems.append(f"{entry['path']}: remote {UPSTREAM_REMOTE!r} missing")
            for topic in entry["topics"]:
                if rev(path, f"refs/heads/{topic['branch']}") is None:
                    problems.append(f"{entry['path']}: branch {topic['branch']} missing")
            if base_is_fork_branch(entry) and \
                    rev(path, f"refs/heads/{entry['base']}") is None:
                problems.append(
                    f"{entry['path']}: base branch {entry['base']} missing")

    lock_path = ws / LOCK_REL
    if not lock_path.is_file():
        problems.append(f"{LOCK_REL}: missing (run `workspace.py init`)")
    else:
        try:
            lock = load_json(lock_path)
        except Fail as exc:
            problems.append(str(exc))
        else:
            entries = lock.get("repos") if isinstance(lock, dict) else None
            for name, entry in (entries or {}).items():
                ip = ws / entry.get("integration_path", "")
                if not ip.is_dir():
                    problems.append(
                        f"{name}: integration worktree missing ({entry.get('integration_path')})"
                    )

    deps = ws / PUBLIC_DEPS_REL
    if not (deps / "SHA256SUMS").is_file():
        problems.append(f"{PUBLIC_DEPS_REL}/SHA256SUMS: missing")
    for root_rel, receipt, label in (
        (AARCH64_ROOT_REL, AARCH64_RECEIPT, "aarch64 kernel cross"),
        (ARMHF_ROOT_REL, ARMHF_RECEIPT, "ARMHF userspace cross"),
    ):
        if not (ws / root_rel / receipt).is_file():
            problems.append(f"{root_rel}/{receipt}: missing ({label})")
    musl = ws / MUSL_ROOT_REL
    if not (musl / "bin" / "arm-linux-musleabihf-gcc").is_file():
        problems.append(f"{MUSL_ROOT_REL}/bin/arm-linux-musleabihf-gcc: missing")
    if not all((ws / NEURAL_REL / path).exists() for path in NEURAL_REQUIRED):
        problems.append(f"{NEURAL_REL}: missing public neural dependency output")
    if not tts_ready(ws):
        problems.append(f"{PUBLIC_DEPS_REL}: missing reviewed TTS voice models")

    source = ws / OTBR_SOURCE_REL
    if not is_git_repo(source):
        problems.append(f"{OTBR_SOURCE_REL}: missing (OTBR source)")
    elif not otbr_source_ready(source):
        problems.append(f"{OTBR_SOURCE_REL}: third_party submodules not initialized")
    else:
        lock_path = ws / PLATFORM_REL / OTBR_LOCK_REL
        if lock_path.is_file():
            try:
                pinned = (load_json(lock_path).get("commit") or "")
            except Fail as exc:
                problems.append(str(exc))
            else:
                if pinned and rev(source, "HEAD") != pinned:
                    problems.append(
                        f"{OTBR_SOURCE_REL}: HEAD is not the SOURCE.lock commit "
                        f"{pinned[:12]}")
    deps = ws / OTBR_DEPS_REL
    if not all((deps / "lib" / lib).is_file() for lib in OTBR_DEPS_LIBS):
        problems.append(f"{OTBR_DEPS_REL}: missing (OTBR deps)")
    for tree in KERNEL_UAPI_TREES:
        if not (ws / KERNEL_UAPI_REL / "include" / tree).is_dir():
            problems.append(
                f"{KERNEL_UAPI_REL}/include/{tree}: missing (Linux UAPI headers)")

    for tool in HOST_TOOLS:
        if shutil.which(tool) is None:
            problems.append(f"host tool missing: {tool}")
    if shutil.which("podman") is None:
        problems.append("podman is not installed (needed to run the build image)")
    else:
        try:
            name, digest = build_image_config(ws)
        except Fail as exc:
            problems.append(str(exc))
        else:
            ref = pinned_image_ref(name, digest)
            proc = subprocess.run(["podman", "image", "inspect", ref],
                                  capture_output=True, text=True)
            if proc.returncode != 0:
                problems.append(f"build image missing: {ref}")
    try:
        find_python311()
    except Fail as exc:
        problems.append(str(exc))
    return problems


def collect_warnings(ws):
    """Non-fatal advisories: the disk, not the inputs."""
    warnings = []
    try:
        free = shutil.disk_usage(ws).free
    except OSError:
        return warnings
    if free < MIN_FREE_DISK:
        warnings.append(
            f"only {free // (1024 ** 3)} GB free under {ws}; 20 GB recommended")
    return warnings


def cmd_doctor(ws):
    problems = collect_problems(ws)
    for problem in problems:
        print(f"MISSING: {problem}")
    for warning in collect_warnings(ws):
        print(f"WARN: {warning}")
    if problems:
        print(f"{len(problems)} item(s) missing; see docs/plan.md Phase 7")
        return 1
    print("ready: clones, integration lock, public inputs and private inputs are present")
    return 0


# --------------------------------------------------------------------------


def main(argv=None):
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--workspace", default=argparse.SUPPRESS,
        help="workspace root (default: parent of tools/, or $LIBREECHO_WORKSPACE)",
    )
    parser = argparse.ArgumentParser(
        description="Prepare work/ and private/ inputs for a Lidar build.",
    )
    parser.add_argument("--workspace", default=None, help=argparse.SUPPRESS)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser(
        "init", parents=[common],
        help="clone forks, rebuild integration, fetch public inputs",
    )
    p_init.add_argument("--no-integrate", action="store_true",
                        help="skip the tools/integrate.py rebuild")
    p_init.add_argument("--no-inputs", action="store_true",
                        help="skip fetching the public build inputs")
    p_init.add_argument("--build-image", action="store_true",
                        help="build the build image locally from the Containerfile "
                             "even when the pin names a digest")
    p_init.add_argument("--no-image", action="store_true",
                        help="skip preparing the build image")
    p_init.add_argument("--sync-forks", action="store_true",
                        help="reset a cached branch whose fork history was rewritten "
                             "(only when no worktree has it checked out)")

    sub.add_parser("keygen", parents=[common],
                   help="create the ed25519 OTA signing key pair")
    sub.add_parser("doctor", parents=[common],
                   help="report missing clones, inputs and private inputs")

    args = parser.parse_args(argv)
    ws = workspace_from(args)
    try:
        if args.cmd == "init":
            return cmd_init(ws, args)
        if args.cmd == "keygen":
            return cmd_keygen(ws)
        return cmd_doctor(ws)
    except Fail as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
