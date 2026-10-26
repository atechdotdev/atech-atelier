"""R510-R517 under freecadcmd: mixing Atech hardware and CAD end to end.
Run by test_mixing_r500.py (never by hand against a real profile: it
expects a scratch HOME and ATECH_R500_DIR):

    HOME=<scratch> ATECH_R500_DIR=<scratch> ATECH_ARTIFACTS=<repo>/models \
        QT_QPA_PLATFORM=offscreen freecadcmd fc_mixing_r500.py

  R510  CAD + electronics: the board shown first (panel._show_board_first),
        then an example applied through build.apply (sandbox): one board, in
        the example's orientation, modules seated / cabled, the CAD around
        the board, one undo back to the board alone
  R511  modules the user placed on the Modules page, then an agent build:
        they stay the user's, the case fits around them (atech_layout)
  R512  cabled modules: "Connected by cable" + length (brief, page); move,
        Remake cable, ap.check passes; the remade cable stays the build's
  R513  save and reopen a mixed project (projects_store): tags, cables,
        colours, chat, id, the Modules page's ports
  R514  Only CAD: no board, no Atech prompt section unless asked for
  R515  Measure fit, Export for print (Atech out by default, in on request),
        BOM with ports and cable lengths
  R516  many documents opened, changed and closed through the shell /
        projects_store / Modules page / board_look observers
  R517  the Modules page judges slide paths with the design's fitted_after

Prints "CHECK <id> PASS|FAIL|SKIP <detail>" and ends with R500_TESTS=<n>.
ATECH_R500_SABOTAGE breaks one fix first; ATECH_R500_ONLY=f1,f3 runs some
flows only.
"""
import ast
import inspect
import json
import os
import shutil
import sys
import tempfile
import textwrap
import time
import traceback
import types

HERE = os.path.dirname(os.path.abspath(__file__))
ADDON = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(ADDON))
for p in (ADDON, os.path.join(REPO, "projects")):
    if p not in sys.path:
        sys.path.insert(0, p)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["ATECH_HARDWARE_MODE"] = "electronics"

TMP = os.environ["ATECH_R500_DIR"]
EXAMPLES = os.path.join(ADDON, "acadagent", "agent_kit", "examples")

import FreeCAD as App  # noqa: E402
from PySide6 import QtWidgets  # noqa: E402

APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

from acadagent import build, export_tools, measure, projects  # noqa: E402
from acadagent import projects_store as ps  # noqa: E402
from acadagent import modules_page as mp  # noqa: E402
from acadagent import panel, shell  # noqa: E402

projects._mod()
import atech_ports as ap  # noqa: E402

# Nothing of the user's profile: trust store, sessions, projects in TMP.
build._trust_path = lambda: os.path.join(TMP, "trusted_builds.json")
ps.STATE_PATH = os.path.join(TMP, "projects.json")
ps.SESSIONS_PATH = os.path.join(TMP, "agent", "sessions.json")
os.makedirs(os.path.dirname(ps.SESSIONS_PATH), exist_ok=True)
FOLDER = os.path.join(TMP, "Atech Projects")
os.makedirs(FOLDER, exist_ok=True)
os.environ["ATECH_PROJECTS_DIR"] = FOLDER

SAB = os.environ.get("ATECH_R500_SABOTAGE", "")
ONLY = set(filter(None, os.environ.get("ATECH_R500_ONLY", "").split(",")))
FAILS = []


def check(cid, ok, detail=""):
    print("\nCHECK %s %s %s" % (cid, "PASS" if ok else "FAIL", str(detail)[:400]))
    sys.stdout.flush()
    if not ok:
        FAILS.append(cid)


def skip(cid, why):
    print("\nCHECK %s SKIP %s" % (cid, why))


def _replaced(func, old, new):
    src = textwrap.dedent(inspect.getsource(func))
    assert old in src, (func.__name__, old)
    ns = {}
    exec(compile(src.replace(old, new), "<sabotage>", "exec"), func.__globals__, ns)  # noqa: S102
    return ns[func.__name__]


# ------------------------------------------------------------ sabotage
if SAB == "boardfirst":
    panel.AgentPanel._show_board_first = lambda self, doc: None
elif SAB == "fitted":
    mp.fitted_after = lambda doc: []
elif SAB == "owner":
    mp.keep_cable_owners = lambda *a, **k: 0
