#!/usr/bin/env bash
#
# build_appimage.sh — assemble the Atech Atelier AppImage from an upstream
# FreeCAD AppImage plus our branding and our addon.
#
# We compile no FreeCAD source (ADR-003 §2, "own the distribution"). The build
# adds files, removes FreeCAD's own desktop entry, and rewrites AppRun; the
# exact list is MEASURED at the end (usr/share/doc/atech-atelier/ATECH_CHANGES.txt).
#
# Usage:
#   ./build_appimage.sh [-i upstream.AppImage] [-o out.AppImage] [--tree-only]
#                       [--build-dir DIR] [--artifacts DIR] [--crane-from DIR]
#                       [--mcp-guard] [--dev-unlicensed]
#
#   -i FILE          upstream AppImage. Default: $ATECH_UPSTREAM_APPIMAGE, else
#                    downloaded from the pinned URL in upstream.env into
#                    ${XDG_CACHE_HOME:-~/.cache}/atech-atelier-build/ (a copy
#                    already in the old atech-studio-build/ cache is reused).
#                    Either way its sha256 must match upstream.env.
#   --build-dir DIR  where to extract (default dist/build). It is WIPED.
#   --artifacts DIR  the Atech module library checkout (models/presets.yaml,
#                    models/stl, models/glb). Default: $ATECH_ARTIFACTS, else
#                    this repository (its models/ directory). DIR may also
#                    be the models directory itself.
#   --crane-from DIR copy the reference-model BREPs from DIR instead of
#                    regenerating them (~50 s) with the extracted freecadcmd.
#   --mcp-guard      also apply vendor/freecad-mcp/optional/ (token + Origin +
#                    Host guard on the RPC server). Off until the owner decides.
#   --dev-unlicensed build and verify without root LICENSE/NOTICE/
#                    LICENSE-models.md. The tree is marked NOT RELEASABLE and
#                    is never repacked.
#
# Release (ADR-006). The version comes from VERSION at the repository root and
# is stamped into the file name (dist/AtechAtelier-<version>-x86_64.AppImage),
# the desktop entries, the metainfo and ATECH_CHANGES. Variables:
#   APPIMAGETOOL       path to appimagetool; default: appimagetool on PATH.
#                      This script never downloads it. Absent -> the tree is
#                      built and verified, the repack is CANNOT DETERMINE
#                      (exit 3).
#   ATECH_UPDATE_INFO  AppImage update information for appimagetool -u.
#                      Unset: the GitHub Releases channel of the PROPOSED
#                      public repo (ADR-006), embedded only when this
#                      appimagetool accepts -u. Set to "" to embed none.
#   ATECH_APPIMAGE_RUNTIME  local type-2 runtime file for appimagetool
#                      --runtime-file (sha256 recorded in ATECH_CHANGES).
#                      Unset: appimagetool fetches the continuous runtime
#                      itself at pack time -- NOT pinned, and recorded so.
#   ATECH_SIGN_KEY     GPG key id for appimagetool --sign --sign-key. Empty
#                      (default): the image is NOT signed, and the build says so.
#   ATECH_SCREENSHOT_URLS  space-separated https://...png|jpg for the
#                      AppStream <screenshots>; empty: a PLACEHOLDER comment.
#   ATECH_SOURCE_CONTACT   contact for written source requests (SOURCE_OFFER).
#
# Outputs next to the AppImage: SHA256SUMS (sha256sum -c format; the AppImage
# and, when appimagetool wrote one, its .zsync).
#
# Requires: bash, python3 (numpy, Pillow, scipy for brand/tools), inkscape, patch, tar,
# sha256sum, curl (only to download the upstream image). appimagetool only to
# repack; with --tree-only you get a runnable extracted tree and no repack.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/.." && pwd)"

# shellcheck source=upstream.env
. "$HERE/upstream.env"

UPSTREAM="${ATECH_UPSTREAM_APPIMAGE:-}"
# One version, from one file (R39); release_meta.py validates its shape.
VERSION="$(python3 "$HERE/release_meta.py" version)" \
  || { echo "FAIL: $REPO/VERSION is not a valid version" >&2; exit 1; }
OUT="${REPO}/dist/$(python3 "$HERE/release_meta.py" outname x86_64)"
BUILD="${REPO}/dist/build"
ARTIFACTS="${ATECH_ARTIFACTS:-$REPO}"
CRANE_FROM=""
TREE_ONLY=0
MCP_GUARD=0
DEV_UNLICENSED=0
APP_ID="dev.atech.Atelier"            # ADR-006
PRODUCT="Atech Atelier"               # ADR-005
DOC_NAME="atech-atelier"              # usr/share/doc/<DOC_NAME>/
GH_OWNER="atechdotdev"                # PROPOSED public repo (ADR-006)
GH_REPO="atech-atelier"
DEFAULT_UPDATE_INFO="gh-releases-zsync|$GH_OWNER|$GH_REPO|latest|AtechAtelier-*x86_64.AppImage.zsync"

while [[ $# -gt 0 ]]; do
  case "$1" in
    -i|--input)       UPSTREAM="$2"; shift 2 ;;
    -o|--output)      OUT="$2"; shift 2 ;;
    --build-dir)      BUILD="$2"; shift 2 ;;
    --artifacts)      ARTIFACTS="$2"; shift 2 ;;
    --crane-from)     CRANE_FROM="$2"; shift 2 ;;
    --tree-only)      TREE_ONLY=1; shift ;;
    --mcp-guard)      MCP_GUARD=1; shift ;;
    --dev-unlicensed) DEV_UNLICENSED=1; shift ;;
    -h|--help)        sed -n '2,56p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

say()  { printf '  %-34s %s\n' "$1" "$2"; }
fail() { echo "FAIL: $*" >&2; exit 1; }

