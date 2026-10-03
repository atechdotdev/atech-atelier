# Example: a revolved knob (lathe profile) with a D-shaft bore and grip flutes.
import atech_cad as cad
import Part

# Profile as (radius, z) points, in order around the outline. x >= 0.
profile = [(0, 0), (15, 0), (15, 12), (12, 16), (0, 16)]
knob = cad.revolve(profile)

# 6 mm shaft bore, 12 mm deep, drilled from the bottom face upward.
knob = cad.hole(knob, at=(0, 0, 0), axis="+Z", d=6.0, depth=12.0)
# D-flat: a block that fills the bore from x = 1.5 outward (6 mm D-shaft).
flat = Part.makeBox(1.6, 6.0, 12.0, App.Vector(1.5, -3.0, 0))
knob = cad.fuse_one(knob, flat.common(Part.makeCylinder(3.2, 12.0)))

# 12 grip flutes cut round the rim: one cutter, polar-patterned about Z.
flute = Part.makeCylinder(1.5, 20.0, App.Vector(15.8, 0, -1))
knob = cad.cut(knob, cad.polar_pattern(flute, 12))

knob = cad.fillet_safe(knob, 1.0, lambda e: e.BoundBox.ZMin > 15.9)

doc.addObject("Part::Feature", "Knob").Shape = knob
