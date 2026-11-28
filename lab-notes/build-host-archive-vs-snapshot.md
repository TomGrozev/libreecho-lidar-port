# Host build pinning: Ubuntu archive snapshot vs live archive

Research note, 2026-11-27. Scope: Ubuntu 24.04 amd64 host baseline for the
LibreEcho build container. Package drift here only changes host tool versions,
not target artifacts. ARM builds come from the live `ports.ubuntu.com` archive.

Reference numbers in brackets point at the list at the end.

## 1. What snapshot.ubuntu.com is, and what it promises

Canonical's service page describes it as a way to "see and use the Ubuntu archive as it was at any specified date and time", with snapshots "available for any date and time after 1 March 2023" [1]. The stated use cases are reproducible deployments of a package set at a date, finding when a behaviour change appeared, and staged update workflows [1].

Timestamp resolution. A snapshot ID is `YYYYMMDDTHHMMSSZ` UTC [1]. A probe of the service: requesting `20240301T123456Z` returns a Release file dated `Fri, 01 Mar 2024 12:17:06 UTC` with different Packages hashes than the `20240301T030400Z` snapshot, so a non-boundary timestamp resolves to the newest snapshot at or before the requested instant rather than failing [25][2]. That matches Debian's documented behaviour ("you will get the latest available timestamp which is before the time you specified" [5]), though Ubuntu's own page words the failure case as "if the snapshot does not exist (for example, if you try to use a date before that Ubuntu release existed)" [1]. Resolution granularity is unspecified by the docs and observed in practice.

Retention. "We intend to ensure snapshots are available for dates up to at least 2 years in the past, which we may extend if there is demand" [1]. An intention, not an SLA, and the window floor moves: a pin set today ages out two years out unless refreshed.

apt integration. On 24.04 and later apt auto-detects snapshot support from a `Snapshots:` field in the repository Release file, so official repositories have snapshots enabled by default [1]. Options: `--snapshot`/`-S` per command, `Snapshot: <ID>` per source (deb822), `[snapshot=yes]` (one-line format), or `APT::Snapshot` globally; `Snapshot: no` opts out [1][23]. apt does no validation of the ID ("APT does not perform any checks so far") [23].

Ports. `https://snapshot.ubuntu.com/ubuntu-ports/<ID>/...` answers HTTP 401 [26], and a project that hit this reports the same, with the workaround that `snapshot.ubuntu.com/ubuntu/<ID>` serves arm64 too [13]. Confirmed from the service side: `.../ubuntu/20240301T030400Z/dists/noble/main/binary-arm64/Release` returns 200 [3] while the same path on `archive.ubuntu.com` returns 404 [4], and the snapshot Release file lists arm64 and armhf `Packages` at multi-megabyte sizes [2]. `noble-security` is in the same namespace at the same ID [27]. So the snapshot is one merged origin covering archive, security and ports content.

Mirrors or single origin. Nothing on the service page documents a mirror set or regional endpoint; it presents one hostname and a snapshot ID as the whole interface [1].

## 2. Debian snapshot.debian.org: intended use, warranty, warnings

Intended use: "a wayback machine that allows access to old packages based on dates and version numbers ... helpful to developers and users ... tracking down when regressions were introduced, or for providing a specific environment that a particular application may require to run" [5].

There is no FAQ page: `https://snapshot.debian.org/faq/` and `/faq` both return 404, and the front page carries no FAQ link. So no warranty or retention text exists to cite, and no explicit warning about end-user builds. What does exist:

- Losses have happened. "imports between September 4 and September 8 unfortunately failed and these snapshots are lost" (2019), and in 2024 the service moved to newly donated hardware after imports lagged [5].
- Old snapshots need a security check disabled: `Acquire::Check-Valid-Until=false` / `[check-valid-until=no]`, because Release files carry `Valid-Until` [5]. Using a snapshot means disabling an expiry guard.
- Debian's rebuild path documents that snapshots do not cover everything: `debrebuild` "use a buildinfo file and snapshot.d.o to recreate binary packages" [9], and its LIMITATIONS say the code "assumes that all packages were at some point part of Debian unstable main. This fails for packages from Debian ports, packages from experimental as well as for locally built packages or packages from third party repositories" [9].

