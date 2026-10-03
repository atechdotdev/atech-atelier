# Atech module assembly — how modules connect to the board

**Source:** David, 2026-09-24 (stated directly). The "Measured" section below
was added the same day from the shipped meshes (not from hardware).
Anything below marked **OPEN** is not known yet. Do not fill it with a
plausible number — leave it open and ask (failure pattern P1).

## The electrical interface: 6 pins per port

Every port carries the same six signals:

| # | signal |
|---|---|
| 1 | DATA1 |
| 2 | DATA2 |
| 3 | GND |
| 4 | 3.3 V |
| 5 | 5 V |
| 6 | 12 V |

- **Board side (the port):** room for **6 female pins** (sockets).
- **Module side:** for each port it uses, a module carries **6 male pins**.
- A module connects by its 6 male pins **sliding into** the port's 6 female
  pins.

The table order is the order David listed the signals in. **OPEN:** whether
that is also the physical pin order along the connector, and which end is
pin 1.

## How a module goes on: slide-in

- Modules **slide in from the side** of the board. The motion is a straight
  slide parallel to the board, not a push down onto the board.
- **Exception, 14-port board:** **ports 7 and 8 slide in from the top and the
  bottom** instead of from the sides.
- **Travel ends at full engagement:** the module **stops once its male pins
  are fully seated in the female pins**. The seated position is the assembled
  position. A module sitting short of that (pins partly in) is not assembled,
  and one that travels past it is interference.

## What this means for CAD

- **Assembly check:** a placed module is correct only if its 6 male pins sit
  inside the port's 6 female pins at full insertion depth, with the module
  against its stop. "The bodies don't overlap" is not enough. A module that
  merely touches the board passes that test while being unplugged (see the
  "wheel bolts engage nothing" failure in CLAUDE.md).
- **Joint:** model the module-to-port joint as a **prismatic (slide) joint**
  along the port's insertion axis: sideways for most ports, vertical for
  ports 7 and 8 on the 14-port board. The travel limit is the seated
  position.
- **Clearance:** each module needs a clear slide path along its insertion axis
  from outside the board to the seated position. Anything in that path blocks
  assembly, even if the seated positions do not collide.
