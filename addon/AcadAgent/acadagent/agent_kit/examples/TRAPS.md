# FreeCAD traps - check these before you finish

1. A fuse of parts with a gap, or touching only at an edge or corner, gives
   2 solids and isValid() is still True. Use `cad.fuse_one(...)`; overlap
   joints by >= 0.5 mm.
2. `Shape.BoundBox` is a loose bound on curved parts. Measure with
   `cad.measure(shape)` (optimalBoundingBox) or read check.py's output.
3. Holes: `at` is the centre ON the entry face, `axis` points INTO the
   material. `cad.hole()` raises when a hole removes nothing (wrong axis).
4. `makeBox(x,y,z,p)` puts its CORNER at p; `makeCylinder(r,h,p,dir)` puts its
   AXIS at p. Mixing them cuts features into empty space.
5. Never fillet every edge. Pick edges (`cad.edges_parallel`, a lambda) and
   use `body = cad.fillet_safe(body, r, edges)`: it returns a SHAPE (never a
   tuple) - on failure the original, unchanged, with the reason printed.
6. A hollow part must actually be hollow: `cad.shell(...)` checks the volume
   dropped. A box with walls is not a solid block.
7. Never model a tangent fit (bearing in seat, pin in hole): leave >= 0.1 mm.
8. No FreeCADGui / ViewObject in model.py unless you must (colours): it does
   not exist headless.
9. Run `./check` in the workspace, then Read check.png and look at it before
   you say you are done. CHECK FAIL or a WARNING line -> fix first.
10. Separate bodies must not intersect unless you list them in
    INTENDED_OVERLAPS = [("Peg", "Plate")]. A tiny stray solid beside a body
    (a fuse that did not join) is a failure too.
11. Do not assert solid counts or collisions in model.py: Atelier and ./check
    measure them.
12. Many cutters (vents, slots, holes): ONE call `cad.cut(body, list_of_tools)`.
    Never `fuse_one` cutters first - disjoint tools are not one body.
13. Gears: `cad.spur_gear(m, z, thickness, bore=...)` gives real involute
    teeth (examples/gear.py). Do not hand-draw teeth.
14. `.extrude(Vector)` is for a FACE (`Part.Face(Part.makePolygon(pts))`),
    never a solid: a box or a cut result is already 3D.
15. `cad.rounded_box(x, y, z, r)`: r must be under half the smaller side
    across the rounded edges (an 8 mm side takes r < 4; r = exactly 4 gives
    full round ends - an obround slot). A plate standing on its edge is
    rounded on its big face with edges='x' / 'y' (the 4 edges along its
    thickness), not the default 'vertical'. `cad.shell` needs t < half the
    part's smallest size.
16. Parts that must join (fins on a tube, a boss on a wall) OVERLAP by
    >= 0.5 mm: a fin starting exactly on the tube's radius touches along a
    face and the fuse comes out invalid.
17. A cutter that stops just short of a face or clips a corner leaves a
    stray sliver solid: make it pass fully through (or stay >= 0.5 mm clear).
18. Model an assembly ASSEMBLED: a lid sits ON its box
    (`lid = cad.place_on(lid, box)`), never parked above or beside it.
    intent.json size_mm is the assembled product: print
    `cad.measure(Part.makeCompound(parts))["size"]` and compare before ./check.
19. `cad.shell` on a `rounded_box` opened on a side that meets a rounded
    edge: FreeCAD's makeThickness returns the solid UNCHANGED. cad.shell then
    cuts an offset core instead; if it still raises, cut the cavity yourself
    (a smaller box through the openings).
20. Atech case: close it. Build the end caps / lid in their CLOSED position
    and list their labels in intent.json `"fitted_after": [...]`: the slide
    path check ignores them, every overlap still counts. Never park caps
    away from the case to pass the check.
21. Margins: ./check prints MARGIN lines (each module's measured margin to
    the part around it, per side). Quote those numbers - never an estimate
    like "6 mm all round".
