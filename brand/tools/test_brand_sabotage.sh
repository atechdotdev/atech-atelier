#!/usr/bin/env bash
# Prove the brand gates can actually FAIL.
#
# A gate that has never been seen to fail is not evidence of anything — it
# may be asking nothing at all. This repo has shipped exactly that: six
# bought modules, all [OK], no geometry (CLAUDE.md). So each check here is
# deliberately broken and must be caught.
#
# S2 is the one that matters most. It passed a pure membership check,
# because #f5f5f5 is light's `base` AND dark's `text` — a valid colour in
# the wrong role. That hole was found by running this test, not by reading
# the code, and it is why build_qss.py grew a second check.
#
# Run:  bash brand/tools/test_brand_sabotage.sh
set -uo pipefail

cd "$(dirname "$0")/../.."
ROOT=$(pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

PASS=0
FAIL=0

restore() { cp "$TMP/$(basename "$1")" "$1"; }
stash()   { cp "$1" "$TMP/$(basename "$1")"; }

# expect_fail <label> <command...>
expect_fail() {
    local label="$1"; shift
    if "$@" >/dev/null 2>&1; then
        echo "[FAIL] $label — the gate PASSED sabotaged input"
        FAIL=$((FAIL + 1))
    else
        echo "[ OK ] $label — gate correctly failed"
        PASS=$((PASS + 1))
    fi
}

expect_pass() {
    local label="$1"; shift
    if "$@" >/dev/null 2>&1; then
        echo "[ OK ] $label"
        PASS=$((PASS + 1))
    else
        echo "[FAIL] $label — the gate failed CLEAN input"
        FAIL=$((FAIL + 1))
    fi
}

echo "=== baseline: clean tree must pass ==="
expect_pass "qss   clean" python3 brand/tools/build_qss.py --check
expect_pass "brand clean" python3 brand/tools/build_brand.py --check

echo
echo "=== S1: a foreign colour (the old invented #5AA2FF brand) ==="
LIGHT="$ROOT/brand/assets/AtechLight.qss"
stash "$LIGHT"
sed -i 's/background: #f5f5f5;/background: #5AA2FF;/' "$LIGHT"
expect_fail "qss   foreign colour" python3 brand/tools/build_qss.py --check
restore "$LIGHT"

echo
echo "=== S2: a VALID colour in the WRONG ROLE (dark text into light sheet) ==="
stash "$LIGHT"
sed -i '0,/color: #111827;/s//color: #f5f5f5;/' "$LIGHT"
expect_fail "qss   wrong role" python3 brand/tools/build_qss.py --check
restore "$LIGHT"

echo
echo "=== S3: a deleted rule (literal count drifts) ==="
stash "$LIGHT"
sed -i '0,/    background: #ffffff;/s///' "$LIGHT"
expect_fail "qss   deleted literal" python3 brand/tools/build_qss.py --check
restore "$LIGHT"

echo
echo "=== S4: the trace no longer reproduces the artwork ==="
# Perturb the tolerance rather than the artwork: the gate's job is to reject
# a trace that has drifted from the source, and tightening the budget below
# the measured floor is the same condition seen from the other side.
python3 - <<'PY' >/dev/null 2>&1
import re, pathlib
p = pathlib.Path("brand/tools/trace.py")
s = p.read_text()
p.with_suffix(".py.bak").write_text(s)
p.write_text(re.sub(r"TOL_ERR_PER_EDGE_DENSITY = [0-9.]+",
                    "TOL_ERR_PER_EDGE_DENSITY = 0.0001", s))
PY
expect_fail "trace tightened budget" python3 brand/tools/build_brand.py --check
mv brand/tools/trace.py.bak brand/tools/trace.py
# mv preserves the .bak's mtime, which can be OLDER than the sabotaged
# module's cached bytecode — CPython then reuses the sabotaged .pyc and the
# "restored" tree keeps failing. MEASURED: this test reported
# "brand restored — the gate failed CLEAN input" until both lines existed.
touch brand/tools/trace.py
rm -rf brand/tools/__pycache__

echo
echo "=== S5: branding.xml points at a missing asset ==="
# check_branding_xml.py only resolves assets when given --home, so build a
# fake AppHomePath whose bin/ holds exactly the files branding.xml names.
BX="$ROOT/branding/branding.xml"
HOME_DIR="$TMP/usr"
mkdir -p "$HOME_DIR/bin"
python3 - "$BX" "$HOME_DIR" <<'PY'
import sys, xml.etree.ElementTree as ET, pathlib
bx, home = sys.argv[1], pathlib.Path(sys.argv[2])
for el in ET.parse(bx).getroot():
    if el.tag in ("WindowIcon", "ProgramLogo", "SplashScreen", "AboutImage",
                  "ProgramIcons") and el.text:
        p = home / el.text.strip()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('<svg xmlns="http://www.w3.org/2000/svg" '
                     'width="1" height="1"/>')
PY
expect_pass "xml   assets present" \
    python3 branding/check_branding_xml.py "$BX" --home "$HOME_DIR"

stash "$BX"
sed -i 's#<WindowIcon>[^<]*</WindowIcon>#<WindowIcon>bin/does_not_exist.svg</WindowIcon>#' "$BX"
expect_fail "xml   missing asset" \
    python3 branding/check_branding_xml.py "$BX" --home "$HOME_DIR"
restore "$BX"

echo
echo "=== S6: a typo'd key (FreeCAD drops it silently) ==="
stash "$BX"
sed -i 's#<WindowIcon>#<WindowIkon>#; s#</WindowIcon>#</WindowIkon>#' "$BX"
expect_fail "xml   unknown key" \
    python3 branding/check_branding_xml.py "$BX" --home "$HOME_DIR"
restore "$BX"

echo
echo "=== final: tree restored, everything passes again ==="
expect_pass "qss   restored" python3 brand/tools/build_qss.py --check
expect_pass "brand restored" python3 brand/tools/build_brand.py --check

echo
echo "passed=$PASS failed=$FAIL"
[ "$FAIL" -eq 0 ] || exit 1
