"""R770 under freecadcmd: the Atech modules added from atech-module-simready
0ba167be seat on the board like every module.

    ATECH_ARTIFACTS=<repo>/models QT_QPA_PLATFORM=offscreen \
        freecadcmd fc_more_modules_r770.py

Prints one "CHECK <id> PASS|FAIL <detail>" line per assertion and ends with
R770_TESTS=<failures>.
"""
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ADDON = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(ADDON))
for p in (ADDON, os.path.join(REPO, "projects")):
    if p not in sys.path:
        sys.path.insert(0, p)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import FreeCAD as App  # noqa: E402

from acadagent import projects  # noqa: E402

projects._mod()
import atech_modules as am  # noqa: E402
import atech_ports as ap  # noqa: E402

FAILS = []
NEW = {"big_screen": 2, "camera": 2, "soil_sensor": 1, "load_cell": 1,
       "power_jack": 1}
#: Ports each is seated on (MEASURED 2026-10-28: every port passes for the
#: one-connector modules but 4, 7 and 8 for the power jack, whose second
#: cell runs into something there; the two-connector ones pass the pairs
#: the screen passes).
PORTS = {"big_screen": (13, 14), "camera": (1, 2), "soil_sensor": 3,
         "load_cell": 11, "power_jack": 9}


def check(cid, ok, detail=""):
    print("CHECK %s %s %s" % (cid, "PASS" if ok else "FAIL", detail))
    if not ok:
        FAILS.append(cid)


def verdicts(doc, obj):
    res = ap.check(doc, only=[obj.Name])[obj.Name]
    return {k: res[k]["verdict"] for k in ("seated", "interference", "slide_path")}


def main():
    specs = am.specs()
    check("in_library", all(n in specs for n in NEW), sorted(set(NEW) - set(specs)))
    check("seatable", ap.seatable(list(NEW)) == NEW, ap.seatable(list(NEW)))
    check("derived", {n for n in NEW if specs[n].get("derived")}
          == {"soil_sensor", "load_cell", "power_jack"})
    check("micro_sd_not_offered", "micro_sd_card" not in specs)
    for name, port in PORTS.items():
        doc = App.newDocument("R770")
        try:
            m = ap.seat(doc, name, port)
            v = verdicts(doc, m)
            check("seat_" + name, set(v.values()) == {"PASS"}, (port, v))
        finally:
            App.closeDocument(doc.Name)
    # The jack's housing covers the next cell along its row: a module there
    # is caught by the check, one elsewhere is not.
    doc = App.newDocument("R770")
    try:
        pj = ap.seat(doc, "power_jack", 9)
        b = ap.seat(doc, "button", 10)
        check("jack_blocks_neighbour", verdicts(doc, b)["interference"] == "FAIL")
        doc.removeObject(b.Name)
        b = ap.seat(doc, "button", 3)
        check("jack_leaves_others", set(verdicts(doc, b).values()) == {"PASS"}
              and set(verdicts(doc, pj).values()) == {"PASS"})
    finally:
        App.closeDocument(doc.Name)
    faces = {n: [f["word"] for f in ap.measure_module(n)["faces"]] for n in NEW}
    check("faces", faces["soil_sensor"] == ["out"] and faces["power_jack"] == ["row+"]
          and faces["camera"] == ["up"], faces)


try:
    main()
except Exception:                                      # noqa: BLE001
    traceback.print_exc()
    FAILS.append("crash")
print("R770_TESTS=%d" % len(FAILS))
