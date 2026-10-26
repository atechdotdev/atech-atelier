"""R300-R306 under freecadcmd: the Modules page's hardware tools, driven
headless (offscreen Qt, no 3D view) against the real library.

    ATECH_ARTIFACTS=<repo>/models QT_QPA_PLATFORM=offscreen \
        freecadcmd fc_modules_r300.py

Prints one "CHECK <id> PASS|FAIL <detail>" line per assertion and ends with
R300_TESTS=<failures>. ATECH_R300_SABOTAGE=<feature> breaks one feature
first (reseat, power, cabled, undo_add, starter, move, hover, free,
by_cable), so
test_modules_page_r300 can prove each check can fail.
"""
import os
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ADDON = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(ADDON))
for p in (ADDON, os.path.join(REPO, "projects")):
    if p not in sys.path:
        sys.path.insert(0, p)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import FreeCAD as App  # noqa: E402
from PySide6 import QtWidgets  # noqa: E402

APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

from acadagent import modules_page as mp  # noqa: E402
from acadagent import projects  # noqa: E402

projects._mod()
import atech_ports as ap  # noqa: E402

SAB = os.environ.get("ATECH_R300_SABOTAGE", "")
FAILS = []


def check(cid, ok, detail=""):
    print("CHECK %s %s %s" % (cid, "PASS" if ok else "FAIL", detail))
    if not ok:
        FAILS.append(cid)


