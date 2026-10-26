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

## Details (atech_detail)

D1. Round edges with `body = cad.soften(body, r)`, never `makeFillet` on
    every edge. Order matters more than radius: soften the outer body FIRST,
    then cut arches, windows and holes, then soften only what the cuts made:
    `body = cad.soften(cut, 1, cad.new_edges(cut, body))`. soften always
    returns a valid shape and prints "N/M edges rounded"; edges it could not
    round stay sharp, and the reason is in `cad.last_reason()`.
D2. Vents and speaker holes: `cad.grille(...)` and `cad.speaker_grille(...)`
    with `center` ON the surface and `normal` pointing OUT of it. Each hole
    is measured, so it follows a curved shell and stops at the first wall.
    Never build hexes as one compound extruded once (MEASURED: 61 s and an
    invalid shape).
D3. Panel lines: `cad.groove_ring(body, "Z", z)` for a belt or split line,
    `cad.groove_outline(body, pts, view="+Y")` for a door or hatch. Keep
    depth <= wall - 0.5; both raise when the groove would break through.
    Both work on spline shells and split halves, and prove the groove at
    probe points: on a big spline body a Volume difference is noise.
D4. Wheels: `w = cad.wheel(d, width, tread="block", axis="+Y", at=...)`
    gives three bodies that do not overlap: w["tyre"], w["rim"], w["cap"].
    A block-tread wheel takes about 2 s: build ONE and place copies
    (`s = w["tyre"].copy(); s.translate(...)`), never four calls.
D5. Lettering: `cad.text(body, "ATECH", at, normal, 6)` embosses (or
    `mode="deboss"`) on a flat or curved face as one solid. `at` is ON the
    surface and `normal` points toward the reader. Keep size >= 3 mm.
D6. Colours: write each one as a direct assignment in model.py, e.g.
    `obj.ViewObject.ShapeColor = cad.color("rubber")` and, for glass,
    smoked plastic or LEDs, `obj.ViewObject.Transparency = cad.transparency("glass")`.
    ./check records these with their values. A helper cannot colour a body
    for you, and a loop of setattr calls is not recorded.
D7. Screws: `lid, case = cad.screw_through(lid, case, at)` cuts the
    countersink and adds the boss from ONE point on the lid, and prints the
    matching `cad.screw("csk_phillips", ...)` call. Add the screw as its own
    body; its shank is 0.1 mm undersize, so it overlaps nothing. Gussets
    reach at most max(2, 2 d) mm out (`rib_len=`); `ribs=0` gives a plain
    column next to a speaker or the other half's wall. Do the screw
    fixings BEFORE grilles and lettering: every boolean on a shell with
    600 faces costs about 1 s.
D8. Buttons, LEDs and lenses: build the part first (`cad.button_cap`,
    `cad.lens`), then `case = cad.opening_for(case, part)`. The opening is
    measured from the part plus clearance. With no axis= it looks out along
    a module's measured working face, or the axis the cap / lens was built
    along; a moved copy needs axis=. It cuts ONE wall: a cut that would run
    along a wall or reach a second one raises, and so does a part that
    still meets the wall.
D9. Grip: `cad.knurl(knob, "Z", center, r, z0, z1, kind="diamond")`. r
    must be the knob's real radius (it is measured). Never use helical
    sweeps: MEASURED 2.7 s and 7 solids.

## Bodies (atech_form)

B1. A sculpted body (car, mouse, robot head, speaker) is TWO outlines:
    `body = cad.profile_body(side, plan, fillet=4)`. side is (x, z) points
    (length, height), plan is (x, y) points (length, width), both over the
    SAME x range. Plain points are smooth spline knots; end the side with
    `("corner", p), ("line", p), ("line", p)` for a flat bottom on z = 0. A
    NOTE line means the spline swings past your knots: add knots there.
B2. Fillet in profile_body, BEFORE any cut. `fillet=(r, 0)` keeps the bottom
    edges sharp. A fillet that does not fit is stepped down and printed.
B3. Hollow a curved body with its own core, never cad.shell (it fails on
    every curved body): `shell = cad.hollow(body, 2, core=lambda t:
    cad.profile_body(side, plan, fillet=4, inset=t))`. Same outlines, same
    fillet. It prints the rung that worked and the MEASURED min wall. A
    core fillet (fillet - t) under 0.5 mm, or one that fails, stays sharp:
    never re-knot the outlines by hand.
B4. Case and lid from one body: hollow it CLOSED, then `chassis, top =
    cad.split(shell, "Z", at=12, lip=1.5)`. Both are one solid and the lip
    keys into a groove with 0.2 mm clearance; `at` on a wall's flat inner
    face is moved 0.01 mm into the cavity (printed). To open a face instead
    (`open_faces=["-Z"]`) its rim edges must be sharp (`fillet=(r, 0)`):
    a rounded rim raises, it would print a knife edge.