## 3. What reproducible-builds.org says

Optional as a mechanism, necessary in effect if you want the exact package set. The "Volatile inputs can disappear" page classifies network inputs as volatile, and if a build must rely on them you should "ensure integrity using cryptographic checksums" and "keep backups" [7]. Under "Preventing dependency drift" it lists lockfiles and vendored dependencies, then: "Debian packages must be reproducible with the packages that were available in the archive when they were built. You can use `snapshot.debian.org` to create a system in that state" [7].

The "Definition strategies" page treats a reference distribution as one legitimate strategy and notes that "some distributions also keep a complete history of source packages or binary packages available for later reinstallation", while warning that installing a distribution reproducibly is itself unsolved [8].

Reading: a dated snapshot is the recognised way to reconstruct a past package set, so the right tool for "rebuild what we shipped", but not sufficient on its own (checksums and backups are still required) and it buys nothing for reproducibility of the base image install itself.

## 4. How real projects pin

Snapshot-pinned:

- Debian official Docker images, via debuerreotype. The README calls it "Reproducible, snapshot-based Debian rootfs builds (especially for Docker)", with the goal of "an auditable, reproducible process ... based on point-in-time snapshots from snapshot.debian.org" [10]. `debuerreotype-init` writes a `debuerreotype-epoch` file and regenerates the sources list with `--snapshot`, so every fetch goes to `snapshot.debian.org/archive/debian/<epoch>` [10].
- dsx-ai-factory/nvke pins one ID for every Ubuntu package, amd64 and arm64, with `fallback: abort` in autoinstall so a missing package fails the build rather than silently hitting the live archive, because "Two builds of the same commit install the same package versions". They record that nodes then need HTTPS to `snapshot.ubuntu.com` [13].
- GuillaumeDua/cpp-toolchain bumps the pin monthly by workflow, verifying all three suites resolve before the PR, and notes "Renovate cannot track this pin, because snapshot.ubuntu.com publishes no index of valid timestamps" [14].

Live-archive tracking:

- Docker Official Images policy: "Rebuilding the same `Dockerfile` should result in the same version of the image being packaged, even if the second build happens several versions later, or the build should fail outright", achieved by pinning the main package (`apt-get install -y my-package=0.1.0`), and explicitly "For dependent packages installed by `apt` there is not usually a need to pin them to a version" [11]. The same README lists "Actively rebuild for updates and security fixes" as a goal [11].
- nodejs/docker-node is the concrete shape of that: `apt-get update && apt-get install -y ca-certificates curl wget gnupg dirmngr xz-utils libatomic1 --no-install-recommends`, no snapshot and no versions [12].

Snapshot-pinned despite cost:

- valmlord/academy keeps the pin through CI outages: three consecutive e2e failures because "snapshot.ubuntu.com answered slowly", recorded as "The pinned snapshot date stays: the image must stay reproducible" [15].

## 5. Documented costs of each

Live archive drift, as it actually breaks builds:

- Exact version pins die when a point release is superseded: "Ubuntu publishes rolling security updates and drops superseded point-releases, so a fresh build of this flavor today fails ... `E: Version '3.0.2-0ubuntu1.21' for 'libssl-dev' was not found`" [17].
- Packages are removed outright: "The pinned `ca-certificates` version ... was removed from the Ubuntu 26.04 archive", blocking every PR [19]; mesa `25.2.8-0ubuntu0.24.04.4` "no longer in Ubuntu noble archive" [18].
- Stale indices give 404s: "the runner image's package lists can reference versions that have since been removed from the Ubuntu archive (currently ghostscript), which makes the install fail with 404s" [20].
- The official-images policy accepts this: a rebuild either matches or "should fail outright" [11].

Snapshot service limits:

