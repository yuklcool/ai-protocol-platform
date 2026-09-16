#!/usr/bin/env bash
#
# upstream-merge.sh — preview/merge the public upstream into a dedicated sync branch.
#
# Canonical upstream:
#   https://github.com/sunholo-data/ai-protocol-platform.git
#
# Safety model:
#   - never merge upstream directly into main;
#   - never touch deploy/* snapshots;
#   - preview by default, commit only with GO=1;
#   - make upstream deletions explicit before commit;
#   - finish through a reviewed sync/upstream-* PR and the full sync regression.
#
# Usage:
#   git switch main && git pull --ff-only
#   git switch -c sync/upstream-YYYYMMDD
#   ./scripts/upstream-merge.sh        # fetch + merge preview, no commit
#   GO=1 ./scripts/upstream-merge.sh   # fetch + merge and commit

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

GO="${GO:-}"
REMOTE="${UPSTREAM_REMOTE:-upstream}"
BRANCH="${UPSTREAM_BRANCH:-main}"
CANONICAL_URL="https://github.com/sunholo-data/ai-protocol-platform.git"
CURRENT_BRANCH="$(git branch --show-current)"

case "$CURRENT_BRANCH" in
  sync/upstream-*) ;;
  main|master|deploy/*)
    echo "ERROR: refusing to merge upstream on protected branch '$CURRENT_BRANCH'." >&2
    echo "Create a dedicated branch first, for example:" >&2
    echo "  git switch -c sync/upstream-$(date +%Y%m%d)" >&2
    exit 2
    ;;
  *)
    echo "ERROR: upstream sync must run on a sync/upstream-* branch; current branch is '$CURRENT_BRANCH'." >&2
    exit 2
    ;;
esac

if ! git remote get-url "$REMOTE" >/dev/null 2>&1; then
  echo "ERROR: no '$REMOTE' remote. Add the canonical public upstream:" >&2
  echo "  git remote add $REMOTE $CANONICAL_URL" >&2
  exit 2
fi

REMOTE_URL="$(git remote get-url "$REMOTE")"
case "$REMOTE_URL" in
  https://github.com/sunholo-data/ai-protocol-platform.git|git@github.com:sunholo-data/ai-protocol-platform.git)
    ;;
  *)
    echo "ERROR: '$REMOTE' points to an unexpected repository:" >&2
    echo "  $REMOTE_URL" >&2
    echo "Expected: $CANONICAL_URL" >&2
    echo "Override UPSTREAM_REMOTE only when intentionally reviewing another remote." >&2
    exit 2
    ;;
esac

if [ -n "$(git status --porcelain)" ]; then
  echo "ERROR: working tree is dirty. Commit or stash first." >&2
  exit 2
fi

echo "Fetching $REMOTE/$BRANCH …"
git fetch --quiet "$REMOTE" "$BRANCH"

BASE="$(git rev-parse HEAD)"
INCOMING="$(git rev-parse "$REMOTE/$BRANCH")"
MERGE_BASE="$(git merge-base HEAD "$REMOTE/$BRANCH" || true)"

if git merge-base --is-ancestor "$INCOMING" HEAD 2>/dev/null; then
  echo "Already contains $REMOTE/$BRANCH ($(git rev-parse --short "$INCOMING"))."
  exit 0
fi

echo
echo "Fork base:      $(git rev-parse --short "$BASE")"
echo "Upstream head:  $(git rev-parse --short "$INCOMING")"
echo "Merge base:     ${MERGE_BASE:-none}"
echo
echo "Incoming commits:"
git --no-pager log --oneline "HEAD..$REMOTE/$BRANCH" | sed 's/^/  /' || true

echo
echo "Incoming path changes:"
git --no-pager diff --name-status "HEAD...$REMOTE/$BRANCH" | sed -n '1,250p' | sed 's/^/  /' || true

echo
echo "Merging (no commit yet) …"
if ! git merge --no-commit --no-ff "$REMOTE/$BRANCH"; then
  echo
  echo "CONFLICTS — resolve each conflict explicitly; do not blanket-choose ours/theirs:" >&2
  git diff --name-only --diff-filter=U | sed 's/^/  /' >&2
  echo >&2
  echo "Use UPSTREAM.md to preserve Self-host/Tenant/Provider/MCP invariants." >&2
  exit 1
fi

DELETIONS="$(git diff --cached --name-only --diff-filter=D)"
if [ -n "$DELETIONS" ]; then
  echo
  echo "!! UPSTREAM DELETIONS — review before committing:"
  echo "$DELETIONS" | sed 's/^/    /'
  echo
  echo "If a deleted path is fork-owned, restore it before continuing:"
  echo "  git checkout HEAD -- <path>"
fi

echo
echo "Staged by the merge:"
git diff --cached --stat | tail -30

if [ "$GO" != "1" ]; then
  echo
  echo "Preview only. Inspect the merge, then either:"
  echo "  git merge --abort"
  echo "or re-run from a clean sync branch with:"
  echo "  GO=1 ./scripts/upstream-merge.sh"
  echo
  echo "After committing, push this sync/upstream-* branch and open a PR to main."
  exit 0
fi

git commit --no-edit

echo
echo "Merged $REMOTE/$BRANCH ($(git rev-parse --short "$INCOMING")) into sync branch from $(git rev-parse --short "$BASE")."
echo "Next: push this branch, open a PR to main, and require the Upstream sync full regression plus applicable normal CI gates before merge."