22. A USB-C module's socket faces the board EDGE its port is on (the side
    the module slid in from), not +Y: the plug opening goes in the wall or
    lid in front of the socket mouth. ./check's OPEN line names the mouth's
    direction; a slot over the module's cover lets no plug in.
23. A pot, cup, planter or tray is OPEN on top: its rim is a RING
    (cylinder minus the bore), never a solid disc. ./check prints CONTAINER.
24. Channels open along their length (a cable clip's push-in slots) are not
    holes: declare them in intent.json as "slots": {"count": n, "d_mm": d}.
    Rectangular notches (a toothbrush holder's slots) are
    "slots": {"count": n, "w_mm": w} (w = the notch width; "depth_mm"
    optional) - never d_mm. Never close a slot with collars to make a hole
    count come out.
25. A hole in ONE wall of a hollow part (a light-pipe hole in a case's front
    wall): `cad.hole(case, at, "-Y", d, through="wall")` - it stops at the
    first wall. `through=True` drills everything on the axis, the back wall
    too; ./check warns about a hole that crosses more than one wall.
26. intent.json records what the user's message states: its sizes, counts
    and named features. A hole count or a size you add yourself is not a
    target the build must meet - ./check reports its miss as a NOTE.
27. `Part.makeWedge` takes 10 bare numbers in an order that is easy to get
    wrong. Use `cad.wedge(x, y, z, top_x=..., top_y=..., at=..., top_at=...)`
    (a ramp, fin or frustum, sizes by name). Never write code you know is
    wrong as a placeholder: every write of model.py is a live preview.
28. A holder, cradle or clip must leave the held object a way in (an open
    end or top, or a mouth at least as wide as the object). Declare it in
    intent.json: "holds": {"size_mm": [x, y, z], "enters": "+Z"}; ./check
    pushes its box in and prints HOLDS with the measured mouth.
29. A lid's lip is a RING (outer box minus inner box), never a solid plug
    filling the opening. ./check notes a lid that fills its box.
30. Quote wall thicknesses from ./check's WALL "side walls" line: a sloped
    wall offset sideways is not the offset thick across its slope.
31. Snap fits on a lid/case pair: build both ASSEMBLED, then ONE call
    `case, lid = cad.snap_fit_pair(case, lid, count=4)` places matched hooks
    on the lid and catch windows through the walls (every face measured,
    the lip cut back round each hook). Never place hooks and windows by
    hand from separate numbers.
32. A hinged or turning part (lid, flap, door, lever) must clear the body
    over its whole swing: its axis ON or OUTSIDE the face it swings past,
    never inside the wall. Declare it in intent.json:
    "motion": [{"part": "Lid", "axis": [[x, y, z], [dx, dy, dz]],
    "range_deg": [0, 90]}] (right-hand rule about the direction); ./check
    sweeps it and fails at the first angle where it hits another part.
33. A clip's round channel holds a cable only when it wraps >= 240 deg:
    its entry slot is NARROWER than the channel (at most 0.8 x d). ./check
    prints each channel's wrap as a CHANNEL line; a slot as wide as the
    bore is an open trough (180 deg) that holds nothing.
34. A pin hinge (a lid, flap or door on a pin): build box and lid ASSEMBLED,
    then ONE call `box, lid, motion = cad.pin_hinge(box, lid, knuckles=3)`
    puts alternating knuckles and one pin bore on the pair, the axis ON the
    back face's top edge, sweeps the lid clear before it returns, and gives
    the intent.json "motion" entry: put it there as `"motion": [motion]`.
    Never place knuckles and bores by hand. With 3+ knuckles ./check warns
    that the pin bore goes through 2 walls: that is the pin bore, meant.
35. A plug opening (USB-C) in a case wall or end lid: ONE call
    `lid = cad.socket_opening(lid, usb)` (usb = the seated module) cuts it in
    front of the socket mouth - direction and size measured from the
    module. Never work out socket coordinates by hand.