- Hard outage: "`snapshot.ubuntu.com` answered `503 Service Unavailable` for every package ... The Dockerfile retried 6 times (about 53 minutes in total) and then gave up", delaying a release [16].
- Slow responses: builds hitting a 15 minute step limit while "snapshot.ubuntu.com answered slowly" [15].
- No public index of valid timestamps, so dependency bots cannot track the pin [14].
- No ports endpoint (`/ubuntu-ports` 401) [26][13]; go through `/ubuntu` [3].
- Rolling window: snapshots exist from 2023-03-01 and are intended for "at least 2 years" back [1], so pins must be refreshed or age out.
- Throughput: measured in this lab at about 15 kB/s from the snapshot host against about 3.4 MB/s from the live archive, consistent with the upstream reports above [15][16].
- Debian equivalents for calibration: lost and lagging imports [5], HTTP-layer rate limiting, and apt-cacher "completely ignores the Cache-Control headers that snapshot sends" [5].

## 6. Alternatives for host-level pinning

- apt Preferences pinning. `apt_preferences(5)` controls which version is selected among those offered; "APT will not question the preferences, so wrong settings can lead to uninstallable packages" [21]. Pins select, they do not fetch: when the archive stops indexing a version, the pin has nothing to select (the failure mode in [17][18][19]).
- Caching proxy (apt-cacher-ng). "A caching proxy for software packages which are downloaded by Unix/Linux system distribution mechanisms from mirror servers accessible via HTTP" [22], with explicit cache cleanup and release-removal maintenance [22]. Buys bandwidth and repeat builds while cached; costs cache lifecycle management and stale cached indices are a known 404 source [20][22].
- Vendored .deb set with checksums. The reproducible-builds checksums plus backups advice, ideally with a fallback location [7]; `debrebuild --cache` is the Debian instance [9]. Buys offline determinism; costs storage, per-architecture sets, and a re-vendor step per security update.
- Scheduled base-image rebuild. Official Images rebuild "for updates and security fixes" while demanding repeatability [11]; bounds drift by construction, at the cost of builds that differ over time and must be re-tested.

## Pros and cons for our case

| Option | Buys us | Costs us | Evidence |
| --- | --- | --- | --- |
| Live archive at build time | Full mirror speed (about 3.4 MB/s here); always current security fixes; no infrastructure | Silent version drift on every unpinned tool; exact pins break when point releases are dropped; occasional 404 from stale indices | [1][11][17][18][19][20] |
| Dated snapshot ID (`Snapshot:` / `-S`) | Same package set on every rebuild; one ID covers noble, updates and security; amd64 and arm64 from one origin | About 15 kB/s here; 503s and slow spells fail builds; no timestamp index to automate; 2 year window; `/ubuntu-ports` unusable | [1][2][3][13][14][15][16][25][26][27] |
| apt Preferences / version pins | No new infrastructure, keeps mirror speed, freezes the tools whose behaviour we bake in | Pins only choose among indexed versions, so they rot; wrong settings give uninstallable packages; everything unpinned still drifts | [21][17][18][19] |
| apt-cacher-ng in front | Repeat builds cheap once warm; survives some upstream flakiness; still uses the fast archive path | Cache lifecycle and cleanup to run; a cold or expired cache needs the live archive; stale index 404s persist | [22][20] |
| Vendored `.deb` set with checksums | Deterministic and offline; immune to drift and snapshot outages | Storage and per-arch sets; manual re-vendor per security update; checksum discipline | [7][9] |
| Rebuild on a schedule, pin nothing | Bounded, visible drift; always patched; simplest pipeline | Each rebuild can change host tool versions; needs a test gate to catch behaviour changes | [11][8] |

## Recommendation

For a build host installed once per image (our case), the snapshot is affordable: the 12 MB index and package download is paid at image build and cached in the layer, not on every product build. Prefer the snapshot, with these guards:

