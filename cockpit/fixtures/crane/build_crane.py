#!/usr/bin/env freecadcmd
"""
ATL-CRANE-003 -- bench lattice gantry crane, PLA, 2 kg x 400 mm.
Runs INSIDE freecadcmd (FreeCAD 1.1.3). ADR-001: FreeCAD is the locked kernel.

Real lattice structure: chords and diagonal bracing are built as a fused tube
network, NOT cut from a solid web. Emits BREP per part + parts.json.

    CRANE_OUT=<dir> freecadcmd build_crane.py
"""
import os, sys, json, math

HERE = os.path.dirname(os.path.abspath(__file__))
OUT  = os.environ.get("CRANE_OUT", os.path.join(HERE, "build"))
os.makedirs(OUT, exist_ok=True)

import FreeCAD as App
import Part
from FreeCAD import Vector as V

def load_params():
    import yaml
    with open(os.path.join(HERE, "params.yaml")) as f:
        return yaml.safe_load(f)

P = load_params()

def solve_params(P):
    """Derive every dimension that MUST agree with the duty requirement.

    CLAUDE.md: "Never type a number that has to agree with something else."
    boom length IS the reach; mast height IS lift + stack-up. Typing them
    separately means a refit can silently leave them inconsistent -- the
    geometry would build fine and be wrong.

    Returns the list of derivations so the UI can show WHY a value is what it
    is, and so a diff can show what a parameter edit propagated to.
    """
    d = P['duty']
    log = []
    def setv(path, val, why):
        node = P
        parts = path.split('.')
        for k in parts[:-1]: node = node[k]
        old = node[parts[-1]]
        node[parts[-1]] = val
        log.append(dict(path=path, old=old, new=val, why=why))

    # jib length is the reach, by definition
    setv('boom.length_mm', float(d['reach_mm']),
         'boom.length_mm := duty.reach_mm')

    # mast must clear: lift travel + carriage + hook stack + deck + head
    stack = (P['carriage']['body_h_mm'] + P['hook']['cheek_h_mm']
             + P['hook']['shank_len_mm'] + P['hook']['throat_mm'] + 30.0)
    setv('mast.height_mm', round(float(d['lift_height_mm']) + stack, 1),
         'mast.height_mm := lift %.0f + carriage/hook stack %.0f' % (d['lift_height_mm'], stack))

    # screw spans the travel plus bearing allowances
    setv('screw.travel_mm', float(d['lift_height_mm']),
         'screw.travel_mm := duty.lift_height_mm')
    setv('screw.length_mm', round(float(d['lift_height_mm']) + 70.0, 1),
         'screw.length_mm := travel + 70 (bearings, nut, runout)')

    # SWL is DERIVED from the duty, never chosen
    d.setdefault('swl_n', 0.0)
    setv('duty.swl_n', round(float(d['payload_kg']) * 9.80665, 2),
         'duty.swl_n := payload_kg x g')
    return log

DERIVED = solve_params(P)
PARTS, JOINTS, MATES = [], [], []
RING_PLANE = 0.0
RING_FACE  = 0.0

def emit(pid, name, shape, material, process, **kw):
    PARTS.append(dict(id=pid, name=name, shape=shape, material=material,
                      process=process, transform=kw.pop('transform',[0.0,0.0,0.0]), **kw))

def tube(p0, p1, d):
    """A structural member between two points. Returns None if degenerate."""
    v = p1.sub(p0); L = v.Length
    if L < 1e-6: return None
    return Part.makeCylinder(d/2, L, p0, v.normalize())

def truss(nodes_a, nodes_b, chord_d, brace_d, close_ends=True):
    """Build a planar/box truss from two chord node lists. Real diagonals."""
    solids = []
    for nl in (nodes_a, nodes_b):
        for i in range(len(nl)-1):
            t = tube(nl[i], nl[i+1], chord_d)
            if t: solids.append(t)
    # verticals + alternating diagonals -- the actual bracing
    for i in range(len(nodes_a)):
        t = tube(nodes_a[i], nodes_b[i], brace_d)
        if t: solids.append(t)
    for i in range(len(nodes_a)-1):
        if i % 2 == 0: t = tube(nodes_a[i], nodes_b[i+1], brace_d)
        else:          t = tube(nodes_b[i], nodes_a[i+1], brace_d)
        if t: solids.append(t)
    return solids

def log(msg):
    print("[build] "+msg); sys.stdout.flush()

