"""R810/R811 under freecadcmd, offscreen Qt: the exploded view's card and
modes, Simulate (plan, run, URDF) and the assembly video button, on a real
FreeCAD document. Run by test_view_tools_r810; prints one line
VIEW_TOOLS_RESULT={"ok", "checks": {name: bool}, "errors": [...]}.
R810_SABOTAGE=<name> breaks one thing so its checks must fail.
"""
import json
import math
import os
import sys
import tempfile
import traceback
import xml.etree.ElementTree as ET

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.environ["R810_ADDON"])

import FreeCAD as App                                  # noqa: E402
import Mesh                                            # noqa: E402
import Part                                            # noqa: E402
from PySide6 import QtCore, QtWidgets                  # noqa: E402

from acadagent import export_tools as et              # noqa: E402
from acadagent import simulate as sm                  # noqa: E402

APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
SAB = os.environ.get("R810_SABOTAGE", "")
checks, errors = {}, []


def check(name, cond):
    checks[name] = bool(cond)


def pump(n=5):
    for _ in range(n):
        APP.processEvents()


# no module library here: faces come from the slide axis / the middle
sm._face_dir = lambda o, words: None
if SAB == "no_coaxial":
    _plan = sm.plan

    def _no_grow(doc):
        p = _plan(doc)
        for m in p["motors"]:
            m["drives"] = m["drives"][:1]
        return p
    sm.plan = _no_grow
if SAB == "same_signs":
    sm.drive_signs = lambda rotors: [1] * len(rotors)
if SAB == "explode_cables":
    et.stays_put = lambda o: getattr(o, "AtechRole", None) == "board"

doc = App.newDocument("R810")
App.setActiveDocument(doc.Name)


def props(o, **kw):
    for k, v in kw.items():
        typ = {str: "App::PropertyString", float: "App::PropertyFloat",
               list: "App::PropertyIntegerList"}.get(type(v), "App::PropertyVector")
        o.addProperty(typ, k, "Atech", "")
        setattr(o, k, v)
    return o


def mesh_box(name, lo, size, **kw):
    m = Mesh.createBox(*size)
    m.translate(lo[0] + size[0] / 2.0, lo[1] + size[1] / 2.0, lo[2] + size[2] / 2.0)
    o = doc.addObject("Mesh::Feature", name)
    o.Mesh = m
    return props(o, **kw)


def part(name, shape):
    o = doc.addObject("Part::Feature", name)
    o.Shape = shape
    return o


V = App.Vector
board = props(part("motherboard", Part.makeBox(60, 40, 2, V(0, 0, 10))), AtechRole="board")
button = mesh_box("button_p2", (5, 5, 12), (10, 10, 6), AtechRole="module",
                  AtechModule="button", AtechJoint="prismatic", AtechPorts=[2],
                  AtechSlideAxis=V(0, 0, -1), AtechSlideOut=5.0)
# a dc_motor on a cable: its shaft (-slide axis) points -X, its end at x=-10
motor = mesh_box("dc_motor_5", (-10, 15, 20), (20, 10, 10), AtechRole="module",
                 AtechModule="dc_motor", AtechJoint="cable", AtechPorts=[5],
                 AtechSlideAxis=V(1, 0, 0), AtechSlideOut=0.0)
cable = props(part("dc_motor_5_cable_p5", Part.makeBox(30, 2, 1, V(5, 19, 13))),
              AtechCableModule="dc_motor_5")
light = mesh_box("light_6", (40, 30, 30), (10, 10, 4), AtechRole="module",
                 AtechModule="light", AtechJoint="cable", AtechPorts=[6],
                 AtechSlideAxis=V(0, 0, -1))
tof = mesh_box("distance_sensor_8", (25, -12, 20), (10, 4, 8), AtechRole="module",
               AtechModule="distance_sensor", AtechJoint="cable", AtechPorts=[8],
               AtechSlideAxis=V(0, 1, 0))
# printed parts: the body, a lid, a wheel on the shaft and its tyre
body = part("Body", Part.makeBox(80, 60, 30, V(-5, -15, 5)).cut(
    Part.makeBox(76, 56, 30, V(-3, -13, 7))))
