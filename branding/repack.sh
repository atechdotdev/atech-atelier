#!/usr/bin/env bash
#
# repack.sh — section 7 of build_appimage.sh: turn a built, VERIFIED tree into
# the release AppImage, with update information, optional signature and
# SHA256SUMS. Split out so every branch is testable without a 3 GB build
# (tests/test_repack.sh drives it with stub appimagetools).
#
#   repack.sh <squashfs-root> <out.AppImage>
#
# appimagetool is NEVER downloaded: $APPIMAGETOOL, else appimagetool on PATH.
# Environment (see build_appimage.sh --help):
#   APPIMAGETOOL, ATECH_UPDATE_INFO (unset = ATECH_DEFAULT_UPDATE_INFO,
#   "" = none), ATECH_SIGN_KEY (empty = unsigned, announced).
# Exit: 0 PASS, 1 FAIL, 2 usage, 3 CANNOT DETERMINE (no appimagetool).
set -euo pipefail
ROOT="${1:?usage: repack.sh <squashfs-root> <out.AppImage>}"
OUT="${2:?usage: repack.sh <squashfs-root> <out.AppImage>}"
say()  { printf '  %-34s %s\n' "$1" "$2"; }
fail() { echo "FAIL: $*" >&2; exit 1; }
[[ -x "$ROOT/AppRun" ]] || fail "$ROOT is not an AppDir (no executable AppRun)"
# Absolute paths: appimagetool is run from the output directory (see below).
ROOT="$(cd "$ROOT" && pwd)"
mkdir -p "$(dirname "$OUT")"
OUT="$(cd "$(dirname "$OUT")" && pwd)/$(basename "$OUT")"

AIT="${APPIMAGETOOL:-$(command -v appimagetool 2>/dev/null || true)}"
if [[ -z "$AIT" || ! -x "$AIT" ]]; then
  cat >&2 <<MSG

CANNOT DETERMINE: appimagetool was not found (APPIMAGETOOL=${APPIMAGETOOL:-<unset>},
not on PATH), so the image was not repacked. This script does not download it.
The branded tree is built and verified at:
  $ROOT
Run it directly with \$ROOT/AppRun, or point APPIMAGETOOL at appimagetool and re-run.
MSG
  exit 3
fi
say "appimagetool" "$AIT"
AIT_HELP="$("$AIT" --help 2>&1 || true)"
AIT_ARGS=()
# Update information (ADR-006: GitHub Releases). Unset -> the default channel;
# set but empty -> none. Embedded only when this appimagetool lists -u.
UPDATE_INFO="${ATECH_UPDATE_INFO-${ATECH_DEFAULT_UPDATE_INFO:-}}"
if [[ -z "$UPDATE_INFO" ]]; then
  say "update info" "none (ATECH_UPDATE_INFO set empty, or no default)"
elif grep -Eq -- '(^|[[:space:]])-u([,[:space:]]|$)|--updateinformation' <<<"$AIT_HELP"; then
  AIT_ARGS+=(-u "$UPDATE_INFO")
  say "update info" "$UPDATE_INFO"
else
  say "update info" "NOT embedded: $AIT has no -u option (wanted $UPDATE_INFO)"
fi
# The type-2 runtime prepended to the image. ATECH_APPIMAGE_RUNTIME = a local
# runtime file (passed as --runtime-file, its sha256 announced). Unset: this
# appimagetool fetches the runtime itself at pack time (MEASURED 2026-10-04 with
# 1.9.1: "Downloading runtime file from .../type2-runtime/releases/download/
# continuous/runtime-x86_64"), which is NOT pinned -- say so.
if [[ -n "${ATECH_APPIMAGE_RUNTIME:-}" ]]; then
  [[ -s "$ATECH_APPIMAGE_RUNTIME" ]] || fail "ATECH_APPIMAGE_RUNTIME=$ATECH_APPIMAGE_RUNTIME is not a file"
  AIT_ARGS+=(--runtime-file "$(cd "$(dirname "$ATECH_APPIMAGE_RUNTIME")" && pwd)/$(basename "$ATECH_APPIMAGE_RUNTIME")")
  say "runtime" "$(basename "$ATECH_APPIMAGE_RUNTIME") sha256 $(sha256sum "$ATECH_APPIMAGE_RUNTIME" | cut -d' ' -f1)"
else
  say "runtime" "WARN: not pinned (ATECH_APPIMAGE_RUNTIME unset); appimagetool may download the continuous runtime"
fi
if [[ -n "${ATECH_SIGN_KEY:-}" ]]; then
  AIT_ARGS+=(--sign --sign-key "$ATECH_SIGN_KEY")
  say "signature" "gpg key $ATECH_SIGN_KEY"
else
  say "signature" "SKIPPED: unsigned image (ATECH_SIGN_KEY is empty)"
fi
rm -f "$OUT" "$OUT.zsync"
# Run FROM the output directory: appimagetool 1.9.1 writes the .zsync into its
# working directory under the image's basename, not next to DESTINATION
# (MEASURED 2026-10-04: it landed in the repo root and was never summed).
( cd "$(dirname "$OUT")" && ARCH=x86_64 "$AIT" "${AIT_ARGS[@]}" "$ROOT" "$OUT" ) \
  || fail "appimagetool failed"
[[ -s "$OUT" ]] || fail "appimagetool wrote no $OUT"
# appimagetool writes the .zsync when given -u and it can run zsyncmake
# (1.9.1 does so with no zsyncmake on PATH); publish whatever it actually wrote.
SUMS=("$(basename "$OUT")")
[[ -f "$OUT.zsync" ]] && SUMS+=("$(basename "$OUT").zsync")
if [[ ${#AIT_ARGS[@]} -gt 0 && "${AIT_ARGS[0]}" == -u && ! -f "$OUT.zsync" ]]; then
  say "zsync" "WARN: no $(basename "$OUT").zsync written (appimagetool made none); delta updates will not work"
fi
# Checksums next to the image, in sha256sum -c format, re-checked at once.
( cd "$(dirname "$OUT")" && sha256sum "${SUMS[@]}" > SHA256SUMS && sha256sum -c --quiet SHA256SUMS ) \
  || fail "could not write or re-check $(dirname "$OUT")/SHA256SUMS"
echo
say "output" "$OUT ($(du -sh "$OUT" | cut -f1))"
say "SHA256SUMS" "$(dirname "$OUT")/SHA256SUMS (${SUMS[*]})"
echo "PASS"
