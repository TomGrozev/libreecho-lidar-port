# LibreEcho-Linux branch audit (2026-11-24)

Repo: `private/forks/LibreEcho-Linux` (remotes: `origin` = aslater3/LibreEcho-Linux,
`fork` = TomGrozev/LibreEcho-Linux). Local work only; nothing pushed.

## Target shape

- Upstream base (verified `origin` is upstream): `origin/feature/linux-6.18` =
  `16989cef41b7` (53 commits after local `v6.18.64`).
- `fix/general-fixes-from-lidar-port` = `16989cef` + 2 cherry-picks:
  - `905f315821d3` ASoC: tlv320aic32x4: Prevent division by zero (upstream 8cf9607d2d85)
  - `bc995c63281f` wifi: cfg80211: fix OOB read in valid_rule() (upstream 9d8ec0b5b529)
  Both fix code built by the MT8163 arm32 targets (tlv320aic32x4 and cfg80211 are in
  `mt8163_arm32_defconfig` / Radar-Puffin DTS), so they are target-independent.
- `feature/lidar-support` = `fix/general-fixes-from-lidar-port` + 34 Lidar commits
  (tip `8094768d2b00`). Stacked on the general topic.

### Classification of the three upstream-style commits

| Commit | Class | Placement |
| --- | --- | --- |
| `09db0effc310` ASoC div-by-zero | general (shared codec) | `fix/general-fixes-from-lidar-port` (`905f315821d3`) |
| `f78cf428744d` cfg80211 OOB | general (shared net/wireless) | `fix/general-fixes-from-lidar-port` (`bc995c63281f`) |
| `40357111ed98` Lidar mono-left | Lidar-only | Lidar topic (`ac9c78f8c324`) |

### Commit intentionally dropped

`370c40b22339` `proc: handle a NULL mm in map_files lookup and readdir` is not ported.
Upstream 6.18 reverted it (`9ba5c0f3d7f8`, 2026-10-24) because `mm_access()` now returns
`ERR_PTR(-ESRCH)`, and re-applying it makes listing a kernel thread's `map_files` fail with
ESRCH instead of returning an empty directory. The commit remains reachable through the
archive tags below.

### Duplicate Kconfig fix

`drivers/misc/Kconfig` had `config AMZ_PRIVACY` twice on
`feature/lidar-support-on-upstream` (upstream already carried one; the port commit added a
second). Fixed inside the commit that introduced it: `feat(lidar): carry privacy and
light-sensor drivers to 6.18` was amended while rebuilding, so it no longer touches
`drivers/misc/Kconfig`. Old `d2f45c04f8aa` -> new `359a84703cf3`. There is no separate fix
commit.

### Other normalisations while rebuilding

- `libreecho/test_targets.py`, `libreecho/validate_targets.py` were mode 100755 on the old
  branch; restored to 100644 (upstream base mode) in `libreecho: add the Lidar arm64 build
  target` (`380f44a38f83`).
- `fix(lidar): run the EFR32 uart without hardware flow control` (`47feddd6b58f`) ported as
  `8094768d2b00`.

## Commands and results

```
# base checks
git rev-parse origin/feature/linux-6.18            -> 16989cef41b7dadade9be2a7b252984599aabcfe
git merge-base feature/lidar-support-on-upstream origin/feature/linux-6.18
                                                   -> 16989cef (branch was exactly upstream + 36)
# general topic
git worktree add -b fix/general-fixes-from-lidar-port /tmp/wt-klidar origin/feature/linux-6.18
git cherry-pick 09db0effc310 f78cf428744d         -> 905f315821d3, bc995c63281f
# lidar topic (new worktree from the general topic; 33 picks + EFR32 + amend)
git worktree add -b feature/lidar-support-next /tmp/wt-klidar2 fix/general-fixes-from-lidar-port
git cherry-pick <33 commits, order as listed below> -> 33 commits, no conflicts
git commit --amend (remove duplicate AMZ_PRIVACY from d2f45c04) -> 359a84703cf3
git commit --amend (restore 100644 modes in 23f3c334)         -> 380f44a38f83
git cherry-pick 47feddd6b58f                        -> 8094768d2b00
git branch -m feature/lidar-support retired/lidar-support-pre-rebase
git branch -m feature/lidar-support-next feature/lidar-support
git worktree remove /tmp/wt-klidar /tmp/wt-klidar2
```

### Tree proof against the OTA kernel `47feddd6b58f`

The new branch is based on a different but descendant base (upstream 6.18 branch instead of
`v6.18.64`), so the literal tree comparison includes the upstream delta. Proof split:

