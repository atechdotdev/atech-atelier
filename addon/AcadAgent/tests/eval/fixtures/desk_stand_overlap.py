# FIXTURE (release PRD S15): the logged "desk stand" model.py that Studio
# accepted as "2 built" (dogfood, speed plan S01). MEASURED by the speed-plan
# prototype check: Clock_Enclosure overlaps Desk_Stand by 20,046 mm3 and
# reaches z = -30 mm, below the desk. Kept verbatim below this header so the
# eval's no_overlap / not_below_desk fitness checks are proven to FAIL it
# (test_eval_harness.py). Do not "fix" this file.
import math
import Part
from FreeCAD import Vector, Placement, Rotation

# ---------------------------------------------------------------- parameters
# Clock enclosure, rebuilt to the existing 107.4 x 26.0 x 147.9 envelope
CW, CT, CH = 107.4, 26.0, 147.9
CR = 6.0                    # rounded vertical edges

# Desk stand
LEAN = 15.0                 # lean-back angle (deg)
CLEAR = 0.4                 # slot clearance per side
SLOT_DEPTH = 22.0           # how far the clock sinks into the stand
WALL = 7.0                  # slot wall thickness
BASE_W = CW + 24.0
BASE_D = 96.0
BASE_H = 20.0               # slab thickness under the slot floor
NOTCH_W = 26.0              # cable notch width
NOTCH_H = 14.0              # cable notch height above the slot floor


def rounded_slab(w, d, h, r, origin=None):
    """Slab of w x d x h with its four vertical edges rounded by r."""
    box = Part.makeBox(w, d, h)
    verticals = [e for e in box.Edges
                 if abs(e.Vertexes[0].Point.z - e.Vertexes[-1].Point.z) > h * 0.5]
    slab = box.makeFillet(r, verticals)
    if origin is not None:
        slab.Placement = Placement(origin, Rotation())
    return slab


# ---------------------------------------------------------------- the clock
clock = rounded_slab(CW, CT, CH, CR)
clock = clock.cut(Part.makeBox(CW - 20.0, 2.5, CH - 36.0, Vector(10.0, -0.01, 24.0)))
clock.translate(Vector(-CW / 2.0, -CT / 2.0, 0))       # centre on X/Y, base at Z=0

clock_obj = doc.addObject("Part::Feature", "Clock_Enclosure")
clock_obj.Shape = clock

# ------------------------------------------------------------ the desk stand
# Frame: X centred, Y runs front(0) -> back(BASE_D), Z up from the desk.
tilt = Rotation(Vector(1, 0, 0), -LEAN)                # lean the top backwards (+Y)
slot_origin = Vector(0, BASE_D / 2.0 - 6.0, BASE_H - SLOT_DEPTH)
seat = Placement(slot_origin, tilt)                    # slot frame -> stand frame

slot_w, slot_t = CW + 2 * CLEAR, CT + 2 * CLEAR
rib_w, rib_t = slot_w + 2 * WALL, slot_t + 2 * WALL

base = rounded_slab(BASE_W, BASE_D, BASE_H, 8.0, Vector(-BASE_W / 2.0, 0, 0))

rib = rounded_slab(rib_w, rib_t, SLOT_DEPTH + 10.0, CR + CLEAR + WALL,
                   Vector(-rib_w / 2.0, -rib_t / 2.0, 0))
rib.Placement = seat.multiply(rib.Placement)

pocket = rounded_slab(slot_w, slot_t, SLOT_DEPTH + 60.0, CR + CLEAR,
                      Vector(-slot_w / 2.0, -slot_t / 2.0, 0))
pocket.Placement = seat.multiply(pocket.Placement)

stand = base.fuse(rib)

# flatten anything the tilted rib pushed below the desk
stand = stand.common(Part.makeBox(BASE_W + 40, BASE_D + 40, 400,
                                  Vector(-(BASE_W + 40) / 2.0, -20, 0)))
stand = stand.cut(pocket)

# cable notch: through the back wall, starting at the slot floor
notch = Part.makeBox(NOTCH_W, 80.0, NOTCH_H, Vector(-NOTCH_W / 2.0, 0, 0))
notch.Placement = seat.multiply(
    Placement(Vector(0, 0, SLOT_DEPTH - NOTCH_H), Rotation()))
stand = stand.cut(notch)

stand = stand.removeSplitter()
if len(stand.Solids) != 1:
    raise RuntimeError("stand made %d solids" % len(stand.Solids))

stand_obj = doc.addObject("Part::Feature", "Desk_Stand")
stand_obj.Shape = stand

# seat the clock: tilted 15 deg back, dropped SLOT_DEPTH into the slot
clock_obj.Placement = seat.multiply(
    Placement(Vector(0, 0, -SLOT_DEPTH), Rotation()))