elif SAB == "cable_parts":
    measure.product_parts = _replaced(
        measure.product_parts, 'getattr(o, "AtechCableModule", None)', "False")
elif SAB == "observer":
    def _old_activate(self, doc):
        self._ping()
        from PySide6 import QtCore
        QtCore.QTimer.singleShot(0, lambda d=doc: shell._note_opened(d))
    shell._DocObserver.slotActivateDocument = _old_activate
elif SAB == "tick":
    shell.closing_documents = lambda: False


def pump(page=None, timeout=5.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        APP.processEvents()
        if page is None or page._anim is None:
            break
        time.sleep(0.01)
    APP.processEvents()


def new_page():
    page = mp.ModulesPage()
    page.resize(380, 1400)
    page._load()
    return page


def literal(src, name):
    for node in ast.parse(src).body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == name
                                                for t in node.targets):
            return ast.literal_eval(node.value)
    return None


def workspace(script_path, intent=None):
    ws = tempfile.mkdtemp(prefix="chat-r500-", dir=os.path.join(TMP, "agent"))
    shutil.copy(script_path, os.path.join(ws, build.SCRIPT))
    with open(script_path, encoding="utf-8") as fh:
        src = fh.read()
    intent = intent if intent is not None else literal(src, "INTENT")
    if intent is not None:
        with open(os.path.join(ws, "intent.json"), "w", encoding="utf-8") as fh:
            json.dump(intent, fh)
    return ws, intent or {}


def remember(doc, ws):
    """What the panel's _remember stores: the chat's workspace by project id."""
    data = ps.load_sessions()
    data[ps.doc_key(doc)] = {"ws": ws, "v": 2}
    ps.write_sessions(data)


def boards(doc):
    return [o for o in doc.Objects if getattr(o, "AtechRole", "") == "board"]


def mods_of(doc):
    return {o.Name: o for o in ap.occupied(doc).values()}


def bad_of(res):
    return {k: ap.first_why(v) for k, v in res.items() if ap.first_why(v)}


def fresh(name):
    doc = App.newDocument(name)
    doc.UndoMode = 1                    # as in the app (freecadcmd starts it off)
    App.setActiveDocument(doc.Name)
    return doc


CASE_AROUND = '''# R511: a case built AROUND the user's own board and modules: it seats
# nothing. It lifts the board so the case rests on the desk; the user's
# modules follow the board (ap.reseat_all re-seats them on their own ports).
import Part
import atech_ports as ap
import atech_cad as cad
from FreeCAD import Vector

W, C = 2.0, 1.0
board = ap.board_object(doc)
mods = sorted({o.Name: o for o in ap.occupied(doc).values()}.values(),
              key=lambda o: o.Name)
low = cad.bound_of(board, *mods).ZMin
pl = board.Placement
pl.Base = pl.Base + Vector(0, 0, W + C - low)
board.Placement = pl
ap.reseat_all(doc)
bb = cad.bound_of(board, *mods)
case = cad.rounded_box(bb.XLength + 2 * (W + C), bb.YLength + 2 * (W + C),
                       bb.ZLength + 2 * (W + C), 0,
                       at=(bb.XMin - W - C, bb.YMin - W - C, bb.ZMin - W - C))
case = cad.shell(case, W, cad.faces_at(case, "+X") + cad.faces_at(case, "-X"))
y_wall = bb.YMax + C
windows = []
for m in mods:
    mb = ap.bbox(m)
    windows.append(Part.makeBox(mb.XLength - 4, W + 1, mb.ZLength - 4,
                                Vector(mb.XMin + 2, y_wall - 0.5, mb.ZMin + 2)))
case = cad.cut(case, windows)
pb = cad.bound_of(board)
floor = bb.ZMin - C
rails = [Part.makeBox(pb.XLength - 4, 1.2, pb.ZMin + 2 - floor + 0.5,
                      Vector(pb.XMin + 2, y, floor - 0.5))
         for y in (pb.YMin - 0.1 - 1.2, pb.YMax + 0.1)]
for m in mods:
    mb = ap.bbox(m)
    keep_out = Part.makeBox(mb.XLength + 1, mb.YLength + 1, mb.ZLength + 1,
                            Vector(mb.XMin - 0.5, mb.YMin - 0.5, mb.ZMin - 0.5))
    for i in (0, 1):
        if keep_out.common(rails[i]).Volume > 0:
            rails[i] = cad.cut(rails[i], keep_out)
case = cad.fuse_one(case, *rails)
doc.addObject("Part::Feature", "Case").Shape = case
cb = case.BoundBox
L, G, T = 2.0, 0.15, 0.8
for name, x, d in (("End_Cap_L", cb.XMin - W, 1), ("End_Cap_R", cb.XMax, -1)):
    plate = cad.rounded_box(W, cb.YLength, cb.ZLength, 0, at=(x, cb.YMin, cb.ZMin))
    x0 = cb.XMin - 0.5 if d > 0 else cb.XMax - L
    iy, iz = cb.YLength - 2 * (W + G), cb.ZLength - 2 * (W + G)
    lip = cad.cut(Part.makeBox(L + 0.5, iy, iz, Vector(x0, cb.YMin + W + G, cb.ZMin + W + G)),
                  Part.makeBox(L + 2, iy - 2 * T, iz - 2 * T,
                               Vector(x0 - 0.75, cb.YMin + W + G + T, cb.ZMin + W + G + T)))
    doc.addObject("Part::Feature", name).Shape = cad.fuse_one(plate, lip)

INTENT = {"board": "upright", "fitted_after": ["End_Cap_L", "End_Cap_R"]}
'''

