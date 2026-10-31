"""import_sesame - the Sesame robot's printed parts, servos and battery, as
BREP files for the "Sesame with Atech" example (agent_kit/examples/sesame_atech.py).

Runs INSIDE freecadcmd:

    STEP=<Sesame-ESP32-v122.step> OUT=<repo>/addon/AcadAgent/acadagent/agent_kit/third_party/sesame \
        <freecadcmd> projects/import_sesame.py

Source: hardware/cad/Sesame-ESP32-v122.step of github.com/seunyboyxu/New_Spyder
at commit 3f76b5f37ac9f9efd3953e50b4beee86e6e88acf (sha256 of the file:
b6ae8936df90d85d4d6f6b24ea53bd387bd0508da2090fdbc535227d5feb9be0), a fork of
Dorian Todd's Sesame Robot (github.com/dorianborian/sesame-robot). Apache-2.0.

What it does to them (NOTICE.md says the same):
  * moves the assembly from its Y-up frame to Atelier's: Z up, the robot
    facing -Y, the body centred on X and Y, the lowest point on z = 0;
  * fuses each servo's pieces (case, horn, gears seen from outside) into one
    solid, so a servo is one part;
  * writes one <name>.brep.gz per part (gzip: a BREP is text) and parts.json (each part's box, volume
    and the source label), nothing else. The geometry is not changed.
"""
import gzip
import hashlib
import json
import os
import re

import FreeCAD as App
import Import
import Part

STEP_SHA256 = "b6ae8936df90d85d4d6f6b24ea53bd387bd0508da2090fdbc535227d5feb9be0"
# Y-up (Sesame) -> Z-up (Atelier): new x = old z, new y = old x, new z = old y,
# then centred on the frame; main() lifts it so the lowest point (measured
# exactly, not the loose BoundBox) is on the desk.
TO_ATELIER = App.Placement(App.Matrix(0, 0, 1, -2.38,
                                      1, 0, 0, -26.02,
                                      0, 1, 0, 32.36,
                                      0, 0, 0, 1))
# our name: the label in the STEP (a Part::Feature, or an App::Part whose
# pieces are fused). FL = front left (robot's own left is +X, front is -Y).
PARTS = {
    "frame": "Internal-Frame",
    "bottom_cover": "Bottom-Cover",
    "top_cover": "COMPOUND002",                 # the original, for reference
    "battery": "14500 7.4V 800mAh Li-ion Battery-PC003 v2",
    "femur_L1": "femur-joint-L1", "femur_L2": "femur-joint-L2",
    "femur_R1": "femur-joint-R1",
    "femur_R2": "femurjoint-R2",
    "foot_L3": "foot-joint-L3", "foot_L4": "foot-joint-L4",
    "foot_R3": "foot-joint-R3", "foot_R4": "foot-joint-R4",
    "servo_hip_FL": "SG90 - Micro Servo 9g - Tower Pro v4",
    "servo_hip_FR": "SG90 - Micro Servo 9g - Tower Pro v001",
    "servo_hip_RR": "SG90 - Micro Servo 9g - Tower Pro v002",
    "servo_hip_RL": "SG90 - Micro Servo 9g - Tower Pro v003",
    "servo_knee_RR": "SG90 - Micro Servo 9g - Tower Pro v004",
    "servo_knee_RL": "SG90 - Micro Servo 9g - Tower Pro v005",
    # the two front knee servos are mirrored copies whose STEP labels
    # FreeCAD rewrites on import: found by "(Mirror)" and their side (+X left)
    "servo_knee_FL": ("(Mirror)", +1),
    "servo_knee_FR": ("(Mirror)", -1),
}


def say(msg):
    os.write(1, (msg + "\n").encode())


def pieces(o):
    if o.TypeId == "Part::Feature":
        return [o] if o.Shape.Solids else []
    out = []
    for k in getattr(o, "Group", []):
        out += pieces(k)
    return out


