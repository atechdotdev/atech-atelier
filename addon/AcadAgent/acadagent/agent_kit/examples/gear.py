# Example: a spur gear with real involute teeth, a bore and a hub.
# cad.spur_gear wraps FreeCAD's bundled fcgear generator and checks the
# result (one valid solid, tip diameter m*(z+2)). Axis +Z, centred on 0,0.
import atech_cad as cad
import Part
from FreeCAD import Vector

M, Z, T = 1.5, 24, 8.0          # module, teeth, face width
BORE, HUB_D, HUB_H = 8.0, 16.0, 5.0
BACKLASH = 0.2                  # taken off the tooth thickness (FDM)

gear = cad.spur_gear(M, Z, T, backlash=BACKLASH)
hub = Part.makeCylinder(HUB_D / 2, HUB_H + 0.5, Vector(0, 0, T - 0.5))
gear = cad.fuse_one(gear, hub)                      # 0.5 mm overlap joins them
gear = cad.hole(gear, at=(0, 0, 0), axis="+Z", d=BORE, through=True)

doc.addObject("Part::Feature", "Gear").Shape = gear
