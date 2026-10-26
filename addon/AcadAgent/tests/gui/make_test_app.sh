#!/usr/bin/env bash
#
# make_test_app.sh — make a SNAPSHOT test app for the GUI harness
# (app_driver.py) from the CURRENT repo, without touching dist/ or any
# tracked file.
#
# Usage:
#   make_test_app.sh [--out DIR] [--overlay | --full] [--base APP]
#     --out DIR    default $ATECH_GUI_SCRATCH or /tmp/atech-gui
#     --overlay    (default) APFS-clone a built Atech app (--base, default
#                  dist/build-macos-<arch>/Atech Atelier.app, only READ) into
#                  <out>/app-build/AtechTest.stage, then overlay what
#                  build_macos.sh would install from the current sources: the
#                  addon (no tests/caches), projects/*.py, presets + meshes,
#                  branding.xml, the regenerated stylesheets, theme and user
#                  template. ~10-20 s. No re-sign (runs locally).
#     --full       snapshot the repo and run the snapshot's own
#                  branding/build_macos.sh --app-only --brand-from-repo
#                  (see "Why --full is not the default" below).
#
# Prints TIMING lines and, at the end, APP=<folder to pass to app_driver --app>.
#
# Why a source snapshot (<out>/src): build_macos.sh and the brand generators
# write brand/assets/*.qss, branding/assets/theme/*.yaml and the user
# template INTO their own checkout. On the live repo that would rewrite
# tracked files while other people edit them.
#
# Why the test app folder is not named *.app, and why --full is not the
# default. MEASURED 2026-10-20, macOS 26.6, from an agent shell without the
# App Management permission:
#   * a clone of the upstream (notarized) FreeCAD.app becomes READ-ONLY to
#     this process during build_macos.sh step 1 (its freecadcmd --version
#     hangs or fails: "upstream version unknown"), and the first install into
#     Contents/Resources/bin fails with "Operation not permitted" -- whatever
#     the folder's name, even with a file added first to break the seal. The
#     folder can then be moved, not written or deleted.
#   * a clone of the user's already-built ad-hoc-signed Atech app stays
#     writable across GUI launches, and runs from a folder NOT named .app
#     (Contents/MacOS/FreeCAD finds its Resources relatively; Cocoa, the
#     macOS style and the Info.plist identity are unchanged).
# From a Terminal that has the App Management permission (System Settings >
# Privacy & Security > App Management), --full works as build_macos.sh does.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../../../.." && pwd)"
ARCH="$(uname -m)"
OUT="${ATECH_GUI_SCRATCH:-/tmp/atech-gui}"
MODE=overlay
BASE="$REPO/dist/build-macos-$ARCH/Atech Atelier.app"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --out) OUT="$2"; shift 2 ;;
    --overlay) MODE=overlay; shift ;;
    --full) MODE=full; shift ;;
    --base) BASE="$2"; shift 2 ;;
    -h|--help) sed -n '2,42p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
mkdir -p "$OUT"
OUT="$(cd "$OUT" && pwd -P)"
SRC="$OUT/src"
BUILD="$OUT/app-build"
t0=$(date +%s)
tick() { echo "TIMING $1 $(( $(date +%s) - t0 ))s"; }

# A previous build may be protected (above): move it aside, never fail on rm.
retire() {
  [[ -e "$1" ]] || return 0
  mkdir -p "$OUT/trash"
  mv "$1" "$OUT/trash/$(basename "$1").$(date +%s).$$"
  rm -rf "$OUT/trash" 2>/dev/null || true
}

snapshot_src() {
  mkdir -p "$SRC"
  rsync -a --delete --exclude=.git --exclude=/dist --exclude=__pycache__ \
        --exclude='*.pyc' --exclude='.DS_Store' --exclude='.*_cache' \
        "$REPO/" "$SRC/"
  tick snapshot
}

if [[ "$MODE" == full ]]; then
  snapshot_src
  CRANE=()
  if compgen -G "$REPO/dist/build-macos-$ARCH/crane/*.brep" >/dev/null; then
    mkdir -p "$OUT/crane"; cp "$REPO/dist/build-macos-$ARCH/crane/"*.brep "$OUT/crane/"
    CRANE=(--crane-from "$OUT/crane")
  fi
  retire "$BUILD"
  ( cd "$SRC" && bash branding/build_macos.sh --app-only --brand-from-repo \
        --build-dir "$BUILD" --artifacts "$SRC" "${CRANE[@]}" ) 2>&1 | tee "$OUT/build.log" \
    || { echo "FAIL: build_macos.sh (log: $OUT/build.log)" >&2; exit 1; }
  tick build
  echo "APP=$BUILD/Atech Atelier.app"
  exit 0