FAN = os.path.join(EXAMPLES, "desk_fan.py")
FAN_BOARD = App.Placement(App.Vector(0, 0, 8.5), App.Rotation(App.Vector(1, 0, 0), 90))
STATE = {}


# ======================================================== R510 board first
def flow1():
    doc = fresh("R510")
    board = panel.AgentPanel._show_board_first(None, doc)
    check("f1.board_first", board is not None and len(boards(doc)) == 1
          and list(doc.UndoNames[:1]) == ["Atech board"],
          "board=%r undo=%r" % (board, list(doc.UndoNames)))
    if not boards(doc):
        return None
    again = panel.AgentPanel._show_board_first(None, doc)
    check("f1.board_once", again is None and len(boards(doc)) == 1)
    ws, intent = workspace(FAN)
    remember(doc, ws)
    r = build.apply(ws, [build.SCRIPT], None)
    check("f1.build_ok", r is not None and r.ok and r.mode == build.SANDBOX,
          (r.error if r else "no result")[:300])
    if r is None or not r.ok:
        return None
    check("f1.no_failures", not build.failures(r), build.failures(r))
    bs = boards(doc)
    check("f1.one_board", len(bs) == 1 and bs[0].Name == board.Name,
          [o.Name for o in bs])
    check("f1.example_orientation", bs[0].Placement.isSame(FAN_BOARD, 1e-6),
          bs[0].Placement)
    occ = ap.occupied(doc)
    joints = {n: getattr(o, "AtechJoint", "") for n, o in occ.items()}
    check("f1.modules_on_ports", sorted(occ) == [1, 6, 7, 14]
          and joints[7] == "cable" and joints[6] != "cable", joints)
    fa = intent.get("fitted_after") or []
    res = ap.check(doc, fitted_after=fa)
    check("f1.modules_pass", res and not bad_of(res), bad_of(res))
    foot = App.BoundBox()
    for lab in ("Base", "Foot_Shell"):
        foot.add(doc.getObjectsByLabel(lab)[0].Shape.BoundBox)
    check("f1.cad_encloses_board", foot.isInside(ap.bbox(bs[0])),
          "%s vs %s" % (foot, ap.bbox(bs[0])))
    check("f1.two_steps", list(doc.UndoNames[:2]) == ["Agent build", "Atech board"],
          list(doc.UndoNames))
    doc.undo()
    doc.recompute()
    left = [(o.Name, getattr(o, "AtechRole", "")) for o in doc.Objects]
    check("f1.undo_board_only", left == [(board.Name, "board")]
          and boards(doc)[0].Placement.isSame(App.Placement(), 1e-9), left)
    doc.redo()
    doc.recompute()
    check("f1.redo", len(ap.occupied(doc)) == 4 and len(boards(doc)) == 1)
    STATE.update(fan=doc, fan_ws=ws, fan_fa=fa, fan_rec=r.record())
    return doc


# ================================================= R511 user modules first
def kit_lets_board_move():
    """R511 needs two kit/build changes owned elsewhere (see the report):
    check.py lets the user's modules follow a moved board, build.py's replay
    re-seats them. True once both are in."""
    try:
        with open(os.path.join(ADDON, "acadagent", "agent_kit", "check.py"),
                  encoding="utf-8") as fh:
            kit = fh.read()
    except OSError:
        return False
    return "_follow_board" in kit and hasattr(build, "_follow_board")