B5. Cut arches, windows and wheel wells AFTER the split, through the walls
    only (a cylinder from the outside to just past the wall). A cut across
    the whole width also cuts the floor and leaves 3 pieces.
B6. Lofts: build every section with the same helper
    (`cad.rounded_rect_wire(w, h, r, center, "X")`, r > 0 on all of them) so
    edge counts match. Draft: `cad.extrude_profile(points, h, taper_deg=3)`,
    never Part::Extrusion with TaperAngle (MEASURED: hung > 100 s).
B7. Left/right parts: `cad.mirror_pair(lamp, "XZ")` for two bodies;
    `cad.symmetric(half, "XZ")` for one body - model the half 0.5 mm past
    the plane. Handles and bumpers: `cad.pipe(points, r=3)`; r must stay
    under the path's tightest bend.

## Round 1 (R270) - each of these cost a turn most of its hour

R1. **Fillet on spline-on-spline.** A fillet (profile_body fillet=, soften,
    fillet_safe) on a body whose side AND plan are splines failed ~15 times
    (r 7 stepped down to 0.3), and such shells tessellate lumpy (slow
    ./check, unreliable opening_for). Fork an example: its outlines are
    lines and arcs (`spline=False`, or a revolve section), filleted INSIDE
    profile_body before any cut.
R2. **A split on a solid section.** `cad.split` at a height where the body
    is solid (a floor, a plinth, the wall's own inner face) raised
    "section is solid", "lip wall too thin" or "lower part invalid" ~14
    times. Split 0.3-1 mm INSIDE the cavity, where the section is a ring
    of wall all round, and below the modules' slide corridors.
R3. **A cusp offset.** `wire.makeOffset2D(-t)` of an outline with a sharp
    inward corner or a tight spline bend self-intersects (a cusp) and
    the core / liner is invalid. Offset faces with
    `cad.profile_body(..., inset=t)` (it checks), keep inside corners
    rounded >= the offset, or use a revolve section with both skins.
R4. **fitted_after listing unbuilt parts.** intent.json "fitted_after"
    naming a part model.py never builds is only a NOTE in your ./check but
    FAILS Studio's build - the turn is lost at the end. List exactly the
    labels you add to the document; when you drop a part, drop its name.
R5. **A screws list never added to the document.** `screws.append(
    cad.screw(...))` builds shapes; nothing is visible or checked until
    each is added: `o = doc.addObject("Part::Feature", "Screw_%d" % i);
    o.Shape = s`. A fastener that is not a document object does not exist
    (no pilot check, no BOM, no render).
R6. **A pilot of the screw's own size bites nothing.** cad.screw_boss /
    screw_through drill the 0.85 d thread-forming pilot (R444); the
    screw's overlap with it is the thread (a NOTE). A pilot at or over d
    is a PROBLEM. For brass inserts cut a 1.4 d + 0.1 pocket in a sleeve.
R7. **Arc corners on windows and slots read as clip channels.** A
    concave quarter-cylinder (a window's rounded corner, a filleted core
    edge) is reported as "a round channel ... wraps 180 deg". Soften such
    corners with 3 straight facets (toy_car.py soft_wire).
R8. **"cut: the tools removed nothing" (24 times).** The cutter missed:
    measure the surface first (a ray: front_y / top_z / bottom_z helpers
    in the examples) and place the cutter from that number, through the
    whole wall. A purely decorative cut may pass `optional=True`.

## Holding it together (R441 / R442) and restyling a seed (R425)

R9. **A lip locates a part; it does not hold it.** Two housing parts that
    meet need a screw through both, a pin of one in a bore of the other,
    or cad.snap_fit_pair - else "fastening: X meets Y but nothing joins
    them". cad.pin_hinge leaves its bore EMPTY: add the pin as its own
    part (hinged_box.py: Hinge_Pin), or put the returned motion entry in
    intent.json - a lid declared on the axis both parts are bored on is
    joined by its hinge (R505). A hardtop keyed into a tub: pegs on
    its lip into blind bores in bosses on the tub (toy_car.py).
R10. **A cabled module hangs on its ribbon.** Every ap.cable module needs
    material within 0.5 mm on two OPPOSITE sides (ribs 0.2-0.3 mm off, a
    pocket, or a part labelled ..._Holder / _Cradle / _Clip round it).
    A key cap on its plunger is one side: add pads under the button. Keep
    the ribs clear of the working face and of the ribbon's way out.
R11. **A restyle breaks what a number did not follow.** Every outline,
    cutter, foot, boss and rib must DERIVE from the RESTYLE knobs (or from
    a measured surface), never repeat a number the base build happened to
    have: at LENGTH 214 a foot placed for 252 landed under a screw head
    (handheld, R425). After a restyle, ./check at the new numbers before
    adding details.

