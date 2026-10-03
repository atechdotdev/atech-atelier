#!/usr/bin/env bash
# Drive branding/repack.sh through every branch with STUB appimagetools.
#
# No real appimagetool is needed or downloaded: each stub records its argv and
# writes a small file where the AppImage (and, when given -u, the .zsync)
# would go. What is under test is repack.sh's own logic:
#
#   no tool                -> exit 3, CANNOT DETERMINE, nothing written
#   tool lists -u          -> the default update info is passed, .zsync summed
#   tool lacks -u          -> nothing passed, and the build SAYS it was not
#   ATECH_UPDATE_INFO=""   -> no -u even though the tool supports it
#   ATECH_SIGN_KEY empty   -> no --sign, "SKIPPED: unsigned image"
#   ATECH_SIGN_KEY set     -> --sign --sign-key <id>
#   SHA256SUMS             -> sha256sum -c passes, and a tampered image fails it
#   sabotage               -> a repack.sh copy that drops -u fails the -u case
#
# Usage: branding/tests/test_repack.sh   (exit 0 = every case passed)
set -uo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
REPACK="${REPACK:-$HERE/repack.sh}"
W="$(mktemp -d)"; trap 'rm -rf "$W"' EXIT
DEFAULT="gh-releases-zsync|atechdotdev|atech-atelier|latest|AtechAtelier-*x86_64.AppImage.zsync"

mkdir -p "$W/AppDir"; printf '#!/bin/sh\n' > "$W/AppDir/AppRun"; chmod +x "$W/AppDir/AppRun"

stub() {  # <path> <with -u in --help: yes|no>
  cat > "$1" <<EOF
#!/bin/bash
if [ "\$1" = --help ]; then
  echo "Usage: appimagetool [OPTION...] SOURCE [DESTINATION]"
  [ "$2" = yes ] && echo "  -u, --updateinformation   Embed update information STRING"
  echo "  -s, --sign                Sign with gpg[2]"
  exit 0
fi
printf '%s\n' "\$@" > "$W/argv"
dest="\${@: -1}"
printf 'STUB APPIMAGE %s\n' "\$RANDOM" > "\$dest"
# Like the real appimagetool 1.9.1 (MEASURED 2026-10-04): the .zsync goes into
# the CURRENT directory under the image's basename, not next to DESTINATION.
for a in "\$@"; do [ "\$a" = -u ] && printf 'STUB ZSYNC\n' > "\$(basename "\$dest").zsync"; done
exit 0
EOF
  chmod +x "$1"
}
stub "$W/ait-u" yes
stub "$W/ait-nou" no

pass=0; fail=0
ok()  { echo "  [OK]      $1"; pass=$((pass+1)); }
bad() { echo "  [FAIL]    $1"; [[ -n "${2:-}" ]] && sed 's/^/            /' <<<"$2"; fail=$((fail+1)); }

run() {  # <out dir> [env ...] -- prints combined output, sets RC
  local out="$1"; shift
  rm -rf "$out" "$W/argv"; mkdir -p "$out"
  OUTPUT="$(env -i PATH=/usr/bin:/bin HOME="$W" ATECH_DEFAULT_UPDATE_INFO="$DEFAULT" "$@" \
            bash "$REPACK" "$W/AppDir" "$out/AtechAtelier-0.1.0-x86_64.AppImage" 2>&1)"
  RC=$?
}
argv_has() { [[ -f "$W/argv" ]] && grep -qxF -- "$1" "$W/argv"; }

# 1. no appimagetool at all (PATH has none; APPIMAGETOOL unset / bogus)
if command -v appimagetool >/dev/null 2>&1; then
  echo "  [SKIP]    no-tool case: appimagetool is on PATH here"
else
  run "$W/o1"
  [[ $RC -eq 3 ]] && grep -q "CANNOT DETERMINE" <<<"$OUTPUT" && [[ -z "$(ls -A "$W/o1")" ]] \
    && ok "no appimagetool -> exit 3 CANNOT DETERMINE, nothing written" \
    || bad "no appimagetool (rc=$RC)" "$OUTPUT"
