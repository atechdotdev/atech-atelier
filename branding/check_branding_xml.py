#!/usr/bin/env python3
"""Static checks on branding.xml — the failures FreeCAD swallows silently.

build_appimage.sh's verify_branding.py asserts on what the running kernel
reports, which is the right check and catches a wrong VALUE. It cannot catch
the three failures below, because in every one of them FreeCAD starts happily
and simply ignores what we wrote:

  1. a typo'd key       -> Branding.cpp filters against a whitelist and DROPS
                           unknown keys with no warning
  2. a dangling asset   -> a missing icon/splash/stylesheet is a no-op at
                           startup; the app just looks "not done yet"
  3. a wrong root tag   -> the ENTIRE file is ignored, total branding loss

None of the three is visible by looking at the app, which is exactly why they
need a test rather than an eyeball.

The whitelist below is DERIVED FROM SOURCE, not transcribed:
    grep -oP 'filter\\.push_back\\("\\K[^"]+' src/App/Branding.cpp
against tools/freecad-src/src/App/Branding.cpp -> 31 keys. Re-run that command
after a FreeCAD upgrade rather than trusting this copy; a list that agrees with
itself proves nothing (P2).

Usage:
    python3 branding/check_branding_xml.py <branding.xml> [--home <usr/>]

--home is the directory relative asset paths resolve against, i.e. FreeCAD's
AppHomePath (the `usr/` inside the AppImage). Asset checks are skipped when it
is not given.

Exit 0 = all checks pass. Exit 1 = at least one FAIL.
"""
import argparse
import os
import sys
import xml.etree.ElementTree as ET

# Derived from src/App/Branding.cpp — see module docstring for the command.
WHITELIST = (
    "Application", "WindowTitle", "CopyrightInfo", "MaintainerUrl",
    "WindowIcon", "ProgramLogo", "ProgramIcons", "DesktopFileName",
    "StyleSheet", "BuildVersionMajor", "BuildVersionMinor",
    "BuildVersionPoint", "BuildRevision", "BuildRevisionDate",
    "BuildVersionSuffix", "BuildRepositoryURL", "AboutImage", "SplashScreen",
    "SplashAlignment", "SplashTextColor", "SplashInfoColor", "SplashInfoFont",
    "SplashInfoPosition", "SplashWarningColor", "StartWorkbench", "ExeName",
    "ExeVendor", "ExeVersion", "AppDataSkipVendor", "NavigationStyle",
    "UserParameterTemplate",
)

# Tags whose value is a path resolved against AppHomePath.
ASSET_TAGS = ("WindowIcon", "ProgramLogo", "SplashScreen", "AboutImage",
              "ProgramIcons")

# StyleSheet is deliberately NOT an asset check. In FreeCAD 1.1 it is a
# stylesheet NAME resolved against the "qss:" search path, not a filesystem
# path — asserting os.path.exists on it would fail on a correct file.


def _report(results):
    for ok, label, detail in results:
        print("  %-14s %-34s %s" % (label, detail, "OK" if ok else "FAIL"))
    bad = [r for r in results if not r[0]]
    print("XML_CHECK_FAILURES=%d" % len(bad))
    return len(bad)


def check(path, home=None):
    results = []

    try:
        root = ET.parse(path).getroot()
    except Exception as exc:  # noqa: BLE001 - any parse error is a FAIL
        print("  %-14s %-34s FAIL (%s)" % ("parse", os.path.basename(path), exc))
        print("XML_CHECK_FAILURES=1")
        return 1

    # CASE 3 — wrong root tag means the whole file is ignored.
    results.append((root.tag == "Branding", "root tag",
                    "<%s> (want <Branding>)" % root.tag if root.tag != "Branding"
                    else "<Branding>"))

    # CASE 1 — unknown keys are dropped silently by Branding.cpp.
    unknown = [e.tag for e in root if e.tag is not ET.Comment
               and e.tag not in WHITELIST]
    results.append((not unknown, "whitelist",
                    "unknown: %s" % ", ".join(unknown) if unknown
                    else "%d keys, all known" % len(list(root))))

    # CASE 2 — a dangling asset path is a silent no-op at startup.
    for tag in ASSET_TAGS:
        el = root.find(tag)
        if el is None or not (el.text or "").strip():
            continue
        value = el.text.strip()
        if os.path.isabs(value):
            results.append((True, "asset", "%s (absolute, skipped)" % tag))
            continue
        if home is None:
            results.append((True, "asset", "%s (no --home, skipped)" % tag))
            continue
        full = os.path.join(home, value)
        results.append((os.path.isfile(full), "asset", "%s -> %s" % (tag, value)))

        # A 0-byte or truncated SVG passes "file exists" but renders nothing.
        if full.lower().endswith(".svg") and os.path.isfile(full):
            try:
                svg = ET.parse(full).getroot()
                tag_ok = svg.tag.endswith("svg")
                sized = bool(svg.get("width") or svg.get("viewBox"))
                results.append((tag_ok and sized, "asset svg",
                                "%s root=<%s> sized=%s"
                                % (tag, svg.tag.rsplit('}', 1)[-1], sized)))
            except Exception as exc:  # noqa: BLE001
                results.append((False, "asset svg", "%s unparseable (%s)" % (tag, exc)))

    return _report(results)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("xml")
    ap.add_argument("--home", default=None,
                    help="AppHomePath that relative asset paths resolve against")
    args = ap.parse_args()
    sys.exit(1 if check(args.xml, args.home) else 0)


if __name__ == "__main__":
    main()