1. Keep the pin but bound the blast radius: install once in the image and cache the layer, never apt-install per build.
2. Add retries (`Acquire::Retries`) and treat a 503 as retryable, since outages are documented [16].
3. Record the resolved package set in the image (`dpkg-query -W`) so a rebuild diff is visible [7][11].
4. Refresh the pin deliberately before the two year window closes, and expect no <K8S_NAMESPACE_A>, since there is no timestamp index [1][14].

Fall back to the live archive, with explicit version pins in the official-images style plus a recorded manifest [11], if the snapshot becomes unreliable for us or the host tool versions need to track security updates faster than we bump the pin.

Tradeoff, stated plainly: the snapshot gives host images that rebuild identically, at the price of a slow single-origin download and a dependency on a best-effort service. The live archive gives speed and freshness at the price of silent drift in host tools and pinned versions that stop resolving when Ubuntu drops them.

## Sources

1. Ubuntu Snapshot Service, https://snapshot.ubuntu.com/
2. Snapshot Release file, noble at 20240301T030400Z, https://snapshot.ubuntu.com/ubuntu/20240301T030400Z/dists/noble/Release
3. Snapshot arm64 index, noble at 20240301T030400Z, https://snapshot.ubuntu.com/ubuntu/20240301T030400Z/dists/noble/main/binary-arm64/Release
4. Live archive arm64 index (HTTP 404), https://archive.ubuntu.com/ubuntu/dists/noble/main/binary-arm64/Release
5. snapshot.debian.org, https://snapshot.debian.org/
7. reproducible-builds.org, Volatile inputs can disappear, https://reproducible-builds.org/docs/volatile-inputs/
8. reproducible-builds.org, Definition strategies, https://reproducible-builds.org/docs/definition-strategies/
9. debrebuild(1), Debian unstable, https://manpages.debian.org/unstable/devscripts/debrebuild.1.en.html
10. debuerreotype, https://github.com/debuerreotype/debuerreotype
11. Docker Official Images README, Repeatability, https://github.com/docker-library/official-images/blob/master/README.md
12. nodejs/docker-node, 24/bookworm-slim Dockerfile, https://github.com/nodejs/docker-node/blob/main/24/bookworm-slim/Dockerfile
13. dsx-ai-factory/nvke PR 2420, https://github.com/dsx-ai-factory/nvke/pull/2420
14. GuillaumeDua/cpp-toolchain PR 157, https://github.com/GuillaumeDua/cpp-toolchain/pull/157
15. valmlord/academy issue 258, https://github.com/valmlord/academy/issues/258
16. palladium-coin/palladiumcore issue 24, https://github.com/palladium-coin/palladiumcore/issues/24
17. exasol/script-languages-release issue 1489, https://github.com/exasol/script-languages-release/issues/1489
18. carbonphysicsai/Carbon issue 1434, https://github.com/carbonphysicsai/Carbon/issues/1434
19. labmonkeys-space/app-container PR 158, https://github.com/labmonkeys-space/app-container/pull/158
20. sul-dlss/exhibits PR 3187, https://github.com/sul-dlss/exhibits/pull/3187
21. apt_preferences(5), Debian bookworm, https://manpages.debian.org/bookworm/apt/apt_preferences.5.en.html
22. Apt-Cacher-NG User Manual, https://www.unix-ag.uni-kl.de/~bloch/acng/html/index.html
23. sources.list(5), Snapshot field, https://manpages.debian.org/unstable/apt/sources.list.5.en.html
24. apt-get(8), -S/--snapshot, https://manpages.debian.org/unstable/apt/apt-get.8.en.html
25. Snapshot resolution probe, noble at 20240301T123456Z, https://snapshot.ubuntu.com/ubuntu/20240301T123456Z/dists/noble/Release
26. Snapshot ports path (HTTP 401), https://snapshot.ubuntu.com/ubuntu-ports/20240301T030400Z/dists/noble/Release
27. Snapshot security suite, noble-security at 20240301T030400Z, https://snapshot.ubuntu.com/ubuntu/20240301T030400Z/dists/noble-security/Release