echo "$PRODUCT $VERSION — branded AppImage build"

# ------------------------------------------------------ 0. the pinned upstream
if [[ -z "$UPSTREAM" ]]; then
  CACHE="${XDG_CACHE_HOME:-$HOME/.cache}/atech-atelier-build"
  UPSTREAM="$CACHE/$(basename "$UPSTREAM_URL")"
  # A copy cached under the product's previous name is the same pinned file.
  OLD_CACHED="${XDG_CACHE_HOME:-$HOME/.cache}/atech-studio-build/$(basename "$UPSTREAM_URL")"
  [[ ! -f "$UPSTREAM" && -f "$OLD_CACHED" ]] && UPSTREAM="$OLD_CACHED"
  if [[ ! -f "$UPSTREAM" ]]; then
    mkdir -p "$CACHE"
    say "downloading" "$UPSTREAM_URL"
    curl -fL --retry 3 -o "$UPSTREAM.part" "$UPSTREAM_URL" \
      || fail "could not download $UPSTREAM_URL"
    mv "$UPSTREAM.part" "$UPSTREAM"
  fi
fi
[[ -f "$UPSTREAM" ]] || fail "upstream AppImage not found: $UPSTREAM"
GOT_SHA="$(sha256sum "$UPSTREAM" | cut -d' ' -f1)"
[[ "$GOT_SHA" == "$UPSTREAM_SHA256" ]] || fail "upstream sha256 mismatch:
  file   $UPSTREAM
  got    $GOT_SHA
  pinned $UPSTREAM_SHA256 (branding/upstream.env)"
say "upstream" "$UPSTREAM"
say "upstream sha256" "$GOT_SHA (matches pin)"
[[ -x "$UPSTREAM" ]] || chmod +x "$UPSTREAM"

# Refuse the stale "Atech CAD" descriptor that lives in brand/ (release PRD
# R45): the ONLY descriptor this build installs is the one next to this
# script, named here and nowhere else. The legacy one is recognised by its
# content, so a copy of it dropped in under any name is refused too.
BRANDING_XML="$HERE/branding.xml"
# The identity keys are read as XML VALUES (comments may mention old names).
# The previous product name in any value is a FAIL (ADR-005), as is the stale
# Atech CAD set anywhere in the file.
python3 - "$BRANDING_XML" "$PRODUCT" "$APP_ID" <<'PY' || fail "$BRANDING_XML identity check failed"
import sys, xml.etree.ElementTree as ET
path, product, app_id = sys.argv[1:4]
root = ET.parse(path).getroot()
val = {e.tag: (e.text or "").strip() for e in root if isinstance(e.tag, str)}
bad = ["%s=%r (want %r)" % (k, val.get(k), product)
       for k in ("Application", "WindowTitle", "ExeName") if val.get(k) != product]
if val.get("DesktopFileName") != app_id:
    bad.append("DesktopFileName=%r (want %r)" % (val.get("DesktopFileName"), app_id))
bad += ["%s carries the previous name: %r" % (k, v) for k, v in val.items()
        if "Atech Studio" in v or "atech-studio" in v]
for b in bad:
    print("  branding.xml: " + b, file=sys.stderr)
sys.exit(1 if bad else 0)
PY
if grep -q -e 'Atech CAD' -e 'atech-cad' -e 'AtechCAD' "$BRANDING_XML"; then
  fail "$BRANDING_XML carries the stale Atech CAD branding set (brand/, R45)"
fi

# Inputs that must exist before we spend minutes extracting.
# Accept the models directory itself as well as its parent.
if [[ ! -f "$ARTIFACTS/models/presets.yaml" && -f "$ARTIFACTS/presets.yaml" ]]; then
  ARTIFACTS="$(cd "$ARTIFACTS/.." && pwd)"
fi
PRESETS="$ARTIFACTS/models/presets.yaml"
BOARD_GLB="$ARTIFACTS/models/glb/frame-2.glb"
ASSEMBLY_MD="$REPO/docs/ATECH_ASSEMBLY.md"
for f in "$PRESETS" "$BOARD_GLB" "$ASSEMBLY_MD" \
         "$REPO/projects/atech_ports.py" "$REPO/projects/atech_modules.py"; do
  [[ -f "$f" ]] || fail "required input missing: $f
  (module library: pass --artifacts DIR or set ATECH_ARTIFACTS)"
done
# Licences (ADR-006): code LGPL-2.1-or-later (root LICENSE, the verbatim LGPL
# v2.1 text), models CC BY-NC 4.0 (root LICENSE-models.md), plus the NOTICE.
LICENSE_FILES=(LICENSE LICENSE-models.md NOTICE)
if [[ "$DEV_UNLICENSED" != 1 ]]; then
  for f in "${LICENSE_FILES[@]}"; do
    [[ -f "$REPO/$f" ]] || fail "root $f is missing (ADR-006 names it as a release
  file). For a local development build pass --dev-unlicensed."
  done
  grep -q 'GNU LESSER GENERAL PUBLIC LICENSE' "$REPO/LICENSE" \
    && grep -q 'Version 2.1, February 1999' "$REPO/LICENSE" \
    || fail "root LICENSE is not the LGPL v2.1 text (ADR-006)"
  grep -q 'CC BY-NC 4.0' "$REPO/LICENSE-models.md" \
    || fail "root LICENSE-models.md does not name CC BY-NC 4.0 (ADR-006)"
  # branding/NOTICE.proposed opens with a draft header; copied without removing
  # it, the release would ship "NOT the release NOTICE".
  ! grep -q -e 'PROPOSED root NOTICE' -e 'NOT the release NOTICE' "$REPO/NOTICE" \
    || fail "root NOTICE still carries the draft header of branding/NOTICE.proposed"
fi