- **Current code:** `projects/atech_ports.py` (2026-09-24) seats modules on
  numbered ports and checks all three rules below; see "Measured".
  `projects/atech_modules.py` still places modules by packing meshes along the
  board — its modules sit at Y = 3.989 (the board's bbox top), 3.99 mm above
  the PCB, with no pin in any contact. It cannot check the rules above.

## Measured (2026-09-24)

Everything here was measured off the shipped meshes; the commands and raw
output are in `docs/verification/2026-09-24_atech_ports.md`. Coordinates are
the board STL frame (`motherboard_14_port.stl`): X across the board
(0..60), Y up out of the PCB, Z along the board (0..120), mm.

### Which mesh is trusted for what

- `models/stl/motherboard_14_port.stl` — housing **envelopes** are right, but
  the triangulation is broken: housing components report
  `hasSelfIntersections() == True` and their inner faces are fan-triangulated
  across concave outlines (a vertical ray finds a "floor" sloping from Y 0.09
  to 2.09 mm). It contains **no female contacts**. Used for display only.
- `models/glb/frame-2.glb` — the same board (its silkscreen reads
  "Frame V2.1"), clean, with materials. Its `socket` material holds the 14
  housings **and 84 separate female fork contacts**. This is the geometry of
  record for contacts and obstacles.
- The two are tied by measurement: GLB → STL is a pure translation of
  **(+30.000, −2.500, +60.000) mm** (difference of bbox minima), after which
  every one of the 14 housings coincides on all six bbox faces to
  **≤ 0.0031 mm**. `atech_ports.measure_board()` re-does this on every run
  and raises `GeometryMismatch` above 0.05 mm.

### Port numbering — read from the board's own silkscreen

The GLB silkscreen text, rendered top-down
(`docs/verification/2026-09-24_atech_ports_silkscreen.png`), viewed from +Y
with −Z up (the text reads unmirrored that way):

```
          -Z (top edge)
   1       7        9
   2               10
   3               11
   4               12 reset
   5               13
   6       8 USB   14
          +Z (bottom edge)
  -X (left)      +X (right)
```

Same as `backend/motherboard/board.yaml` and `atech_docs/.../14_port.md`.

### Port table (derived by `atech_ports.port_table()`)

Every port: a **15.64 × 8.50 × 2.40 mm** housing standing on the PCB
(underside Y = −0.003), with **6 fork contacts at 2.54 mm pitch** inside.
The contacts' solder tails leave the **inboard** face, so the **mouth faces
outboard** — the module travels mouth → tails.

| port | edge (module comes from) | insertion axis (module travel) | mouth plane | connector centre |
|---|---|---|---|---|
| 1 | left | +X | X = 8.273 | Z = 10.000 |
| 2 | left | +X | X = 8.273 | Z = 30.000 |
| 3 | left | +X | **X = 8.171** | Z = 50.000 |
| 4 | left | +X | **X = 8.222** | **Z = 70.199** |
| 5 | left | +X | **X = 8.222** | **Z = 90.100** |
| 6 | left | +X | X = 8.273 | Z = 109.999 |
| 7 | top | +Z | Z = 8.273 | X = 30.001 |
| 8 | bottom | −Z | Z = 111.727 | X = 30.000 |
| 9–14 | right | −X | X = 51.729 | Z = 10.001, 30.001, 50.000, 70.000, 90.000, 110.000 |

Source of every cell: GLB housing + contact geometry (edge/axis from the tail
side; mouth = housing face opposite the tails; centre = mean of the 6 contact
centres); number from the silkscreen. Ports 3, 4, 5 are **off the grid** the
other eleven sit on (X −0.10/−0.05/−0.05, Z 0/+0.20/+0.10 mm) in **both**
meshes.

### The female side (per contact, measured from the mouth plane inward)

| | mm |
|---|---|
| contact envelope | 1.40 (Y) × 2.00 (row) × 9.90 (axis), incl. tail |
| fork starts | 1.60 inside the mouth |
| fork base (pin would bottom here) | 6.66 inside the mouth |
| tail ends | 11.50 inside the mouth (past the housing's inner face at 8.50) |
| tine height band | Y 1.000 .. 1.403 above the PCB |
| entry holes | 6, chamfered, in a 0.84 mm front plate; clear aperture ≈ Y 0.9..1.5 at the pin centreline |

### The male side (same in every module that has one)

Measured in the module STLs (button, light, usbc, orientation,
temp_humidity, distance_sensor, dc_motor: 1 connector; screen, microphone,
speaker: 2 connectors **20.00 mm apart** — the same as the 20.0 mm port pitch):

- A 6-pin **2.54 mm header lying flat under the module PCB**: plastic body
  15.24 × 2.54 × 2.54 mm, pins **0.64 mm square**, pitch 2.54 mm.
- Pins joggle: the rear part is a solder tail against the PCB underside; the
  **mating part runs at header mid-height** (0.95..1.59 above the module's
  bottom face) and protrudes **5.84 mm** beyond the header's front face.
- Under the PCB the module has an **open-ended channel 15.64 mm wide** —
  exactly the housing width (zero side clearance) — that the housing slides
  into. The channel is open at the mating edge and closed at the back.

### The seat

- **What forms the stop:** the header body's front face meeting the housing's
  mouth face. It is the first rigid contact along the travel (nothing else on
  the module or board is met earlier — the slide-path check is what proves
  that, per module, per port).
- **Seated state (all 14 ports, 1-connector modules):** pin centre 1.267 mm
  above the PCB (inside the 1.000–1.403 tine band); pin **4.244 mm** into the
  fork; **0.824–0.831 mm** short of the fork base (pins do not bottom out);
  row error ≤ 0.004 mm.
- **Vertical datum:** the module's bottom face rests on the PCB (Y = −0.003).
  Clearances that follow: housing top 2.399 vs module PCB underside 2.537 →
  **0.138 mm**; frame ledge just inboard of the housing (GLB, top Y = 2.50
  at X 17–20, probed on port 2's rows only) vs module PCB underside →
  **0.037 mm**. (The interference check passes it: 0.037 mm is inside its
  0.05–0.10 mm contact tolerance, so treat it as "touching", not "clear".)
- **Travel from clear-of-board to seated:** 19.12 mm for a 19.5 mm module
  (recorded on each seated object as `AtechSlideOut`).
- **Neighbour gaps along a column:** 0.50 mm on the 20.0 mm grid; 0.70 mm
  between 3 and 4; 0.40 mm between 4–5 and 5–6.
- **Multi-connector modules on ports 3/4/5:** a rigid 2-connector module
  cannot seat both connectors: it stops at the first mouth, leaving the other
  connector **0.102 mm** (pair 2,3) or **0.051 mm** (pairs 3,4 and 5,6) short
  of its mouth. Where the pair's pitch is 20.2 / 19.9 mm, the zero-clearance
  rails also overlap the housing side by 0.05–0.10 mm (at the check's
  resolution). All other pairs (1,2), (4,5)\*, (9,10) … (13,14) seat.
  \*speaker on (4,5): seated, but a 0.05 mm side sliver is reported.
- **Overhang:** modules longer than one cell hang **outboard**, off the board
  edge: speaker X −20.6 (ports 1,2), dc_motor X −29.2. This contradicts
  `atech-artifacts/docs/MODULE_MATING_GEOMETRY.md` Q1 (speaker reaching
  inboard into port 7), which used a different mating orientation.

### Pin order — the two sources disagree

David's list above is DATA1, DATA2, GND, 3.3 V, 5 V, 12 V.
`atech_docs/.../14_port.md` gives pins 1–6 as HV (12 V), 5 V, 3.3 V, GND,
Data A, Data B — the **exact reverse** of David's sequence. Neither says which
physical end of the row is pin 1, and no pin-1 key or asymmetry exists in
either mesh (the six contacts and six pins are identical). **Still OPEN.**

## OPEN — still unknown

- **Pin-1 end of the row**, and therefore which physical pin carries which
  signal (see "Pin order" above — two sources, opposite orders).
- **Ports 3, 4, 5 off the grid** (0.05–0.20 mm): is that the real board, or an
  export artefact present in both meshes? Settles whether 2-connector modules
  can use pairs (2,3), (3,4), (5,6). Measure a real board's housing positions.
- **Port 8 and port 12 as module slots.** Geometry: full, identical housings.
  `board.yaml`: "reserved and cannot host modules". `14_port.md`: port 8 takes
  the USB-C module; both have power, data lines reserved. The library lets
  any module seat on either; the rule belongs to whoever owns the port map.
- **Retention.** No latch, detent or friction feature exists in any mesh;
  only the fork contacts' grip holds a module. Is that the design?
- **Knob** — its STL has no header or pins at all, so it cannot be seated
  (`NoConnector`). Needs a mesh with its connector.
- Contact normal force / insertion force; current rating per pin (12 V pin).
- Port layout on boards other than the 14-port board.
- Everything here is measured off **CAD meshes**, not off hardware. The
  0.037 mm ledge clearance and the 0 mm rail-to-housing clearance in
  particular are below any print or moulding tolerance and need a physical fit
  check.

## Superseded OPEN items (answered by measurement above)

- Pin pitch / section / insertion depth → 2.54 mm, 0.64 mm square, stop at
  header-on-mouth with 4.24 mm in the fork.
- Which edge each port is on → port table; "top/bottom" for 7 and 8 are the
  board's own in-plane edges (−Z / +Z), not up/down.
- What forms the stop → the header body against the housing mouth.