def world(o):
    s = o.Shape.copy()
    s.Placement = TO_ATELIER.multiply(o.getGlobalPlacement())
    return s


#: servo pieces smaller than this (mm^3) are left out: the two case screws'
#: heads, the label film and the cable stubs. They add hundreds of faces to
#: a servo and nothing a fit check needs.
SERVO_MIN_PIECE = 100.0


def one_solid(shapes):
    solids = [so for s in shapes for so in s.Solids if so.Volume >= SERVO_MIN_PIECE]
    if len(solids) == 1:
        return solids[0]
    big = max(solids, key=lambda s: s.Volume)
    rest = [s for s in solids if s is not big]
    fused = big.fuse(rest)
    if len(fused.Solids) != 1:
        # pieces that only touch: glue them with a fuzzy fuse
        fused = big.fuse(rest, 0.01)
    if len(fused.Solids) != 1:
        raise SystemExit("could not make one solid of %d pieces" % len(solids))
    try:                        # merge coplanar faces; OCC refuses on some
        refined = fused.removeSplitter()
        if len(refined.Solids) == 1 and refined.isValid():
            fused = refined
    except Exception:           # noqa: BLE001 - keep the plain fuse
        pass
    return fused.Solids[0]


def main():
    step, out = os.environ["STEP"], os.environ["OUT"]
    with open(step, "rb") as fh:
        got = hashlib.sha256(fh.read()).hexdigest()
    if got != STEP_SHA256:
        raise SystemExit("STEP sha256 %s is not the pinned %s" % (got, STEP_SHA256))
    doc = App.newDocument("Sesame")
    Import.insert(step, doc.Name)
    root = [o for o in doc.Objects if not o.InList][0]
    by_label = {k.Label: k for k in root.Group}
    info, shapes_out = {}, {}
    for name, label in PARTS.items():
        if isinstance(label, tuple):
            word, side = label
            cands = [k for k in root.Group if word in k.Label and k.TypeId == "App::Part"]
            src = [k for k in cands
                   if side * Part.makeCompound([world(p) for p in pieces(k)]).BoundBox.Center.x > 0]
            if len(src) != 1:
                raise SystemExit("%s: %d candidates" % (name, len(src)))
            src, label = src[0], src[0].Label
        else:
            src = by_label[label]
        shapes = [world(p) for p in pieces(src)]
        shape = one_solid(shapes) if name.startswith("servo") else (
            shapes[0] if len(shapes) == 1 else Part.makeCompound(shapes))
        shapes_out[name] = (shape, label)
    # the lowest point (exact, not the loose BoundBox) on the desk
    lift = -min(sh.optimalBoundingBox(True, False).ZMin for sh, _l in shapes_out.values())
    for name, (shape, label) in shapes_out.items():
        shape.translate(App.Vector(0, 0, lift))
        b = shape.BoundBox
        info[name] = {"label": re.sub(r"[^\x20-\x7e]", "", label), "solids": len(shape.Solids), "valid": shape.isValid(),
                      "volume_mm3": round(shape.Volume, 1), "faces": len(shape.Faces),
                      "box": [round(v, 2) for v in (b.XMin, b.YMin, b.ZMin, b.XMax, b.YMax, b.ZMax)]}
        with gzip.open(os.path.join(out, name + ".brep.gz"), "wt", encoding="utf-8") as fh:
            fh.write(shape.exportBrepToString())
        say("%-14s %s" % (name, json.dumps(info[name])))
    say("lift %.4f" % lift)
    with open(os.path.join(out, "parts.json"), "w") as fh:
        json.dump({"source": "github.com/seunyboyxu/New_Spyder@3f76b5f3 "
                             "hardware/cad/Sesame-ESP32-v122.step",
                   "step_sha256": STEP_SHA256, "lift_mm": round(lift, 4), "parts": info},
                  fh, indent=1, sort_keys=True)
        fh.write("\n")


main()
os._exit(0)