def fuse(solids):
    """Fuse a member list.

    OCCT's multiFuse over ~100 tube solids is superlinear -- the lattice mast
    measured 2.5 min as one call. Fusing in a balanced binary tree keeps each
    boolean small and cuts that to seconds. Same result, different schedule.
    """
    solids = [s for s in solids if s is not None]
    if not solids: return None
    while len(solids) > 1:
        nxt = []
        for i in range(0, len(solids)-1, 2):
            nxt.append(solids[i].fuse(solids[i+1]))
        if len(solids) % 2: nxt.append(solids[-1])
        solids = nxt
    r = solids[0].removeSplitter()
    # Unwrap unconditionally: FreeCAD 1.1.3 returns a Compound from every
    # boolean and removeSplitter() does not undo it (docs/GOTCHAS.md #2).
    # A Compound has no CenterOfMass, so every mass query downstream fails.
    if r.ShapeType == 'Compound':
        sol = r.Solids
        if len(sol) == 1:
            r = sol[0]
        elif len(sol) > 1:
            # genuinely disconnected -- fuse once more, then unwrap again
            r = sol[0].multiFuse(sol[1:]).removeSplitter()
            if r.ShapeType == 'Compound' and len(r.Solids) >= 1:
                r = r.Solids[0] if len(r.Solids) == 1 else r
    return r

# ---------------------------------------------------------------- BASE -------
def make_base():
    log("base...")
    b = P['base']
    L, W, T = b['plate_l_mm'], b['plate_w_mm'], b['plate_t_mm']
    plate = Part.makeBox(L, W, T, V(-L/2, -W/2, 0))
    # bench bolt holes
    for sx in (-1,1):
        for sy in (-1,1):
            h = Part.makeCylinder(b['bolt_dia_mm']/2, T*3,
                                  V(sx*b['bolt_span_x_mm']/2, sy*b['bolt_span_y_mm']/2, -T))
            plate = plate.cut(h)
    # stiffening ribs under the slew ring
    rh, rt = b['rib_h_mm'], b['rib_t_mm']
    ribs = []
    for a in range(4):
        ang = math.radians(45+90*a)
        r0 = V(0,0,-rh); dirv = V(math.cos(ang), math.sin(ang), 0)
        rib = Part.makeBox(L*0.42, rt, rh, V(0,-rt/2,-rh))
        rib.rotate(App.Vector(0,0,0), App.Vector(0,0,1), 45+90*a)
        ribs.append(rib)
    plate = fuse([plate]+ribs)
    # central boss for the slew bearing
    s = P['slew']
    boss = Part.makeCylinder(s['outer_dia_mm']/2+8, 10, V(0,0,T))
    boss = boss.cut(Part.makeCylinder(s['inner_dia_mm']/2, 60, V(0,0,T-2)))
    plate = fuse([plate, boss])
    emit('base_plate','Base Plate (bolts to bench)', plate, P['materials']['structure'],'FDM')
    return T+10

# ---------------------------------------------------------------- SLEW -------
def make_slew(z0):
    log("slew...")
    s = P['slew']
    ro, ri, h = s['outer_dia_mm']/2, s['inner_dia_mm']/2, s['height_mm']
    ring = Part.makeCylinder(ro, h, V(0,0,z0)).cut(Part.makeCylinder(ri, h*4, V(0,0,z0-h)))
    emit('slew_ring','Slew Bearing Race', fuse([ring]), 'STEEL_A2','COTS')

    # slew ring gear -- real teeth as radial features
    dsl = P['drive_slew']
    m, zt, fw = dsl['gear_module_mm'], dsl['ring_teeth'], dsl['face_width_mm']
    pitch_r = m*zt/2
    z_ring_plane = z0 + h
    gear = Part.makeCylinder(pitch_r+m, fw, V(0,0,z_ring_plane))
    gear = gear.cut(Part.makeCylinder(ri, fw*4, V(0,0,z_ring_plane-fw)))
    teeth=[]
    for i in range(zt):
        a = 2*math.pi*i/zt
        t = Part.makeBox(m*1.9, m*1.6, fw, V(pitch_r-m*0.5, -m*0.8, z_ring_plane))
        t.rotate(App.Vector(0,0,0), App.Vector(0,0,1), math.degrees(a))
        teeth.append(t)
    gear = fuse([gear]+teeth)
    emit('slew_ring_gear','Slew Ring Gear (%dT m%.1f)'%(zt,m), gear, P['materials']['printed'],'FDM',
         teeth=zt, module=m)

    ztop = z0+h+fw
    # turret deck
    t = Part.makeCylinder(s['outer_dia_mm']/2, 12, V(0,0,ztop))
    t = t.cut(Part.makeCylinder(ri*0.55, 60, V(0,0,ztop-4)))
    for i in range(int(s['n_bolts'])):
        a=2*math.pi*i/s['n_bolts']
        t=t.cut(Part.makeCylinder(s['bolt_dia_mm']/2, 60,
             V(s['bolt_circle_dia_mm']/2*math.cos(a), s['bolt_circle_dia_mm']/2*math.sin(a), ztop-4)))
    emit('turret','Turret Deck', fuse([t]), P['materials']['structure'],'FDM')
    global RING_PLANE, RING_FACE
    RING_PLANE, RING_FACE = z_ring_plane, fw
    JOINTS.append(dict(id='j_slew', type='revolute', parent='slew_ring', child='turret',
        origin=[0,0,ztop], axis=[0,0,1],
        limits=dict(lower=math.radians(s['limit_deg'][0]), upper=math.radians(s['limit_deg'][1]),
                    effort=0.10, velocity=4.2),
        driver=dict(mode='position', waveform='sine', amplitude=math.radians(150), frequency=0.05)))
    MATES.append(dict(a_node='base_plate', b_node='slew_ring', type='coincident'))
    return ztop+12

