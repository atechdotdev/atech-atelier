# Example: a 60 x 40 x 25 mm box with a lid on a pin hinge.
# Build the pair ASSEMBLED (the lid seated on the box), then ONE call puts
# alternating knuckles on both and one pin bore through them, with the axis
# ON the back face's top edge, and returns the intent.json "motion" entry.
import Part
import atech_cad as cad

L, W, H = 60.0, 40.0, 25.0     # box outside, mm
T = 2.0                        # wall and lid thickness
PIN = 1.75                     # the pin: a length of 1.75 mm filament

box = cad.rounded_box(L, W, H, 3.0)
box = cad.shell(box, T, cad.faces_at(box, "+Z"))          # open on top
lid = cad.place_on(cad.rounded_box(L, W, T, 3.0), box)    # seated, closed
# 2 knuckles: one on each part, so each bore crosses one knuckle. With 3 or
# more, the box's knuckles share one bore and ./check prints a WARNING that
# the hole goes through 2 walls - that is the pin bore, and it is meant.
box, lid, motion = cad.pin_hinge(box, lid, knuckles=2, pin_d=PIN,
                                 clearance=0.2, axis="+Y")
doc.addObject("Part::Feature", "Box").Shape = box
doc.addObject("Part::Feature", "Lid").Shape = lid
# Put the returned entry in intent.json so ./check sweeps the lid open:
#   "motion": [{"part": "Lid", "axis": [[30, 40, 25], [-1, 0, 0]],
#               "range_deg": [0, 90]}]
print("MOTION_ENTRY", motion)
