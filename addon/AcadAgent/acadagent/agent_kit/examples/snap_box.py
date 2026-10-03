# Example: a box with a snap-fit lid. Both parts are built ASSEMBLED (the lid
# seated on the box), then ONE call adds matched hooks on the lid and catch
# windows through the box walls - never positioned by hand.
import atech_cad as cad

X, Y, Z = 80.0, 60.0, 40.0     # outside size, lid on
WALL, R = 2.0, 3.0             # wall thickness, vertical corner radius
LID_T = 3.0                    # lid plate
CLEAR = 0.2                    # lip-to-wall clearance per side (FDM)

box = cad.rounded_box(X, Y, Z - LID_T, R)
box = cad.shell(box, WALL, cad.faces_at(box, "+Z"))       # open top

lid = cad.rounded_box(X, Y, LID_T, R, at=(0, 0, Z - LID_T))
LIP, LIP_H = 1.6, 4.0          # lip wall and depth into the box
o = WALL + CLEAR               # the lip's outside, inset from the box's
lip = cad.rounded_box(X - 2 * o, Y - 2 * o, LIP_H + 0.5, 1.0,
                      at=(o, o, Z - LID_T - LIP_H))
lip = cad.cut(lip, cad.rounded_box(X - 2 * (o + LIP), Y - 2 * (o + LIP), LIP_H + 2, 0.5,
                                   at=(o + LIP, o + LIP, Z - LID_T - LIP_H - 1)))
lid = cad.fuse_one(lid, lip)                              # a ring lip, not a plug

box, lid = cad.snap_fit_pair(box, lid, count=4)           # hooks + windows

doc.addObject("Part::Feature", "Box").Shape = box
doc.addObject("Part::Feature", "Lid").Shape = lid
