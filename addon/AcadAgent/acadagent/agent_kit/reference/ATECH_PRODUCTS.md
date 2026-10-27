# Atech hardware catalogue and product recipes

Every number here was MEASURED with the bundled `freecadcmd`, the shipped
meshes and the live library (`import atech_ports as ap, atech_cad as cad`).
Each recipe's hardware block passed `./check` (`CHECK PASS`). The recipes
with an example are complete, passing products you FORK (R270, R410-R413):
`examples/toy_car.py`, `examples/desk_robot.py`, `examples/smart_speaker.py`,
`examples/handheld_console.py`, `examples/bedside_lamp.py`,
`examples/alarm_clock.py`, `examples/desk_fan.py`,
`examples/weather_station.py`, `examples/rc_tank.py` (each has an
`INTENT = {...}` block: that is its intent.json). Each is laid out in three
marked sections - `# === PARAMETERS (restyle here) ===`, `# === STAGE A:
hardware, shell, every working-face opening, fasteners ===`, `# === STAGE
B: details ===` - so a fork keeps the hardware code, redesigns the outlines for
the request (R600), ./checks after STAGE A, then adds details.

Contents: 0 known limits - 0A ARCHETYPE TABLE (which example to fork) -
1 the board - 2 placing hardware - 3 modules - 4 off-board parts - 5 rules
for every product - 6 build lessons - 7 recipes (with human-design details
and colours) - 8 unknowns - 9 cable for ergonomics - 10 robust body
recipes.

---

## 0. Known limits (read first)

1. **See-through parts and covers (R250).** A part coloured with
   `cad.transparency("glass" | "smoked" | "frosted")` lets the rays of an
   OPTICAL module (light, screen, distance sensor) out: a lens, visor or
   cover glass is the right design. A key cap over a button needs
   intent.json `"covers": {"Cap": "button_p3"}` (every example has it).
   A button, speaker, microphone or plug is sealed by glass - give it an
   opening. Since R270 a microphone needs >= 3 % of its face open
   (`cad.speaker_grille(..., d >= 14, hole 1.5)` over it, MEASURED 3.6 %).
2. **Overlaps are tested pairwise for the first 30 bodies only** (board,
   modules and ribbons count). A detailed product has more; build the
   parts most likely to collide first and keep copies (wheels, screws)
   last.
