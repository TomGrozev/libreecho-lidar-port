#!/usr/bin/env python3
"""Prove the 2026-11-24 branch cleanup loses no commit.

For each fork, every commit reachable from a backup/2026-11-24/* tag or a stash must,
after the planned branch deletions, still be either
  - reachable from a kept ref (remaining local branch, archive/* tag, other non-backup tag,
    remote-tracking branch), or
  - patch-equivalent (same `git patch-id --stable`) to a commit reachable from a kept ref.
Backup tags are excluded from the kept set on purpose: they are a safety net, not a home.

Usage: verify-no-lost-commits.py [--deletes FILE]
FILE lines: `<repo> <branch>` for branches the owner will delete with `git branch -D`.
Exit 0 iff no repo has an unplaced commit.
"""
import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
FORKS = ROOT / "private" / "forks"
REPOS = ["LibreEcho", "LibreEcho-Platform", "LibreEcho-UI", "LibreEcho-Linux",
         "LibreEcho-Installer-Web", "kaeru", "amonet-koboreru", "u-boot"]


def git(repo, *args, stdin=None, raw=False):
    out = subprocess.run(["git", "-C", str(FORKS / repo), *args],
                         input=stdin.encode() if stdin is not None else None,
                         capture_output=True, check=True).stdout
    return out if raw else out.decode(errors="replace")


def patch_ids(repo, shas):
    if not shas:
        return {}
    # Merge commits have no single patch; they are reported separately.
    out = git(repo, "log", "--no-walk=unsorted", "--no-merges", "-p", "--format=commit %H",
              "--stdin", stdin="\n".join(shas) + "\n", raw=True)
    pid = subprocess.run(["git", "-C", str(FORKS / repo), "patch-id", "--stable"], input=out,
                         capture_output=True, check=True).stdout.decode()
    return {line.split()[1]: line.split()[0] for line in pid.splitlines()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--deletes", type=Path)
    a = ap.parse_args()
    deletes = {}
    if a.deletes:
        for line in a.deletes.read_text().splitlines():
            if line.strip() and not line.startswith("#"):
                repo, branch = line.split()
                deletes.setdefault(repo, set()).add(branch)

    failed = False
    for repo in REPOS:
        refs = git(repo, "for-each-ref", "--format=%(refname)").split()
        # Current heads too: branches created after the backup (trials, other sessions).
        sources = [r for r in refs if r.startswith(("refs/tags/backup/2026-11-24/", "refs/heads/"))]
        stash = git(repo, "rev-list", "-g", "refs/stash").split() if "refs/stash" in refs else []
        kept = [r for r in refs
                if not r.startswith("refs/tags/backup/") and r != "refs/stash"
                and not (r.startswith("refs/heads/")
                         and r[len("refs/heads/"):] in deletes.get(repo, ()))]
        # Stash commits carry index/untracked parents; check only the stash commit itself.
        src_commits = set(git(repo, "rev-list", *sources, "--not", *kept).split()) if sources else set()
        stash_orphans = [s for s in stash
                         if not git(repo, "for-each-ref", "--points-at", s, "refs/tags/archive/")]
        unplaced = sorted(src_commits)
        merges = []
        if unplaced:
            # A rebased or cherry-picked copy is committed after its original, so kept
            # commits older than the oldest unplaced one cannot be its copy.
            oldest = min(int(git(repo, "log", "-1", "--format=%ct", c)) for c in unplaced)
            cands = git(repo, "rev-list", "--no-merges", f"--since={oldest - 86400}", *kept).split()
            kept_ids = set(patch_ids(repo, cands).values())
            src_ids = patch_ids(repo, unplaced)
            merges = [c for c in unplaced if c not in src_ids]
            unplaced = [c for c in unplaced if c in src_ids and src_ids[c] not in kept_ids]
        status = "OK" if not unplaced and not stash_orphans else "LOST"
        failed |= status != "OK"
        print(f"{status:4} {repo}: {len(src_commits)} commit(s) only in backups, "
              f"{len(unplaced)} with no equivalent on a kept ref, "
              f"{len(merges)} merge(s) only in backups, "
              f"{len(stash)} stash(es), {len(stash_orphans)} untagged")
        for c in merges:
            print("     merge " + git(repo, "log", "-1", "--format=%h %s", c).strip())
        for c in unplaced:
            print("     " + git(repo, "log", "-1", "--format=%h %s", c).strip())
        for s in stash_orphans:
            print("     stash " + git(repo, "log", "-1", "--format=%h %s", s).strip())
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