# ---------------------------------------------------------------- 1. extract
rm -rf "$BUILD"; mkdir -p "$BUILD"
( cd "$BUILD" && "$UPSTREAM" --appimage-extract >/dev/null )
ROOT="$BUILD/squashfs-root"
[[ -d "$ROOT/usr/bin" ]] || fail "no usr/bin in extracted tree"
say "extracted" "$(du -sh "$ROOT" | cut -f1)"

# Snapshot the pristine tree NOW, so ATECH_CHANGES is measured, not typed.
python3 "$HERE/tree_changes.py" snapshot "$ROOT" "$BUILD/upstream_manifest.json" 2>/dev/null \
  || fail "could not snapshot the upstream tree"
say "upstream snapshot" "$(python3 -c 'import json,sys;print(len(json.load(open(sys.argv[1]))))' "$BUILD/upstream_manifest.json") files"

# An empty HOME for every freecadcmd we run, so nothing reads or writes the
# builder's own FreeCAD / Atech Atelier profile. Bytecode: MEASURED
# 2026-09-25, every freecadcmd run in the tree writes .pyc files (the embedded
# interpreter ignores PYTHONDONTWRITEBYTECODE; kept anyway for the day it
# does not), so prune_pyc removes whatever the upstream image did not have.
SCRATCH_HOME="$(mktemp -d "${TMPDIR:-/tmp}/atech-build-home.XXXXXX")"
trap 'rm -rf "$SCRATCH_HOME"' EXIT
fc_clean() {  # fc_clean [VAR=val ...] cmd ... — run with a clean env
  env -i HOME="$SCRATCH_HOME" PATH=/usr/bin:/bin LANG=C.UTF-8 \
         PYTHONDONTWRITEBYTECODE=1 "$@"
}

prune_pyc() {
  python3 "$HERE/tree_changes.py" prune-bytecode "$ROOT" "$BUILD/upstream_manifest.json" >/dev/null \
    || fail "could not prune build-time bytecode"
}

UPSTREAM_VER="$(fc_clean "$ROOT/usr/bin/freecadcmd" --version 2>/dev/null | head -1 || true)"
prune_pyc
say "upstream version" "${UPSTREAM_VER:-unknown}"

# ------------------------------------------------- 2. branding + assets
# branding.xml must sit next to the binary: App::Application reads
# <AppHomePath>/bin/branding.xml. Asset paths inside it are relative to
# AppHomePath, hence the "bin/" prefixes there.
# Assets are GENERATED from brand/tokens.py and the vendored atech.dev logo
# artwork (brand/assets/source) — never hand-drawn. Regenerate before
# installing so a stale asset cannot ship, and let the generators' own gates
# fail the build. build_theme gets THIS tree's upstream parameters.
( cd "$REPO" && python3 brand/tools/build_brand.py \
               && python3 brand/tools/build_qss.py \
               && python3 brand/tools/build_theme.py \
                    --upstream "$ROOT/usr/share/Gui/Stylesheets/parameters" \
               && python3 brand/tools/build_template.py ) \
  || fail "brand asset generation failed"

BA="$REPO/brand/assets"
install -m 0644 "$BRANDING_XML"  "$ROOT/usr/bin/branding.xml"
cmp -s "$BRANDING_XML" "$ROOT/usr/bin/branding.xml" \
  || fail "installed usr/bin/branding.xml is not branding/branding.xml (R45)"

# The light variants install under the UNSUFFIXED names branding.xml points
# at. branding.xml can name exactly one icon/logo/splash, so light — the
# seeded default, matching the website — is the one it names. The dark
# variants ship alongside for the runtime switch.
install -m 0644 "$BA/atech_icon-light.svg"    "$ROOT/usr/bin/atech_icon.svg"
install -m 0644 "$BA/atech_logo-light.svg"    "$ROOT/usr/bin/atech_logo.svg"
install -m 0644 "$BA/atech_splash-light.svg"  "$ROOT/usr/bin/atech_splash.svg"
install -m 0644 "$BA/atech_icon-dark.svg"     "$ROOT/usr/bin/atech_icon-dark.svg"
install -m 0644 "$BA/atech_logo-dark.svg"     "$ROOT/usr/bin/atech_logo-dark.svg"
install -m 0644 "$BA/atech_splash-dark.svg"   "$ROOT/usr/bin/atech_splash-dark.svg"
install -m 0644 "$HERE/assets/atech_user_template.built.cfg" \
                "$ROOT/usr/bin/atech_user_template.cfg"
say "branding.xml + assets" "installed to usr/bin/ (light + dark)"

# Both stylesheets go on FreeCAD's "qss:" search path, which is what the
# MainWindow/StyleSheet preference resolves against. This is the mode switch:
# branding.xml's <StyleSheet> is only a FALLBACK (StartupProcess.cpp:533), so
# shipping two sheets and seeding the preference is the only way to offer both.
QSSDIR="$ROOT/usr/share/Gui/Stylesheets"
[[ -d "$QSSDIR" ]] || fail "upstream stylesheet dir missing: $QSSDIR"
install -m 0644 "$BA/AtechLight.qss" "$QSSDIR/AtechLight.qss"
install -m 0644 "$BA/AtechDark.qss"  "$QSSDIR/AtechDark.qss"
say "stylesheets" "AtechLight.qss + AtechDark.qss -> share/Gui/Stylesheets/"
# The overlay panels take their own sheet from the "overlay:" search path
# (MainWindow/OverlayActiveStyleSheet, seeded by the template); R88.
[[ -d "$QSSDIR/overlay" ]] || fail "upstream overlay stylesheet dir missing: $QSSDIR/overlay"
install -m 0644 "$BA/Atech Overlay.qss" "$QSSDIR/overlay/Atech Overlay.qss"
say "overlay sheet" "Atech Overlay.qss -> share/Gui/Stylesheets/overlay/"