def flow2():
    page = new_page()
    doc = fresh("R511")
    for n, m in ((3, "button"), (9, "screen"), (13, "light")):
        page.pick(n)
        page._add(m)
        pump(page)
    mine = mods_of(doc)
    check("f2.user_added", len(mine) == 3 and not page.err.isVisibleTo(page),
          sorted(mine))
    b = ap.board_object(doc, create=False)
    rel = {n: b.Placement.inverse().multiply(o.Placement) for n, o in mine.items()}
    before = {n: (o.Label, o.AtechModule, list(o.AtechPorts)) for n, o in mine.items()}
    path = os.path.join(TMP, "case_around.py")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(CASE_AROUND)
    ws, intent = workspace(path)
    r = build.apply(ws, [build.SCRIPT], None)
    after = {n: (o.Label, o.AtechModule, list(o.AtechPorts)) for n, o in mods_of(doc).items()}
    check("f2.user_modules_kept", after == before
          and not any(getattr(o, "AtechAgentBuilt", False) for o in mods_of(doc).values()),
          after)
    check("f2.one_board", len(boards(doc)) == 1)
    if not kit_lets_board_move():
        skip("f2.case_fits", "needs the R511 kit change (check.py _follow_board, "
             "build._follow_board): the build is refused: %s" % ((r.error or "")[:160]
                                                                 if r else ""))
        check("f2.refusal_names_board", r is not None and not r.ok
              and "does not own" in (r.error or ""), (r.error if r else "")[:200])
        return
    check("f2.build_ok", r is not None and r.ok, (r.error if r else "")[:300])
    if r is None or not r.ok:
        return
    check("f2.layout_passes", not r.layout_problems and not build.failures(r),
          (r.layout_problems, build.failures(r)))
    b = ap.board_object(doc, create=False)
    followed = all(b.Placement.inverse().multiply(o.Placement).isSame(rel[n], 1e-6)
                   for n, o in mods_of(doc).items())
    check("f2.modules_follow_board", followed
          and not any(ap.stale_modules(doc)[k] for k in ("seated", "cabled")),
          ap.stale_modules(doc))
    res = ap.check(doc, fitted_after=intent.get("fitted_after"))
    check("f2.modules_pass", not bad_of(res), bad_of(res))
    remember(doc, ws)
    page.refresh()
    page._check_all()
    av = page.all_verdicts.text()
    check("f2.page_check_all", "Slides in freely" in av and "in the way" not in av, av[:300])


# ======================================================= R512/R517 cables
def flow3(doc):
    br = build.document_brief(doc)
    line = [ln for ln in br.splitlines() if "dc_motor_7:" in ln]
    check("f3.brief_cable", line and "cabled to port 7" in line[0]
          and "mm long" in line[0], line)
    page = new_page()
    page.pick(7)
    sub = page.port_sub.text()
    check("f3.page_connected", "Connected by cable" in sub and " mm" in sub, sub)
    row = [b.text() for b in page._on_rows if "by cable" in b.text()]
    check("f3.page_row", len(row) == 1 and "DC Motor" in row[0], row)
    # R517: a seated module of the closed product is judged like the build did
    page.pick(6)
    vt = page.verdicts.text()
    check("f3.page_fitted", "Slides in freely" in vt and "in the way" not in vt, vt[:300])
    check("f3.page_fitted_note", "Slide paths checked before" in vt, vt[-200:])
    page._check_all()
    av = page.all_verdicts.text()
    check("f3.check_all_fitted", "in the way" not in av, av[:300])
    # move the cabled motor, then Remake cable
    m = doc.getObject("dc_motor_7")
    old_len = round(ap.cables_of(doc, m)[0].AtechCableLength, 1)
    pl = App.Placement(m.Placement)
    pl.Base = pl.Base + App.Vector(0, 0.2, 0)
    m.Placement = pl
    page.pick(7)
    check("f3.stale_offered", page.btn_recable.isVisibleTo(page))
    page._remake_cable()
    cs = ap.cables_of(doc, m)
    res = ap.check(doc, only=[m.Name], fitted_after=STATE["fan_fa"])[m.Name]
    check("f3.remade_pass", len(cs) == 1 and not ap.first_why(res)
          and not page.btn_recable.isVisibleTo(page), ap.first_why(res))
    check("f3.remade_length", cs and abs(cs[0].AtechCableLength - old_len) > 0.05
          and ("%d mm" % round(cs[0].AtechCableLength)) in page.port_sub.text(),
          (old_len, cs and cs[0].AtechCableLength, page.port_sub.text()))
    check("f3.cable_owned", cs and getattr(cs[0], "AtechAgentBuilt", False)
          and cs[0].Label == "dc_motor_7_cable_p7", cs and cs[0].Label)
    # the next build replaces it: one cable, fresh
    r = build.apply(STATE["fan_ws"], [build.SCRIPT], STATE["fan_rec"])
    m = doc.getObject("dc_motor_7")
    cs = ap.cables_of(doc, m) if m is not None else []
    allc = [o.Name for o in doc.Objects if getattr(o, "AtechCableModule", None)]
    check("f3.rebuild_one_cable", r is not None and r.ok and len(cs) == 1 and len(allc) == 1
          and not ap.stale_modules(doc)["cabled"], (allc, r and r.error[:200]))
    if r is not None and r.ok:
        STATE["fan_rec"] = r.record()


