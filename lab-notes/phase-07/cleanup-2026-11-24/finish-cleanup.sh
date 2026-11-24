#!/usr/bin/env bash
# Owner-run final step of the 2026-11-24 branch cleanup. The agents' safety net blocks
# `git branch -D` and `git stash clear`, so these deletions are left to the owner.
#
# Nothing here deletes a commit: verify-no-lost-commits.py first proves that every commit on
# the branches below and every stash entry stays reachable from a topic branch, an archive/*
# tag or a backup/2026-11-24/* tag (or has an identical patch on a topic), and the script
# stops if it does not. No tag is deleted. It runs the check again afterwards.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
forks=$(cd "$here/../../../forks" && pwd)

python3 "$here/verify-no-lost-commits.py" --deletes "$here/owner-deletes.txt"

grep -v '^#' "$here/owner-deletes.txt" | while read -r repo branch; do
  [ -n "$repo" ] || continue
  if git -C "$forks/$repo" show-ref -q --verify "refs/heads/$branch"; then
    git -C "$forks/$repo" branch -D "$branch"
  fi
done

# Every stash entry is tagged archive/stash-*; the check above refuses an untagged one.
for repo in LibreEcho LibreEcho-Platform LibreEcho-UI LibreEcho-Linux; do
  git -C "$forks/$repo" stash clear
done

python3 "$here/verify-no-lost-commits.py"
echo "cleanup finished; backup/2026-11-24/* and archive/* tags remain"