# The theme is a PARAMETERS file against FreeCAD's own unmodified FreeCAD.qss,
# not a hand-written stylesheet — so we inherit upstream widget fixes for free.
THEMEDIR="$ROOT/usr/share/Gui/Stylesheets/parameters"
[[ -d "$THEMEDIR" ]] || fail "upstream theme parameters dir missing: $THEMEDIR"
install -m 0644 "$HERE/assets/theme/$PRODUCT Light.yaml" "$THEMEDIR/$PRODUCT Light.yaml"
install -m 0644 "$HERE/assets/theme/$PRODUCT Dark.yaml"  "$THEMEDIR/$PRODUCT Dark.yaml"
say "theme" "$PRODUCT Light + Dark -> share/Gui/Stylesheets/parameters/"

# --------------------------------------------------------------- 3. the addon
# MEASURED 2026-09-24: ExeName moves user data to
# ~/.local/share/<ExeName>/v1-1/, so the user's existing FreeCAD Mod dir is
# NOT read by a branded build. The addon therefore ships bundled in usr/Mod/.
# tests/ and __pycache__/ never ship (R40): one test imports repo-only paths,
# another creates documents in the user's session.
AA="$ROOT/usr/Mod/AcadAgent"
rm -rf "$AA"
tar -C "$REPO/addon" --exclude=tests --exclude=__pycache__ \
    --exclude='.*_cache' --exclude='*.pyc' -cf - AcadAgent \
  | tar -C "$ROOT/usr/Mod" -xf -
say "addon bundled" "usr/Mod/AcadAgent ($(find "$AA" -name '*.py' | wc -l) py files, no tests/caches)"

# ------------------------------------------------- 3a. the module library (R07)
# The Modules tab, the New Project menu and the agent's seating rules need the
# two library modules, their meshes + presets, and ATECH_ASSEMBLY.md. Layout
# (resolved relative to the addon at runtime, release PRD R08):
#   usr/Mod/AcadAgent/projects/   atech_ports.py, atech_modules.py
#   usr/Mod/AcadAgent/data/models presets.yaml, stl/*.stl, glb/frame-2.glb,
#                                 LICENSE-models.md
#   usr/Mod/AcadAgent/docs/       ATECH_ASSEMBLY.md
# Licence of the meshes and presets.yaml: CC BY-NC 4.0 (ADR-006). The notice
# sits NEXT to them, so a copy of the models folder carries its terms.
mkdir -p "$AA/projects" "$AA/data/models/stl" "$AA/data/models/glb" "$AA/docs"
install -m 0644 "$REPO/projects/atech_ports.py" "$REPO/projects/atech_modules.py" "$AA/projects/"
install -m 0644 "$PRESETS" "$AA/data/models/presets.yaml"
if [[ -f "$REPO/LICENSE-models.md" ]]; then
  install -m 0644 "$REPO/LICENSE-models.md" "$AA/data/models/LICENSE-models.md"
  say "models licence" "usr/Mod/AcadAgent/data/models/LICENSE-models.md (CC BY-NC 4.0)"
elif [[ "$DEV_UNLICENSED" != 1 ]]; then
  fail "root LICENSE-models.md missing"
fi
install -m 0644 "$BOARD_GLB" "$AA/data/models/glb/frame-2.glb"
install -m 0644 "$ASSEMBLY_MD" "$AA/docs/ATECH_ASSEMBLY.md"
# Every mesh presets.yaml names must be present — a module the library lists
# but cannot load is the failure the Modules page shows as a broken card.
n_stl=0
while IFS= read -r f; do
  [[ -n "$f" ]] || continue
  src="$ARTIFACTS/models/stl/$f"
  [[ -f "$src" ]] || fail "presets.yaml names $f but $src does not exist"
  install -m 0644 "$src" "$AA/data/models/stl/$f"
  n_stl=$((n_stl + 1))
done < <(sed -n 's/^[[:space:]]*file:[[:space:]]*\([^[:space:]#]*\).*/\1/p' "$PRESETS" | sort -u)
[[ "$n_stl" -gt 0 ]] || fail "presets.yaml names no meshes ($PRESETS)"
ART_REV="$(git -C "$ARTIFACTS" rev-parse HEAD 2>/dev/null || echo "not a git checkout")"
say "module library" "2 modules, $n_stl meshes + frame-2.glb, $(du -sh "$AA/data" | cut -f1)"
say "assembly doc" "usr/Mod/AcadAgent/docs/ATECH_ASSEMBLY.md"