fi

# ------------------------------------------------------------- overlay mode
[[ -x "$BASE/Contents/MacOS/FreeCAD" ]] || { echo "FAIL: no built app at $BASE (run branding/build_macos.sh once, or pass --base)" >&2; exit 1; }
snapshot_src
STAGE="$BUILD/AtechTest.stage"
retire "$STAGE"
mkdir -p "$BUILD"
cp -Rc "$BASE" "$STAGE"
tick clone
RES="$STAGE/Contents/Resources"
: > "$RES/bin/.atech-gui-test" \
  || { echo "FAIL: the cloned app is not writable (App Management, see header)" >&2; exit 1; }

# brand assets regenerated in the SNAPSHOT (same commands as build_macos.sh step 2)
( cd "$SRC" && python3 brand/tools/build_qss.py >/dev/null \
    && python3 brand/tools/build_theme.py --upstream "$RES/share/Gui/Stylesheets/parameters" >/dev/null \
    && python3 brand/tools/build_template.py >/dev/null ) \
  || { echo "FAIL: brand asset generation (in the snapshot)" >&2; exit 1; }
BA="$SRC/brand/assets"
install -m 0644 "$SRC/branding/branding.xml" "$RES/bin/branding.xml"
install -m 0644 "$SRC/branding/assets/atech_user_template.built.cfg" "$RES/bin/atech_user_template.cfg"
Q="$RES/share/Gui/Stylesheets"
install -m 0644 "$BA/AtechLight.qss" "$BA/AtechDark.qss" "$Q/"
install -m 0644 "$BA/Atech Overlay.qss" "$Q/overlay/Atech Overlay.qss"
for m in Light Dark; do
  install -m 0644 "$SRC/branding/assets/theme/Atech Atelier $m.yaml" "$Q/parameters/Atech Atelier $m.yaml"
done
tick brand

# the addon, as build_macos.sh step 3 (code replaced, bundled data refreshed)
AA="$RES/Mod/AcadAgent"
KEEP="$OUT/keep.$$"; rm -rf "$KEEP"; mkdir -p "$KEEP"
for d in data docs fixtures; do if [[ -d "$AA/$d" ]]; then mv "$AA/$d" "$KEEP/$d"; fi; done
rm -rf "$AA"
tar -C "$SRC/addon" --exclude=tests --exclude=__pycache__ \
    --exclude='.*_cache' --exclude='*.pyc' --exclude='.DS_Store' -cf - AcadAgent | tar -C "$RES/Mod" -xf -
for d in data docs fixtures; do if [[ -d "$KEEP/$d" ]]; then rm -rf "$AA/$d"; mv "$KEEP/$d" "$AA/$d"; fi; done
rm -rf "$KEEP"
mkdir -p "$AA/projects" "$AA/data/models/stl" "$AA/data/models/glb" "$AA/docs"
install -m 0644 "$SRC/projects/atech_ports.py" "$SRC/projects/atech_modules.py" "$AA/projects/"
install -m 0644 "$SRC/models/presets.yaml" "$AA/data/models/presets.yaml"
if [[ -f "$SRC/models/glb/frame-2.glb" ]]; then install -m 0644 "$SRC/models/glb/frame-2.glb" "$AA/data/models/glb/frame-2.glb"; fi
if [[ -f "$SRC/docs/ATECH_ASSEMBLY.md" ]]; then install -m 0644 "$SRC/docs/ATECH_ASSEMBLY.md" "$AA/docs/ATECH_ASSEMBLY.md"; fi
while IFS= read -r f; do
  if [[ -n "$f" && -f "$SRC/models/stl/$f" ]]; then install -m 0644 "$SRC/models/stl/$f" "$AA/data/models/stl/$f"; fi
done < <(sed -n 's/^[[:space:]]*file:[[:space:]]*\([^[:space:]#]*\).*/\1/p' "$SRC/models/presets.yaml" | sort -u)
echo "  addon: $(find "$AA" -name '*.py' | wc -l | tr -d ' ') py files from the repo working tree"
tick addon
echo "APP=$STAGE"