fi
run "$W/o1b" APPIMAGETOOL="$W/does-not-exist"
[[ $RC -eq 3 ]] && ok "APPIMAGETOOL pointing nowhere -> exit 3" || bad "bogus APPIMAGETOOL (rc=$RC)" "$OUTPUT"

# 2. tool with -u: default channel embedded, unsigned announced, sums incl. zsync
run "$W/o2" APPIMAGETOOL="$W/ait-u"
if [[ $RC -eq 0 ]] && argv_has "-u" && argv_has "$DEFAULT" && ! argv_has "--sign" \
   && grep -q "SKIPPED: unsigned image" <<<"$OUTPUT" \
   && grep -q "AtechAtelier-0.1.0-x86_64.AppImage.zsync" "$W/o2/SHA256SUMS" \
   && (cd "$W/o2" && sha256sum -c --quiet SHA256SUMS); then
  ok "-u supported -> default update info embedded, unsigned announced, SHA256SUMS (image + zsync) checks"
else
  bad "-u supported (rc=$RC)" "$OUTPUT"
fi
# tampering is caught by the published sums
printf 'tampered\n' >> "$W/o2/AtechAtelier-0.1.0-x86_64.AppImage"
(cd "$W/o2" && sha256sum -c --quiet SHA256SUMS >/dev/null 2>&1) \
  && bad "SHA256SUMS did not catch a tampered image" \
  || ok "SHA256SUMS catches a tampered image"

# 3. tool without -u: nothing passed, and the output says so
run "$W/o3" APPIMAGETOOL="$W/ait-nou"
[[ $RC -eq 0 ]] && ! argv_has "-u" && grep -q "NOT embedded" <<<"$OUTPUT" \
  && [[ "$(wc -l < "$W/o3/SHA256SUMS")" -eq 1 ]] \
  && ok "-u unsupported -> not embedded, and reported" \
  || bad "-u unsupported (rc=$RC)" "$OUTPUT"

# 4. explicit empty update info
run "$W/o4" APPIMAGETOOL="$W/ait-u" ATECH_UPDATE_INFO=
[[ $RC -eq 0 ]] && ! argv_has "-u" && ok "ATECH_UPDATE_INFO=\"\" -> no update info" \
  || bad "empty ATECH_UPDATE_INFO (rc=$RC)" "$OUTPUT"

# 5. override
run "$W/o5" APPIMAGETOOL="$W/ait-u" "ATECH_UPDATE_INFO=zsync|https://example.org/x.zsync"
[[ $RC -eq 0 ]] && argv_has "zsync|https://example.org/x.zsync" && ! argv_has "$DEFAULT" \
  && ok "ATECH_UPDATE_INFO overrides the default" || bad "override (rc=$RC)" "$OUTPUT"

# 6. signing only behind the variable
run "$W/o6" APPIMAGETOOL="$W/ait-u" ATECH_SIGN_KEY=ABCDEF12
[[ $RC -eq 0 ]] && argv_has "--sign" && argv_has "--sign-key" && argv_has "ABCDEF12" \
  && ok "ATECH_SIGN_KEY set -> --sign --sign-key passed" || bad "signing (rc=$RC)" "$OUTPUT"

# 7. sabotage: a repack.sh that never passes -u must fail case 2
sed 's/AIT_ARGS+=(-u "$UPDATE_INFO")/:/' "$HERE/repack.sh" > "$W/repack-broken.sh"
if cmp -s "$HERE/repack.sh" "$W/repack-broken.sh"; then
  bad "sabotage edit changed nothing (stale expression)"
else
  SAVE_REPACK="$REPACK"; REPACK="$W/repack-broken.sh"; run "$W/o7" APPIMAGETOOL="$W/ait-u"; REPACK="$SAVE_REPACK"
  if [[ $RC -eq 0 && -f "$W/argv" ]] && ! argv_has "-u"; then
    ok "sabotage: a repack that drops -u runs, and the -u check sees it missing"
  else
    bad "sabotage run did not behave as a silent -u drop (rc=$RC)" "$OUTPUT"
  fi
fi

echo "REPACK_PASSED=$pass REPACK_FAILED=$fail"
[[ "$fail" -eq 0 ]] || exit 1
echo "REPACK_TESTS_OK"