# ---------------------------------------------------------------- MAST -------
def make_mast(z0):
    log("mast...")
    m = P['mast']
    H, Wd = m['height_mm'], m['width_mm']
    n = int(m['n_bays'])
    nsec = int(m.get('n_sections', 1))
    ov  = m.get('section_overlap_mm', 24.0)
    clr = m.get('spigot_clear_mm', 0.25)
    half = Wd/2
    corners = [(-half,-half),(half,-half),(half,half),(-half,half)]

    # Build the full lattice once, then CUT it into printable sections and add
    # keyed spigots. A butt joint would pass interference and connectivity while
    # the tower comes apart in the hand -- CLAUDE.md forbids it explicitly.
    zs = [z0 + H*i/n for i in range(n+1)]
    chords = {ci: [V(cx,cy,z) for z in zs] for ci,(cx,cy) in enumerate(corners)}
    solids = []
    for ci in chords:
        for i in range(n):
            solids.append(tube(chords[ci][i], chords[ci][i+1], m['chord_dia_mm']))
    for ci in range(4):
        a, b = chords[ci], chords[(ci+1)%4]
        for i in range(n):
            solids.append(tube(a[i], b[i], m['brace_dia_mm']))
            if i%2==0: solids.append(tube(a[i], b[i+1], m['brace_dia_mm']))
            else:      solids.append(tube(b[i], a[i+1], m['brace_dia_mm']))
        solids.append(tube(a[n], b[n], m['brace_dia_mm']))
    full = fuse(solids)

    if nsec <= 1:
        emit('mast','Lattice Mast', full, P['materials']['structure'],'FDM')
    else:
        seg = H/nsec
        cd = m['chord_dia_mm']
        for k in range(nsec):
            zlo, zhi = z0 + seg*k, z0 + seg*(k+1)
            box = Part.makeBox(Wd*3, Wd*3, seg, V(-Wd*1.5, -Wd*1.5, zlo))
            part = full.common(box)
            spig = []
            if k < nsec-1:
                # male spigot up from this section, into the one above
                for (cx,cy) in corners:
                    spig.append(Part.makeCylinder(cd/2-clr, ov, V(cx,cy,zhi)))
            if k > 0:
                # female socket: bore the chord ends so the spigot below enters
                for (cx,cy) in corners:
                    part = part.cut(Part.makeCylinder(cd/2-clr+0.15, ov+0.4,
                                                      V(cx,cy,zlo-0.2)))
            part = fuse([part]+spig) if spig else fuse([part])
            emit('mast_s%d'%(k+1), 'Lattice Mast — section %d/%d'%(k+1,nsec),
                 part, P['materials']['structure'],'FDM',
                 section=k+1, of=nsec, joint='keyed spigot %.1f mm' % ov)
            if k:
                MATES.append(dict(a_node='mast_s%d'%k, b_node='mast_s%d'%(k+1),
                                  type='coincident'))
    MATES.append(dict(a_node='turret', b_node='mast_s1' if nsec>1 else 'mast',
                      type='coincident'))

    cap = Part.makeBox(Wd+18, Wd+18, m['cap_t_mm'], V(-(Wd+18)/2, -(Wd+18)/2, z0+H))
    cap = cap.cut(Part.makeCylinder(11, 60, V(0,0,z0+H-6)))
    emit('mast_head','Mast Head Plate', fuse([cap]), P['materials']['structure'],'FDM')
    return z0+H, z0+H+m['cap_t_mm']