# ====================================================== R513 save/reopen
def flow4():
    doc = ps.create_project("Mixed R513")
    doc.UndoMode = 1
    App.setActiveDocument(doc.Name)
    path = doc.FileName
    panel.AgentPanel._show_board_first(None, doc)
    ws, _intent = workspace(FAN)
    r = build.apply(ws, [build.SCRIPT], None)
    check("f4.build_ok", r is not None and r.ok, (r.error if r else "")[:300])
    if r is None or not r.ok:
        return
    base = doc.getObjectsByLabel("Base")[0]
    export_tools.record_override(doc, base, color=(0.9, 0.1, 0.1), transparency=20)
    chats = {ps.doc_id(doc): {"transcript": {"entries": [
        {"kind": "bubble", "text": "a small desk fan", "role": "user"}],
        "last_text": "a small desk fan"}, "ws": ws}}
    ps.set_chat_provider(lambda d: chats.get(ps.doc_id(d)))
    page = new_page()
    page.refresh()
    ports_before = sorted(ap.occupied(doc))
    rows_before = [b.text() for b in page._on_rows]

    def snap(d):
        out = {}
        for o in d.Objects:
            if getattr(o, "AtechRole", None) or getattr(o, "AtechCableModule", None):
                out[o.Name] = tuple(str(getattr(o, p, None)) for p in (
                    "AtechRole", "AtechModule", "AtechPorts", "AtechJoint",
                    "AtechCableModule", "AtechCablePort", "AtechCableLength",
                    "AtechAgentBuilt", "Placement"))
        return out
    tags, pid = snap(doc), ps.doc_id(doc)
    doc.save()
    App.closeDocument(doc.Name)
    pump()
    d = App.openDocument(path)
    App.setActiveDocument(d.Name)
    pump()
    check("f4.tags_survive", snap(d) == tags and len(tags) >= 6,
          set(tags) ^ set(snap(d)))
    check("f4.cables_fresh", not ap.stale_modules(d)["cabled"]
          and not ap.stale_modules(d)["seated"], ap.stale_modules(d))
    ov = export_tools.overrides(d).get("Base") or {}
    check("f4.colour_survives", ov.get("color") and abs(ov["color"][0] - 0.9) < 1e-6
          and ov.get("transparency") == 20, ov)
    chat = ps.read_doc_chat(d)
    check("f4.chat_in_file", chat is not None and [e.get("text") for e in
          chat["transcript"]["entries"]] == ["a small desk fan"]
          and "intent.json" in (chat.get("files") or {}), chat and sorted(chat["files"]))
    check("f4.project_id", ps.doc_id(d) == pid and ps.file_id(path) == pid,
          (ps.doc_id(d), pid))
    page.refresh()
    check("f4.page_same_ports", sorted(ap.occupied(d)) == ports_before
          and [b.text() for b in page._on_rows] == rows_before,
          ([b.text() for b in page._on_rows], rows_before))
    # R517 after a reopen with no chat record (the script / the file's intent.json)
    data = ps.load_sessions()
    data.pop(ps.doc_key(d), None)
    ps.write_sessions(data)
    check("f4.fitted_after_reopen", "Foot_Shell" in mp.fitted_after(d), mp.fitted_after(d))
    ps.set_chat_provider(None)
    App.closeDocument(d.Name)