- `P` = 234 paths changed by either the OTA series (`v6.18.64..47feddd6`) or the new series
  (`fix/general..feature/lidar-support`). Outside `P`, in `arch/arm64/boot/dts`, `drivers`
  and `sound`, 1571 of 1572 changed paths have blob(new) == blob(origin/6.18) and
  blob(47feddd6) == blob(v6.18.64); the 1572nd is `sound/soc/codecs/tlv320aic32x4-clk.c`,
  changed only by the general topic. Every hunk there is therefore the upstream 6.18 delta.
- Inside `P`, 17 paths differ from `47feddd6`:

| Path | Hunk | Classification |
| --- | --- | --- |
| `.github/workflows/checks.yml` | +255 | intended: OTA's 6.18-lts-line CI replaced by upstream's checks.yml + arm64 lane (`380f44a38f83`) |
| `.../libreecho-lidar-audio.dtsi` | +2 | intended: `libreecho,mono-left` (`ac9c78f8c324`) |
| `.../libreecho-lidar.dts` | 0 (identical) | EFR32 fix ported |
| `drivers/iio/light/Kconfig` | +2 | upstream 6.18 base already has the LibreEcho source line |
| `drivers/leds/leds-is31fl32xx.c` | +21 | upstream 6.18 base (`91abd011436f` LED ring) |
| `drivers/misc/Kconfig` | 2 | upstream layout + `source mediatek/Kconfig`; duplicate removed |
| `drivers/usb/musb/mediatek.c` | +830 | upstream 6.18 base (`6f13c1a4825a` MT8163 MUSB) |
| `drivers/usb/musb/musb_gadget.c` | +17 | upstream 6.18 base diag lines |
| `fs/proc/base.c` | 22 | intended: upstream reverted the NULL-mm patch; not re-applied |
| `libreecho/targets.json` | +20 | upstream tooling + Lidar row (`380f44a38f83`) |
| `libreecho/test_targets.py` | +166 | upstream tooling + arm64 cases |
| `libreecho/validate_targets.py` | +98 | upstream tooling + arch/image validation |
| `sound/soc/codecs/tlv320aic32x4.c` | +1087 | upstream 6.18 base (Radar-Puffin AIC32x4) + our biquad/page/mono commits |
| `sound/soc/codecs/tlv320aic32x4.h` | +7 | same base |
| `sound/soc/mediatek/Kconfig` | +32 | upstream 6.18 base (`ab11d3b2d05e` MT8163 AFE/card) |
| `sound/soc/mediatek/Makefile` | +2 | same base |
| `tools/mt8163_mute_lamp_contract_test.py` | +119 | upstream 6.18 base |
| `tools/mt8163_pstore_ramoops_contract_test.py` | +83 | upstream 6.18 base |

Rebuild equivalence check: `git diff 23f3c3340969 feature/lidar-support` shows only
`libreecho-lidar.dts` (EFR32), `drivers/misc/Kconfig` (duplicate removed),
`fs/proc/base.c` (revert kept), and two 0-line mode fixes. No other content moved.

### Compile (real, out-of-tree)

```
cd <worktree on feature/lidar-support>
LD_LIBRARY_PATH=private/artifacts/phase-05/toolchains/aarch64-cross/usr/lib/x86_64-linux-gnu \
make O=/tmp/klidar-check ARCH=arm64 \
  CROSS_COMPILE=private/artifacts/phase-05/toolchains/aarch64-cross/usr/bin/aarch64-linux-gnu- \
  LD=.../aarch64-linux-gnu-ld.bfd mt8167_arm64_defconfig
... same env, KBUILD_BUILD_TIMESTAMP='2026-11-24 07:58:51 UTC' make -j12 \
  O=/tmp/klidar-check ... Image mediatek/libreecho-lidar.dtb
```

Result: complete build, no errors, 172 s.
- `Image` sha256 `9bc49cc9a853fa6997b11da5eda286ae56545435aec5c738f9b4b0a971e28fa0`
  (15,311,360 bytes)
- `libreecho-lidar.dtb` sha256
  `0e72a705958126552da101a48769d3442bded0e820b9b4ee6aca5a71182247ec`
  (24,036 bytes)
- OTA `47feddd6` DTB (`private/artifacts/phase-07/ota-v0.2.35/kernel/libreecho-lidar.dtb`)
  sha256 `0e9cc4ffd16b6ece79d5c698a15bb35aa5e252c73276f9525f9e73f64154913a`.
- `dtc -I dtb -O dts` (kernel-built `scripts/dtc/dtc`) diff: exactly one hunk, the
  `libreecho,mono-left;` property. No `uart-has-rtscts` in either DTB.

The toolchain needs `LD_LIBRARY_PATH=<prefix>/usr/lib/x86_64-linux-gnu` (binutils host lib)
or `scripts/Kconfig.include` reports "unknown assembler invoked".

