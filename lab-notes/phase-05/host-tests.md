# Host tests for the shell suites

The shell-level suites start `/bin/busybox` directly. This workstation has no
`/bin/busybox` and its `/usr/bin` is root-owned, so the suites cannot run as
the normal user. They are not skipped: a static x86_64 busybox is built under
`artifacts/phase-05/host-tools/` and a bubblewrap mount namespace makes it
visible at `/bin/busybox` for the test process only.

## Busybox

Source and version match the ARM32 build: `busybox-1.37.0.tar.bz2` from
`artifacts/phase-05/toolchains/sources/`, built from `make defconfig` plus
three host changes: `CONFIG_STATIC=y`, built-in crypt
(`CONFIG_USE_BB_CRYPT=y`, `CONFIG_USE_BB_CRYPT_SHA=y`, because this host has
no static libcrypt), and `CONFIG_TC` disabled because this host's kernel
headers removed the CBQ constants the applet still uses. The host compiler is
gcc 16.2.1. The ARM32 config was tried first, but the resulting static binary
segfaulted while extracting multiple named tar members, which the updater
needs.

Artifacts:

- `artifacts/phase-05/host-tools/busybox/busybox`
  sha256 `9289dc0ed3270bf0a0d2d0476d61af23776eeed3dce97aebc338aafb9113eee4`
- `artifacts/phase-05/host-tools/busybox/busybox-1.37.0-x86_64.config`
  sha256 `5f0f80d5e87c9501a0229cbc18fc64c7c076fd1c7f22d2380ac9f906e048d4b1`
- `artifacts/phase-05/host-tools/SHA256SUMS`

The build tree is `artifacts/phase-05/host-tools/busybox-defconfig/`; its
`build.log` records the full compile.

## Wrapper

`artifacts/phase-05/host-tools/run-host-tests.sh` execs bubblewrap 0.13.1
from `/usr/sbin/bwrap`. The namespace leaves everything in place and replaces
`/usr/bin` with a directory of absolute symlinks into a read-only bind of the
real `/usr/bin`, plus the static busybox. A read-only bind of the real
`/usr/bin` is also mounted at `artifacts/phase-05/host-tools/realbin`, which is
the symlink target, and `/usr/lib` and `/usr/include` are bound at the
wrapper's `lib` and `include` so gcc resolves `cc1` and its headers from its
prefix. `/bin` is a symlink to `usr/bin`, so both `/bin/busybox` and every
normal host tool resolve. `unshare` is not used.

Exact invocation:

```
artifacts/phase-05/host-tools/run-host-tests.sh \
  uv run --with pynacl python -m unittest <suite> -q
```

Everything runs as the normal user. The wrapper touches only
`artifacts/phase-05/host-tools/`, never the system.
