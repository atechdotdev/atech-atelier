#!/usr/bin/env bash
# Sabotage-test check_branding_xml.py. A verifier that has never failed proves
# nothing, so mutate a good branding.xml three ways and require a FAIL each time.
#
# All three failures are SILENT in FreeCAD: the app launches and looks fine, it
# just ignores what we wrote. That is why they need a test, not an eyeball.
#
# Usage: branding/test_branding_sabotage.sh   (exit 0 = the verifier bites)
set -uo pipefail
cd "$(dirname "$0")/.."
CHECK="branding/check_branding_xml.py"
HOME_DIR="dist/build/squashfs-root/usr"
W="$(mktemp -d)"; trap 'rm -rf "$W"' EXIT
cp branding/branding.xml "$W/good.xml"

pass=0; fail=0
expect() {  # <label> <expect-fail yes|no> [--home]
  local label="$1" want="$2"; shift 2
  local out n
  out="$(python3 "$CHECK" "$W/t.xml" "$@" 2>&1)"
  n="$(grep -oP 'XML_CHECK_FAILURES=\K\d+' <<<"$out")"
  if [ "$want" = yes ] && [ "${n:-0}" -ge 1 ]; then
    echo "  [CAUGHT]  $label"; pass=$((pass+1))
  elif [ "$want" = no ] && [ "${n:-1}" -eq 0 ]; then
    echo "  [OK]      $label"; pass=$((pass+1))
  else
    echo "  [MISSED]  $label  <-- verifier is blind here"; fail=$((fail+1))
  fi
}

# 1. Typo'd key: Branding.cpp filters against a whitelist and DROPS unknowns.
sed 's|<WindowTitle>|<WindowTitel>|; s|</WindowTitle>|</WindowTitel>|' \
    "$W/good.xml" > "$W/t.xml"
expect "typo'd key (WindowTitel)" yes

# 2. Dangling asset: a missing icon/splash is a no-op; app looks unfinished.
sed 's|bin/atech_logo.svg|bin/does_not_exist.svg|' "$W/good.xml" > "$W/t.xml"
expect "dangling asset path" yes --home "$HOME_DIR"

# 3. Wrong root tag: the ENTIRE file is ignored — total branding loss.
sed 's|<Branding |<Brandings |; s|</Branding>|</Brandings>|' \
    "$W/good.xml" > "$W/t.xml"
expect "wrong root tag" yes

# Restoring the pristine file must pass again, or the test proves nothing.
cp "$W/good.xml" "$W/t.xml"
expect "restored pristine" no

echo "SABOTAGE_PASSED=$pass SABOTAGE_FAILED=$fail"
[ "$fail" -eq 0 ] || { echo "FAIL: verifier has blind spots" >&2; exit 1; }