# ---------------------------------------------------------------- BOOM -------
def make_boom(ztop):
    log("boom...")
    b = P['boom']
    L, rh, th, w = b['length_mm'], b['root_h_mm'], b['tip_h_mm'], b['width_mm']
    n = int(b['n_bays'])
    zb = ztop - rh/2      # boom centreline just under the head
    # top and bottom chord node rows, tapering
    xs = [L*i/n for i in range(n+1)]
    def depth(x): return rh + (th-rh)*(x/L)
    top_l=[V(x,-w/2, zb+depth(x)/2) for x in xs]
    top_r=[V(x, w/2, zb+depth(x)/2) for x in xs]
    bot_l=[V(x,-w/2, zb-depth(x)/2) for x in xs]
    bot_r=[V(x, w/2, zb-depth(x)/2) for x in xs]
    solids=[]
    for row in (top_l,top_r,bot_l,bot_r):
        for i in range(n):
            solids.append(tube(row[i],row[i+1], b['chord_dia_mm']))
    # side trusses (real diagonals)
    for a_,b_ in ((top_l,bot_l),(top_r,bot_r)):
        for i in range(n):
            solids.append(tube(a_[i],b_[i], b['brace_dia_mm']))
            if i%2==0: solids.append(tube(a_[i],b_[i+1], b['brace_dia_mm']))
            else:      solids.append(tube(b_[i],a_[i+1], b['brace_dia_mm']))
        solids.append(tube(a_[n],b_[n], b['brace_dia_mm']))
    # top and bottom lacing
    for a_,b_ in ((top_l,top_r),(bot_l,bot_r)):
        for i in range(n):
            solids.append(tube(a_[i],b_[i], b['brace_dia_mm']))
            if i%2==0: solids.append(tube(a_[i],b_[i+1], b['brace_dia_mm']))
    boom = fuse(solids)
    emit('boom','Lattice Jib', boom, P['materials']['structure'],'FDM')
    MATES.append(dict(a_node='mast_head', b_node='boom', type='coincident'))

    # head sheave at the jib tip
    sd = b['head_sheave_dia_mm']
    xs_ = L-16
    bore_r = 4.2
    sh = Part.makeCylinder(sd/2, 10, V(xs_,-5,zb), V(0,1,0))
    sh = sh.cut(Part.makeCylinder(bore_r, 40, V(xs_,-20,zb), V(0,1,0)))
    emit('jib_sheave','Jib Head Sheave', fuse([sh]), P['materials']['printed'],'FDM')

    # --- the sheave's axle (R188). Without it the sheave floated 6.10 mm off
    # the boom with nothing carrying it. The pin runs across the jib between
    # the two side trusses. Its size is DERIVED, not typed:
    #   diameter = sheave bore - 2 x running clearance
    #   length   = MEASURED against the boom: the ends stop END_GAP short of
    #              the side-truss members they bear on.
    # The side-truss diagonal crosses the axle's end at a slant, so the
    # closed form "width - brace dia" measured 0.382 mm short, outside the
    # 0.3 mm connectivity tolerance. Bisect on the measured gap instead. The
    # boom is not cut, so the ends never overlap it: in contact at the
    # connectivity tolerance, never a tangent fit (CLAUDE.md gotcha).
    run_clr, end_gap = 0.2, 0.1
    ax_r = bore_r - run_clr
    def pin(half):
        return Part.makeCylinder(ax_r, 2*half, V(xs_, -half, zb), V(0,1,0))
    lo = w/2 - b['brace_dia_mm']/2 - 1.0      # clear of the boom
    hi = w/2 + b['chord_dia_mm']              # through the side truss
    if boom.distToShape(pin(lo))[0] <= end_gap or boom.common(pin(hi)).Volume <= 0:
        raise RuntimeError('jib sheave axle: bisection bracket does not hold')
    for _ in range(40):
        mid = (lo+hi)/2
        if boom.distToShape(pin(mid))[0] > end_gap: lo = mid
        else: hi = mid
        if hi - lo < 1e-4: break
    ax_half = lo
    axle = pin(ax_half)
    # MEASURE, never assert: re-check the chosen pin as a whole. If the
    # lattice changes and it cannot seat, the build fails here instead of
    # emitting a floating or interfering axle.
    ov = boom.common(axle).Volume
    gap_boom = boom.distToShape(axle)[0]
    gap_shv = sh.distToShape(axle)[0]
    if ov > 1e-6 or not (0.0 < gap_boom <= 0.3) or not (0.0 < gap_shv <= 0.3):
        raise RuntimeError('jib sheave axle does not seat: overlap %.4f mm3, '
                           'boom gap %.3f mm, sheave gap %.3f mm'
                           % (ov, gap_boom, gap_shv))
    log("jib sheave axle d%.1f x %.1f: boom gap %.3f mm, sheave gap %.3f mm"
        % (2*ax_r, 2*ax_half, gap_boom, gap_shv))
    emit('jib_sheave_axle','Jib Head Sheave Axle (Ø%.1f pin)' % (2*ax_r),
         fuse([axle]), 'STEEL_A2','COTS',
         dia_mm=2*ax_r, length_mm=2*ax_half, fit='running %.1f mm radial' % run_clr)
    MATES.append(dict(a_node='boom', b_node='jib_sheave_axle', type='coincident'))
    # parent stays the boom: the axle is fixed to it (mate above), so the
    # sheave's kinematic parent is unchanged for every joint-tree consumer.
    JOINTS.append(dict(id='j_jib_sheave', type='revolute', parent='boom',
        child='jib_sheave', origin=[xs_,0,zb], axis=[0,1,0],
        limits=dict(effort=0.2, velocity=60.0)))
    return L, zb