# ======================================================== R514 Only CAD
def flow5():
    os.environ["ATECH_HARDWARE_MODE"] = "cad_only"
    try:
        doc = fresh("R514")
        got = panel.AgentPanel._show_board_first(None, doc)
        check("f5.no_board_first", got is None and not boards(doc))
        # doc= as the panel passes it (_turn_args): the turn's own document
        plain = build.system_prompt("/nonexistent/ws", request="a phone stand", doc=doc)
        asked = build.system_prompt("/nonexistent/ws", doc=doc,
                                    request="a phone stand with an Atech button module")
        # the full section only when asked; a plain request keeps the two-line
        # pointer ("only if the user asks", build._atech_pointer, S27/S34)
        full = "ATECH MODULES AND BOARDS (this is the complete reference)"
        check("f5.prompt_plain", full not in plain and "ap.seat(doc" not in plain,
              "active=%s full=%s seat=%s" % (getattr(App.ActiveDocument, "Name", None),
                                             full in plain, "ap.seat(doc" in plain))
        check("f5.prompt_when_named", full in asked or "ap.seat(doc" in asked)
        path = os.path.join(TMP, "stand.py")
        with open(path, "w") as fh:
            fh.write("import Part\ndoc.addObject('Part::Feature', 'Stand').Shape = "
                     "Part.makeBox(60, 40, 5)\n")
        ws, _ = workspace(path, intent={})
        r = build.apply(ws, [build.SCRIPT], None)
        check("f5.plain_build", r is not None and r.ok and not boards(doc)
              and not ap.occupied(doc), (r.error if r else "")[:200])
        App.closeDocument(doc.Name)
    finally:
        os.environ["ATECH_HARDWARE_MODE"] = "electronics"


# ================================================ R515 measure / export
def flow6(doc):
    App.setActiveDocument(doc.Name)
    parts = measure.product_parts(doc)
    check("f6.fit_no_cable", parts and not any(getattr(o, "AtechCableModule", None)
                                               for o in parts),
          [o.Label for o in parts if getattr(o, "AtechCableModule", None)])
    res = measure.measure("fit", [], doc)
    labels = {r.get("label") for r in res.get("margins") or []}
    want = {"motherboard", "button_p6", "light_p14", "usbc_p1", "dc_motor_7"}
    check("f6.fit_rows", want <= labels, sorted(labels))
    words = measure.describe(res)
    check("f6.fit_described", bool(words), str(words)[:200])
    out = os.path.join(TMP, "export")
    rep = export_tools.export_for_print(doc, os.path.join(out, "fan"), fmt="3MF")
    hw = {o.Label for o in doc.Objects if export_tools.is_hardware(o)}
    check("f6.export_excludes_atech", hw and hw <= set(rep["left_out"])
          and not (hw & set(rep["parts"])), (sorted(hw), rep["left_out"]))
    rep2 = export_tools.export_for_print(doc, os.path.join(out, "fan_all"), fmt="3MF",
                                         include_atech=True)
    check("f6.export_includes_on_request", hw <= set(rep2["parts"])
          and not rep2["left_out"], (rep2["left_out"], sorted(hw - set(rep2["parts"]))))
    names = [o.get("name") for o in export_tools.read_3mf(rep2["files"][0])]
    check("f6.3mf_has_hardware", "motherboard" in names and "dc_motor_7" in names,
          names[:8])
    names = [o.get("name") for o in export_tools.read_3mf(rep["files"][0])]
    check("f6.3mf_default_no_hardware", names and "motherboard" not in names, names[:8])
    b = export_tools.bom(doc)
    hwr = b["hardware"]
    kinds = [r["kind"] for r in hwr]
    mods = {r["label"]: r["ports"] for r in hwr if r["kind"] == "Module"}
    cab = [r for r in hwr if r["kind"] == "Cable"]
    m = doc.getObject("dc_motor_7")
    clen = round(ap.cables_of(doc, m)[0].AtechCableLength, 1)
    check("f6.bom_hardware", kinds.count("Board") == 1 and mods == {
        "usbc_p1": "1", "button_p6": "6", "dc_motor_7": "7", "light_p14": "14"}, hwr)
    check("f6.bom_cable", len(cab) == 1 and cab[0]["ports"] == "7"
          and cab[0]["length_mm"] == clen and "DC Motor" in cab[0]["name"], cab)
    csv = export_tools.bom_csv(b)
    check("f6.bom_csv", "Cable to DC Motor" in csv and "%.1f" % clen in csv
          and "Atech board" in csv, csv[-300:])
    check("f6.bom_printed_no_hw", not any(r["part"].startswith(("dc_motor", "motherboard"))
                                          for r in b["printed"]),
          [r["part"] for r in b["printed"]][:10])


