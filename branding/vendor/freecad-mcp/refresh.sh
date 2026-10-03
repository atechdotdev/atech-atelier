#!/usr/bin/env bash
# Re-vendor the FreeCADMCP addon at a new upstream commit.
#
#   branding/vendor/freecad-mcp/refresh.sh <commit>
#
# Fetches the upstream repo into a temp dir, replaces addon/ and LICENSE with
# that commit's pristine files, rewrites the commit in UPSTREAM, and then
# dry-runs every patch so a stale one is found HERE rather than in a build.
# Nothing is committed.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMMIT="${1:?usage: refresh.sh <upstream commit>}"
URL="$(sed -n 's/^url=//p' "$HERE/UPSTREAM")"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
git clone -q "$URL" "$T/src"
git -C "$T/src" archive "$COMMIT" addon/FreeCADMCP LICENSE | tar -x -C "$T"
rm -rf "$HERE/addon"; mv "$T/addon" "$HERE/addon"; cp "$T/LICENSE" "$HERE/LICENSE"
sed -i "s/^commit=.*/commit=$COMMIT/" "$HERE/UPSTREAM"
mkdir -p "$T/try"; cp -r "$HERE/addon" "$T/try/"
for p in "$HERE"/patches/*.patch "$HERE"/optional/*.patch; do
  patch -p1 -s --no-backup-if-mismatch -d "$T/try" < "$p" \
    || { echo "FAIL: $(basename "$p") no longer applies at $COMMIT" >&2; exit 1; }
done
echo "vendored $COMMIT; all patches apply"
