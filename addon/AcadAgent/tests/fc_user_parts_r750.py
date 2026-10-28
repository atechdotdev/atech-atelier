"""R750 under freecadcmd: parts that are not Atech modules (user_parts.py),
imported from real files into a scratch parts folder and used through the
same library calls the agent and the Modules page use.

    ATELIER_PARTS=<empty dir> ATECH_ARTIFACTS=<repo>/models \
        QT_QPA_PLATFORM=offscreen freecadcmd fc_user_parts_r750.py

Prints one "CHECK <id> PASS|FAIL <detail>" line per assertion and ends with
R750_TESTS=<failures>.
"""
import os
import shutil
import sys
import tempfile
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ADDON = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(ADDON))
for p in (ADDON, os.path.join(REPO, "projects")):
    if p not in sys.path:
        sys.path.insert(0, p)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import FreeCAD as App  # noqa: E402
import Part  # noqa: E402

from acadagent import projects  # noqa: E402

projects._mod()
import atech_modules as am  # noqa: E402
import atech_ports as ap  # noqa: E402
import user_parts as up  # noqa: E402

FAILS = []
PARTS = os.environ["ATELIER_PARTS"]
SRC = tempfile.mkdtemp(prefix="r750_src_")


def check(cid, ok, detail=""):
    print("CHECK %s %s %s" % (cid, "PASS" if ok else "FAIL", detail))
    if not ok:
        FAILS.append(cid)


def step_box(name, x, y, z, at=(0, 0, 0)):
    p = os.path.join(SRC, name + ".step")
    Part.makeBox(x, y, z, App.Vector(*at)).exportStep(p)
    return p


def raises(fn, *a, **kw):
    try:
        fn(*a, **kw)
    except up.PartError as exc:
        return str(exc)
    return None


def main():
    check("dir", up.parts_dir() == os.path.abspath(PARTS), up.parts_dir())

    # A STEP far from the origin, recentred: measured, not typed.
    src = step_box("nano", 45.0, 18.0, 7.0, at=(300, -40, 12))
    sp = up.import_part(src, display_name="Arduino Nano", category="electronics",
                        electrical={"interface": "i2c", "voltage_v": 5,
                                    "wiring": "Qwiic cable to the board"},
                        agent_notes="USB on the -X end must stay reachable.",
                        recentre=True)
    dims = sp["dimensions_mm"]
    check("measured", (dims["x"], dims["y"], dims["z"]) == (45.0, 18.0, 7.0), dims)
    check("kept_source", os.path.isfile(os.path.join(PARTS, sp["source"]["kept_as"])),
          sp["source"])
    check("merged", "arduino_nano" in am.specs() and am.is_user_part("arduino_nano")
          and not am.is_user_part("button"))
    import Mesh
    bb = Mesh.Mesh(am.stl_path("arduino_nano")).BoundBox
    check("recentred", abs(bb.YMin) < 1e-6 and abs(bb.XMin + bb.XMax) < 1e-6
          and abs(bb.ZMin + bb.ZMax) < 1e-6, bb)
    check("ports_stl", ap.stl_path("arduino_nano") == am.stl_path("arduino_nano"))

    # Units: an inch file, and a file in metres refused without a scale.
    src = step_box("cell", 2.0, 0.5, 1.0)
    sp = up.import_part(src, name="cell_pack", category="power", scale=25.4)
    check("inches", sp["dimensions_mm"]["x"] == 50.8, sp["dimensions_mm"])
    src = step_box("huge", 5000.0, 10.0, 10.0)
    msg = raises(up.import_part, src, name="huge_part")
    check("units_refused", msg is not None and "scale" in msg, msg)
    check("units_left_nothing", "huge_part" not in up.specs())

    # Names: never shadow Atech's library; no silent overwrite.
    check("atech_name_refused", raises(up.import_part, src, name="button",
                                       scale=0.01) is not None)
    check("duplicate_refused", raises(up.import_part, step_box("n2", 1, 1, 1),
                                      name="arduino_nano") is not None)
    check("bad_interface", raises(up.import_part, step_box("n3", 5, 5, 5),
                                  name="n3", electrical={"interface": "can"})
          is not None)

    # A part with a real Atech header seats like any module.
    clone = os.path.join(SRC, "my_sensor.stl")
    shutil.copyfile(os.path.join(ap.STL_DIR, "button.stl"), clone)
    up.import_part(clone, name="my_sensor", display_name="My sensor",
                   category="module", recentre=False)
    seat = ap.seatable(["my_sensor", "arduino_nano"])
    check("header_seatable", seat == {"my_sensor": 1}, seat)
    doc = App.newDocument("R750")
    try:
        m = ap.seat(doc, "my_sensor", 2)
        check("seated", m.AtechModule == "my_sensor" and list(m.AtechPorts) == [2],
              (m.AtechModule, list(m.AtechPorts)))
        res = ap.check(doc, only=[m.Name])[m.Name]
        verdicts = {k: res[k]["verdict"] for k in ("seated", "interference",
                                                   "slide_path")}
        check("seat_check", set(verdicts.values()) == {"PASS"}, verdicts)

        # Every other part is a free part, placed by hand.
        free = projects.free_parts()
        check("free_offered", "arduino_nano" in free and "cell_pack" in free
              and "my_sensor" not in free, free)
        o = projects.place_free_part(doc, "arduino_nano")
        check("free_placed", o.AtechRole == "part" and o.AtechModule == "arduino_nano")
    finally:
        App.closeDocument(doc.Name)

    # The agent sees them, with the user's wiring words marked as theirs.
    card = ap.api_card()
    sec = card.split("YOUR PARTS", 1)[1].split("CALLS", 1)[0] if "YOUR PARTS" in card else ""
    check("card_section", "arduino_nano" in sec and "cell_pack" in sec, sec[:400])
    check("card_wiring", "wiring (user says): i2c; 5V; Qwiic cable" in sec, sec[:400])
    row = [ln for ln in card.splitlines() if ln.strip().startswith("my_sensor")]
    check("card_module_row", row and "USER PART" in row[0] and "conn 1" in row[0], row)
    check("card_not_open", "arduino_nano" not in card.split("cannot be seated")[0]
          .splitlines()[-1] if "cannot be seated" in card else True)

    # Removing deletes the entry, the mesh and the kept source.
    kept = os.path.join(PARTS, up.specs()["cell_pack"]["source"]["kept_as"])
    stl = up.stl_path("cell_pack")
    up.remove_part("cell_pack")
    check("removed", "cell_pack" not in am.specs() and not os.path.exists(stl)
          and not os.path.exists(kept))

    # A broken parts.yaml never takes the Atech library down.
    with open(os.path.join(PARTS, "parts.yaml"), "a") as fh:
        fh.write("\n: : [unclosed\n")
    check("broken_catalog", "button" in am.specs() and am.user_specs() == {})


try:
    main()
except Exception:                                      # noqa: BLE001
    traceback.print_exc()
    FAILS.append("crash")
finally:
    shutil.rmtree(SRC, ignore_errors=True)
print("R750_TESTS=%d" % len(FAILS))
sys.stdout.flush()
os._exit(0)