# ------------------------------------------------------- LEADSCREW HOIST -----
def make_screw(z_deck, z_head):
    log("screw...")
    s = P['screw']
    L = s['length_mm']
    z0 = z_deck + 26
    rod = Part.makeCylinder(s['nominal_dia_mm']/2, L, V(0,0,z0))
    # thread relief groove so it reads as a leadscrew, not a smooth rod
    emit('leadscrew','T8x%g Leadscrew (self-locking)' % P['screw']['lead_mm'], fuse([rod]), 'STEEL_A2','COTS',
         lead_mm=s['lead_mm'], travel_mm=s['travel_mm'])
    JOINTS.append(dict(id='j_screw', type='revolute', parent='mast_s1', child='leadscrew',
        origin=[0,0,z0], axis=[0,0,1], limits=dict(effort=0.05, velocity=21.0),
        driver=dict(mode='velocity', waveform='const', amplitude=6.0)))
    return z0, z0+L

def make_carriage(z_screw0):
    log("carriage...")
    c = P['carriage']; s = P['screw']
    w,h,t = c['body_w_mm'], c['body_h_mm'], c['body_t_mm']
    # Park at the BOTTOM of travel. The viewer adds hoist travel upward, so
    # authoring mid-stroke made a 400 mm command overshoot the mast head.
    z = z_screw0 + 8
    body = Part.makeBox(w, t, h, V(-w/2, -t/2, z))
    body = body.cut(Part.makeCylinder(s['nut_body_dia_mm']/2, h*3, V(0,0,z-h)))
    # lightening pockets
    for sx in (-1,1):
        body = body.cut(Part.makeBox(w*0.22, t*2, h*0.5,
                 V(sx*w*0.26-w*0.11, -t, z+h*0.25)))
    # hook eye
    body = body.cut(Part.makeCylinder(c['hook_eye_dia_mm']/2, t*3, V(0,-t*1.5,z+6), V(0,1,0)))
    emit('carriage','Hoist Carriage (travelling nut)', fuse([body]), P['materials']['structure'],'FDM')
    JOINTS.append(dict(id='j_carriage', type='prismatic', parent='mast_s1', child='carriage',
        origin=[0,0,z], axis=[0,0,1],
        limits=dict(lower=0.0, upper=s['travel_mm'], effort=P['duty']['payload_kg']*9.80665, velocity=13.0),
        coupled_to='j_screw', ratio=s['lead_mm']/(2*math.pi)))
    # brass nut
    nut = Part.makeCylinder(s['nut_flange_dia_mm']/2, 5, V(0,0,z-5))
    nut = fuse([nut, Part.makeCylinder(s['nut_body_dia_mm']/2+2, s['nut_len_mm'], V(0,0,z-5))])
    nut = nut.cut(Part.makeCylinder(s['nominal_dia_mm']/2, 60, V(0,0,z-20)))
    emit('lead_nut','T8 Brass Lead Nut', nut, 'BRASS','COTS')
    return z

# ---------------------------------------------------------------- MOTORS -----
def nema17(pid, name, org, axis_deg, z_rot=0):
    """NEMA17 emitted as TWO parts: a fixed body and a rotating shaft.

    The case is bolted to the frame -- only the shaft turns. Spinning the whole
    motor was wrong, and invisible anyway: a square body repeats every 90 deg
    and a plain cylinder looks the same at every angle. The shaft therefore
    carries a flat and a keyed collar so its rotation is actually legible.
    """
    d = P['drive_hoist']
    a, l = d['motor_body_mm'], d['motor_len_mm']
    body = Part.makeBox(a, a, l, V(-a/2, -a/2, 0))
    for sx in (-1, 1):
        for sy in (-1, 1):
            cut = Part.makeBox(12, 12, l*1.2, V(sx*a/2-6, sy*a/2-6, -l*0.1))
            cut.rotate(App.Vector(sx*a/2, sy*a/2, 0), App.Vector(0,0,1), 45)
            body = body.cut(cut)
    boss = Part.makeCylinder(11, 2, V(0,0,l))
    body = fuse([body, boss])
    body.rotate(App.Vector(0,0,0), App.Vector(1,0,0), axis_deg)
    if z_rot: body.rotate(App.Vector(0,0,0), App.Vector(0,0,1), z_rot)
    body.translate(org)
    emit(pid, name, body, 'STEEL_A2', 'COTS', motor='NEMA17')

    # --- rotating shaft, with a flat and an index collar so spin is visible ---
    sd = d['motor_shaft_dia_mm']
    shaft = Part.makeCylinder(sd/2, 24, V(0,0,l))
    shaft = shaft.cut(Part.makeBox(sd, sd, 16, V(sd/2-0.5, -sd/2, l+6)))   # D-flat
    collar = Part.makeCylinder(sd*1.5, 3, V(0,0,l+2))
    mark = Part.makeBox(sd*1.6, 2.0, 3.2, V(0,-1.0,l+2))                   # index key
    shaft = fuse([shaft, collar, mark])
    shaft.rotate(App.Vector(0,0,0), App.Vector(1,0,0), axis_deg)
    if z_rot: shaft.rotate(App.Vector(0,0,0), App.Vector(0,0,1), z_rot)
    shaft.translate(org)
    emit(pid+'_shaft', name.replace('Motor','Shaft'), shaft, 'STEEL_A2', 'COTS',
         rotates=True, axis_org=[org.x, org.y, org.z])
    return body