## Branch table

| Old branch | Old head | New | New head |
| --- | --- | --- | --- |
| `feature/lidar-support` | `f07f26f4ab68` | `feature/lidar-support` (rebuilt) | `8094768d2b00` |
| `feature/lidar-support-on-upstream` | `23f3c3340969` | same topic (36 -> 33 + 1 port; 2 general, 1 dropped) | `8094768d2b00` |
| `fix/lidar-port-identity` | `47feddd6b58f` | same topic + EFR32 commit | `8094768d2b00` |
| `feature/lidar-6.18` | `89b7f3f07a51` | commits folded into topic; branch archived | tag |
| `feature/lidar-6.18-audio` | `12ea437df304` | folded; archived | tag |
| `feature/lidar-6.18-mt7668` | `275ab69ce648` | folded; archived | tag |
| `fix/lidar-6.18-boot` | `15e16539a61d` | folded; archived | tag |
| `fix/lidar-6.18-volume` | `d70e787ff949` | folded; archived | tag |
| `feature/6.18-lts-line` | `600d0257d7f3` | superseded by upstream tooling; archived | tag |
| `feature/lidar-support-6.1` | `6046668bd5ed` | superseded (MT8163 stays 6.1 but not this repo's 6.18 topic); archived | tag |
| `experiment/lidar-console-wdt` | `79801bc0efe1` | archived | tag |
| `experiment/lidar-lk-slot-source` | `79d8d10e16b6` | archived | tag |
| `experiment/lidar-usb-upstream-glue` | `a251a739ff78` | archived | tag |
| `experiment/lidar-wdt-fetch-diag` | `a251a739ff78` | archived | tag |
| `linux-6.18` | `fd7cfd39c885` | only the v6.18.64 tag commit; archived | tag |
| `main` | `2922465d65dc` | kept; primary worktree now on it | unchanged |

## Commit mapping (old -> new)

Upstream-style and Lidar commits from `23f3c3340969` (same mapping applies to the
patch-equivalent commits on `47feddd6b58f` and `f07f26f4ab68`; the OTA-side duplicate
`c3babd92785b` maps to new `566d1d7b7128`):

| Old | New | Subject |
| --- | --- | --- |
| `09db0effc310` | `905f315821d3` (general) | ASoC: tlv320aic32x4: Prevent division by zero |
| `f78cf428744d` | `bc995c63281f` (general) | wifi: cfg80211: fix OOB read in valid_rule() |
| `9a98045c52f3` | `1045ed46f1a3` | import MT7668 gen4 SDIO WLAN |
| `ef5bf1573fbc` | `a9ad54b82243` | MT8516 audio front end |
| `7a9efa9ac91f` | `e7110e5b3b80` | Amazon Lidar sound card |
| `f1725cb77f74` | `50bfabc54ad4` | biquad and mono mix controls |
| `269191008e2d` | `596c65fb9a1e` | TDM and BCLK-only clocking |
| `73b0061fdef5` | `566d1d7b7128` | audio devicetree |
| `e4e6e1876b8f` | `60d5b5c6e748` | docs BCLK-only |
| `1f862b971acd` | `fb219151294a` | port mt7668 to cfg80211 API |
| `2a7c1f4b87df` | `fe6364f4c659` | avoid duplicate is_world_regdom |
| `d532da93747f` | `a1a62e320d11` | MT8516 reset and MSDC2 |
| `d2f45c04f8aa` | `359a84703cf3` | privacy and light-sensor drivers (Kconfig fixed) |
| `a2540850711b` | `e0ae97204268` | frame ABI on is31fl32xx |
| `4f4c9355ac43` | `b6d8960cc00a` | MUSB receive fix + isoc PIO |
| `0ee7cdce9e48` | `f90e97250e62` | MT7668 Bluetooth firmware |
| `c0d930683eb4` | `47553a743e54` | MT8516 AFE node |
| `4c76054b7a9d` | `af8d87a2567a` | RT5738 Vproc buck |
| `144c9dfc7728` | `26a104cae2c1` | privacy state from GPIO |
| `0c83da2c0f86` | `e4badb174356` | Lidar board DTS and defconfig |
| `3c9a4ac4a3aa` | `5afd9366cae7` | build audio and Wi-Fi in |
| `9dac3b9d3ba7` | `0d5f7f2c5b7e` | 8250_mtk power-down sleep |
| `9961afe0ab77` | `dd76e4bd2e0b` | MSDC hosts bind |
| `fe2307af4e2a` | `8dc569b1b18e` | MUSB rx_kick port |
| `f82c9245bbf4` | `b8ca241cbfdd` | AIC32x4 page selector |
| `900abb2b8521` | `a0e1c8fb919a` | 8250 serial aliases |
| `e440c6b4e4cb` | `5e8410dd3dbf` | privacy node amz_privacy |
| `8b9e28718e6f` | `dcee79e89b97` | mediatek-cpufreq 1.3 GHz |
| `d74556925951` | `fa8b9b6f602b` | MFG power domains off |
| `57ebaeecf1a1` | `a5cb8ec44c2a` | TSL2540, tmp112, thermal zone |
| `c0cd1de2ee94` | `9988fc91c52e` | tsl2540 remove unwinds |
| `542603f40610` | `04065168023b` | ambient light sensor power |
| `88c7a2656ea2` | `e883e987d964` | thermal trip points |
| `40357111ed98` | `ac9c78f8c324` | Lidar mono playback left slot |
| `23f3c3340969` | `380f44a38f83` | Lidar arm64 build target |
| `370c40b22339` | (dropped) | proc NULL-mm (upstream reverted) |
| `47feddd6b58f` | `8094768d2b00` | EFR32 uart without rtscts |

Branches whose commits are all archived (no topic mapping): `feature/6.18-lts-line`,
`feature/lidar-support-6.1`, the four `experiment/*`, `linux-6.18`.

## Archive tags created (`archive/<branch>-2026-11-24`)

`archive/experiment/lidar-console-wdt-2026-11-24` -> `79801bc0efe1`
`archive/experiment/lidar-lk-slot-source-2026-11-24` -> `79d8d10e16b6`
`archive/experiment/lidar-usb-upstream-glue-2026-11-24` -> `a251a739ff78`
`archive/experiment/lidar-wdt-fetch-diag-2026-11-24` -> `a251a739ff78`
`archive/feature/6.18-lts-line-2026-11-24` -> `600d0257d7f3`
`archive/feature/lidar-6.18-2026-11-24` -> `89b7f3f07a51`
`archive/feature/lidar-6.18-audio-2026-11-24` -> `12ea437df304`
`archive/feature/lidar-6.18-mt7668-2026-11-24` -> `275ab69ce648`
`archive/feature/lidar-support-2026-11-24` -> `f07f26f4ab68`
`archive/feature/lidar-support-6.1-2026-11-24` -> `6046668bd5ed`
`archive/feature/lidar-support-on-upstream-2026-11-24` -> `23f3c3340969`
`archive/fix/lidar-6.18-boot-2026-11-24` -> `15e16539a61d`
`archive/fix/lidar-6.18-volume-2026-11-24` -> `d70e787ff949`
`archive/fix/lidar-port-identity-2026-11-24` -> `47feddd6b58f`
`archive/linux-6.18-2026-11-24` -> `fd7cfd39c885`

Existing `archive/*` tags pointed at older heads and were left untouched. Backup tags
`backup/2026-11-24/*` were made by Main and not duplicated.

## Owner-deletes (git branch -d cannot reach these; they are not ancestors of HEAD)

`retired/lidar-support-pre-rebase` (old `feature/lidar-support`, `f07f26f4ab68`),
`feature/lidar-support-on-upstream`, `fix/lidar-port-identity`, `feature/lidar-6.18`,
`feature/lidar-6.18-audio`, `feature/lidar-6.18-mt7668`, `fix/lidar-6.18-boot`,
`fix/lidar-6.18-volume`, `feature/6.18-lts-line`, `feature/lidar-support-6.1`,
`experiment/lidar-console-wdt`, `experiment/lidar-lk-slot-source`,
`experiment/lidar-usb-upstream-glue`, `experiment/lidar-wdt-fetch-diag`, `linux-6.18`.
All have an archive tag at the exact head. `main` stays.

## Worktrees and manifest entry

```
private/forks/LibreEcho-Linux        -> main (2922465d65dc), clean
private/forks/LibreEcho-Linux-618    -> feature/lidar-support (8094768d2b00), clean
artifacts/.../ota-v0.2.35/src/Linux-618 -> detached 47feddd6, untouched
```

```json
{
  "name": "LibreEcho-Linux",
  "path": "private/forks/LibreEcho-Linux",
  "integration_path": "private/integration/LibreEcho-Linux",
  "base": "origin/feature/linux-6.18",
  "topics": [
    {"branch": "fix/general-fixes-from-lidar-port", "scope": "general"},
    {"branch": "feature/lidar-support", "scope": "lidar"}
  ],
  "in_ota": true
}
```

## Open questions

- The Lidar topic is stacked on the general topic; if the integration manifest places general
  after lidar, merges would break order. Manifest must keep general first (as above).
- `Image` was not compared to the OTA image because the base and compiler differ (GCC vs the
  OTA's LLVM build); only the DTB is comparable, and it matches apart from `mono-left`.