def pump(page, timeout=5.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        APP.processEvents()
        if page._anim is None:
            break
        time.sleep(0.01)
    APP.processEvents()


# ------------------------------------------------------------ sabotage
if SAB == "reseat":
    ap.reseat_all = lambda doc: {"reseated": [], "recabled": [], "failed": {}}
elif SAB == "power":
    mp.power_warning = lambda modules: None
elif SAB == "cabled":
    mp.CABLED_WORDS = mp.CHECK_WORDS
    mp.CABLED_ORDER = mp.CHECK_ORDER
elif SAB == "undo_add":
    _orig_after = mp.ModulesPage._after_add
    mp.ModulesPage._after_add = lambda self, doc, oname, txn=None: _orig_after(self, doc, oname)
elif SAB == "starter":
    def _untagged(key, doc_name=None):
        return projects._mod().build_named(key, doc_name=doc_name)
    projects.build_starter = _untagged
elif SAB == "move":
    ap.move = lambda doc, o, port_arg: o
elif SAB == "hover":
    mp.port_tooltip = lambda n, *a, **k: "Port %d" % n
elif SAB == "free":
    projects.FREE_ROLE = "module"
elif SAB == "by_cable":
    mp.ModulesPage._add_cabled = lambda self, name: None


def new_page():
    page = mp.ModulesPage()
    page.resize(380, 1400)
    page._load()
    return page


def occ_names(doc):
    return {n: o.Name for n, o in ap.occupied(doc).items()}


def run():
    page = new_page()
    check("load", page._unavailable is None and bool(page._ports),
          "unavailable=%r" % page._unavailable)
    doc = App.newDocument("R300")
    doc.UndoMode = 1                    # as in the app (freecadcmd starts it off)
    App.setActiveDocument(doc.Name)

    # ---- R304 Undo add ------------------------------------------------
    page.pick(3)
    page._add("button")
    pump(page)
    o = ap.occupied(doc).get(3)
    check("add.seated", o is not None and o.AtechModule == "button")
    check("undo_add.row", page.undo_row.isVisibleTo(page)
          and page.undo_text.text().startswith("Added Button"),
          repr(page.undo_text.text()))
    check("undo_add.txn", list(doc.UndoNames[:1]) == ["Add button"],
          repr(list(doc.UndoNames[:3])))
    page._undo_remove()
    check("undo_add.undone", 3 not in ap.occupied(doc), repr(occ_names(doc)))

    # ---- R300 move and swap -------------------------------------------
    page.pick(2)
    page._add("light")
    pump(page)
    page.pick(3)
    page._add("button")
    pump(page)
    light = ap.occupied(doc)[2]
    lname = light.Name
    page.pick(2)
    page._start_move()
    check("move.mode", page.move_row.isVisibleTo(page) and page.map.moving == (2,),
          repr(page.map.moving))
    page.pick(5)
    occ = occ_names(doc)
    check("move.moved", occ.get(5) == lname and 2 not in occ, repr(occ))
    check("move.label", doc.getObject(lname).Label == "light_p5",
          doc.getObject(lname).Label)
    res = ap.check(doc, only=[lname])[lname]
    check("move.check_pass", all(v["verdict"] == "PASS" for v in res.values()),
          repr(ap.first_why(res)))
    check("move.undo_row", page.undo_text.text().startswith("Moved Light to port 5"),
          repr(page.undo_text.text()))
    page._undo_remove()
    occ = occ_names(doc)
    check("move.undo", occ.get(2) == lname and 5 not in occ, repr(occ))
    # swap light (2) with button (3)
    bname = ap.occupied(doc)[3].Name
    page.pick(2)
    page._start_move()
    page.pick(3)
    occ = occ_names(doc)
    check("swap.done", occ.get(3) == lname and occ.get(2) == bname, repr(occ))
    check("swap.row", page.undo_text.text().startswith("Swapped Light and Button"),
          repr(page.undo_text.text()))
    # a two-port module cannot swap with a one-port one
    page.pick(9)
    page._add("screen")
    pump(page)
    sname = ap.occupied(doc)[9].Name
    page.pick(9)
    page._start_move()
    page.pick(2)
    check("swap.refused", page.err.isVisibleTo(page) and "same number of ports"
          in page.err.text() and occ_names(doc).get(2) == bname, page.err.text())
    page._cancel_move()
    # two-port move: the screen to port 13 (with a free neighbour)
    page.pick(9)
    page._start_move()
    page.pick(13)
    sp = sorted(int(p) for p in doc.getObject(sname).AtechPorts)
    check("move.pair", 13 in sp and len(sp) == 2 and 9 not in sp, repr(sp))
    res = ap.check(doc, only=[sname])[sname]
    check("move.pair_pass", all(v["verdict"] == "PASS" for v in res.values()),
          repr(ap.first_why(res)))

    # ---- R302 cables in the UI ----------------------------------------
    cmod, cabs = ap.cable(doc, "button", 11, ap.module_placement(
        "button", (30, -140, 20), face="-Y", cable="+Z"))
    page.refresh()
    rows = [b.text() for b in page._on_rows]
    crow = [b for b in page._on_rows if "by cable" in b.text()]
    check("cable.row", len(crow) == 1 and not crow[0].icon().isNull()
          and " mm" in crow[0].text(), repr(rows))
    page.pick(11)
    sub = page.port_sub.text()
    check("cable.sub", "Connected by cable" in sub and " mm" in sub, sub)
    vt = page.verdicts.text()
    check("cable.words", "Connected by cable" in vt and "Fully seated" not in vt
          and "Slides in freely" not in vt, vt)
    check("cable.no_remake_when_fresh", not page.btn_recable.isVisibleTo(page))
    # the module moved by hand: its cable no longer reaches
    pl = App.Placement(cmod.Placement)
    pl.Base = pl.Base + App.Vector(0, 0, 15)
    cmod.Placement = pl
    page.pick(11)
    check("cable.stale_button", page.btn_recable.isVisibleTo(page))
    check("cable.stale_banner", page.stale_row.isVisibleTo(page)
          and "cable" in page.stale_text.text(), page.stale_text.text())
    page._remake_cable()
    res = ap.check(doc, only=[cmod.Name])[cmod.Name]
    check("cable.remade", res["seated"]["verdict"] == "PASS"
          and not page.btn_recable.isVisibleTo(page), repr(ap.first_why(res)))
    check("cable.remade_row", page.undo_text.text().startswith("Remade the cable"),
          page.undo_text.text())

    # ---- by cable: a module off the board, wired to its port -----------
    pbtn = [b for b in page._module_btns if b.text().startswith("PIR")]
    check("bycable.derived_label", len(pbtn) == 1 and "derived" in pbtn[0].text()
          and "not Atech CAD" in pbtn[0].toolTip(), repr([b.text() for b in pbtn]))
    check("bycable.knob_seatable", "knob" in page._seatable, repr(sorted(page._seatable)))
    page.pick(6)
    check("bycable.toggle", page.by_cable.isVisibleTo(page))
    page.by_cable.setChecked(True)
    page._add("pir")
    pump(page)
    page.by_cable.setChecked(False)
    po = ap.occupied(doc).get(6)
    check("bycable.added", po is not None and po.AtechModule == "pir"
          and po.AtechJoint == "cable" and list(po.AtechPorts) == [6],
          repr(po and (po.AtechModule, po.AtechJoint)))
    if po is not None:
        pb, bb0 = ap.bbox(po), ap.bbox(ap.board_object(doc, create=False))
        check("bycable.off_board", not pb.intersect(bb0), "%s vs %s" % (pb, bb0))
        res = ap.check(doc, only=[po.Name])[po.Name]
        check("bycable.pass", all(v["verdict"] == "PASS" for v in res.values()),
              repr(ap.first_why(res)))
        check("bycable.cable", len(ap.cables_of(doc, po)) == 1)
    check("bycable.undo", list(doc.UndoNames[:1]) == ["Add pir by cable"]
          and page.undo_text.text().startswith("Added"),
          repr(list(doc.UndoNames[:2])))

    # ---- R304 port hover info -----------------------------------------
    tips = page.map.tips
    check("hover.empty", "empty" in tips.get(1, "") and "slides in" in tips.get(1, ""),
          tips.get(1))
    check("hover.cable", "Button on a" in tips.get(11, "") and "mm cable" in tips.get(11, ""),
          tips.get(11))
    s13 = tips.get(13, "")
    check("hover.two_port", "Screen, seated" in s13 and "also on port" in s13, s13)
    check("hover.tooltip", page.map.tip_for(11) == tips.get(11))

    # ---- R303 power rule ----------------------------------------------
    page._check_all()
    av = page.all_verdicts.text()
    check("power.warns", "No USB-C module" in av, av[:200])
    page.pick(8)
    page._add("usbc")
    pump(page)
    page._check_all()
    check("power.quiet_with_usbc", "No USB-C module" not in page.all_verdicts.text())

    # ---- R301 re-seat all after the board moves -----------------------
    b = ap.board_object(doc, create=False)
    b.Placement = App.Placement(App.Vector(12, 4, -6), App.Rotation(App.Vector(0, 1, 0), 25))
    page.refresh()
    st = page.stale_text.text()
    check("reseat.detected", page.stale_row.isVisibleTo(page)
          and "The board has moved" in st, st)
    names_before = sorted(o.Name for o in ap.occupied(doc).values())
    page._reseat_all()
    page.refresh()
    check("reseat.banner_gone", not page.stale_row.isVisibleTo(page),
          page.stale_text.text())
    res = ap.check(doc)
    bad = {k: ap.first_why(v) for k, v in res.items() if ap.first_why(v)}
    check("reseat.all_pass", not bad, repr(bad))
    check("reseat.same_objects",
          sorted(o.Name for o in ap.occupied(doc).values()) == names_before)
    check("reseat.row", page.undo_text.text().startswith("Re-seated"),
          page.undo_text.text())

    # ---- R305 free parts ----------------------------------------------
    # (the knob left this list with the simready v1.7 mesh: it has pins)
    check("free.offered", sorted(page._free_names) == ["n20_wheel", "nema17_stepper"],
          repr(page._free_names))
    check("free.buttons", len(page._free_btns) == 2
          and page.free_label.isVisibleTo(page))
    n_before = len(doc.Objects)
    page._add_free("nema17_stepper")
    mot = [o for o in doc.Objects if getattr(o, "AtechModule", "") == "nema17_stepper"]
    check("free.placed", len(mot) == 1 and mot[0].AtechRole == "part"
          and len(doc.Objects) == n_before + 1, repr([o.Name for o in mot]))
    kb, bb = ap.bbox(mot[0]), ap.bbox(b)
    check("free.clear_of_board", kb.XMin > bb.XMax, "%s vs %s" % (kb, bb))
    check("free.not_a_port", all(o.Name != mot[0].Name
                                  for o in ap.occupied(doc).values()))
    check("free.row", len(page._free_rows) == 1)
    page._check_all()
    check("free.not_in_check_all", "NEMA" not in page.all_verdicts.text())
    page._add_free("n20_wheel")
    page._add_free("n20_wheel")
    parts = projects.placed_free_parts(doc)
    boxes = [ap.bbox(o) for o in parts]
    olap = [(i, j) for i in range(len(boxes)) for j in range(i + 1, len(boxes))
            if boxes[i].intersect(boxes[j])]
    check("free.three_apart", len(parts) == 3 and not olap, repr(olap))
    page._remove_free(parts[-1].Name)
    check("free.removed", len(projects.placed_free_parts(doc)) == 2
          and page.undo_text.text().startswith("Removed"))

    # ---- R306 starter projects with real hardware ----------------------
    for key in projects.project_keys():
        sdoc, rep = projects.build_starter(key)
        meshes = [o for o in sdoc.Objects if o.TypeId == "Mesh::Feature"]
        untagged = [o.Label for o in meshes if not getattr(o, "AtechRole", "")]
        mods = [o for o in meshes if getattr(o, "AtechRole", "") == "module"]
        res = ap.check(sdoc)
        bad = {k: ap.first_why(v) for k, v in res.items()
               if getattr(sdoc.getObject(k), "AtechRole", "") == "module"
               and ap.first_why(v)}
        want = len(projects.project_info(key)["modules"])
        check("starter.%s" % key, not untagged and mods and not bad
              and not rep["skipped"]
              and len(mods) + len(projects.placed_free_parts(sdoc)) == want,
              "untagged=%r bad=%r skipped=%r" % (untagged, bad, rep.get("skipped")))
        App.closeDocument(sdoc.Name)


try:
    run()
except Exception:                                      # noqa: BLE001
    traceback.print_exc()
    FAILS.append("crash")
print("R300_TESTS=%d %s" % (len(FAILS), ",".join(FAILS)))