def spur(pid, name, teeth, module, face, org, axis=V(0,0,1), material=None):
    """Gear with real teeth, plus ONE marked tooth so rotation is legible.

    A 60-tooth gear is rotationally near-symmetric on screen: without an index
    feature you cannot tell a spinning gear from a still one.
    """
    pr = module*teeth/2
    blank = Part.makeCylinder(pr-module*0.9, face, org, axis)
    tl=[]
    for i in range(teeth):
        a = 2*math.pi*i/teeth
        t = Part.makeBox(module*2.0, module*1.55, face,
                         V(pr-module*1.1, -module*0.775, 0))
        t.rotate(App.Vector(0,0,0), App.Vector(0,0,1), math.degrees(a))
        t.translate(org)
        tl.append(t)
    # index rib on the hub -- one radial spoke, unmistakable when it turns
    rib = Part.makeBox(pr*0.92, module*0.8, face*0.55,
                       V(0, -module*0.4, 0))
    rib.translate(org)
    tl.append(rib)
    g = fuse([blank]+tl)
    g = g.cut(Part.makeCylinder(2.6, face*4, org.sub(V(0,0,face)), axis))
    emit(pid, name, g, material or P['materials']['printed'], 'FDM',
         teeth=teeth, module=module, rotates=True,
         axis_org=[org.x, org.y, org.z])
    return g

def make_drives(z_deck, z_screw0):
    log("drives...")
    dh = P['drive_hoist']; ds = P['drive_slew']

    # --- HOIST: motor position is DERIVED from the mesh, not chosen. ---------
    # The pinion must sit exactly m(z1+z2)/2 from the screw axis, and both
    # gears must occupy the SAME z band or the teeth never touch.
    # Hand-placing the motor at "mast_width/2 + 34" put it 79 mm out against a
    # 45 mm requirement, and 30 mm above the wheel: the train was disconnected.
    cd_h = dh['gear_module_mm'] * (dh['pinion_teeth'] + dh['wheel_teeth']) / 2.0
    fw_h = dh['face_width_mm']
    z_gear = z_screw0 - fw_h - 2          # gear plane, just under the screw start
    mx, my = 0.0, cd_h                    # motor axis, cd_h from the screw axis

    # motor sits below the gear plane, shaft pointing up into the pinion
    z_motor = z_gear - dh['motor_len_mm'] - 2
    nema17('motor_hoist','NEMA17 Hoist Motor', V(mx, my, z_motor), 0)
    spur('gear_hoist_pinion','Hoist Pinion %dT m%.1f'%(dh['pinion_teeth'],dh['gear_module_mm']),
         dh['pinion_teeth'], dh['gear_module_mm'], fw_h, V(mx, my, z_gear))
    spur('gear_hoist_wheel','Hoist Wheel %dT m%.1f'%(dh['wheel_teeth'],dh['gear_module_mm']),
         dh['wheel_teeth'], dh['gear_module_mm'], fw_h, V(0, 0, z_gear))

    JOINTS.append(dict(id='j_hoist_motor', type='revolute', parent='turret',
        child='gear_hoist_pinion', origin=[mx,my,z_gear], axis=[0,0,1],
        limits=dict(effort=dh['motor_holding_nm'], velocity=21.0),
        driver=dict(mode='velocity', waveform='const', amplitude=12.0)))
    JOINTS.append(dict(id='j_hoist_mesh', type='gear',
        parent='gear_hoist_pinion', child='gear_hoist_wheel',
        origin=[0,0,z_gear], axis=[0,0,1],
        ratio=-dh['pinion_teeth']/dh['wheel_teeth'], coupled_to='j_hoist_motor',
        centre_distance=cd_h))

    # --- SLEW: same rule, centre distance from the mesh -----------------------
    cd_s = ds['gear_module_mm'] * (ds['pinion_teeth'] + ds['ring_teeth']) / 2.0
    fw_s = ds['face_width_mm']
    z_ring = RING_PLANE                   # EXACTLY the ring gear's own plane
    sx_, sy_ = cd_s, 0.0
    nema17('motor_slew','NEMA17 Slew Motor',
           V(sx_, sy_, z_ring - ds.get('motor_len_mm', dh['motor_len_mm']) - 2), 0)
    spur('gear_slew_pinion','Slew Pinion %dT m%.1f'%(ds['pinion_teeth'],ds['gear_module_mm']),
         ds['pinion_teeth'], ds['gear_module_mm'], fw_s, V(sx_, sy_, z_ring),
         material=P['materials']['printed'])
    JOINTS.append(dict(id='j_slew_motor', type='revolute', parent='turret',
        child='gear_slew_pinion', origin=[sx_,sy_,z_ring], axis=[0,0,1],
        limits=dict(effort=0.4, velocity=21.0)))
    JOINTS.append(dict(id='j_slew_mesh', type='gear',
        parent='gear_slew_pinion', child='slew_ring_gear',
        origin=[0,0,z_ring], axis=[0,0,1],
        ratio=-ds['pinion_teeth']/ds['ring_teeth'], coupled_to='j_slew_motor',
        centre_distance=cd_s))
    return z_ring, fw_s