# ------------------------------------------------- 3b. the reference model
# The reference model ships WITH the app, so the 3D view has something real to
# show on a machine that has never built the fixture. The BREPs are build
# output (gitignored), so they are REGENERATED here with the freecadcmd we
# just extracted — a clean clone needs nothing prebuilt. Missing = FAIL.
CRANE_DST="$AA/fixtures/crane/build"
mkdir -p "$CRANE_DST"
if [[ -n "$CRANE_FROM" ]]; then
  compgen -G "$CRANE_FROM/*.brep" >/dev/null || fail "no .brep in --crane-from $CRANE_FROM"
  cp "$CRANE_FROM"/*.brep "$CRANE_DST/"
  say "reference model" "copied from $CRANE_FROM"
else
  CRANE_OUT="$BUILD/crane"
  mkdir -p "$CRANE_OUT"
  CRANE_LOG="$(fc_clean CRANE_OUT="$CRANE_OUT" "$ROOT/usr/bin/freecadcmd" \
                 "$REPO/cockpit/fixtures/crane/build_crane.py" 2>&1 || true)"
  prune_pyc
  CRANE_RES="$(grep '^FCRESULT ' <<<"$CRANE_LOG" | tail -1 || true)"
  [[ -n "$CRANE_RES" ]] || { tail -20 <<<"$CRANE_LOG" >&2; fail "crane build printed no FCRESULT"; }
  grep -q '"all_valid": true' <<<"$CRANE_RES" || fail "crane build has invalid parts: $CRANE_RES"
  compgen -G "$CRANE_OUT/*.brep" >/dev/null || fail "crane build wrote no .brep"
  cp "$CRANE_OUT"/*.brep "$CRANE_DST/"
  say "reference model" "regenerated: ${CRANE_RES#FCRESULT }"
fi
say "reference model" "$(ls "$CRANE_DST"/*.brep | wc -l) parts -> usr/Mod/AcadAgent/fixtures/"

# ------------------------------------------------- 3c. FreeCADMCP (vendored)
# Pinned pristine copy + patch series (vendor/freecad-mcp/UPSTREAM). A patch
# that no longer applies fails the build. Nothing seeds a settings file:
# the public build keeps the RPC server OFF (upstream default, R10). Whether
# the bridge ships at all, and whether it autostarts, is the owner's call.
MCP_V="$HERE/vendor/freecad-mcp"
MCP_STAGE="$BUILD/mcp-stage"
rm -rf "$MCP_STAGE"; mkdir -p "$MCP_STAGE"
cp -r "$MCP_V/addon" "$MCP_STAGE/"
MCP_SERIES=("$MCP_V"/patches/*.patch)
[[ "$MCP_GUARD" == 1 ]] && MCP_SERIES+=("$MCP_V"/optional/*.patch)
for p in "${MCP_SERIES[@]}"; do
  patch -p1 -s --no-backup-if-mismatch -d "$MCP_STAGE" < "$p" \
    || fail "FreeCADMCP patch does not apply: $(basename "$p")"
done
rm -rf "$ROOT/usr/Mod/FreeCADMCP"
tar -C "$MCP_STAGE/addon" --exclude=__pycache__ --exclude='*.pyc' -cf - FreeCADMCP | tar -C "$ROOT/usr/Mod" -xf -
install -m 0644 "$MCP_V/LICENSE" "$ROOT/usr/Mod/FreeCADMCP/LICENSE"
MCP_COMMIT="$(sed -n 's/^commit=//p' "$MCP_V/UPSTREAM")"
say "mcp addon bundled" "usr/Mod/FreeCADMCP @ ${MCP_COMMIT:0:12} + ${#MCP_SERIES[@]} patch(es), RPC off by default"

# --------------------------------------------------- 3d. AppRun agent lifecycle
# Make the product behave like a desktop app: launching it brings the agent
# backend up, and closing the window takes it back down with nothing orphaned.
#
# This works ONLY because upstream's AppRun ends with `"${MAIN}" "$@"` and NOT
# `exec "${MAIN}"`. The bash wrapper therefore stays alive as freecad's parent
# for the whole session, which is what allows `trap ... EXIT` to fire after
# freecad returns. MEASURED with a control: with the trap the backend child is
# reaped; with the trap line removed the identical script orphans it and the
# port stays held. If a future upstream AppRun adds `exec`, this block stops
# working -- so assert the shape rather than assume it.
FRAG="$HERE/apprun_agent_block.sh"
MIGRATE_FRAG="$HERE/apprun_migrate_block.sh"
[[ -f "$FRAG" ]] || fail "missing $FRAG"
[[ -f "$MIGRATE_FRAG" ]] || fail "missing $MIGRATE_FRAG"
if ! grep -q '^"\${MAIN}" "\$@"$' "$ROOT/AppRun"; then
  echo "FAIL: AppRun does not end with the expected non-exec \"\${MAIN}\" \"\$@\" line;" >&2
  echo "      the EXIT trap cannot reap the backend if freecad is exec'd." >&2
  exit 1
fi
# The environment snapshot goes in FIRST, before any upstream export, so a
# child the user types into can get the caller's own values back (R61). The
# names are measured from this AppRun's export lines, not typed here.
SNAP="$(python3 "$HERE/apprun_env.py" patch "$ROOT/AppRun")" \
  || fail "could not insert the pre-AppRun environment snapshot"
bash -n "$ROOT/AppRun" || fail "AppRun with env snapshot is not valid bash"
say "apprun env snapshot" "${SNAP#APPRUN_SNAPSHOT }"
if grep -q 'atech_cleanup' "$ROOT/AppRun"; then
  say "apprun lifecycle" "already present, skipped"
else
  # The user-data migration (ADR-005) goes first: it must run before the
  # backend block creates the new data folder for its log.
  python3 - "$ROOT/AppRun" "$MIGRATE_FRAG" "$FRAG" <<'PY'
import sys
apprun, frags = sys.argv[1], sys.argv[2:]
src = open(apprun, encoding="utf-8").read()
block = "\n\n".join(open(f, encoding="utf-8").read().rstrip("\n") for f in frags)
tail = '"${MAIN}" "$@"'
assert src.count(tail) == 1, "expected exactly one launch line, found %d" % src.count(tail)
open(apprun, "w", encoding="utf-8").write(src.replace(tail, block + "\n\n" + tail))
PY
  bash -n "$ROOT/AppRun" || fail "patched AppRun is not valid bash"
  grep -q '^atech_migrate_tree()' "$ROOT/AppRun" || fail "AppRun lacks the user-data migration"
  say "apprun lifecycle" "profile migration + adopt-or-start + trap cleanup installed"
fi

# ------------------------------------------------------ 4. desktop integration
# One reverse-DNS id for the desktop file, the metainfo and the icon (R38,
# ADR-006: dev.atech.Atelier). Both files are templates in branding/, stamped
# by release_meta.py, so the validators below judge exactly what ships.
DESKTOP_SRC="$HERE/$APP_ID.desktop"
METAINFO_SRC="$HERE/$APP_ID.metainfo.xml"
[[ -f "$DESKTOP_SRC" ]] || fail "missing $DESKTOP_SRC"
[[ -f "$METAINFO_SRC" ]] || fail "missing $METAINFO_SRC"
# Upstream's entries would present the product as "FreeCAD, The FreeCAD Team"
# in launchers and software stores.
rm -f "$ROOT/org.freecad.FreeCAD.desktop" "$ROOT/org.freecad.FreeCAD.svg" \
      "$ROOT/usr/share/applications/org.freecad.FreeCAD.desktop" \
      "$ROOT/usr/share/metainfo/org.freecad.FreeCAD.metainfo.xml" \
      "$ROOT/usr/share/metainfo/org.freecad.FreeCAD.appdata.xml"
mkdir -p "$ROOT/usr/share/applications" "$ROOT/usr/share/metainfo" \
         "$ROOT/usr/share/icons/hicolor/scalable/apps"
install -m 0644 "$DESKTOP_SRC" "$ROOT/$APP_ID.desktop"
install -m 0644 "$DESKTOP_SRC" "$ROOT/usr/share/applications/$APP_ID.desktop"
for d in "$ROOT/$APP_ID.desktop" "$ROOT/usr/share/applications/$APP_ID.desktop"; do
  python3 "$HERE/release_meta.py" desktop "$d" "$VERSION" \
    || fail "could not stamp X-AppImage-Version into $d"
done
# AppImage requires the top-level icon basename to match Icon=.
grep -qx "Icon=$APP_ID" "$ROOT/$APP_ID.desktop" || fail "$APP_ID.desktop: Icon= is not $APP_ID"
install -m 0644 "$BA/atech_icon-light.svg" "$ROOT/$APP_ID.svg"
install -m 0644 "$BA/atech_icon-light.svg" "$ROOT/usr/share/icons/hicolor/scalable/apps/$APP_ID.svg"
rm -f "$ROOT/.DirIcon"
ln -sf "$APP_ID.svg" "$ROOT/.DirIcon"
install -m 0644 "$METAINFO_SRC" "$ROOT/usr/share/metainfo/$APP_ID.metainfo.xml"
# Release date: SOURCE_DATE_EPOCH when set (reproducible builds), else the
# date of the commit being built, else today (UTC).
if [[ -n "${SOURCE_DATE_EPOCH:-}" ]]; then REL_DATE="$(date -u -d "@$SOURCE_DATE_EPOCH" +%F)"
else REL_DATE="$(git -C "$REPO" log -1 --format=%cs 2>/dev/null || date -u +%F)"; fi
python3 "$HERE/release_meta.py" metainfo "$ROOT/usr/share/metainfo/$APP_ID.metainfo.xml" \
    "$VERSION" "$REL_DATE" || fail "could not stamp the release into the metainfo"
# shellcheck disable=SC2086  # word splitting of the URL list is intended
python3 "$HERE/release_meta.py" screenshots "$ROOT/usr/share/metainfo/$APP_ID.metainfo.xml" \
    ${ATECH_SCREENSHOT_URLS:-} || fail "could not stamp screenshots into the metainfo"
if [[ -z "${ATECH_SCREENSHOT_URLS:-}" ]]; then
  say "screenshots" "WARN: PLACEHOLDER, none published (ATECH_SCREENSHOT_URLS empty)"
else
  say "screenshots" "$(wc -w <<<"$ATECH_SCREENSHOT_URLS") url(s)"
fi
say "version" "$VERSION ($REL_DATE): desktop X-AppImage-Version, metainfo <release>"
if command -v desktop-file-validate >/dev/null 2>&1; then
  for d in "$ROOT/$APP_ID.desktop" "$ROOT/usr/share/applications/$APP_ID.desktop"; do
    desktop-file-validate "$d" || fail "desktop-file-validate rejected $d"
  done
  say "desktop entry" "$APP_ID.desktop (desktop-file-validate OK, both copies)"
else
  say "desktop entry" "$APP_ID.desktop (desktop-file-validate absent: CANNOT DETERMINE)"
fi
if command -v appstreamcli >/dev/null 2>&1; then
  AS_OUT="$(appstreamcli validate --no-net "$ROOT/usr/share/metainfo/$APP_ID.metainfo.xml" 2>&1 || true)"
  if grep -q '^E:' <<<"$AS_OUT"; then echo "$AS_OUT" >&2; fail "appstreamcli reports errors"; fi
  say "metainfo" "$APP_ID.metainfo.xml ($(grep -c '^[WI]:' <<<"$AS_OUT" || true) warning/info, 0 errors)"
else
  say "metainfo" "$APP_ID.metainfo.xml (appstreamcli absent: CANNOT DETERMINE)"
fi

# ------------------------------------------- 5. notices, licences, README
# ADR-003: keep the licence text, state our changes, preserve copyright,
# never imply endorsement. A branded build makes this load-bearing.
DOC="$ROOT/usr/share/doc/$DOC_NAME"
mkdir -p "$DOC/third_party/FreeCADMCP-patches"
install -m 0644 "$REPO/README.md" "$DOC/README.md"
# Credits for every open-source project the image is built on or ships; the
# in-app "Credits & open-source licences" dialog reads this copy. Never
# optional, not even for a dev build.
[[ -f "$REPO/CREDITS.md" ]] || fail "root CREDITS.md missing"
install -m 0644 "$REPO/CREDITS.md" "$DOC/CREDITS.md"
cmp -s "$REPO/CREDITS.md" "$DOC/CREDITS.md" \
  || fail "installed usr/share/doc/$DOC_NAME/CREDITS.md is not CREDITS.md"
grep -q '^## FreeCAD' "$DOC/CREDITS.md" \
  || fail "CREDITS.md has no FreeCAD section"
say "credits" "usr/share/doc/$DOC_NAME/CREDITS.md"
for f in "${LICENSE_FILES[@]}"; do
  if [[ -f "$REPO/$f" ]]; then
    install -m 0644 "$REPO/$f" "$DOC/$f"
    cmp -s "$REPO/$f" "$DOC/$f" || fail "installed $DOC_NAME/$f differs from root $f"
  elif [[ "$DEV_UNLICENSED" != 1 ]]; then fail "root $f missing"; fi
done
say "licences" "$(cd "$DOC" && ls "${LICENSE_FILES[@]}" 2>/dev/null | tr '\n' ' ')-> usr/share/doc/$DOC_NAME/"
sed -e "s|@FREECADMCP_COMMIT@|$MCP_COMMIT|" -e "s|@DOC_NAME@|$DOC_NAME|g" \
    "$HERE/third_party/NOTICE.third_party" \
  > "$DOC/third_party/NOTICE.third_party"
install -m 0644 "$MCP_V/LICENSE" "$DOC/third_party/LICENSE.FreeCADMCP"
install -m 0644 "$HERE/third_party/LICENSE.Lucide" "$HERE/third_party/LICENSE.Feather" \
                "$DOC/third_party/"
for p in "${MCP_SERIES[@]}"; do install -m 0644 "$p" "$DOC/third_party/FreeCADMCP-patches/"; done
say "third-party notices" "FreeCADMCP (MIT, modified), Lucide (ISC), Feather (MIT)"

cat > "$DOC/SOURCE_OFFER.txt" <<OFFER
Atech Atelier — where to get the source code
============================================

This image contains FreeCAD and roughly 300 libraries it bundles, many under
the LGPL or GPL. Their licences are listed in

  usr/share/doc/FreeCAD/ThirdPartyLibraries.html
  usr/share/doc/FreeCAD/LICENSE.html

FreeCAD
  The FreeCAD part of this image is the unmodified official release
    $UPSTREAM_URL
    sha256 $UPSTREAM_SHA256
  built from FreeCAD tag $FREECAD_TAG, commit
    https://github.com/FreeCAD/FreeCAD/tree/$FREECAD_COMMIT
  (The "Revision" in the version string is a build date, not a commit.)

Bundled libraries
  packages.txt at the root of this image lists every bundled package with
  its version, build string and channel (conda-forge). The recipe and source
  URL of each one is in its conda-forge feedstock:
    https://github.com/conda-forge/<package>-feedstock
  and the exact source archives are linked from each package's page at
    https://anaconda.org/conda-forge/<package>

Atech's additions
  The files Atech added or changed are listed, measured against the
  upstream image, in usr/share/doc/$DOC_NAME/ATECH_CHANGES.txt. Their
  source is the Python and data files installed in this image. Atech's code
  is licensed LGPL-2.1-or-later (usr/share/doc/$DOC_NAME/LICENSE); the Atech
  module models and presets.yaml are CC BY-NC 4.0
  (usr/share/doc/$DOC_NAME/LICENSE-models.md).

Written offer
  ${ATECH_SOURCE_CONTACT:+On request to $ATECH_SOURCE_CONTACT, Atech will provide the complete corresponding source code for any GPL- or LGPL-licensed component of this image, for at least three years after this release, for no more than the cost of providing it.}${ATECH_SOURCE_CONTACT:-A contact for written source requests has not been set yet (build variable ATECH_SOURCE_CONTACT). Until it is, use the upstream locations above.}
OFFER
if [[ -z "${ATECH_SOURCE_CONTACT:-}" ]]; then
  say "source offer" "WARN: no ATECH_SOURCE_CONTACT; offer has no contact (owner)"
else
  say "source offer" "SOURCE_OFFER.txt (contact: $ATECH_SOURCE_CONTACT)"
fi

# ATECH_CHANGES is generated LAST, from a diff against the pristine snapshot,
# so no file the build adds, removes or rewrites can be left out of it.
CHANGES="$DOC/ATECH_CHANGES.txt"
# The packer, recorded by name, version and sha256 (never its local path: the
# personal-data gate scans this file). Same resolution as repack.sh.
PACK_AIT="${APPIMAGETOOL:-$(command -v appimagetool 2>/dev/null || true)}"
if [[ "$TREE_ONLY" == 1 || "$DEV_UNLICENSED" == 1 ]]; then
  PACKED_BY="not packed (tree only)"
elif [[ -n "$PACK_AIT" && -x "$PACK_AIT" ]]; then
  if [[ -n "${ATECH_APPIMAGE_RUNTIME:-}" && -s "$ATECH_APPIMAGE_RUNTIME" ]]; then
    PACK_RT="$(basename "$ATECH_APPIMAGE_RUNTIME"), sha256 $(sha256sum "$ATECH_APPIMAGE_RUNTIME" | cut -d' ' -f1)"
  else
    PACK_RT="type2-runtime fetched by appimagetool at pack time (continuous channel, NOT pinned)"
  fi
  PACKED_BY="$(basename "$PACK_AIT")
  version        $("$PACK_AIT" --version 2>&1 | grep -m1 . || echo unknown)
  sha256         $(sha256sum "$PACK_AIT" | cut -d' ' -f1)
  runtime        $PACK_RT"
else
  PACKED_BY="appimagetool not found (image not repacked)"
fi
{
  cat <<NOTICE
Atech Atelier — changes relative to upstream FreeCAD
====================================================

Version          $VERSION

Upstream image   $UPSTREAM_URL
  sha256         $UPSTREAM_SHA256
  FreeCAD        tag $FREECAD_TAG, commit $FREECAD_COMMIT
  version string ${UPSTREAM_VER:-unknown}
Built by         branding/build_appimage.sh from the Atech Atelier sources
                 (commit $(git -C "$REPO" rev-parse HEAD 2>/dev/null || echo unknown)$(git -C "$REPO" diff --quiet HEAD 2>/dev/null || echo ", with uncommitted changes"))
Module library   $(basename "$ARTIFACTS") @ $ART_REV
FreeCADMCP       $MCP_COMMIT + ${#MCP_SERIES[@]} Atech patch(es)
Packed by        $PACKED_BY

FreeCAD is free software licensed LGPL-2.1-or-later, Copyright (C) 2001-2026
Jürgen Riegel and the FreeCAD contributors. Atech Atelier is NOT endorsed by,
affiliated with, or a product of the FreeCAD project.

No FreeCAD source file is patched or recompiled. The lists below are
MEASURED: every file in this image was compared (sha256, or link target for
symlinks) with the same path in the unmodified upstream image. This file
itself (usr/share/doc/$DOC_NAME/ATECH_CHANGES.txt) is written after the
comparison and is the one addition not listed.

AppRun is MODIFIED: an environment snapshot is inserted at the top (it
records the caller's values of the variables AppRun exports, as
ATECH_PRE_APPRUN_<NAME>; source apprun_env.py). Before the final launch line
two blocks are inserted: a one-time profile copy from the product's previous
name ("Atech Studio") to "Atech Atelier" (source apprun_migrate_block.sh), and
an agent-backend lifecycle block (start/adopt on launch, reap on exit; source
apprun_agent_block.sh). FreeCAD's launch line itself is unchanged.

Corresponding source: usr/share/doc/$DOC_NAME/SOURCE_OFFER.txt

NOTICE
  python3 "$HERE/tree_changes.py" diff "$ROOT" "$BUILD/upstream_manifest.json"
} > "$BUILD/ATECH_CHANGES.txt" || fail "could not generate ATECH_CHANGES"
install -m 0644 "$BUILD/ATECH_CHANGES.txt" "$CHANGES"
python3 "$HERE/tree_changes.py" diff "$ROOT" "$BUILD/upstream_manifest.json" \
  | grep -v "^  usr/share/doc/$DOC_NAME/ATECH_CHANGES.txt\$" > "$BUILD/changes.before_verify"
say "ATECH_CHANGES" "$(grep -E '^(ADDED|REMOVED|MODIFIED) ' "$CHANGES" | tr '\n' ' ')"

# ---------------------------------------------------------------- 6. verify
# env -i + empty HOME: the gate sees what a user's machine would see, not the
# builder's profile, PATH or checkout. See verify_tree.py for the rules.
echo "verifying the built tree:"
VERIFY_ENV=()
[[ "$DEV_UNLICENSED" == 1 ]] && VERIFY_ENV+=(ATECH_VERIFY_DEV_UNLICENSED=1)
# The builder's home and git e-mail must not ship (personal-data gate).
VERIFY_ENV+=("ATECH_VERIFY_FORBID=$(realpath "$HOME" 2>/dev/null || echo "$HOME")
$(git -C "$REPO" config user.email 2>/dev/null || true)")
# freecadcmd IMPORTS a .py argument after putting its directory on sys.path
# (measured), so run a copy from the scratch HOME: branding/ in the checkout
# must never be importable by the gate, and its bytecode lands there, not in
# the repo.
mkdir -p "$SCRATCH_HOME/gate"
install -m 0644 "$HERE/verify_tree.py" "$SCRATCH_HOME/gate/verify_tree.py"
VERIFY_OUT="$(cd "$SCRATCH_HOME" && fc_clean "${VERIFY_ENV[@]}" \
                "$ROOT/usr/bin/freecadcmd" "$SCRATCH_HOME/gate/verify_tree.py" 2>&1 || true)"
echo "$VERIFY_OUT" | sed -n '/^  /p;/^VERIFY_FAILURES/p;/^VERIFY_FAILED/p'
if ! grep -q '^VERIFY_FAILURES=0$' <<<"$VERIFY_OUT"; then
  fail "branding verification did not pass"
fi
# The gate itself runs Python inside the tree. Anything it leaves behind would
# ship without being in ATECH_CHANGES: drop its bytecode, then re-measure and
# demand no other change.
prune_pyc
python3 "$HERE/tree_changes.py" diff "$ROOT" "$BUILD/upstream_manifest.json" \
  | grep -v "^  usr/share/doc/$DOC_NAME/ATECH_CHANGES.txt\$" > "$BUILD/changes.after_verify"
diff -u "$BUILD/changes.before_verify" "$BUILD/changes.after_verify" >&2 \
  || fail "verification changed the tree after ATECH_CHANGES was written"
echo "verify OK"

if [[ "$DEV_UNLICENSED" == 1 ]]; then
  echo
  echo "NOT RELEASABLE: built with --dev-unlicensed (root LICENSE/LICENSE-models.md/NOTICE not required)."
  echo "Tree for local use only: $ROOT/AppRun"
  [[ "$TREE_ONLY" == 1 ]] && exit 0
  fail "--dev-unlicensed never repacks an AppImage (add --tree-only)"
fi

if [[ "$TREE_ONLY" == "1" ]]; then
  echo
  echo "PASS (tree only). Run it with:"
  echo "  $ROOT/AppRun"
  exit 0
fi

# ---------------------------------------------------------------- 7. repack
# repack.sh never downloads appimagetool; exit 3 = CANNOT DETERMINE.
# Not exec'd: the EXIT trap must still remove the scratch HOME.
rc=0
ATECH_DEFAULT_UPDATE_INFO="$DEFAULT_UPDATE_INFO" "$HERE/repack.sh" "$ROOT" "$OUT" || rc=$?
exit "$rc"