3. **The `agent_notes` in `models/presets.yaml` describe an older pipeline**
   (Tinkercad `is_hole` primitives, "auto-carve", "the board pocket is
   carved for you"). Use them for intent only ("never cover the screen").
   The board has no USB connector of its own: power comes through the
   `usbc` module, so every product needs one.

---

## 0A. ARCHETYPE TABLE - the closest example to start from (R270, R600)

Start from the example in the second column: its hardware and fit code (the
board placement, modules and cables, cradle, stops, openings, fasteners) is
working code to KEEP. Its body is not your design: REDESIGN the silhouette
freely for the request, on its construction calls with your numbers, and
move the hardware where the new form needs it. Never size the silhouette
from the board's footprint: the hardware sets a minimum inner pocket,
nothing more (cabled where the product needs it, section 9). The last two
columns describe each EXAMPLE as built - inspiration, never minimums or
gates. MEASURED times: ./check of the example with the review sheet off
(`test_kit_examples_r270`).

| Category | Start from this example | Board | Seated modules | Cabled modules | The example's silhouette | The example's hero element |
|---|---|---|---|---|---|---|
| vehicle (car, truck, rover) | `examples/toy_car.py` | FLAT under the floor, nose at port 8 | dc_motor 1 + 9 (rear axle), usbc 7 (tail) | headlights 6 + 14, distance_sensor 8 in the nose | a low wedge: length 1.56 x the width, height 0.55 x the width, arches cut into haunches over the wheels, a lofted cabin narrower than the body | the face: 2 lenses in bezels + grille with the ToF lens, 60 mm wide or more |
| tank / tracked vehicle | `examples/rc_tank.py` (R413, CHECK PASS, ./check 26 s MEASURED) | FLAT under the deck, nose at port 8 | dc_motor 1 + 9 (rear sprockets), usbc 7 (rear plate) | distance_sensor 8 and headlights 6 + 14 in the glacis (the car's routes), each held by ribs | length >= 1.5 x the width over the tracks (MEASURED 1.64), two tracks the full length | turret on a pinned ring with a barrel; belts, tread pads, road wheels, sprockets, idlers |
| robot / character / pet | `examples/desk_robot.py` | LANDSCAPE_UP in the torso, modules face -Y | speaker 1-2 (belly), button 3, microphone 4-5, usbc 7 (side) | screen 11-12 up the neck into the head | torso depth / width >= 0.6 with a crowned belly; head >= 40 % of the height, wider than deep | the head: a visor >= 35 mm wide with a raised bezel (the example: 100 x 60) and a neck collar |
| speaker / radio / round gadget | `examples/smart_speaker.py` (TALL = True for a column) | FLAT on the puck's axis | speaker 11-12, microphone 4-5, buttons 2 + 3, usbc 7, lights 1/6/8/9/14 | - | puck: height >= 0.4 x the diameter (the example 0.44); column: height >= 1.2 x the diameter | the top: grille + frosted light ring over every light, 100 mm across |
| handheld / game pad / remote | `examples/handheld_console.py` | FLAT, turned so its long side runs across | screen 11-12 (centre), usbc 4 (bottom edge), light 3 (power LED) | D-pad 9, B 14, A 8 (straight out of the end port), shoulders 10 + 13 | 200 x 94 face, <= 30 mm thick where held, grip bellies under the thumbs | the cover glass: >= 40 % of the face, a control under each thumb |
| lamp / night light / tall product | `examples/bedside_lamp.py` | UPRIGHT_FRONT in the column | usbc 2 (side), lights 5 + 13 behind a frosted window | light 8 straight up the neck into the globe, button 7 down into the foot | height >= 2 x the foot diameter, foot >= 1.6 x the column | the diffuser globe, the largest part (100 mm across) |
| clock / alarm clock / timer | `examples/alarm_clock.py` (R410, CHECK PASS, ./check 28 s MEASURED) | LANDSCAPE_FRONT, everything tilted back 12 deg as one Placement | speaker 13-14 (grille), screen 9-10 + light 3 behind the lens, keys 6 + 5, usbc 8 (left side) | snooze button from 2 up behind the board to the top, in a bracket | face tilted back 10-15 deg on its foot, a back that swells in one curve, width 1.7 x the height | the smoked lens in a recessed bezel, >= 50 % of the front (MEASURED 53 %) |
| fan | `examples/desk_fan.py` (R411, ./check 17 s MEASURED; CHECK PASS waits on the R440 fan gate's shaft-direction fix) | FLAT in the long foot | button 6, light 14 (glow lens), usbc 1 (left side) | dc_motor from 7 up the hollow stem, collar and neck into the pod, held by ribs | guard >= 60 % of the front, on a stem over a long foot | the guard: ring, radial bars, two rings over six wide blades |
| weather station / thermometer / barometer | `examples/weather_station.py` (R412, CHECK PASS, ./check 25 s MEASURED) | LANDSCAPE_UP in a body leaning back 12 deg (one Placement, as the clock) on a sculpted foot | screen 11-12 behind a lens, keys 3 + 4, light 9 (alert), usbc 7 (left side) | temp_humidity 13 straight up a hollow post into the louvred hut | a wedged display body 144 x 31 x 86 (curved back, rolled top edge) + hut 28 x 20 x 30 on top, away from the board's heat | the display and the louvred hut (slats, pitched roof, drip edges) |
| planter / smart pot / herb garden | `examples/smart_planter.py` (R700, CHECK PASS, ./check 19 s MEASURED) | LANDSCAPE_UP in a shallow bay behind the flat face (board x 0..120, z 30..90) | screen 10-11 behind a smoked lens, light 14 (frosted glow pipe), temp_humidity 6 (round-hole vent + slot vent under it), usbc 7 (left side) | - | 160 x 135 x 120: a crisp flat face, CORNER-rounded back, a partition closing the bay from the soil cavity open at the top | the instrument face and the terracotta inner pot (drainage holes, rolled rim) standing in a drip tray, soil in it |
| pet feeder / dispenser | `examples/pet_feeder.py` (R700, CHECK PASS, ./check 27 s MEASURED) | LANDSCAPE_UP high in the base unit's face (board x 0..120, z 180..240), split front / back behind it | screen 10-11 behind a smoked lens, button 13 (FEED key cap), light 3 (status pipe), usbc 7 (left side) | dc_motor 4 straight down (pins up, shaft down: twist-free) into cradle cheeks on the dispenser drum | a 160 x 150 x 250 base unit on a base plate with a 110 mm tongue for the bowl, a 110 mm hopper bin pinned on top, its lid on a pin hinge | the hopper window and the curved spout over the bowl; inside, a six-pocket rotor in a closed drum fed by a duct |
| doorbell / intercom / wall sensor | `examples/video_doorbell.py` (R500, CHECK PASS, ./check 36 s MEASURED) | UPRIGHT_FRONT behind the face; LIFT stands the wall plate's foot on z = 0 | button 7 (the big press, bottom centre), light 9 (glow ring), distance_sensor 6 + microphone 13-14 behind a smoked visor (the ToF gets an open aperture), usbc 3 (right side) | speaker 1-2 over the board's top edge: the ribbons fold back round the right edge, run flat behind the board and loop over the speaker into its top, held by posts and side ribs | a tall rounded slab 84 x 196 x 36 (crowned face, rolled edge) on a wall plate 6 mm proud at the sides, 15 at the ends with two countersunk wall screws | the big round brushed press in a frosted glow ring, low on the centre line |
| arcade cabinet / bartop / jukebox | `examples/mini_arcade.py` (R500, CHECK PASS, ./check 42 s MEASURED) | FLAT under the deck, long side across (port 1 front-left), the base on rubber feet | knob 1-2 (a spinner: its cap turns flush in the deck), light 3 (START lens), buttons 4 + 5 under big caps on long plungers, usbc 7 (left side) | screen 10-11 and speaker 13-14 up the panel leaning back 12 deg, from the back-edge pairs: loop up and forward / rise behind the screen, each shifting sideways only in its own plane (no twist, no crossing), held by side ribs | one side profile (kick, deck, leaning panel, overhanging marquee, roof) extruded 142 x 110 x 196, split into Base + Shell | the leaning panel: smoked glass over a gloss-black mask window, a round speaker grille above, the lettered marquee over both |
| music box / jukebox / record player | `examples/music_box.py` (R425, CHECK PASS, ./check 23 s MEASURED) | FLAT, turned so its long side runs across (ports 9-14 toward the front); the board rides at HEIGHT minus its stack | speaker 13-14 (front left), knob 9-10 (front right), light 11 (lit window), button 4 (back row), usbc 7 (right side) | - | a walnut box 170 x 108 x 40 on a dark plinth, the lid 1 mm proud over a lid line, brass hinges across it at the back | the lid top: a domed brass grille, a frosted lit window with a pixel grid, a knurled brass knob cap 14 mm proud on a frosted light ring |
| parking sign / garage parking assistant / wall signal | `examples/parking_sensor.py` (R425, CHECK PASS, ./check 10 s MEASURED) | UPRIGHT_FRONT in a wall pod, modules face the car (-Y), the wall behind (+Y) | lights 2 / 4 / 6 (green / amber / red), distance_sensor 9 (open slot), button 10 (SET), screen 13-14 (portrait), usbc 7 (bottom) | - | a portrait pod 96 x 170 x 30 with 18 mm corners, screwed through a wall plate that stands 6 mm proud all round and carries the sign above it | the traffic light: three domed lenses 26 mm across with hoods in a black signal bezel, 40 mm apart; a blue P sign on the plate |
| organizer / desk tidy / pen holder | `examples/desk_organizer.py` (R720, CHECK PASS, ./check 28 s MEASURED) | LANDSCAPE_UP in the front display block, 24 mm up (a bottom-row module slides 20 mm down out of its port) | screen 10-11 behind a smoked lens, temp_humidity 14 in a sealed chamber behind a slot vent, button 6 under a key, usbc 7 (left side) | - | a 232 x 90 tray: a display block 144 x 30 x 96 on its front left, three pen cups (0.72 / 1.0 / 0.86 of 140 mm) behind it, a hollow phone dock with a slot leaning back 14 deg on the right | the display block (lens in a recessed black bezel) and the stepped cups |
| photo frame / picture frame / digital frame | `examples/photo_frame.py` (R720, CHECK PASS, ./check 18 s MEASURED) | UPRIGHT_FRONT behind the picture, off the frame's centre line (no 2-port pair centres the screen: 3+4 fails its seat check), everything tilted back 12 deg as one Placement | screen 10-11 (portrait), orientation 5, usbc 2 (right side) | button from 7 straight down into the bottom rail (ribs + a pad), light from 14 straight out to the left, facing the back behind a frosted strip (ribs above and below) | a 136 x 190 portrait (5 x 7) flat wood moulding on a back box set in 3 mm, leaning on a hinged kickstand (lug + knuckle + pin) | the moulding's chamfered sight and the bevelled mat window round the screen |
| metronome / tempo pyramid | `examples/metronome.py` (R620, CHECK PASS, ./check 35 s MEASURED) | INVERTED upright (`Rotation(Vector(1, 0, 0), 180)`: modules face -Y, port 7 at the TOP centre), the whole product tilted back ALPHA (half the back's slope) as one Placement | speaker 13-14 (click grille), knob 4-5 (in a dial pod, its cap flush with the rim), screen 9-10 (portrait) + light 2 behind one lens, usbc 1 (left flank) | tap button straight up from port 7 into the apex, in a cradle | a pyramid: a 154 wide foot to a ~47 wide top over 230, front and back leaning in alike, on a walnut plinth | the smoked lens that follows the taper, and the dial pod with its frosted LED ring |
| macro pad / stream deck / keypad | `examples/macro_pad.py` (R620, CHECK PASS, ./check 31 s MEASURED) | FLAT ACROSS (long side left to right, modules up), the deck tilted back ALPHA as one Placement | screen 9-10 (labels, back-left), buttons 1 + 2 (big keys in front of it), light 5 (status strip), knob 13-14 (back-right, in a dial crown, its cap flush with the rim), usbc 7 (left end) | - | a low wedge 141 x 108, 19 mm thick at the front rising 13 mm to the back, rolled edges, a black base under a graphite top | the dial crown with its frosted LED ring, and the two big keys under the label window |
| generic case (no product named) | `examples/atech_case.py` - read for its CALLS, never fork its box | UPRIGHT | button 3, speaker 9-10 | - | a box shrink-wrapped round the board is NOT a product | - |

---

## 1. The board (`motherboard_14_port`)

| Property | Measured |
|---|---|
| Extents (board frame, as drawn) | x 0.01..59.99, y -2.50..4.50, z 0.01..119.99 = **60 x 7 x 120 mm** |
| PCB top / module seat plane | board y = 0; the underside is flat at y -2.5 |
| Raised central frame ("spine") | x 20..40, z 20..100, top at y +4.5. Free of modules: the place for a hold-down rib from the lid (0.2 mm off it) |
| Mounting holes | **none**; corners rounded r ~1. Hold the board by ledges / a pocket under its edges (0.3 mm clear) or standoffs 0.1 mm under it, plus a rib onto the spine |
| Ports | 14 housings, 15.64 x 8.50 x 2.40, 6 fork contacts at 2.54 mm. 1-6 left edge (slide +X), 9-14 right edge (slide -X), 7 top edge (slide +Z), 8 bottom edge (slide -Z) |
| Port pitch | 20.0 mm along a column (ports 3/4/5 are 0.05-0.20 mm off-grid) |
| Seated module overhang | 0.37-0.67 mm proud of the board edge |
| Slide-in travel | 19.1 mm (19.4 for the speaker): each seated module slides in along its axis from 19.1 mm outside the board edge. That corridor must be empty, or every part in it must be listed in intent.json `fitted_after` |
| Ports 8 and 12 | geometrically identical to the others |

**Valid port pairs for 2-connector modules** (each seated and checked):

| Module | Passes | Fails |
|---|---|---|
| screen, microphone | (1,2) (4,5) (9,10) (10,11) (11,12) (12,13) (13,14) | (2,3) (3,4) (5,6): header 0.05-0.10 mm short |
| speaker | (1,2) (9,10) (10,11) (11,12) (12,13) (13,14) | (4,5) hits the board; (2,3) (3,4) (5,6) as above |
| cabled 2-connector (`ap.cable`) | the same pairs | (2,3) fails |

Every 1-connector module passes on all 14 ports. `ap.pair_for(doc, name,
port)` picks a passing pair.

**Stack heights above the PCB top** (add 2.5 mm for the board underside):

| Height | Modules |
|---|---|
| 9.54 | light, distance_sensor, temp_humidity, orientation |
| 9.64 | screen |
| 10.04 | button |
| 10.21 | usbc |
| 10.84 | microphone |
| 19.14 | dc_motor |
| 20.20 | speaker |

A 1-cell stack is **12.7 mm** thick; with a speaker **22.7 mm**.

### Orientation presets

Set `board.Placement` **before** seating; modules follow it. Seating again
on the same ports returns the old object, so never re-orient after seating.

```python
from FreeCAD import Vector, Placement, Rotation
FLAT            = Rotation(Vector(1, 0, 0), 90)       # modules face +Z; board x 0..60, y -120..0
UPRIGHT_FRONT   = Rotation(Vector(0, 0, 1), 180)      # portrait, modules face -Y (the front)
LANDSCAPE_UP    = Rotation(Vector(0, 0, 1), 180).multiply(Rotation(Vector(0, 1, 0), -90))  # 120 wide, 60 tall, face -Y
LANDSCAPE_FRONT = Rotation(Vector(0, 0, 1), 180).multiply(Rotation(Vector(0, 1, 0), 90))   # the same, rows swapped
board = ap.board_object(doc)
def place_board(rot, x0=0.0, y0=None, z0=0.0):        # the board's measured box min at (x0, y0, z0)
    board.Placement = Placement(Vector(), rot)
    bb = ap.bbox(board)
    board.Placement = Placement(Vector(x0 - bb.XMin, 0 if y0 is None else y0 - bb.YMin, z0 - bb.ZMin), rot)
```

| Preset | Port map (world, board box at the origin) |
|---|---|
| **FLAT** (face +Z) | 1-6 left column x -0.4..19.1, y -10 -> -110 (1 at the back, y ~0). 9-14 right column x 40.9..60.4. 7 back centre (y -19..+0.4, a USB-C mouth there faces +Y); 8 front centre (y -120.4..-101). Put the product's nose at the port-8 end (-Y = FreeCAD's front) |
| **UPRIGHT_FRONT** (face -Y) | 1-6 on the viewer's right (x 41..60, z 0 -> 120 bottom to top), 9-14 on the left (x -0.4..19). 7 bottom centre (a USB-C mouth faces -Z, down). 8 top centre, exits +Z |
| **LANDSCAPE_UP** (face -Y) | `place_board(LANDSCAPE_UP, 0, None, 36)` gives x 0..120, z 36..96: bottom row 1..6 left -> right (z 36..56), top row 9..14 (z 76..96), 7 at the left end (z 56..76, USB-C mouth -X), 8 at the right end. Top centre pair **(11,12) x 40..80** |
| **LANDSCAPE_FRONT** (face -Y) | top row 6..1 left -> right, bottom row 14..9, 8 left end, 7 right end. Bottom centre pair (12,11) x 40..80; speaker pairs on the bottom row hang 20 mm below |

In LANDSCAPE_UP the board's spine is world x 20..100, z 56..76 (between
the rows), its face at y -4.5. A 2-connector module's long side runs along
its port column: a screen is landscape on a horizontal column.

---

## 2. Three ways to place hardware

### 2a. `ap.seat(doc, name, port_or_pair)`: the default
No ribbons; passes `./check` when its slide corridor is clear (or the
parts in it are `fitted_after`). The working face points away from the
board, except usbc (mouth toward the board edge) and dc_motor (shaft
outboard). `ap.bbox(module)` is its measured world box.

### 2b. `ap.cable(doc, name, port(s), ap.module_placement(name, at, face, cable), via=[...])`: a module where the product needs it
Returns `(module, [ribbon, ...])`. Each ribbon is a Part::Feature that
counts for overlaps: keep every part clear of it. A cabled module has no
slide path.

| Item | Size |
|---|---|
| Ribbon | 14 x 0.6 mm |
| Board end (plug) | sits in the port; the ribbon leaves outboard and runs ~3.7 mm straight past the board edge before it bends |
| Module end (socket) | 8.5 mm beyond the module's pin side + 6 mm lead = **14.5 mm straight run** along `cable` |
| Ribbon width | at the plug, along the board edge; at the module, along `face x cable` |
| Cost | `cable()` ~0.2 s; `ap.check` ~0.5 s |

Route rules (MEASURED):
- Put the module beyond the board edge its port is on, the 14.5 mm socket
  run pointing back toward the plug or at 90 degrees. A hairpin made 16 mm
  loops and overlapping ribbons.
- Twist-free needs `face x cable` parallel to the plug's width (FLAT ports
  1-6/9-14: world Y; 7/8: world X; LANDSCAPE rows: X). Otherwise the ribbon
  twists 90 degrees through a ~30 mm cube.
- **Straight rises are the cleanest.** LANDSCAPE_UP top-row pair (11,12)
  into a screen straight above (`face="-Y", cable="-Z"`, centre y -4.84):
  two straight ribbons up a neck (desk_robot.py, 34 mm above the board).
- **A nose sensor ahead of FLAT port 8** (`face="-Y", cable="-Z"`) needs
  its centre >= PCB top + 30 (at +27 the ribbon clipped the sensor);
  y -131.4 (rc_tank.py; toy_car.py runs the same route NOSE = 24 mm
  further forward, y -155.4, MEASURED R500).
- **Headlights from FLAT ports 6/14 facing -Y** (`cable="-Z"`): one
  waypoint keeps the ribbon off the floor. Centre (30 -+ 34, -132, PCB
  top + 24) with `via=[(-3, -118, 24)]` / `[(63, -118, 24)]` ran z
  13.9..38.9; without the via it sagged to z 8.5 (MEASURED).
- Never move the board or a module after `cable()`.

### 2c. `am.load_module(doc, name, placement=...)`: off-board parts
`n20_wheel`, `nema17_stepper`: no electrical connection.

---

## 3. Module catalogue

Sizes are row x up x slide (mm). Features measured from height maps.

| Module | Size | Conn | Working face | What must be exposed | Opening spec |
|---|---|---|---|---|---|
| **button** | 19.50x10.04x19.50 | 1 | up | round cap ~11, centred, only 0.5 mm proud of an 18.5 sq cover (top 10.04 above the PCB) | `cad.button_cap(11.5, h, flange=1.5, at=..., axis=...)` through the wall, its flange 0.1 mm behind the wall, then `cad.opening_for(wall, cap, axis=...)`; fuse a plunger (r 3) down to 0.16 mm above the module's cap. Travel unknown: leave 0.5-1 mm |
| **light** | 19.50x9.54x19.50 | 1 | up | 3x3 LEDs (4x4, 6.5 pitch) over **17x17** under a flat cover | a clear lens / light pipe 0.4-0.5 mm off it (`cad.lens`), or a frosted ring/pipe; never solid over it |
| **distance_sensor** (ToF) | 19.50x9.54x19.50 | 1 | up | funnel ~16 wide to ~4x9; emitter/receiver 4.5 mm apart along the slide axis | an OPEN aperture >= 10x6 (no glass), centred; a grille slot 6.6 x 23 works (toy_car.py) |
| **temp_humidity** | 19.50x9.54x19.50 | 1 | up | 4.5x4.5 hole over a 3x3 sensor at the centre | a vent grille over a 12 zone (`cad.grille`, >= 5 holes 1.5-2) plus a second vent; keep it away from motors, speaker, USB |
| **orientation** (IMU) | 19.50x9.54x19.50 | 1 | sealed | nothing | no opening; 2 mm air above; seat it square to the product |
| **screen** | 39.50x9.64x19.50 | 2 (20 apart) | up | **active area 25.6x13.5**, centred (<= 0.75 off) | a window >= 27x15 centred, a recessed bezel 0.8-1.5 mm (desk_robot.py: a black face plate set 1 mm back, window 28 x 16) |
| **microphone** | 39.50x10.84x19.50 | 2 | up | an engraved mic icon mid-plate; no explicit port in the mesh | `cad.speaker_grille(wall, c, n, 14-15, ring_pitch=2.4-2.5, hole=1.5-1.6)` (~20 holes: >= 3 % of the face open, ./check R270) + a ring rib (tube) from the wall to 0.3 mm off the mic face; >= 30 mm from the speaker |
| **speaker** | 40.00x20.20x40.00 | 2 | up | 38.7 sq top, round surround ~27 centred; hangs **20.6 mm outboard** of the board edge | `cad.speaker_grille(wall, c, n, 32-36, ring_pitch=2.6, hole=1.5)` (95-133 holes, 21-29 % open), 0.5-2 mm air gap |
| **usbc** | 19.50x10.21x19.75 | 1 | out (its board edge) | receptacle 10.0x3.5, **centre 5.9 mm above the PCB top**, mouth 0.25 proud | `cad.socket_opening(wall, usb, margin=1.5)` = 13 x 6.5. **The wall must be <= ~1.5 mm in front of the mouth**: cut a pocket and fuse a liner whose back wall starts 0.25 mm off the mouth (all three examples) |
| **dc_motor** (N20 + DRV8833) | 19.50x19.14x48.30 | 1 | out (shaft) | shaft 3.0 D, **10.14 mm above the PCB top**, 8.8 mm beyond the body; body overhangs the board edge 20.4, the shaft tip 29.2 | a hole >= 5 round the shaft (a soft square avoids a "hole through 2 walls" warning); a wheel bore 3.3 |
| **knob** | - | **0** | - | no pin header: cannot be seated or cabled | do not use; two buttons (+/-) instead |

---

## 4. Off-board parts

| Part | Measured | Use |
|---|---|---|
| **n20_wheel** | 5.40x3.70x6.00 hub, D-bore ~3.16 / 2.68 flat | a shaft coupler, not a road wheel. Road wheels: `cad.wheel(d, width, bore=3.3, axis=..., at=...)` |
| **nema17_stepper** | 42.3x64x42.3; face at y 0, shaft +Y 5 x 24, M3 on a 31 square, pilot 22 x 2 | no driver module exists: mechanical only, on a mount plate (22.5 pilot, 3.2-3.4 holes) |

---

## 5. Rules for every Atech product

1. **Size the body from the measured stack:** `cad.bound_of(board, *modules,
   *ribbons)` + clearance + wall. With rounded corners keep **5 mm** between
   any hardware corner and the inner wall (a 12 mm corner radius cuts 2.9
   mm into the corner, the back-edge fillet more: MEASURED 3.5 mm
   overlapped the board).
2. **Power:** always a `usbc` module, where a real product's port would be.
3. **Assembly:** modules slide in sideways, so a part beside them blocks
   them. A **fixed** tray/base below or behind the module layer holds the
   board; everything else is **fitted after** (listed in `fitted_after`).
   Split a hollow body with `cad.split(body, axis, at, lip=1.2)` so the
   fixed part stays out of every corridor (car: split z 11.5, lip top 13.0
   under the corridors at z >= 13.9; robot: split y = board back - 0.3).
4. **Containment:** each module's box (motor shafts included) inside the
   union box of the parts.
5. **Desk:** the lowest point exactly z = 0 (wheels, feet).
6. **Every working face gets its real opening** from section 3, placed
   from `ap.bbox(module)`, never a guessed number.
7. **Joints:** a part that only touches another fails `./check`
   ("only touches ... falls off"). Pin it (a peg 0.15 mm clear in a hole,
   >= 1 mm deep), key it (a lip), or fill its own opening exactly (an
   insert: glass, grille, light ring).

---

## 6. Build lessons (MEASURED while building the five examples)

- **Insert pattern** (glass, grilles, tail lights, light rings): `piece =
  shell.common(cutter); shell = shell.cut(cutter)` - the piece fills its
  opening exactly, no overlap, no gap. Exact booleans first; OCCT's exact
  common returned 0 mm3 for a spline-cornered window through two walls,
  `shell.common(cutter, 0.01)` (fuzzy) worked.
- **Hollow a sculpted body with its own core cut:** `cad.cut(body, core)`
  where the core is `cad.profile_body` of outlines moved 2 mm in. A fillet
  on an OCCT offset curve failed at every radius (0.6 mm up), so re-knot an
  offset spline (`wire.makeOffset2D(-2).discretize(n)` -> new points);
  `spline=False` polygon outlines with `fillet=` build in 0.1-0.6 s.
- **Revolved products:** one closed (radius, height) section that already
  contains the walls (outer skin out, inner skin back) revolves straight
  into a hollow body - no core, no boolean (smart_speaker.py: 0.2 s).
- **`cad.split` needs a hollow section:** splitting exactly at a wall's
  inner face raised "section is solid"; split 0.3-1 mm inside the cavity.
- **`cad.groove_ring` needs a closed ring section:** fine on a revolved
  shell; it raised "section too small" on a split (open) part and on a
  hollow profile_body with a spline outline - cut grooves before splitting.
- **Screw bosses:** `cad.screw_through` grows gussets 0.6 x the column
  length tall (up to 3 d + 4) reaching ~12 mm out: on a 30 mm column they
  hit a speaker and the other half's side wall. Far from walls use it; else
  `cad.screw_boss(..., ribs=0)` + `cad.countersink` in the lid.
- **`cad.opening_for(wall, part, axis=...)`: give the axis.** Without it,
  it picked a side wall and cut a 1593 mm3 channel across a car's nose.
- **A cut that frees an island** (a ring round a top) leaves 2 solids: make
  the island its own part (the speaker's aluminium top).
- **Coaxial round holes in two walls** (axle holes, pin holes) give a
  "hole through 2 walls" WARNING: use soft-square holes for round pins.
- **One wheel build**, mirrored and copied (`cad.mirror`, `.copy()`):
  `cad.wheel` takes ~2 s; three builds cost 68 CPU-s.
- Measure a surface before you drill it: a ray through a hole you just
  cut finds nothing.
- **Screws need a pilot under their size (R270).** `cad.screw_boss` /
  `cad.screw_through` still drill the nominal d (./check: "the thread has
  nothing to cut into"). Every example then cuts a heat-set insert pocket
  (1.4 d + 0.1: M2 3.2, M2.5 3.6) in a sleeve round the boss end:
  `case = cad.fuse_one(case, cyl(pocket / 2 + 1.2, foot, axis, 10))` and
  `case = cad.cut(case, cyl(pocket / 2, foot + 0.5 along axis, axis, 9.5))`
  - start the sleeve clear of any floor fillet and the pocket 0.5 mm off
  the boss's lead-in (a coincident start made the cut INVALID).
- **Grooves, bands and reveals on a revolved body go INTO the section**
  (a notch of 4 points per groove), never `cad.groove_ring` on the
  revolved barrel (12767 faces, 100 s - smart_speaker.py, R270).
- **Window and slot corners as straight facets** (3 per corner), not
  arcs: an arc corner is a concave cylinder that ./check reads as an open
  clip channel ("wraps 180 deg"). The same for a hollow core: keep its
  inner edges sharp (`fillet=None` on the core) when the body's fillet is
  small.
- **Cut through the WHOLE wall or not at all:** a badge or window
  cutter that stops inside the wall leaves a 0.6 mm skin (WALL WARNING);
  a box side crossing a curved wall obliquely leaves a knife-edge sliver -
  cut a revolved wall with a SECTOR (radial sides, bedside_lamp.py).
- **A rib or boss under a window or visor:** put it on the insert (the
  handheld's bezel carries its spine rib) or outside the cutter - the
  insert cut otherwise frees it (2 solids).
- **Slot vents on a deep flat back** made the cut INVALID once (desk
  robot); `kind="hex"` on the same face worked.


---

## 7. Recipes

All hardware blocks pass `./check`. "Product" sizes are the stack + 2 x
(clearance + wall) plus the named extras.

### 7.1 "a toy car" - FLAT, nose -Y (examples/toy_car.py, CHECK PASS)
```python
R = 24.0; L = R - 10.14                                # wheel radius; PCB top (shaft = PCB top + 10.14)
board.Placement = Placement(Vector(0, 0, L), FLAT)
mot_l = ap.seat(doc, "dc_motor", 1); mot_r = ap.seat(doc, "dc_motor", 9)   # rear axle, shafts out
usb = ap.seat(doc, "usbc", 7)                                              # tail, mouth +Y
eye, eye_rib = ap.cable(doc, "distance_sensor", 8, ap.module_placement(
    "distance_sensor", (30, -131.4 - NOSE, L + 20), face="-Y", cable="-Z"),
    via=[(30, -106 - NOSE, 18)])                              # behind the grille's ToF lens
head_l, hl_rib = ap.cable(doc, "light", 6, ap.module_placement(
    "light", (-1, -132 - NOSE, L + 14), face="-Y", cable="-Z"), via=[(1, -118 - NOSE, 17)])
head_r, hr_rib = ap.cable(doc, "light", 14, ap.module_placement(
    "light", (61, -132 - NOSE, L + 14), face="-Y", cable="-Z"), via=[(59, -118 - NOSE, 17)])
# NOSE = 34: the hood and wheelbase stretched so the car is 1.56 x as long
# as it is wide (R610: the haunches reach the tyres' outer faces)
```
- **Product:** 137 W x 215 L x 76 H (bumpers included). A LOW coupe
  (R610 - the 4x4 tub read as "a box on wheels"): ONE spline body
  (`cad.profile_body`, spline side and plan) - a wedge side (the nose
  face 41 high for the lamps, the hood rising to the shoulder at z 57, a
  rear deck falling to a rounded tail) and a Coke-bottle plan (haunches
  |y| 68.6 over the axles, doors pinched to 56); the four wheel ARCHES are
  cut into the haunches, each well with a 2 mm liner (the core less a
  keep-out round each arch). The cabin is a ruled `cad.loft` from the
  shoulder (110 x 92) to a smaller roof (44 x 70) 19 higher: raked
  windscreen, fastback, tumblehome. Wheels 48 x 14 at x 30 -+ 60.5,
  wheelbase 134 (100 + NOSE); ground clearance 7.5; chassis tops out at
  z 13.0.
- **Parts:** Chassis (fixed: floor, chin, sills, board cradle, bumpers),
  Body_Shell, Hardtop, Grille, ToF_Lens, 4 panes, 2 light pipes + 2
  bezels, 2 tail lights, 4 screws, 4 tyres + 4 rims - all but the
  chassis fitted after.
- **STAGE A** (hardware, body + arches, cabin + rib, motor holes and
  axles, lights, grille + ToF lens, USB-C pocket, cradle, screws with
  insert pockets, four wheels) passes ./check on its own; STAGE B adds
  the rest.
- **Spline-shell traps (R610, MEASURED):** every boolean on it costs 1-7 s
  - batch cuts and fuses (one call, many tools), run `cad.screw_through`
  on a local piece; `fixTolerance(0.01)` the filleted body (its BOP check
  fails and booleans misfire); Shape.Volume differences are tens of mm3
  of noise (prove small cuts with probe points); cut grooves as the band
  less the body inset 0.5 mm, never with moved copies of the surface.
- **Human-design details (all in the example):**
  1. one spline body, every edge filleted 4.5 mm;
  2. a wedge side profile: low nose, the hood rising to the shoulder;
  3. a flat shoulder line the cabin sits on;
  4. a rear deck falling to a rounded tail;
  5. four wheel arches cut into the body, each well lined;
  6. a Coke-bottle plan: haunches over the axles, pinched doors;
  7. a separate two-tone lofted cabin keyed into the tub by a 1 mm lip and
     PINNED by four 3 mm pegs into bored bosses (a lip alone fails
     ./check's fastening gate: it lifts off);
  8. a raked windscreen and a fastback rear window;
  9. side windows; every pane a smoked insert cut square to its face;
  10. A-pillars and C-pillars;
  11. a rib from the roof onto the board's spine (0.2 mm off);
  12. stub axles and hub spacers;
  13. soft-square shaft holes for the motors;
  14. round headlights: clear light pipes with a retaining flange;
  15. chrome bezels in 1.1 mm counterbores;
  16. a recessed black grille insert, 0.8 mm behind the face;
  17. five grille slots, the middle one the ToF window (6.6 wide);
  18. a clear ToF lens filling that slot (a distance sensor sees through glass);
  19. tail lights as red inserts in the tail;
  20. a USB-C pocket with a liner 0.25 mm off the socket mouth;
  21. door seam grooves on both sides;
  22. door handle recesses;
  23. a hood panel line;
  24. "ATECH" debossed on the tail;
  25. side mirrors on stalks;
  26. wrap-around bumpers front and rear on brackets;
  27. a board cradle (ledge 0.1 mm under the board, a rim 0.3 mm round it, notched for the ribbon);
  28. four countersunk screws from below into heat-set insert bosses;
  29. a parting-line reveal groove round the tub over the seam;
  30. block-tread tyres, five-window rims, the centre cap fused into the rim.
- **Colours:** Body_Shell `toy_yellow`, Hardtop `matte_white`, Chassis
  `graphite`, Grille `matte_black`, panes `smoked` (+transparency), light
  pipes and ToF lens `glass`, bezels and screws `chrome`, tail lights
  `led_red`, tyres `rubber`, rims `brushed_alu`.

### 7.2 "an RC tank" - FLAT, the car's skeleton

**Example (R413): `examples/rc_tank.py`, CHECK PASS (./check 26 s MEASURED).** It keeps the car's
ToF and headlight routes (the block below with L = SHAFT_Z - 10.14 = 9.16), drops the
speaker / button / IMU, and runs two tracks (belt + tread pads, sprocket, idler,
road-wheel bogie) 222 mm long so the length is 1.6 x the width.

```python
L = 8.86; board.Placement = Placement(Vector(0, 0, L), FLAT)
mot_l = ap.seat(doc, "dc_motor", 1); mot_r = ap.seat(doc, "dc_motor", 9)   # rear drive sprockets
usb = ap.seat(doc, "usbc", 7); lamp_l = ap.seat(doc, "light", 6); lamp_r = ap.seat(doc, "light", 14)
spk = ap.seat(doc, "speaker", (10, 11))                                    # engine-deck grille
btn = ap.seat(doc, "button", 3); imu = ap.seat(doc, "orientation", 4)
eye, rib = ap.cable(doc, "distance_sensor", 8, ap.module_placement(
    "distance_sensor", (30, -131.4, L + 30), face="-Y", cable="-Z"))       # turret mantlet
```
- **Stack:** 118.3 x 136.8 x 42.2. **Product:** hull 107 W x ~150 L,
  tracks 12 wide each side -> ~131 W x 150 L x 55 H.
- **Human-design details:** 1. drive sprockets on the shafts
  (`cad.spur_gear`, bore 3.3); 2. an idler at the front; 3. 4-5 road
  wheels on stubs; 4. track link plates; 5. grousers on each link;
  6. return rollers; 7. a turret on a ring (fitted after); 8. a turret
  ring groove; 9. a gun barrel (`cad.pipe`); 10. a muzzle brake with slots;
  11. the ToF in the mantlet behind an open slot; 12. a commander's hatch
  with a hinge (`cad.pin_hinge`); 13. side skirts; 14. engine-deck louvres
  over the speaker (`cad.grille` slots); 15. headlight lenses on the
  glacis with guards; 16. tow hooks; 17. rivets along the hull; 18. an
  exhaust pipe; 19. a jerry can rack; 20. a rear USB-C pocket; 21. a
  start button cap on the hull; 22. panel lines on the glacis; 23. a
  driver's vision block; 24. an antenna; 25. a hull split with a lip and
  four screws; 26. lettering on the turret side.
- **Colours:** hull and turret `toy_green` (or `graphite`), tracks and
  sprockets `rubber` / `graphite`, barrel `satin_grey`, lenses `glass`,
  screws `chrome`.

### 7.3 "a little desk robot" - LANDSCAPE_UP torso, cabled screen face (examples/desk_robot.py, CHECK PASS)
```python
place_board(LANDSCAPE_UP, 0, None, 36)                 # x 0..120, z 36..96, face -Y
spk = ap.seat(doc, "speaker", (1, 2))                  # belly, hangs to z 15.4
btn = ap.seat(doc, "button", 3)
mic = ap.seat(doc, "microphone", (4, 5))
usb = ap.seat(doc, "usbc", 7)                          # left side, mouth -X
scr, scr_ribs = ap.cable(doc, "screen", (11, 12), ap.module_placement(
    "screen", (60, -24.5, 158.0), face="-Y", cable="-Z"),
    via=[(60, -4, 97), (60, -12, 119)])                 # up the neck, jogging forward to the visor
```
- **Product:** ~177 W (arms) x 92 D x 225 H. Torso 134 x 82 x 93 (depth /
  width 0.61, a crowned belly 5 mm proud, front silhouette corner r 14);
  head 132 x 70 x 90 (>= 40 % of the height, the hero) on a neck 48 x 20
  that carries both ribbons; a 100 x 60 smoked visor right in front of
  the screen.
- **Parts:** Torso_Back (fixed: back wall, board ledges top and bottom,
  standoffs 0.1 mm behind it), Torso_Front, Head_Front, Head_Back,
  Face_Plate (visor), Face_Bezel, Neck_Collar, Button_Cap, 2 arms, 2
  ears, 2 feet, 2 screws.
- **Body:** the torso plan is lines and ONE arc (the belly) and the core is
  `profile_body(..., inset=t)` through `cad.hollow` - a spline plan with a
  long straight back made every grille cut on the front INVALID (MEASURED,
  R270).
- **Human-design details (all in the example):**
  1. a deep torso with a crowned belly;
  2. a big head - the hero, wider than the torso is deep;
  3. a smoked visor over the cabled screen;
  4. a raised black visor bezel that replaces the head wall round it;
  5. a brushed neck pivot collar (turntable) with a spigot;
  6. a groove round the collar rim;
  7. the screen's two ribbons routed inside the neck;
  8. a round speaker grille over the measured surround;
  9. a speaker chamber tube from the wall to the driver;
  10. a mic pin-hole cluster (>= 3 % open);
  11. a ring rib sealing the mic;
  12. a raised ring round the mic;
  13. a key cap with a flange and a plunger;
  14. a raised ring round the button;
  15. a USB-C pocket in the left side with a liner;
  16. "ATECH" debossed on the chest;
  17. a rib from the front onto the board's spine;
  18. ledges over and under the board, standoffs behind it;
  19. two countersunk screws on the back into heat-set insert bosses;
  20. a hex vent field on the back;
  21. "ATECH" on the back;
  22. front/back halves keyed by a lip;
  23. a parting-line reveal round the head;
  24. one arm waving (clear of the USB-C), one down;
  25. shoulder discs pinned into soft-square holes;
  26. round hands;
  27. ear discs pinned into the head;
  28. an antenna with a ball;
  29. long feet pinned into the torso;
  30. two-tone shells (fronts white, backs sky).
- **Colours:** fronts `matte_white`, backs and arms `sky`, visor `smoked`
  (+transparency), bezel `matte_black`, collar `brushed_alu`, ears and key
  cap `coral`, feet `graphite`, screws `chrome`.

### 7.4 "a smart speaker" - FLAT, revolved puck with a light ring (examples/smart_speaker.py, CHECK PASS)
```python
L = 13.3                                               # board corners (r 67) clear the step floor
board.Placement = Placement(Vector(0, 0, L), FLAT)
spk = ap.seat(doc, "speaker", (11, 12)); mic = ap.seat(doc, "microphone", (4, 5))
vol_dn = ap.seat(doc, "button", 2); vol_up = ap.seat(doc, "button", 3)
usb = ap.seat(doc, "usbc", 7)
lights = [ap.seat(doc, "light", n) for n in (1, 6, 8, 9, 14)]   # r 50.6-54.1 from the board centre
```
- **Product:** 144 x 144 x 63.8 (feet included; height 0.44 x the
  diameter); `TALL = True`: 144 x 144 x 176 (1.2 x the width). The puck
  is centred on the board (30, -60) so the board corners (r 67) clear the
  inner wall (r ~70). The five lights sit at r 50.6-54.1: a ring r
  48.5..58.5 is over all of them.
- **Body:** ONE closed (radius, height) section of lines and tangent arcs
  (rolled top, barrel side, step edge, plinth) with the fabric grooves
  and the reveal notched INTO it - one revolve, no boolean (groove_ring on
  the revolved barrel made 12767 faces and 100 s, MEASURED R270).
- **Parts:** Base (fixed: floor, standoffs, fences), Shell, Top,
  Light_Ring, Gasket, Cap_Minus, Cap_Plus, 3 feet, 3 screws.
- **Human-design details (all in the example):**
  1. one revolved section with the walls in it;
  2. a barrel side (tangent arcs, no spline);
  3. a rolled top edge (r 10);
  4. a recessed dark plinth that makes it float;
  5. a step underside with a chamfer;
  6. fabric-like grooves round the band (in the section);
  7. a parting-line reveal over the plinth seam;
  8. a frosted light ring in the top (the lens of all five lights);
  9. a light pipe from the ring to each light;
  10. an aluminium top disc as its own part;
  11. a round speaker grille (133 holes);
  12. a driver chamber tube from the top to the speaker;
  13. a rubber gasket in the chamber's foot;
  14. a mic pin-hole cluster (>= 3 % open);
  15. a ring rib sealing the mic;
  16. volume key caps with flanges;
  17. plungers down to the buttons;
  18. raised - and + on the caps;
  19. raised rings round the keys;
  20. "ATECH" debossed on the top;
  21. a rib onto the board's spine;
  22. three bosses without gussets, each with a heat-set insert pocket;
  23. three countersunk screws from below;
  24. a lip keying the shell to the base;
  25. standoffs under the board and fences off its long edges;
  26. a USB-C pocket at the back with a liner;
  27. rubber feet in 1.2 mm recesses;
  28. "ATECH" debossed under the base.
- **Colours:** Shell `cream`, Top `brushed_alu`, Base and key caps
  `graphite`, Light_Ring `frosted` (+transparency), feet and gasket
  `rubber`, screws `chrome`.

### 7.5 "a handheld game console" - FLAT across the device, controls cabled to the thumbs (examples/handheld_console.py, CHECK PASS)
```python
ACROSS = Rotation(Vector(0, 0, 1), 90).multiply(FLAT)  # long side along X
board.Placement = ...                                   # centred: x -60..60, y -30..30, PCB top z 8
screen = ap.seat(doc, "screen", (11, 12))               # x -20..20, y 11..30: the centre line
usb = ap.seat(doc, "usbc", 4); led = ap.seat(doc, "light", 3)   # bottom edge, power LED
dpad, _ = ap.cable(doc, "button", 9, ap.module_placement("button", (-82, 28, 16.5), face="+Z", cable="+X"),
                   via=[(-50, 38.5, 15), (-52, 33, 19.5)])
btn_b, _ = ap.cable(doc, "button", 14, ap.module_placement("button", (82, 28, 16.5), face="+Z", cable="-X"),
                    via=[(50, 38.5, 15), (52, 33, 19.5)])
btn_a, _ = ap.cable(doc, "button", 8, ap.module_placement("button", (88.5, 0, 16.5), face="+Z", cable="-X"))
sh_l, _ = ap.cable(doc, "button", 10, ap.module_placement("button", (-70, 50, 12.75), face="+Y", cable="+X"),
                   via=[(-31, 40, 10), (-36, 47, 11), (-42, 50, 12)])   # and 13 mirrored for R
```
- **Product:** 207 x 97 x 27.3 (a Switch Lite is 208 x 91 x 14 + sticks);
  face 200 x 94, a 118 x 65 cover glass = 40 % of it; 25.5 thick at the
  face, grip bellies down to the desk, the back crowned 2.3 mm over the
  board.
- **Parts:** Back (fixed: pads under the board, fences at its ends),
  Front, Cover_Glass (clear), Bezel (black mask with the screen window and
  a rib onto the spine), DPad_Cap, A_Cap, B_Cap, L_Cap, R_Cap, LED_Pipe, 4
  feet, 4 screws.
- **D-pad (honest):** one button under a rocking cross cap - it reads
  "pressed", not the direction. Four directions need four button modules.
- **Human-design details (all in the example):**
  1. a crowned back;
  2. grip bellies down to the desk under each hand;
  3. soft 4 mm edges round the whole body;
  4. a black bezel mask under the cover glass;
  5. a clear window in it over the screen's active area;
  6. a raised rim round the cover glass;
  7. a cross D-pad cap with a flange and a plunger;
  8. round A / B caps with flanges and plungers;
  9. "A" / "B" debossed on the caps;
  10. arrows debossed on the D-pad;
  11. L / R shoulder keys standing in the top edge;
  12. a power LED light pipe;
  13. a USB-C pocket in the bottom edge with a liner;
  14. a parting-line reveal round the body;
  15. a battery door seam on the back;
  16. a door finger notch;
  17. a slot vent field on the back;
  18. four rubber feet on the bellies (the only thing touching the desk);
  19. a lanyard loop at a top corner;
  20. "ATECH" debossed under the window;
  21. four countersunk screws from the back into insert bosses;
  22. a rib under the bezel onto the board's spine;
  23. board pads and end fences in the back;
  24. a lip keying front to back;
  25. plungers under every key;
  26. a two-colour key set (red A / B, graphite D-pad and shoulders).
- **Colours:** body `toy_blue`, bezel `matte_black`, cover glass `smoked`
  (+transparency), A / B `signal_red`, D-pad and shoulders `graphite`, LED
  `led_green`, feet `rubber`, screws `chrome`.

### 7.6 "a weather station" - LANDSCAPE_UP with a sensor hut

**Example (R412): `examples/weather_station.py`, CHECK PASS (./check 25 s MEASURED).** The board
at z 22 (not 30), the keys on 3 + 4, the alert light on 9; the sensor's ribbon rises
straight from port 13 up a hollow post (bore >= 0.75 mm round it) into the hut.

```python
place_board(LANDSCAPE_UP, 0, None, 30)
scr = ap.seat(doc, "screen", (11, 12)); alert = ap.seat(doc, "light", 9)
mode = ap.seat(doc, "button", 3); nxt = ap.seat(doc, "button", 4); usb = ap.seat(doc, "usbc", 7)
th, rib = ap.cable(doc, "temp_humidity", 13, ap.module_placement(
    "temp_humidity", (90, -4.84, 120), face="-Y", cable="-Z"))   # straight rise into the hut
```
- **Stack:** 120.6 x 12.7 x 100.2. **Product:** (R610) a display body
  144 x 31 x 86 built upright and leaned back 12 deg as one Placement (the
  board through it, the cabled sensor too; `ibox()` measures a module
  back in the upright frame): three views - a soft front silhouette, a
  plan with a curved back, a wedge (deep at the foot, thin at the top,
  the top edge rolled) - standing in a sculpted foot (a spline
  cross-section: a lip in front, a backrest behind; a bowed plan), a
  louvred hut ~30 x 22 x 28 on top right.
- **Human-design details:** 1. stacked louvre slats on the hut; 2. a hut
  roof with overhang; 3. a wall between the hut and the electronics;
  4. a screen bezel with a 1 mm step; 5. weather icons debossed by the
  screen; 6. two key caps under the screen; 7. an alert LED lens; 8. a
  sloped wedge foot; 9. rubber feet; 10. a vent row along the bottom;
  11. a cable exit with strain relief on the left; 12. a USB-C pocket;
  13. a front/back split with a lip; 14. screws on the back; 15. a
  wall-hang keyhole; 16. a rib onto the spine; 17. "ATECH" on the foot;
  18. soft outer fillets; 19. a sun shade over the screen; 20. the
  ribbon routed inside the hut post; 21. a hut drip edge; 22. a label
  recess; 23. chamfered openings; 24. grip grooves on the foot's back edge;
  25. two-tone body and hut.
- **Colours:** body `matte_white`, hut `cream`, foot `graphite`, screen
  bezel `matte_black`, LED `led_blue`.

### 7.7 "an alarm clock" - LANDSCAPE_FRONT clock radio

**Example (R410): `examples/alarm_clock.py`, CHECK PASS (./check 28 s MEASURED).** The board at
(10, 28), the speaker on 13-14, the screen on 9-10 and an alarm LED on 3 behind ONE
smoked lens (53 % of the front), keys 6 + 5, USB-C on 8 (left side), the snooze button
cabled from 2 (face +Z, cable -Y, centre y 30: one flat bend behind the board); the
whole build is tilted back 12 deg with one Placement (TILT) set on the board BEFORE
seating, multiplied into the cabled module's placement, and applied to every part.

```python
place_board(LANDSCAPE_FRONT, 0, None, 24)
spk = ap.seat(doc, "speaker", (13, 14)); scr = ap.seat(doc, "screen", (9, 10))
set_a = ap.seat(doc, "button", 2); set_b = ap.seat(doc, "button", 1); glow = ap.seat(doc, "light", 5)
usb = ap.seat(doc, "usbc", 7)
snz, rib = ap.cable(doc, "button", 4, ap.module_placement(
    "button", (50, -32, 96), face="+Z", cable="+Y"))             # top snooze bar
```
- **Stack:** 120.6 x 44.2 x 97.6. **Product:** ~127 x 50 x 104, wedge
  front. The snooze ribbon twists 180 degrees (cosmetic; flip `cable`).
- **Human-design details:** 1. a grille on the left; 2. the display on
  the right with a smoked lens; 3. a wide snooze bar cap riding on the
  top button; 4. "AL" / "SET" debossed keys; 5. a night-light diffuser;
  6. a sloped front; 7. a rear kickstand; 8. rubber feet; 9. a parting
  groove; 10. a USB-C pocket at the back; 11. a rib onto the spine;
  12. key caps with flanges and plungers; 13. a snooze bar guide slot;
  14. a split with a lip; 15. back screws; 16. vent slots; 17. a carry
  notch; 18. rounded corners r 10; 19. a chrome-ring speaker trim;
  20. lettering on the top; 21. a cable groove; 22. chamfered openings;
  23. a frosted glow band; 24. soft fillets on every outer edge;
  25. a two-tone shell.
- **Colours:** body `orange` or `cream`, grille insert `graphite`, lens
  `smoked`, glow `frosted`, keys `matte_white`, feet `rubber`.

### 7.8 "a bedside lamp" - UPRIGHT_FRONT column with a globe (examples/bedside_lamp.py, CHECK PASS)
```python
place_board(UPRIGHT_FRONT, 0, None, 20)                           # x 0..60, z 20..140, face -Y
usb = ap.seat(doc, "usbc", 2)                                     # right side, mouth +X
glow_r = ap.seat(doc, "light", 5); glow_l = ap.seat(doc, "light", 13)   # behind the light bar
top_light, _ = ap.cable(doc, "light", 8, ap.module_placement(
    "light", (30, -4.8, 185), face="-Y", cable="-Z"))             # straight up the neck into the globe
btn, _ = ap.cable(doc, "button", 7, ap.module_placement(
    "button", (30, -50, 9.5), face="+Z", cable="+Y"))             # down into the foot, facing up
```
- **Product:** 120 x 120 x 277: a foot r 60 x 19, a cove into a column r
  35 (the board stands in it), a rolled shoulder, a neck r 13 carrying
  the ribbon, a frosted globe r 52 on a brass gallery.
- **Body:** ONE closed (radius, height) section of lines and concentric
  arcs - foot, cove, column, shoulder, neck, with the reveal and the
  column bands notched into it - revolved, split low in the foot.
- **Parts:** Base (fixed: floor, a plate with standoffs behind the board,
  posts under it), Shell, Globe, Light_Window, Gallery, Badge, Finial,
  Button_Cap, Ring_Foot, 3 screws.
- **Human-design details (all in the example):**
  1. a flared foot;
  2. rolled foot edges;
  3. a cove from the foot into the column;
  4. a turned column;
  5. a rolled shoulder;
  6. a neck cove;
  7. a frosted globe diffuser;
  8. the globe's collar on the gallery;
  9. a brass gallery ring keyed into the neck;
  10. a brass finial pinned through the globe's pole;
  11. a solid frosted light bar over the two front lights (a sector cut: no slivers);
  12. a brass badge inset in the column, lettered;
  13. a parting-line reveal on the foot;
  14-15. two bands round the column;
  16. a touch key cap in the foot's top;
  17. a raised ring round it;
  18. a plunger to the button;
  19. a USB-C pocket in the side with a liner;
  20. slot vents on the back;
  21. "ATECH" on the foot;
  22. a rib onto the board's spine;
  23. a plate with standoffs behind the board, posts under it;
  24. three countersunk screws from below into heat-set insert bosses;
  25. a lip keying the shell to the base;
  26. a rubber ring foot in a recess;
  27. the light's ribbon hidden inside the neck.
- **Colours:** shell `cream`, globe and light bar `frosted`
  (+transparency), gallery, badge, finial and key `brass`, base
  `graphite`, ring foot `rubber`, screws `chrome`.

### 7.9 "a doorbell" - UPRIGHT_FRONT wall unit
```python
place_board(UPRIGHT_FRONT, 0, None, 4)
ring = ap.seat(doc, "button", 7); glow_l = ap.seat(doc, "light", 9); glow_r = ap.seat(doc, "light", 1)
motion = ap.seat(doc, "distance_sensor", 8); mic = ap.seat(doc, "microphone", (4, 5))
usb = ap.seat(doc, "usbc", 11)
```
- **Stack:** 61.0 x 13.3 x 120.7. **Product:** 67 x 22 x 127 (a Ring
  doorbell is 62 x 22 x 128).
- **Human-design details:** 1. a big round bell cap (18) with a plunger;
  2. a translucent halo ring fed by the two lights; 3. light pipes to the
  halo; 4. an open sensor window at the top (no glass); 5. a dark visor
  around it; 6. mic pin holes and a ring rib; 7. a wall back-plate
  (fixed); 8. two countersunk screw slots in it; 9. the front shell
  clipped on (`cad.snap_fit_pair`); 10. a rain lip over the button;
  11. a security screw at the bottom; 12. a USB-C pocket; 13. a cable
  channel in the back plate; 14. soft fillets; 15. a recessed name plate;
  16. a chamfered bell opening; 17. a split line; 18. a drip edge at the
  bottom; 19. a rib onto the spine; 20. lettering; 21. a level bubble
  recess; 22. a wedge spacer option; 23. vent slots underneath;
  24. matching radius on every corner; 25. a two-tone face.
- **Colours:** shell `satin_grey`, face `matte_black`, halo `led_white`,
  bell cap `brushed_alu`, plate `graphite`.

### 7.10 "a plant monitor" - UPRIGHT_FRONT stake
```python
place_board(UPRIGHT_FRONT, 0, None, 60)                          # 60 mm spike below
scr = ap.seat(doc, "screen", (13, 14)); th = ap.seat(doc, "temp_humidity", 6)
mood = ap.seat(doc, "light", 4); btn = ap.seat(doc, "button", 11); usb = ap.seat(doc, "usbc", 7)
```
- **Stack:** 60.8 x 12.7 x 120.6 (z 59.4..180). **Product:** a tag 67 x
  19 x 127 + a 60 mm spike -> ~187 tall. USB-C points down: run a cable
  channel through the spike's back. **No soil-moisture module exists:**
  the spike is mechanical only - say so.
- **Human-design details:** 1. a leaf-shaped top; 2. vent slots by the
  sensor; 3. a second vent below; 4. a portrait gauge bezel; 5. a mood
  LED in a leaf-vein lens; 6. a spike with a ribbed cross-section; 7. a
  drip-line groove; 8. a cable channel; 9. a key cap; 10. a split with a
  lip; 11. back screws; 12. a rib onto the spine; 13. a hanging hole;
  14. leaf veins debossed; 15. a stalk transition (`cad.loft`); 16. soft
  fillets; 17. lettering; 18. a label recess; 19. a water-line mark;
  20. a USB-C pocket at the bottom; 21. chamfered openings; 22. a
  rounded spike tip; 23. a stop collar on the spike; 24. a two-tone
  leaf; 25. a matte back.
- **Colours:** leaf `toy_green` / `mint`, spike `graphite`, bezel
  `matte_black`, mood lens `led_green`.

---

### 7.11 "a small desk fan" - FLAT foot, motor cabled up a stem (examples/desk_fan.py, R411)
```python
board.Placement = Placement(Vector(0, 0, 8.5), FLAT)
key = ap.seat(doc, "button", 6); glow = ap.seat(doc, "light", 14); usb = ap.seat(doc, "usbc", 1)
motor, rib = ap.cable(doc, "dc_motor", 7, ap.module_placement(
    "dc_motor", (30, -37.85, 125), face="+Z", cable="+Y"),        # pins back: the shaft points -Y
    via=[(30, 8, 20), (30, 9, 60), (30, 9, 104)])                 # up a 17.2 mm stem bore at y 9
```
- **Product:** 160 x 161 x 206: a foot 80 x 160 x 25, a stem r 11, a tilt collar,
  a revolved pod r 19.5, a guard r 80 (>= 60 % of the front), six blades pitched 12 deg.
- **MEASURED:** ./check 17 s; the ribbon twists 90 deg inside the round stem
  (14 wide: a round bore takes it); a disc bulkhead across the pod read as a 35 mm
  hole through three walls - hold the motor with ribs 0.3 mm off it instead.
- **Human-design details (all in the example):**
  1. a front guard ring;
  2. twelve radial bars;
  3. two concentric rings;
  4. a rim band hooked behind the rear guard, pinned;
  5. a rear guard with twelve radial bars, pinned to the pod;
  6. a domed coral centre badge;
  7. six wide pitched blades on a domed hub (the rotor, its own part);
  8. a revolved motor pod with a rolled nose;
  9. a domed rear cap;
  10. the cap's screw into a pad on the axis;
  11. a brushed tilt collar across the stem;
  12. tilt knobs on both ends;
  13. grooves round the collar;
  14. a hollow chrome stem;
  15. a raised socket ring where the stem meets the foot;
  16. a long foot with chamfered top edges and soft fillets;
  17. a power key cap with a flange and a plunger;
  18. a raised ring round it;
  19. a frosted glow lens (a light pipe with a flange);
  20. a raised ring round it;
  21. "ATECH" on the foot's nose;
  22. a USB-C pocket with a liner in the left side;
  23. slot vents on the foot's back;
  24. four rubber feet in recesses;
  25. four countersunk screws under the foot into heat-set insert bosses;
  26. the motor ribbon run inside the stem, collar and neck;
  27. ribs holding the motor 0.3 mm off its body;
  28. a rib onto the board's spine;
  29. standoffs and fences under the board;
  30. a lip keying the foot shell to the base.
- **Colours:** foot shell and pod `mint`, base and cap `graphite`, guards, stem
  and key `chrome`, blades `sky`, badge `coral`, collar `brushed_alu`, lens
  `frosted` (+transparency), feet `rubber`, screws `chrome`.

## 8. Unknown - never fill with a guess

The knob's connector, the button's travel, the microphone's port position,
a soil-moisture or stepper-driver module, the pin-1 order, module
retention, and ports 8/12 as special. Say what is unknown in the reply.

---

## 9. Cable for ergonomics (R270)

Seated modules land where the BOARD is; a product puts its controls,
lights and sensors where HANDS and EYES are. `ap.cable` moves a module
there. Rules MEASURED on the five examples:

1. **Decide the touch points first** (thumbs, the face, the nose, the
   shade), then pick each module's port by its exit: a port's ribbon
   leaves OUTBOARD along the board, ~3.7 mm straight. FLAT: ports 1-6 /
   9-14 exit -Y / +Y with the plug's width along the columns; 7 / 8 exit
   along the board's length (width across it).
2. **Twist-free first:** `face x cable` parallel to the plug's width.
   A button facing +Z beyond an END port, its pins pointing back at the
   port (`cable` = toward the board), needs NO bend: the socket meets the
   plug's lead (handheld A on port 8). A light facing -Y straight above
   the top-centre port of an upright board is a straight rise (lamp).
3. **A 90-degree twist is fine** when the route has room (>= 30 mm): the
   handheld's D-pad (port 9 -> the left thumb), B (14) and the shoulder
   keys (10, 13) all twist. Give 2-3 `via` points along the route you
   want: with none, the spline overshoots (a lamp ribbon dropped to
   z -95 and lost its ribbon solid, MEASURED).
4. **Route under or over, never through:** a ribbon under its own module
   must stay >= 1.5 mm below it (the handheld's A came 1 mm too close
   when the module sat over the plug - 91 sampled points inside).
5. **Hairpins (U-turns) want height:** a U in the plane of the ribbon's
   flat side needs ~2 x 4 mm; an edgewise U needs radius >= 7 (half the
   14 mm width) and still looks wrong - prefer a route with one turn.
6. **Plan the room before the body:** list every ribbon's corridor and
   keep the shell, bosses, ribs and the other ribbons out of it; a
   screen cabled to a head jogs forward INSIDE the neck (desk_robot.py:
   the neck is 20 deep for that).
7. **Held products:** thumbs at about +-(40-45 %) of the width from the
   centre, controls >= 3 mm from the window's edge, shoulder keys in the
   top edge standing on their side (face +Y) - all cabled; the board
   stays in the middle under the window.

---

## 10. Robust body recipes (R270)

Round 1 lost most of its hour to the body: ~15 profile_body fillet
failures, ~14 split failures ("section is solid", "lip wall too thin"),
"every rung failed" hollows, zero-volume lofts, a cusp offset, and 24
"cut: the tools removed nothing". The five examples use only these:

1. **Lines + arcs outlines** (`spline=False`; `("arc", mid, end)` items
   or straight facets): `cad.profile_body(side, plan, spline=False,
   fillet=r)`, hollowed with its OWN core through `cad.hollow(body, 2,
   core=lambda t: cad.profile_body(side, plan, spline=False, fillet=r,
   inset=t))` (the car, the robot torso, the handheld). A plan corner of
   6 straight facets is safer than an exact arc on a large body (the
   handheld's arc plan made a 3.2 mm3 cut remove 0.36 mm3, MEASURED).
2. **Revolve** anything round: ONE closed (radius, height) section with
   both skins in it (outer up, inner back down, concentric arcs) -
   `cad.revolve_profile(section, at=axis)` is already hollow, fair and
   instant (speaker 0.3 s, lamp 0.2 s). Grooves and reveals are notches
   in the section.
3. **`cad.shell_body(side, plan, wall, split_z=..., fillet=...)`** (WS2,
   R270): profile_body + hollow + split with a lip in ONE call, every
   step on its fallback ladder. Use it when the kit lists it (`help(cad)`
   / the helper card shows `cad.shell_body(`); if it raises or is
   missing, FALL BACK to recipe 1 written out (profile_body, hollow with
   the inset core, `cad.split(..., lip=1.2)`) exactly as the examples do.
4. **Split 0.3-1 mm inside the cavity**, never on a wall's inner face,
   and below / behind every module's slide corridor (car: z 11.5; robot:
   board back - 0.3; speaker and lamp: low in the plinth / foot).
5. **Fillet in profile_body, before any cut**, never a fillet on a
   spline-on-spline body after it (they tessellate lumpy and fail).
6. **Inserts** (glass, grilles, bezels, badges, light rings): `piece =
   shell.common(cutter); shell = shell.cut(cutter)` - one cutter through
   ONE wall (a cutter across a cabin cuts the ribs inside it too).