# ---------------------------------------------------------------- HOOK -------
def make_hook(z_carriage, tip_x, z_sheave):
    log("hook...")
    """The load hangs at the JIB TIP, over the edge -- not up the mast.

    The rope runs: carriage -> up the mast -> over the jib head sheave -> down
    to the hook. So carriage travel becomes hook travel, but the hook hangs at
    the full duty reach. Every load figure in this project (overturning moment,
    bolt tension, slew gear sizing) assumes the load acts at that radius; a
    hook hanging at x=0 would make all of them wrong.
    """
    hk = P['hook']
    cw,ch,ct,gap = hk['cheek_w_mm'],hk['cheek_h_mm'],hk['cheek_t_mm'],hk['gap_mm']
    # hang below the sheave, at the tip, with the carriage at its parked height
    # Park low enough that the FULL lift travel still stops below the sheave.
    # Hook top must satisfy: z + cheek_h + travel < z_sheave - clearance.
    # Otherwise the hook is hauled up into the jib head at full travel.
    clearance = 40.0
    z = z_sheave - clearance - ch - P['screw']['travel_mm']
    cheeks=[]
    for sy in (-1,1):
        c = Part.makeBox(cw, ct, ch, V(tip_x-cw/2, sy*(gap/2) - (ct if sy>0 else 0), z))
        c = c.cut(Part.makeCylinder(4.5, ct*4, V(tip_x, sy*(gap/2+ct*2), z+ch-11), V(0,1,0)))
        cheeks.append(c)
    tie_top = Part.makeBox(cw*0.55, gap+2*ct, ct, V(tip_x-cw*0.275, -(gap/2+ct), z+ch-ct))
    tie_bot = Part.makeBox(cw*0.55, gap+2*ct, ct, V(tip_x-cw*0.275, -(gap/2+ct), z))
    spacer  = Part.makeCylinder(5.0, gap, V(tip_x,-gap/2, z+ch*0.30), V(0,1,0))
    block = fuse(cheeks+[tie_top, tie_bot, spacer])
    emit('hook_block','Hook Block', block, P['materials']['structure'],'FDM')

    sd = hk['sheave_dia_mm']
    sv = Part.makeCylinder(sd/2, gap-1, V(tip_x,-(gap-1)/2, z+ch-11), V(0,1,0))
    sv = sv.cut(Part.makeCylinder(4.2, gap*3, V(tip_x,-gap*1.5,z+ch-11), V(0,1,0)))
    emit('hook_sheave','Hook Sheave', fuse([sv]), P['materials']['printed'],'FDM')
    JOINTS.append(dict(id='j_hook_sheave', type='revolute', parent='hook_block', child='hook_sheave',
        origin=[tip_x,0,z+ch-11], axis=[0,1,0], limits=dict(effort=0.2, velocity=60.0)))

    r = hk['throat_mm']/2; sdm = hk['stock_dia_mm']
    shank = Part.makeCylinder(sdm/2, hk['shank_len_mm'], V(tip_x,0,z-hk['shank_len_mm']))
    ring = Part.makeTorus(r, sdm/2, V(tip_x,0,z-hk['shank_len_mm']-r), V(0,1,0), -170, 120)
    hook = fuse([shank, ring])
    emit('hook','Lifting Hook', hook, 'STEEL_A2','COTS')
    JOINTS.append(dict(id='j_hook_swivel', type='revolute', parent='hook_block', child='hook',
        origin=[tip_x,0,z], axis=[0,0,1], limits=dict(effort=0.1, velocity=12.0)))
    # the hook rides the rope, which the carriage pays out over the jib sheave
    JOINTS.append(dict(id='j_hook_rope', type='prismatic', parent='boom', child='hook_block',
        origin=[tip_x,0,z], axis=[0,0,1],
        limits=dict(lower=0.0, upper=P['screw']['travel_mm'],
                    effort=P['duty']['payload_kg']*9.80665, velocity=13.0),
        coupled_to='j_carriage', ratio=1.0))
    return z

