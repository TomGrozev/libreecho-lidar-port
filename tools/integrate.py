#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Rebuild per-repo `integration` branches from the topic branches in
`integration.json`.

The integration branch is never edited by hand: it is recreated from the
manifest's base plus `git merge --no-ff` of every topic, in manifest order.
Conflicts are resolved on the topic branch; `rerere` replays a resolution once
it has been recorded here.

Commands:
  status [repo...]          show branch state, merge state, dirty worktrees and
                            overlapping topic changes; --strict exits 1 on a
                            dirty worktree or a topic not based on the manifest base
  audit [repo...]           report topics already merged upstream, duplicate
                            patch-ids, topics cut from another base and fork
                            branches the manifest does not list; exits 1 on any
  rebuild [repo...]         recreate the integration branch and lock file
  check-lock                verify the lock matches the worktrees on disk

Paths are resolved against the workspace root (the parent of tools/). Override
with --workspace or LIBREECHO_WORKSPACE.
"""

import argparse
import datetime
import fcntl
import hashlib
import itertools
import json
import os
import subprocess
import sys
from pathlib import Path

SCHEMA_VERSION = 1
LOCK_REL = "work/integration/integration.lock.json"


class Fail(Exception):
    """A repo-scoped failure: report it, keep going with other repos."""


def workspace_from(args):
    ws = getattr(args, "workspace", None) or os.environ.get("LIBREECHO_WORKSPACE")
    if ws:
        return Path(ws).expanduser().resolve()
    return Path(__file__).resolve().parent.parent


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        raise Fail(f"missing file: {path}") from None
    except json.JSONDecodeError as exc:
        raise Fail(f"invalid JSON in {path}: {exc}") from exc


def git(repo, *args, check=True):
    """Run git in `repo`; raise Fail with stderr when check is set."""
    # The only commits made here are generated integration merges of already-signed
    # topic commits; they are never pushed, so they are not signed.
    proc = subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "-C", str(repo), *args],
        text=True,
        capture_output=True,
    )
    if check and proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip() or f"exit {proc.returncode}"
        raise Fail(f"git {' '.join(args)}: {detail}")
    return proc


def git_out(repo, *args):
    return git(repo, *args).stdout.strip()


def is_git_repo(path):
    if not path.is_dir():
        return False
    return git(path, "rev-parse", "--git-dir", check=False).returncode == 0


def rel_to_ws(ws, path):
    try:
        return str(Path(path).resolve().relative_to(ws))
    except ValueError:
        return str(path)


def base_remote(repo_dir, base):
    """Return the configured remote when base is a remote-tracking ref.

    Anything else (a tag such as `v2026.10`, or a local ref) returns None; the
    caller then skips the branch fetch and may fetch tags instead.
    """
    ref = base
    if ref.startswith("refs/remotes/"):
        ref = ref[len("refs/remotes/"):]
    elif ref.startswith("remotes/"):
        ref = ref[len("remotes/"):]
    if "/" not in ref:
        return None
    remote = ref.split("/", 1)[0]
    proc = git(repo_dir, "remote", check=False)
    remotes = proc.stdout.split() if proc.returncode == 0 else []
    return remote if remote in remotes else None


def rev(repo, revish):
    proc = git(repo, "rev-parse", "--verify", "--quiet", revish, check=False)
    return proc.stdout.strip() if proc.returncode == 0 else None


def branch_exists(repo, branch):
    return rev(repo, f"refs/heads/{branch}") is not None


def load_manifest(ws):
    path = ws / "integration.json"
    doc = load_json(path)
    if doc.get("schema_version") != SCHEMA_VERSION:
        raise Fail(f"{path}: unsupported schema_version {doc.get('schema_version')!r}")
    seen = set()
    for repo in doc.get("repos", []):
        for key in ("name", "path", "integration_path", "base", "topics"):
            if key not in repo:
                raise Fail(f"{path}: repo entry missing {key!r}: {repo}")
        if repo["name"] in seen:
            raise Fail(f"{path}: duplicate repo {repo['name']!r}")
        seen.add(repo["name"])
        if not isinstance(repo["topics"], list):
            raise Fail(f"{path}: {repo['name']}: topics must be a list")
        for topic in repo["topics"]:
            if "branch" not in topic:
                raise Fail(f"{path}: {repo['name']}: topic missing 'branch'")
    return doc


def select_repos(manifest, names):
    repos = manifest["repos"]
    if not names:
        return repos
    by_name = {r["name"]: r for r in repos}
    unknown = [n for n in names if n not in by_name]
    if unknown:
        raise Fail(f"unknown repo(s): {', '.join(unknown)} (known: {', '.join(by_name)})")
    wanted = set(names)
    return [r for r in repos if r["name"] in wanted]


# --------------------------------------------------------------------------
# status


def worktrees(repo_dir):
    """Parse `git worktree list --porcelain` into dicts."""
    out = git_out(repo_dir, "worktree", "list", "--porcelain")
    entries, current = [], {}
    for line in out.splitlines():
        if not line:
            if current:
                entries.append(current)
                current = {}
            continue
        key, _, value = line.partition(" ")
        if key == "branch":
            current["branch"] = value[len("refs/heads/"):] if value.startswith("refs/heads/") else value
        else:
            current[key] = value
    if current:
        entries.append(current)
    return entries


def dirty_paths(path):
    proc = git(path, "status", "--porcelain", check=False)
    if proc.returncode != 0:
        return None
    return [ln for ln in proc.stdout.splitlines() if ln.strip()]


def topic_files(repo_dir, base_sha, branch):
    mb = rev(repo_dir, f"refs/heads/{branch}")
    if not mb:
        return []
    proc = git(repo_dir, "diff", "--name-only", base_sha, mb, check=False)
    if proc.returncode != 0:
        return []
    return [ln for ln in proc.stdout.splitlines() if ln]


def upstream_merged(repo_dir, base, branch):
    """Return (label, unique_count)."""
    proc = git(repo_dir, "cherry", base, f"refs/heads/{branch}", check=False)
    if proc.returncode != 0:
        return "unknown (git cherry failed)", 0
    unique = [ln for ln in proc.stdout.splitlines() if ln[:1] == "+"]
    if not unique:
        return "yes", 0
    return "no", len(unique)


def based_on(repo_dir, base_sha, branch):
    """The branch contains the manifest base commit."""
    proc = git(repo_dir, "merge-base", "--is-ancestor", base_sha,
               f"refs/heads/{branch}", check=False)
    return proc.returncode == 0


def patch_ids(repo_dir, log_args):
    """Map commit sha to stable patch-id for the commits `git log` selects.

    `git patch-id --stable` keys on the diff, so a cherry-pick gets the same id
    as the commit it copies and the audit can spot duplicates.
    """
    proc = subprocess.run(
        ["git", "-C", str(repo_dir), "log", "--no-merges", "--patch",
         "--format=commit %H", *log_args],
        text=True, capture_output=True,
    )
    if proc.returncode != 0:
        return None
    pid = subprocess.run(["git", "patch-id", "--stable"],
                         input=proc.stdout, text=True, capture_output=True)
    if pid.returncode != 0:
        return None
    pairs = {}
    for line in pid.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            pairs[parts[1]] = parts[0]
    return pairs


def own_patch_ids(repo_dir, base_sha, branch, other_branches):
    """Patch-ids of the commits unique to `branch`, not a parent topic's.

    Stacked topics share their parent's commits; subtracting the other heads
    leaves only the commits this topic adds, so a shared ancestor is not
    mistaken for a duplicate.
    """
    log_args = [f"{base_sha}..refs/heads/{branch}"]
    if other_branches:
        log_args += ["--not", *[f"refs/heads/{b}" for b in other_branches]]
    return patch_ids(repo_dir, log_args)


def summarize_commits(repo_dir, shas, limit=3):
    bits = []
    for sha in shas[:limit]:
        subject = git(repo_dir, "show", "-s", "--format=%s", sha,
                      check=False).stdout.strip()
        bits.append(f"{sha[:8]} {subject}".strip())
    if len(shas) > limit:
        bits.append(f"+{len(shas) - limit} more")
    return ", ".join(bits)


def cmd_status(ws, manifest, names, strict=False):
    repos = select_repos(manifest, names)
    problems = []
    for repo in repos:
        name = repo["name"]
        repo_dir = ws / repo["path"]
        print(f"== {name} ({repo['path']})")
        if not is_git_repo(repo_dir):
            print(f"   ERROR: not a git repository: {repo['path']}")
            continue

        base = repo["base"]
        remote = base_remote(repo_dir, base)
        base_sha = rev(repo_dir, f"{base}^{{commit}}")
        kind = "" if remote else " (tag/local ref)"
        if base_sha:
            print(f"   base {base}{kind} @ {base_sha[:10]}")
        elif remote:
            print(f"   base {base}: MISSING (fetch {remote}?)")
        else:
            print(f"   base {base}{kind}: MISSING (fetch tags?)")

        ip = ws / repo["integration_path"]
        wts = worktrees(repo_dir)
        integ = next((w for w in wts if Path(w["worktree"]).resolve() == ip.resolve()), None)
        if integ is None:
            print(f"   integration {repo['integration_path']}: no worktree")
        else:
            head = rev(ip, "HEAD")
            changed = dirty_paths(ip) or []
            state = "dirty" if changed else "clean"
            print(
                f"   integration {repo['integration_path']}: branch {integ.get('branch', 'detached')}"
                f" @ {(head or '')[:10]}, {state}"
            )
            if changed:
                problems.append(
                    f"{name}: integration worktree {repo['integration_path']} is dirty"
                )

        file_sets = {}
        for topic in repo["topics"]:
            branch = topic["branch"]
            scope = topic.get("scope", "?")
            if not branch_exists(repo_dir, branch):
                print(f"   topic {branch} [{scope}]: MISSING")
                continue
            head = rev(repo_dir, f"refs/heads/{branch}")
            bits = [f"exists @ {(head or '')[:10]}"]
            if base_sha:
                counts = git(repo_dir, "rev-list", "--left-right", "--count",
                             f"{base}...refs/heads/{branch}", check=False)
                if counts.returncode == 0:
                    behind, ahead = (int(x) for x in counts.stdout.split())
                    bits.append(f"ahead {ahead} behind {behind}")
                if not based_on(repo_dir, base_sha, branch):
                    bits.append(f"NOT BASED on {base}")
                    problems.append(f"{name}: topic {branch} is not based on {base}")
                merged, unique = upstream_merged(repo_dir, base, branch)
                if unique:
                    bits.append(f"upstream merged: {merged} ({unique} unique)")
                else:
                    bits.append("upstream merged: yes")
            dirty_here = []
            holders = [w for w in wts if w.get("branch") == branch]
            if holders:
                states = []
                for wt in holders:
                    wt_path = Path(wt["worktree"])
                    changed = dirty_paths(wt_path) if wt_path.is_dir() else None
                    if changed is None:
                        states.append(f"{rel_to_ws(ws, wt_path)} (missing)")
                    elif changed:
                        dirty_here.append(rel_to_ws(ws, wt_path))
                        states.append(f"DIRTY {rel_to_ws(ws, wt_path)} ({len(changed)} path(s))")
                    else:
                        states.append(f"{rel_to_ws(ws, wt_path)} (clean)")
                bits.append("checked out: " + ", ".join(states))
            else:
                bits.append("checked out: not in any worktree")
            if base_sha:
                files = topic_files(repo_dir, base_sha, branch)
                file_sets[branch] = set(files)
                bits.append(f"{len(files)} changed file(s)")
            print(f"   topic {branch} [{scope}]: " + ", ".join(bits))
            if dirty_here:
                print(f"   ! DIRTY worktree for {branch}: " + ", ".join(dirty_here))
                problems.append(f"{name}: topic {branch} has a dirty worktree")

        if len(file_sets) > 1:
            printed = False
            for a, b in itertools.combinations(sorted(file_sets), 2):
                common = sorted(file_sets[a] & file_sets[b])
                if not common:
                    continue
                if not printed:
                    print("   shared files (likely conflicts):")
                    printed = True
                shown = ", ".join(common[:8])
                if len(common) > 8:
                    shown += f", ... (+{len(common) - 8})"
                print(f"     {a} vs {b}: {len(common)} file(s): {shown}")
            if not printed:
                print("   shared files: none")
    if problems:
        print(f"strict: {len(problems)} problem(s)")
        for problem in problems:
            print(f"   ! {problem}")
    return 1 if strict and problems else 0


# --------------------------------------------------------------------------
# audit


def audit_repo(ws, repo):
    """Return the audit problems for one repo; read-only."""
    repo_dir = ws / repo["path"]
    if not is_git_repo(repo_dir):
        return [f"not a git repository: {repo['path']}"]
    base = repo["base"]
    base_sha = rev(repo_dir, f"{base}^{{commit}}")
    if not base_sha:
        return [f"base {base} does not resolve (fetch it?)"]

    branches = [t["branch"] for t in repo["topics"]]
    problems = []
    heads = {}
    for branch in branches:
        if not branch_exists(repo_dir, branch):
            problems.append(f"topic {branch} is missing")
            continue
        heads[branch] = rev(repo_dir, f"refs/heads/{branch}")
        if not based_on(repo_dir, base_sha, branch):
            problems.append(f"topic {branch} is not based on {base}")

        proc = git(repo_dir, "cherry", base, f"refs/heads/{branch}", check=False)
        if proc.returncode == 0:
            merged = [ln.split()[1] for ln in proc.stdout.splitlines()
                      if ln.startswith("- ")]
            if merged:
                problems.append(
                    f"topic {branch}: {len(merged)} commit(s) already in {base} "
                    f"(patch-id): {summarize_commits(repo_dir, merged)}"
                )

    owners = {}
    for branch in heads:
        ids = own_patch_ids(repo_dir, base_sha, branch,
                            [b for b in heads if b != branch])
        if ids is None:
            problems.append(f"topic {branch}: patch-id computation failed")
            continue
        for sha, patch_id in ids.items():
            owners.setdefault(patch_id, []).append((branch, sha))
    for patch_id, copies in owners.items():
        if len({branch for branch, _ in copies}) < 2:
            continue
        where = ", ".join(f"{branch} ({sha[:8]})" for branch, sha in copies)
        problems.append(f"duplicate patch-id {patch_id[:12]}: {where}")

    proc = git(repo_dir, "for-each-ref", "--format=%(refname:lstrip=3)",
               "refs/remotes/fork", check=False)
    if proc.returncode == 0:
        # The base branch and the fork's default branch are not topic leftovers.
        # A base is either remote/branch or a branch the fork itself carries
        # (base/linux-6.18.64), so list both readings.
        listed = set(branches)
        listed.update({base, base.split("/", 1)[-1]})
        default = git(repo_dir, "symbolic-ref", "--quiet", "--short",
                      "refs/remotes/fork/HEAD", check=False)
        if default.returncode == 0 and default.stdout.strip():
            listed.add(default.stdout.strip().removeprefix("fork/"))
        extra = sorted({ref for ref in proc.stdout.split()
                        if ref and ref != "HEAD" and ref not in listed})
        if extra:
            shown = ", ".join(extra[:8])
            if len(extra) > 8:
                shown += f", ... (+{len(extra) - 8})"
            problems.append(
                f"fork branches not in the manifest: {len(extra)}: {shown}"
            )
    return problems


def cmd_audit(ws, manifest, names):
    repos = select_repos(manifest, names)
    bad = 0
    for repo in repos:
        print(f"== {repo['name']} ({repo['path']})")
        problems = audit_repo(ws, repo)
        if problems:
            bad += 1
            for problem in problems:
                print(f"   PROBLEM: {problem}")
        else:
            print("   OK")
    if bad:
        print(f"FAIL: {bad} repo(s) need attention")
        return 1
    print("PASS: no audit problems")
    return 0


# --------------------------------------------------------------------------
# rebuild


def unmerged_paths(ip):
    proc = git(ip, "diff", "--name-only", "--diff-filter=U", check=False)
    return [ln for ln in proc.stdout.splitlines() if ln] if proc.returncode == 0 else []


def merge_in_progress(ip):
    return rev(ip, "MERGE_HEAD") is not None


def rebuild_repo(ws, repo, do_fetch):
    repo_dir = ws / repo["path"]
    base = repo["base"]
    remote = base_remote(repo_dir, base)

    if not is_git_repo(repo_dir):
        raise Fail(f"not a git repository: {repo['path']}")

    git(repo_dir, "config", "rerere.enabled", "true")
    git(repo_dir, "config", "rerere.autoupdate", "true")
    # A rewrite undoes through the reflog, so its entries must never expire.
    git(repo_dir, "config", "gc.reflogExpire", "never")
    git(repo_dir, "config", "gc.reflogExpireUnreachable", "never")

    if remote:
        if do_fetch:
            print(f"   fetch {remote}")
            proc = git(repo_dir, "fetch", "--no-tags", remote, check=False)
            if proc.returncode != 0:
                raise Fail(f"git fetch {remote}: {proc.stderr.strip() or 'failed'}")
    elif rev(repo_dir, f"{base}^{{commit}}"):
        print(f"   base {base} is a tag/local ref: skipping fetch")
    elif do_fetch:
        remotes = git_out(repo_dir, "remote").split()
        default = "origin" if "origin" in remotes else (remotes[0] if remotes else None)
        if not default:
            raise Fail(f"base {base} does not resolve and the repo has no remote to fetch tags from")
        print(f"   base {base} is a tag/local ref: fetching tags from {default}")
        proc = git(repo_dir, "fetch", "--tags", default, check=False)
        if proc.returncode != 0:
            raise Fail(f"git fetch --tags {default}: {proc.stderr.strip() or 'failed'}")

    base_sha = rev(repo_dir, f"{base}^{{commit}}")
    if not base_sha:
        raise Fail(f"base {base} does not resolve (fetch {remote}?)")

    branches = [t["branch"] for t in repo["topics"]]
    missing = [b for b in branches if not branch_exists(repo_dir, b)]
    if missing:
        raise Fail(f"missing topic branch(es): {', '.join(missing)}")

    ip = ws / repo["integration_path"]
    registered = any(Path(w["worktree"]).resolve() == ip.resolve() for w in worktrees(repo_dir))
    if registered:
        changed = dirty_paths(ip)
        if changed is None:
            raise Fail(f"integration worktree unreadable: {repo['integration_path']}")
        # A product build leaves untracked files behind (its build lock, for
        # one), and rebuild replaces the branch anyway, so drop those
        # instead of failing. Tracked changes stay an error: they mean a
        # merge is unresolved or someone edited the generated tree.
        tracked = [ln for ln in changed if not ln.startswith("??")]
        if tracked:
            raise Fail(
                f"integration worktree is dirty ({repo['integration_path']}): "
                + ", ".join(tracked[:10])
                + (" ..." if len(tracked) > 10 else "")
            )
        if changed:
            print(f"   removing {len(changed)} untracked path(s) left by a build")
            proc = git(ip, "clean", "-fd", check=False)
            if proc.returncode != 0:
                raise Fail(f"git clean -fd: {proc.stderr.strip() or 'failed'}")
        proc = git(ip, "checkout", "-B", "integration", base, check=False)
        if proc.returncode != 0:
            raise Fail(f"git checkout -B integration: {proc.stderr.strip()}")
    else:
        if ip.exists():
            raise Fail(f"{repo['integration_path']} exists but is not a worktree of {repo['path']}")
        ip.parent.mkdir(parents=True, exist_ok=True)
        proc = git(repo_dir, "worktree", "add", "-B", "integration", str(ip), base, check=False)
        if proc.returncode != 0:
            raise Fail(f"git worktree add: {proc.stderr.strip()}")

    print(f"   integration @ {base_sha[:10]} ({base})")
    for topic in repo["topics"]:
        branch = topic["branch"]
        proc = git(
            ip, "merge", "--no-ff", "--no-edit", "-m",
            f"Merge {branch} into integration", f"refs/heads/{branch}",
            check=False,
        )
        if proc.returncode == 0:
            print(f"   merged {branch}")
            continue

        conflicts = unmerged_paths(ip)
        if merge_in_progress(ip) and not conflicts:
            commit = git(ip, "commit", "--no-edit", check=False)
            if commit.returncode != 0:
                raise Fail(
                    f"merge of {branch} looked rerere-resolved but commit failed: "
                    f"{commit.stderr.strip()}"
                )
            print(f"   merged {branch} (conflict auto-resolved by rerere)")
            continue

        print(f"   CONFLICT merging {branch} in {repo['integration_path']}", file=sys.stderr)
        if conflicts:
            print("   conflicting files:", file=sys.stderr)
            for path in conflicts:
                print(f"     {path}", file=sys.stderr)
        else:
            print(f"   merge failed without unmerged paths: {proc.stderr.strip()}", file=sys.stderr)
        print(
            "   hint: fix the commit on the topic branch and rerun, or resolve here once\n"
            f"         (edit, `git -C {repo['integration_path']} add <files>`, "
            f"`git -C {repo['integration_path']} commit --no-edit`)\n"
            "         so rerere records it, then rerun. The merge is left in progress.",
            file=sys.stderr,
        )
        raise Fail(f"merge conflict while merging {branch} (left in progress)")

    head = rev(ip, "HEAD")
    return {
        "integration_path": repo["integration_path"],
        "base_ref": base,
        "base_sha": base_sha,
        "topics": [{"branch": b, "sha": rev(repo_dir, f"refs/heads/{b}")} for b in branches],
        "head": head,
    }


def write_lock(ws, manifest, rebuilt, manifest_path):
    lock_path = ws / LOCK_REL
    old = {}
    if lock_path.exists():
        try:
            old = load_json(lock_path).get("repos", {})
        except Fail:
            print(f"warning: ignoring unreadable lock {LOCK_REL}", file=sys.stderr)
            old = {}

    by_name = {r["name"]: r for r in manifest["repos"]}
    entries = {}
    for name, entry in rebuilt.items():
        if entry is not None:
            entries[name] = entry

    for name, repo in by_name.items():
        if name in rebuilt:
            continue
        prev = old.get(name)
        if not prev:
            continue
        ip = ws / repo["integration_path"]
        head = rev(ip, "HEAD") if ip.is_dir() else None
        if head and head == prev.get("head"):
            entries[name] = prev

    ordered = {name: entries[name] for name in by_name if name in entries}
    doc = {
        "schema_version": SCHEMA_VERSION,
        "generated": datetime.datetime.now(datetime.UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "manifest_sha256": sha256_file(manifest_path),
        "repos": ordered,
    }
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {LOCK_REL} ({len(ordered)} repo(s))")
    return lock_path


def build_in_progress(ws):
    """The pid of a running lab build, or None.

    rebuild rewrites the integration worktrees, so running it while a build
    compiles from them replaces files under the compiler and produces
    failures that vanish on a rerun. The lock is an fcntl.flock held for the
    build's lifetime, so probing it never leaves a stale lock behind.
    """
    lock_path = ws / "work/builds/.build.lock"
    try:
        fd = os.open(lock_path, os.O_RDWR)
    except OSError:
        return None
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            try:
                pid = int(os.read(fd, 64).decode().strip())
            except (OSError, ValueError):
                return -1
            return pid
        # Nobody held it: release and report idle.
        fcntl.flock(fd, fcntl.LOCK_UN)
        return None
    finally:
        os.close(fd)


def manifest_dirty(ws):
    """integration.json has changes not committed in the port repo."""
    if not is_git_repo(ws):
        return False
    proc = git(ws, "status", "--porcelain", "--", "integration.json", check=False)
    return proc.returncode == 0 and bool(proc.stdout.strip())


def cmd_rebuild(ws, manifest, names, do_fetch, only_in_ota=False,
                allow_during_build=False, allow_dirty_manifest=False):
    pid = None if allow_during_build else build_in_progress(ws)
    if pid:
        raise Fail(
            f"a lab build is running (pid {pid}); rebuild would change its "
            "worktrees mid-build, so wait for it to finish or stop it"
        )
    if not allow_dirty_manifest and manifest_dirty(ws):
        raise Fail(
            "integration.json has uncommitted changes; commit it first so the "
            "lock pins a committed manifest, or pass --allow-dirty-manifest"
        )
    repos = select_repos(manifest, names)
    if only_in_ota:
        for repo in repos:
            if repo.get("in_ota") is not True:
                print(f"note: skipping {repo['name']} (not in_ota)", file=sys.stderr)
        repos = [r for r in repos if r.get("in_ota") is True]
        if not repos:
            print("note: no repo selected has in_ota: true", file=sys.stderr)
    rebuilt = {}
    failures = 0
    for repo in repos:
        print(f"== {repo['name']}")
        try:
            rebuilt[repo["name"]] = rebuild_repo(ws, repo, do_fetch)
            print(f"   ok: {repo['name']} @ {rebuilt[repo['name']]['head'][:10]}")
        except Fail as exc:
            failures += 1
            rebuilt[repo["name"]] = None
            print(f"   FAIL {repo['name']}: {exc}", file=sys.stderr)
    write_lock(ws, manifest, rebuilt, ws / "integration.json")
    return 1 if failures else 0


# --------------------------------------------------------------------------
# check-lock


def cmd_check_lock(ws):
    manifest_path = ws / "integration.json"
    lock_path = ws / LOCK_REL
    try:
        lock = load_json(lock_path)
    except Fail as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2
    try:
        manifest = load_manifest(ws)
    except Fail as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2

    ok = True
    want = sha256_file(manifest_path)
    if lock.get("manifest_sha256") != want:
        print(f"FAIL manifest_sha256: lock {lock.get('manifest_sha256')} != manifest {want}")
        ok = False
    else:
        print(f"PASS manifest_sha256 {want}")

    for name, entry in lock.get("repos", {}).items():
        ip = ws / entry.get("integration_path", "")
        problems = []
        if not ip.is_dir() or not is_git_repo(ip):
            problems.append("worktree missing")
        else:
            head = rev(ip, "HEAD")
            if head != entry.get("head"):
                problems.append(f"HEAD {(head or '?')[:10]} != lock {(entry.get('head') or '?')[:10]}")
            changed = dirty_paths(ip)
            if changed:
                problems.append(f"dirty ({len(changed)} path(s))")
        if problems:
            ok = False
            print(f"FAIL {name}: " + "; ".join(problems))
        else:
            print(f"PASS {name} @ {entry['head'][:10]} clean")

    manifest_names = {r["name"] for r in manifest["repos"]}
    for missing in sorted(manifest_names - set(lock.get("repos", {}))):
        print(f"note: {missing} has no lock entry (not rebuilt yet)", file=sys.stderr)
    for gone in sorted(set(lock.get("repos", {})) - manifest_names):
        print(f"note: lock entry {gone} is not in the manifest", file=sys.stderr)
    return 0 if ok else 1


# --------------------------------------------------------------------------


def main(argv=None):
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--workspace", default=argparse.SUPPRESS,
        help="workspace root (default: parent of tools/, or $LIBREECHO_WORKSPACE)",
    )
    parser = argparse.ArgumentParser(
        description="Rebuild integration branches from topic branches (integration.json).",
    )
    parser.add_argument("--workspace", default=None, help=argparse.SUPPRESS)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_status = sub.add_parser("status", parents=[common], help="show branch and merge state")
    p_status.add_argument("repos", nargs="*", help="repo names (default: all)")
    p_status.add_argument(
        "--strict", action="store_true",
        help="exit 1 when a worktree is dirty or a topic is not based on the base",
    )

    p_audit = sub.add_parser(
        "audit", parents=[common],
        help="report merged topics, duplicate patch-ids and unlisted fork branches",
    )
    p_audit.add_argument("repos", nargs="*", help="repo names (default: all)")

    p_rebuild = sub.add_parser("rebuild", parents=[common], help="recreate integration branches")
    p_rebuild.add_argument("repos", nargs="*", help="repo names (default: all)")
    p_rebuild.add_argument("--no-fetch", action="store_true", help="skip fetching the base remote")
    p_rebuild.add_argument(
        "--only-in-ota", action="store_true",
        help="only rebuild repos marked in_ota: true in the manifest",
    )
    p_rebuild.add_argument(
        "--allow-during-build", action="store_true",
        help="permit a rebuild while a lab build holds the lock (lab-build's own call)",
    )
    p_rebuild.add_argument(
        "--allow-dirty-manifest", action="store_true",
        help="rebuild even when integration.json has uncommitted changes",
    )

    sub.add_parser("check-lock", parents=[common], help="verify the lock against the worktrees")

    args = parser.parse_args(argv)
    ws = workspace_from(args)
    try:
        manifest = load_manifest(ws) if args.cmd != "check-lock" else None
        if args.cmd == "status":
            return cmd_status(ws, manifest, args.repos, args.strict)
        if args.cmd == "audit":
            return cmd_audit(ws, manifest, args.repos)
        if args.cmd == "rebuild":
            return cmd_rebuild(ws, manifest, args.repos, not args.no_fetch, args.only_in_ota,
                               args.allow_during_build, args.allow_dirty_manifest)
        if args.cmd == "check-lock":
            return cmd_check_lock(ws)
    except Fail as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    sys.exit(main())
