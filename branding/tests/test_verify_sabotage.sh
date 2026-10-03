#!/usr/bin/env bash
# R09: prove the build gate FAILS when the image lacks what the app needs.
#
# A gate that has never failed proves nothing. Against an already built tree,
# remove one required piece at a time, run verify_tree.py exactly as the build
# does (env -i, empty HOME), require the matching VERIFY_FAILED key, restore.
# A positive control first and last shows the pristine tree still passes.
#
# Usage: branding/tests/test_verify_sabotage.sh <squashfs-root>
#        (exit 0 = every sabotage was caught)
# Touches only the tree it is given, and restores every file it moves.
set -uo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
ROOT="${1:?usage: test_verify_sabotage.sh <squashfs-root>}"
ROOT="$(cd "$ROOT" && pwd)"
FC="$ROOT/usr/bin/freecadcmd"
AA="$ROOT/usr/Mod/AcadAgent"
[[ -x "$FC" ]] || { echo "no freecadcmd in $ROOT" >&2; exit 2; }
H="$(mktemp -d)"; P="$(mktemp -d)"
trap 'rm -rf "$H" "$P"' EXIT
# Run a copy from the temp HOME, as the build does: freecadcmd imports the
# script with its directory on sys.path, which must not be the checkout.
mkdir -p "$H/gate"; cp "$HERE/verify_tree.py" "$H/gate/verify_tree.py"

# A tree built WITH the release licence files is judged as a release (their
# absence is then a FAIL the sabotage below must see); a --dev-unlicensed
# tree is judged as one.
DEV_FLAG=ATECH_VERIFY_DEV_UNLICENSED=1
[[ -f "$ROOT/usr/share/doc/atech-atelier/LICENSE" ]] && DEV_FLAG=ATECH_VERIFY_DEV_UNLICENSED=0
echo "  licence files: $([[ $DEV_FLAG == *=0 ]] && echo 'present, judged as a release' || echo 'absent, judged as a dev build')"

verify() {
  (cd "$H" && env -i HOME="$H" PATH=/usr/bin:/bin LANG=C.UTF-8 \
     PYTHONDONTWRITEBYTECODE=1 "$DEV_FLAG" \
     "$FC" "$H/gate/verify_tree.py" 2>&1)
  # FreeCAD's own startup still writes bytecode into our addons; drop it so
  # one run cannot fail the next run's "no dev files" check.
  find "$AA" "$ROOT/usr/Mod/FreeCADMCP" -name __pycache__ -type d -prune \
       -exec rm -rf {} + 2>/dev/null
  # ...and into the stdlib and other Mods. With the build's snapshot next to
  # the tree, remove every .pyc upstream did not ship, so the tree is left
  # exactly as the build left it.
  if [[ -f "$ROOT/../upstream_manifest.json" ]]; then
    python3 "$HERE/tree_changes.py" prune-bytecode "$ROOT" \
            "$ROOT/../upstream_manifest.json" >/dev/null
  fi
}

pass=0; fail=0
control() {
  local out; out="$(verify)"
  if grep -q '^VERIFY_FAILURES=0$' <<<"$out"; then
    echo "  [OK]      $1"; pass=$((pass+1))
  else
    echo "  [BROKEN]  $1 -- pristine tree does not pass:"; grep '^VERIFY_FAILED' <<<"$out"
    fail=$((fail+1))
  fi
}
sabotage() {  # <label> <path relative to ROOT> <expected VERIFY_FAILED key regex>
  local label="$1" rel="$2" key="$3" out
  [[ -e "$ROOT/$rel" ]] || { echo "  [SKIP]    $label: $rel absent"; fail=$((fail+1)); return; }
  mv "$ROOT/$rel" "$P/moved"
  out="$(verify)"
  mv "$P/moved" "$ROOT/$rel"
  if grep -Eq "^VERIFY_FAILED ($key)\$" <<<"$out" && ! grep -q '^VERIFY_FAILURES=0$' <<<"$out"; then
    echo "  [CAUGHT]  $label -> $(grep -E "^VERIFY_FAILED ($key)\$" <<<"$out" | head -1)"
    pass=$((pass+1))
  else
    echo "  [MISSED]  $label  <-- the gate is blind here"
    grep -E '^VERIFY_(FAILED|FAILURES)' <<<"$out" | head -5
    fail=$((fail+1))
  fi
}