# ------------------------------------------------------- COUNTERWEIGHT -------
def make_cw(z_deck):
    log("counterweight...")
    c = P['counterweight']
    w,h,t,x = c['width_mm'],c['height_mm'],c['thick_mm'],c['x_mm']
    blk = Part.makeBox(t, w, h, V(x-t/2, -w/2, z_deck+4))
    blk = blk.cut(Part.makeCylinder(5, 300, V(x, -w, z_deck+4+h*0.62), V(0,1,0)))
    emit('counterweight','Counterweight (boom balance)', fuse([blk]), 'STEEL_A2','COTS')
    MATES.append(dict(a_node='turret', b_node='counterweight', type='coincident'))

# ----------------------------------------------------------------- MAIN ------
def main():
    App.newDocument("crane")
    z1 = make_base()
    z_deck = make_slew(z1)
    z_masttop, z_head = make_mast(z_deck)
    boom_len, z_boom = make_boom(z_head)
    z_s0, z_s1 = make_screw(z_deck, z_head)
    z_car = make_carriage(z_s0)
    make_drives(z_deck, z_s0)
    make_hook(z_car, boom_len-16, z_boom)
    make_cw(z_deck)

    out=[]
    for p in PARTS:
        sh = p['shape']
        norm=False; disc=False
        if sh.ShapeType=='Compound':
            sol=sh.Solids
            if len(sol)==1: sh=sol[0]; norm=True
            elif len(sol)>1:
                sh=sol[0].multiFuse(sol[1:]); norm=True; disc=True
                if sh.ShapeType=='Compound' and len(sh.Solids)==1: sh=sh.Solids[0]
        brep=os.path.join(OUT,p['id']+'.brep'); sh.exportBrep(brep)
        bb=sh.BoundBox
        if sh.ShapeType=='Compound' and len(sh.Solids)>=1:
            sh = sh.Solids[0] if len(sh.Solids)==1 else sh.Solids[0].multiFuse(sh.Solids[1:])
            if sh.ShapeType=='Compound' and sh.Solids: sh=sh.Solids[0]
            norm=True
        try:
            it=sh.MatrixOfInertia
            inert=[it.A11,it.A12,it.A13,it.A21,it.A22,it.A23,it.A31,it.A32,it.A33]
        except Exception: inert=[0.0]*9
        rec={k:v for k,v in p.items() if k!='shape'}
        rec.update(dict(brep=os.path.basename(brep), volume=sh.Volume, area=sh.Area,
            com=[sh.CenterOfMass.x,sh.CenterOfMass.y,sh.CenterOfMass.z], inertia=inert,
            bbox=dict(min=[bb.XMin,bb.YMin,bb.ZMin],max=[bb.XMax,bb.YMax,bb.ZMax]),
            n_faces=len(sh.Faces), valid=sh.isValid(),
            closed=all(s.isClosed() for s in sh.Shells) if sh.Shells else False,
            disconnected=disc, shape_type=sh.ShapeType))
        out.append(rec)

    meta=dict(run=P['run'], meta=P['meta'], duty=P['duty'], derived=DERIVED, parts=out,
              joints=JOINTS, mates=MATES, params=P, kernel='FreeCAD',
              kernel_version='.'.join(App.Version()[0:3]),
              key_heights=dict(deck=z_deck, mast_top=z_masttop, head=z_head,
                               boom_z=z_boom, screw_lo=z_s0, screw_hi=z_s1,
                               carriage=z_car, overall=max(r['bbox']['max'][2] for r in out)))
    json.dump(meta, open(os.path.join(OUT,'parts.json'),'w'), indent=1)
    print("FCRESULT "+json.dumps(dict(n_parts=len(out), n_joints=len(JOINTS),
        total_faces=sum(r['n_faces'] for r in out), all_valid=all(r['valid'] for r in out),
        all_closed=all(r['closed'] for r in out),
        disconnected=[r['id'] for r in out if r['disconnected']],
        invalid=[r['id'] for r in out if not r['valid']],
        height_mm=round(max(r['bbox']['max'][2] for r in out),1))))

main()
