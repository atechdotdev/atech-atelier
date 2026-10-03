#!/usr/bin/env bash
#
# publish_release.sh — upload a built Atech Atelier release to GitHub Releases
# (ADR-006). DRY RUN BY DEFAULT: it checks the files and prints the exact
# commands, and changes nothing anywhere.
#
#   branding/publish_release.sh [--dist DIR]            # dry run
#   branding/publish_release.sh [--dist DIR] --execute  # really publish
#
# --execute additionally requires ATECH_PUBLISH_CONFIRM to equal the target
# repository ("atechdotdev/atech-atelier"), so a stray flag cannot publish.
# Publishing is an OUTWARD action: the owner decides when, and to which repo.
# The repo name is the PROPOSED one from ADR-006 and does not exist until the
# owner creates it; this script never creates a repository.
#
# What it checks before printing or running anything:
#   - dist/AtechAtelier-<VERSION>-x86_64.AppImage exists and is not a stub
#   - SHA256SUMS lists it (and the .zsync when present) and `sha256sum -c` passes
#   - the tag v<VERSION> is the root VERSION file's value
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$HERE/.." && pwd)"
GH_REPO="atechdotdev/atech-atelier"
DIST="$REPO_DIR/dist"
EXECUTE=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dist)    DIST="$2"; shift 2 ;;
    --execute) EXECUTE=1; shift ;;
    -h|--help) sed -n '2,21p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
fail() { echo "FAIL: $*" >&2; exit 1; }

VERSION="$(python3 "$HERE/release_meta.py" version)" || fail "VERSION is not valid"
IMG="$(python3 "$HERE/release_meta.py" outname x86_64)"
TAG="v$VERSION"
[[ -f "$DIST/$IMG" ]] || fail "$DIST/$IMG not found (build it first)"
# A real AppImage is an ELF with the AppImage type-2 magic 'AI\x02' at offset 8.
MAGIC="$(od -An -tx1 -j8 -N3 "$DIST/$IMG" | tr -d ' \n')"
[[ "$MAGIC" == "414902" ]] || fail "$IMG is not a type-2 AppImage (magic '$MAGIC'); a stub or a broken repack"
[[ -f "$DIST/SHA256SUMS" ]] || fail "$DIST/SHA256SUMS missing"
grep -q "  $IMG\$" "$DIST/SHA256SUMS" || fail "SHA256SUMS does not list $IMG"
( cd "$DIST" && sha256sum -c --quiet SHA256SUMS ) || fail "SHA256SUMS does not match the files"
FILES=("$DIST/$IMG" "$DIST/SHA256SUMS")
[[ -f "$DIST/$IMG.zsync" ]] && FILES+=("$DIST/$IMG.zsync")

NOTES="Atech Atelier $VERSION (preview), Linux x86_64 AppImage.

Built on unmodified FreeCAD 1.1.3. Atech's code: LGPL-2.1-or-later. Atech
module models: CC BY-NC 4.0. Not endorsed by or affiliated with the FreeCAD
project. Verify the download with: sha256sum -c SHA256SUMS"

CMD=(gh release create "$TAG" --repo "$GH_REPO" --title "Atech Atelier $VERSION"
     --prerelease --notes "$NOTES" "${FILES[@]}")

echo "release      $GH_REPO $TAG (prerelease)"
for f in "${FILES[@]}"; do echo "asset        $(basename "$f")  $(du -h "$f" | cut -f1)"; done
echo "command      $(printf '%q ' "${CMD[@]}")"

if [[ "$EXECUTE" != 1 ]]; then
  echo "DRY RUN: nothing was published. Re-run with --execute and"
  echo "ATECH_PUBLISH_CONFIRM=$GH_REPO once the owner has said so."
  exit 0
fi
[[ "${ATECH_PUBLISH_CONFIRM:-}" == "$GH_REPO" ]] \
  || fail "--execute needs ATECH_PUBLISH_CONFIRM=$GH_REPO"
command -v gh >/dev/null 2>&1 || fail "gh (GitHub CLI) not installed"
"${CMD[@]}"
echo "published $GH_REPO $TAG"