mutate() {  # <label> <path relative to ROOT> <sed expr> <expected key regex>
  local label="$1" rel="$2" expr="$3" key="$4" out
  [[ -f "$ROOT/$rel" ]] || { echo "  [SKIP]    $label: $rel absent"; fail=$((fail+1)); return; }
  mv "$ROOT/$rel" "$P/orig"
  sed "$expr" "$P/orig" > "$ROOT/$rel"
  chmod --reference="$P/orig" "$ROOT/$rel"
  if cmp -s "$P/orig" "$ROOT/$rel"; then
    mv -f "$P/orig" "$ROOT/$rel"
    echo "  [SKIP]    $label: the edit changed nothing (expression stale?)"; fail=$((fail+1)); return
  fi
  out="$(verify)"
  mv -f "$P/orig" "$ROOT/$rel"
  if grep -Eq "^VERIFY_FAILED ($key)\$" <<<"$out" && ! grep -q '^VERIFY_FAILURES=0$' <<<"$out"; then
    echo "  [CAUGHT]  $label -> $(grep -E "^VERIFY_FAILED ($key)\$" <<<"$out" | head -1)"
    pass=$((pass+1))
  else
    echo "  [MISSED]  $label  <-- the gate is blind here"
    grep -E '^VERIFY_(FAILED|FAILURES)' <<<"$out" | head -5
    fail=$((fail+1))
  fi
}

control  "pristine tree passes (before)"
sabotage "module meshes missing"   usr/Mod/AcadAgent/data               'library|library-dir|library-path:.*'
sabotage "library modules missing" usr/Mod/AcadAgent/projects           'library-dir'
sabotage "ATECH_ASSEMBLY.md missing" usr/Mod/AcadAgent/docs/ATECH_ASSEMBLY.md 'assembly-doc'
sabotage "reference model missing" usr/Mod/AcadAgent/fixtures           'reference-model'
sabotage "FreeCADMCP licence missing" usr/Mod/FreeCADMCP/LICENSE        'mcp-licence'
sabotage "third-party notice missing" usr/share/doc/atech-atelier/third_party/NOTICE.third_party 'doc:third_party/NOTICE.third_party'
sabotage "credits missing"            usr/share/doc/atech-atelier/CREDITS.md 'doc:CREDITS.md|credits-dialog'
sabotage "overlay sheet missing (R88)" "usr/share/Gui/Stylesheets/overlay/Atech Overlay.qss" 'template:overlay-file'
sabotage "desktop entry missing"      usr/share/applications/dev.atech.Atelier.desktop 'desktop:share/applications/dev.atech.Atelier.desktop|desktop:name:share'
sabotage "metainfo missing"           usr/share/metainfo/dev.atech.Atelier.metainfo.xml 'desktop:share/metainfo/dev.atech.Atelier.metainfo.xml|metainfo.*'
sabotage "top-level icon missing"     dev.atech.Atelier.svg 'desktop:icon|desktop:diricon'
sabotage "light theme missing"        "usr/share/Gui/Stylesheets/parameters/Atech Atelier Light.yaml" 'share/Gui/Stylesheets/parameters/Atech Atelier Light.yaml|theme-refs:Light'
if [[ "$DEV_FLAG" == *=0 ]]; then
  sabotage "code licence missing"     usr/share/doc/atech-atelier/LICENSE 'doc:LICENSE'
  sabotage "models licence missing next to the models" usr/Mod/AcadAgent/data/models/LICENSE-models.md 'models:LICENSE-models.md'
fi
# Content sabotage: a file that is PRESENT but wrong. mv-based sabotage cannot
# express these, so each swaps the file for a doctored copy and restores it.
mutate "previous name in desktop"     dev.atech.Atelier.desktop 's/^Name=Atech Atelier$/Name=Atech Studio/' 'desktop:name:root|old-name'
mutate "licence expression dropped"   usr/share/metainfo/dev.atech.Atelier.metainfo.xml 's/ AND CC-BY-NC-4.0//' 'metainfo:project_license'
mutate "AppRun loses migration"       AppRun 's/^atech_migrate_tree() {/atech_migrate_treeX() {/' 'apprun-migration'
mutate "draft NOTICE shipped"         usr/share/doc/atech-atelier/NOTICE '1i PROPOSED root NOTICE for Atech Atelier, written by the packaging workstream.' 'licence:notice-draft'
mutate "builder home path in a doc"   usr/share/doc/atech-atelier/ATECH_CHANGES.txt 's|^Module library .*|Module library   /home/someone/dev/atech-artifacts @ 0|' 'personal-data'
control  "pristine tree passes (after restore)"

echo "SABOTAGE_PASSED=$pass SABOTAGE_FAILED=$fail"
[[ "$fail" -eq 0 ]] || { echo "FAIL: the build gate has blind spots" >&2; exit 1; }