# =================================================== R516 close-all
def flow7():
    page = new_page()
    calls = {"live": 0, "dead": 0, "two_side": 0}
    real_base = export_tools.ensure_base

    def ensure_base(d):
        try:
            alive = d.Name in App.listDocuments()
        except Exception:                              # noqa: BLE001
            alive = False
        calls["live" if alive else "dead"] += 1
        return real_base(d)
    export_tools.ensure_base = ensure_base
    from acadagent import viewport
    real_two = viewport.two_side_meshes

    def two_side(d):
        calls["two_side"] += 1
        return real_two(d)
    viewport.two_side_meshes = two_side
    real_noted = shell._note_opened

    def noted(d):
        # a closed document's object handed to a deferred call is the hazard
        if d is not None:
            try:
                alive = d.Name in App.listDocuments()
            except Exception:                          # noqa: BLE001
                alive = False
            calls["live" if alive else "dead"] += 1
        return real_noted(d)
    shell._note_opened = noted
    events = []
    obs = shell._DocObserver(lambda: events.append(1))
    App.addDocumentObserver(obs)
    look = None
    try:
        from acadagent import board_look
        look = board_look._Observer()
        App.addDocumentObserver(look)
    except Exception:                                  # noqa: BLE001
        look = None
    ps.install_observer()
    errors = []
    try:
        for rnd in range(3):
            names = []
            for i in range(8):
                d = App.newDocument("R516_%d_%d" % (rnd, i))
                names.append(d.Name)
                App.setActiveDocument(d.Name)
                box = d.addObject("Part::Box", "Box")
                d.recompute()
                if i % 2 == 0:
                    ap.seat(d, "button", 3)
                box.Length = 20 + i
                d.recompute()
            pump(page)
            # activate each, then close them all before any event runs (Close
            # All: each close activates the next document)
            for n in names:
                App.setActiveDocument(n)
            for n in names:
                App.closeDocument(n)
                if rnd == 1:
                    pump(page)          # ... and with events in between
            closing = shell.closing_documents()
            shell._light_atech_meshes()
            if rnd == 0:
                check("f7.tick_quiet", closing and calls["two_side"] == 0,
                      (closing, calls["two_side"]))
            pump(page)
            page.refresh()
            if page._current() is not None and page._current().Name in names:
                errors.append("page shows a closed document")
    except Exception:                                  # noqa: BLE001
        errors.append(traceback.format_exc())
    finally:
        App.removeDocumentObserver(obs)
        if look is not None:
            App.removeDocumentObserver(look)
        export_tools.ensure_base = real_base
        viewport.two_side_meshes = real_two
        shell._note_opened = real_noted
    check("f7.no_errors", not errors, errors[:2])
    check("f7.no_dead_doc", calls["dead"] == 0 and calls["live"] >= 1, calls)
    check("f7.observer_events", len(events) >= 24, len(events))
    check("f7.all_closed", not [n for n in App.listDocuments() if n.startswith("R516_")])
    # board_look no longer shares Coin scenes across views (each view owns
    # its own), so the quit-time pin is gone: nothing shared to keep alive
    check("f7.no_shared_scenes", not hasattr(shell, "_pin_shared_scenes"))


def want(flow):
    return not ONLY or flow in ONLY


def run():
    fan = None
    if want("f1") or want("f3") or want("f6"):
        fan = flow1()
    if want("f2"):
        flow2()
    if fan is not None and want("f6"):
        flow6(fan)              # before f3 rebuilds it
    if fan is not None and want("f3"):
        flow3(fan)
    if want("f4"):
        flow4()
    if want("f5"):
        flow5()
    if want("f7"):
        flow7()


try:
    run()
except Exception:                                      # noqa: BLE001
    traceback.print_exc()
    FAILS.append("crash")
print("\nR500_TESTS=%d %s" % (len(FAILS), ",".join(FAILS)))
sys.stdout.flush()