lid = part("Lid", Part.makeBox(80, 60, 3, V(-5, -15, 36)))
ax = V(-1, 0, 0)
wheel = part("Wheel", Part.makeCylinder(12, 6, V(-10, 20, 25), ax))
tyre = part("Tyre", Part.makeCylinder(16, 6, V(-10, 20, 25), ax).cut(
    Part.makeCylinder(12, 6, V(-10, 20, 25), ax)))
doc.recompute()
NAMES = [o.Name for o in doc.Objects]


def placements():
    return {o.Name: o.Placement.copy() for o in doc.Objects}


def same(a, b):
    return all(a[n].isSame(b[n], 1e-9) for n in a)


BASE = placements()

try:
    # ------------------------------------------------ R810 exploded view
    et.set_explode(doc, 1.0, mode="out")
    after = placements()
    stay = [n for n in ("motherboard", "dc_motor_5", "dc_motor_5_cable_p5", "light_6")]
    check("explode_electronics_stay", all(after[n].isSame(BASE[n], 1e-9) for n in stay))
    d = after["button_p2"].Base - BASE["button_p2"].Base
    check("explode_module_slides_out_of_its_port",
          abs(d.x) < 1e-9 and abs(d.y) < 1e-9 and d.z > 5.0)
    check("explode_parts_move", not after["Lid"].isSame(BASE["Lid"], 1e-9))
    check("explode_mode_out", et.explode_mode(doc) == "out")
    et.set_explode(doc, 1.0, mode="layers")
    lay = placements()
    dz = {n: lay[n].Base - BASE[n].Base for n in ("Body", "Wheel", "Lid")}
    check("layers_only_z", all(abs(v.x) < 1e-9 and abs(v.y) < 1e-9 for v in dz.values()))
    check("layers_in_order", dz["Lid"].z > dz["Wheel"].z >= dz["Body"].z
          or dz["Lid"].z > dz["Body"].z)
    check("layers_mode", et.explode_mode(doc) == "layers")
    order = [o.Name for o in et.explode_parts(doc)]
    check("step_order_parts_then_modules", order[-1] == "button_p2" and "Lid" in order
          and "motherboard" not in order and "dc_motor_5" not in order)
    check("describe_module", "out of its port" in et.describe_part(button)
          and "port 2" in et.describe_part(button))
    et.set_explode(doc, 0.0)
    check("explode_put_back", same(BASE, placements()))
    et.set_explode(doc, 0.0, mode="out")

    # the card, offscreen
    from acadagent import explode_card
    host = QtWidgets.QWidget()
    host.resize(1200, 800)
    host.show()
    picked, fits = [], []
    card = explode_card.ExplodeCard(host, lambda: doc,
                                    select_fn=lambda dd, o: picked.append(o and o.Name),
                                    fit_fn=lambda: fits.append(1))
    et.set_explode(doc, 0.6)                      # E / the view bar / the menu
    pump()
    check("card_opens_when_apart", getattr(card, "is_open", False) and card.isVisible())
    check("card_top_right", card.geometry().right() > 900 and card.geometry().top() == 16)
    check("card_fits_view", len(fits) >= 1)
    check("card_slider_shows_amount", card.slider.value() == 60)
    card.go(1)
    check("card_step_selects", picked and picked[-1] == et.explode_parts(doc)[0].Name)
    check("card_step_names", card.part_name.text().startswith("1 of %d" % len(et.explode_parts(doc))))
    card.go(-1)
    check("card_step_wraps", card.part_name.text().startswith("%d of" % len(et.explode_parts(doc))))
    card.chips["layers"].click()
    check("card_mode_layers", et.explode_mode(doc) == "layers")
    card.slider.setValue(100)
    check("card_slider_drives", abs(et.explode_amount(doc) - 1.0) < 1e-9)
    card.btn_back.click()
    pump()
    check("card_put_back", et.explode_amount(doc) == 0.0 and same(BASE, placements()))
    check("card_closed", not card.isVisible())
    et.set_explode(doc, 0.5)
    pump()
    et.toggle_explode(doc)                        # E again
    pump()
    check("card_closes_on_e", not card.isVisible() and same(BASE, placements()))

    # ------------------------------------------------ R811 simulate
    p = sm.plan(doc)
    mot = [m for m in p["motors"] if m["name"] == "dc_motor_5"]
    check("plan_finds_motor", len(mot) == 1)
    drives = set(mot[0]["drives"]) if mot else set()
    check("plan_motor_drives_wheel_and_tyre", drives == {"Wheel", "Tyre"})
    check("plan_body_not_driven", "Body" not in drives and "Lid" not in drives)
    check("plan_axis", mot and abs(mot[0]["axis"][0] + 1.0) < 1e-9)
    check("plan_light", [x["name"] for x in p["lights"]] == ["light_6"])
    check("plan_sensor", [x["name"] for x in p["sensors"]] == ["distance_sensor_8"])
    check("summary", sm.summary(p)[0] == "1 motor turns 2 parts")
    sim = sm.Simulation(doc, p)
    c0 = doc.getObject("Wheel").Shape.BoundBox.Center
    sim.rpm = 60.0
    sim.step(0.125)                               # 45 degrees
    moved = {n for n, pl in placements().items() if not pl.isSame(BASE[n], 1e-9)}
    check("sim_turns_only_driven", moved == {"Wheel", "Tyre"})
    rot = doc.getObject("Wheel").Placement.Rotation
    check("sim_turns_about_shaft", abs(abs(rot.Angle) - 0.785398) < 1e-3
          and abs(abs(rot.Axis.x) - 1.0) < 1e-6)
    c1 = doc.getObject("Wheel").Shape.BoundBox.Center
    check("sim_wheel_stays_on_axle", (c1 - c0).Length < 0.5)
    et.restore_exploded(doc)                      # a build / save puts it back
    check("sim_put_back_by_save", same(BASE, placements()) and sm.running(doc) is None)
    sm.Simulation(doc, p).step(0.1)
    et.set_explode(doc, 0.5)
    et.set_explode(doc, 0.0)
    check("sim_put_back_by_explode", same(BASE, placements()) and sm.running(doc) is None)

    # the glows and the beam, in a bare scene graph (no 3D view here)
    from pivy import coin

    class FakeView(object):
        def __init__(self):
            self.sg = coin.SoSeparator()

        def getSceneGraph(self):                      # noqa: N802
            return self.sg
    fv = FakeView()
    deco = sm._Decorations(p, view=fv)
    check("deco_in_scene", fv.sg.getNumChildren() == 1
          and deco.root.getNumChildren() == len(p["lights"]) + len(p["sensors"]))
    deco.pulse(0.3)
    check("deco_pulses", any(0.0 <= m.transparency.getValues()[0] <= 0.95
                             for m, _b, _k in deco.mats))
    deco.remove()
    check("deco_removed", fv.sg.getNumChildren() == 0)

    out = tempfile.mkdtemp(prefix="r811-")
    r = sm.export_urdf(doc, out, p)
    root = ET.parse(r["urdf"]).getroot()
    joints = root.findall("joint")
    check("urdf_one_continuous_joint", len(joints) == 1
          and joints[0].get("type") == "continuous")
    axis = [float(x) for x in joints[0].find("axis").get("xyz").split()] if joints else []
    check("urdf_axis", axis and abs(axis[0] + 1.0) < 1e-6)
    names = [e.get("name") for e in root.iter() if e.tag in ("visual", "collision")]
    check("urdf_unique_geom_names", len(names) == len(set(names)) and names)
    files = [e.get("filename") for e in root.iter("mesh")]
    check("urdf_meshes_exist", files and all(os.path.getsize(os.path.join(out, f)) > 84
                                             for f in files))
    import struct
    counts = []
    for f in set(files):
        with open(os.path.join(out, f), "rb") as fh:
            fh.read(80)
            n = struct.unpack("<I", fh.read(4))[0]
            counts.append(n * 50 + 84 == os.path.getsize(os.path.join(out, f)))
    check("urdf_binary_stl_valid", all(counts))
    masses = [float(m.get("value")) for m in root.iter("mass")]
    check("urdf_masses", len(masses) == 2 and all(m > 0 for m in masses))
    check("urdf_readme", os.path.exists(os.path.join(out, "README.md")))
    check("urdf_leaves_doc", same(BASE, placements()))

    # R813: the MuJoCo scene beside it runs: a floor, a free base, a speed
    # servo per shaft started by the "drive" keyframe
    mj = ET.parse(r["mjcf"]).getroot()
    check("mjcf_floor_and_free_base", mj.find("worldbody/geom[@type='plane']") is not None
          and mj.find("worldbody/body/freejoint") is not None)
    hinges = mj.findall(".//joint[@type='hinge']")
    acts = mj.findall("actuator/velocity")
    check("mjcf_servo_per_shaft", len(hinges) == 1 and len(acts) == 1
          and acts[0].get("joint") == hinges[0].get("name"))
    key = mj.find("keyframe/key[@name='drive']")
    check("mjcf_drive_key", key is not None and abs(abs(float(key.get("ctrl")))
                                                    - sm.DRIVE_RPM * math.pi / 30) < 1e-3)
    mfiles = [m.get("file") for m in mj.iter("mesh")]
    check("mjcf_meshes_exist", mfiles and all(os.path.exists(os.path.join(out, "meshes", f))
                                              for f in mfiles))
    lift = float(mj.find("worldbody/body").get("pos").split()[2])
    check("mjcf_rests_on_floor", abs(lift - (0.002 - 0.005)) < 1e-6)   # Body from z=5 mm
    signs = sm.drive_signs([{"axis": (0, 1, 0)}, {"axis": (0, -1, 0)},
                            {"axis": (0, 0.99, 0.1)}])
    check("mjcf_car_sides_drive_together", signs == [1, -1, 1])
    with open(r["run"]) as fh:
        compile(fh.read(), r["run"], "exec")
    check("run_sim_script", "mj_resetDataKeyframe" in open(r["run"]).read())
    mdir = os.environ.get("ATELIER_MUJOCO_DIR")
    if mdir and sm.mujoco_available():
        import subprocess
        pr = subprocess.run(sm.run_command(r["run"], check=1.5), capture_output=True,
                            text=True, timeout=300)
        ln = [x for x in pr.stdout.splitlines() if x.startswith("SIM_CHECK")]
        spins = eval(ln[0].split("shafts_rad_s=")[1].split(" ")[0]) if ln else []
        check("physics_shaft_turns", ln and "ok=True" in ln[0] and spins
              and abs(spins[0] - sm.DRIVE_RPM * math.pi / 30) < 2.0)

    # the card, offscreen, no 3D decorations
    scard = sm.SimulationCard(host, lambda: doc, gui=False)
    scard.open_card()
    pump()
    check("simcard_plays", scard.timer.isActive() and scard.sim is not None)
    check("simcard_says_what", "1 motor turns 2 parts" in scard.what.text())
    scard._last = None
    scard._tick()
    check("simcard_tick_turns", not placements()["Wheel"].isSame(BASE["Wheel"], 1e-9))
    scard.speed.setValue(120)
    check("simcard_speed", scard.sim.rpm == 120.0 and scard.rpm.text() == "120 rpm")
    res = scard.export(tempfile.mkdtemp(prefix="r811c-"))
    check("simcard_export", res and os.path.exists(res["urdf"]) and scard.timer.isActive())
    # Run physics: exports to the default folder, asks before installing
    # MuJoCo, opens it when there
    launched = []
    phys = tempfile.mkdtemp(prefix="r813-")
    real = sm.mujoco_available, sm.default_folder
    sm.default_folder = lambda d: os.path.join(phys, "design")
    try:
        sm.mujoco_available = lambda python=None: False
        asked = []
        res = scard.run_physics(confirm=lambda: asked.append(1) or False,
                                launch=launched.append)
        check("physics_asks_before_install", asked == [1] and res is None
              and launched == [] and "Not installed" in scard.status.text())
        sm.mujoco_available = lambda python=None: True
        res = scard.run_physics(confirm=lambda: 1 / 0, launch=launched.append)
        check("physics_launches", res and launched == [res["run"]]
              and os.path.exists(os.path.join(phys, "design", "scene.xml"))
              and "MuJoCo is opening" in scard.status.text())
        check("physics_stops_animation", not scard.timer.isActive()
              and same(BASE, placements()))
    finally:
        sm.mujoco_available, sm.default_folder = real
    check("physics_button", scard.btn_physics.isEnabled()
          and scard.btn_physics.text() == "Run physics")
    scard.play()
    scard.close_card()
    pump()
    check("simcard_close_puts_back", same(BASE, placements()) and not scard.timer.isActive())

    # ------------------------------------------------ R810 video button
    calls = []

    class FakePanel(object):
        def make_video(self, d):
            calls.append(d.Name)
            return object()
    vb = et.video_button(None, lambda: doc, panel_fn=lambda: FakePanel())
    vb.click()
    check("video_button_makes_video", calls == [doc.Name])
    check("video_button_look", vb.objectName() == "VBtn"
          and vb.property("atech_icon") in et.ICONS)
    none = et.video_button(None, lambda: None, panel_fn=lambda: FakePanel())
    none.click()
    check("video_button_no_doc", calls == [doc.Name])
    acts = [a.text() for a in et.menu_actions(None, lambda: doc)]
    check("menu_has_simulate_and_video", "Simulate" in acts and "Make assembly video" in acts)
    # ------------------------------------------------ R812 Edit shapes
    from acadagent import manual_edit, shape_edit as se
    doc2 = App.newDocument("R812")
    App.setActiveDocument(doc2.Name)
    doc2.UndoMode = 1
    base = doc2.addObject("Part::Box", "Base")
    base.Length, base.Width, base.Height = 40, 40, 10
    cube = doc2.addObject("Part::Box", "Cube")
    cube.Length = cube.Width = cube.Height = 10
    cube.Placement.Base = V(10, 10, 30)
    far = doc2.addObject("Part::Box", "Far")
    far.Placement.Base = V(200, 0, 25)
    doc2.recompute()
    check("drop_height_onto_part", abs(se.drop_height(cube, [base, far]) - 10.0) < 1e-6)
    check("drop_height_floor", abs(se.drop_height(far, [base, cube]) - 0.0) < 1e-6)
    se.drop(cube)
    check("drop_lands_on_base", abs(se.position(cube)[2] - 10.0) < 1e-6)
    manual_edit._selection = lambda: [doc2.getObject("Cube")]
    manual_edit._doc = lambda: doc2
    ed = manual_edit.ShapeEditor(None)
    ed.show()
    pump()
    check("editor_has_drop_undo_redo", all(hasattr(ed, n) for n in
                                           ("btn_drop", "btn_undo", "btn_redo", "turn_step")))
    ed.turn_step.setCurrentIndex(manual_edit.TURN_STEPS.index(45.0))
    ed.turn_buttons[0].click()
    ang = math.degrees(doc2.getObject("Cube").Placement.Rotation.Angle)
    check("editor_turns_by_step", abs(ang - 45.0) < 1e-6)
    check("editor_undo_enabled", ed.btn_undo.isEnabled())
    ed.history(False)                     # FreeCADGui absent: doc.undo()
    pump()
    ang = math.degrees(doc2.getObject("Cube").Placement.Rotation.Angle)
    check("editor_undo_undoes", abs(ang) < 1e-6)
    ed.history(True)
    pump()
    check("editor_redo_redoes", abs(math.degrees(
        doc2.getObject("Cube").Placement.Rotation.Angle) - 45.0) < 1e-6)
    cube2 = doc2.getObject("Cube")
    cube2.Placement.Base = V(cube2.Placement.Base.x, cube2.Placement.Base.y, 50)
    doc2.recompute()
    ed.load()
    ed.btn_drop.click()
    check("editor_drop_button", abs(se.position(cube2)[2] - 10.0) < 0.5)
    ed.close()
except Exception:                                           # noqa: BLE001
    errors.append(traceback.format_exc())

print("VIEW_TOOLS_RESULT=" + json.dumps({"ok": not errors and all(checks.values()),
                                          "checks": checks, "errors": errors}))
