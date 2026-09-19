# Shared geometry helpers for the CANARY enclosure.
# Enclosure frame "E": X = left->right seen from the front, Y = up, Z = toward the viewer (front).
# Fusion frame:        X_f = X_e,  Y_f = -Z_e,  Z_f = Y_e   (so Fusion "Front" view shows the display).
import adsk.core, adsk.fusion, math

M = 0.1  # mm -> cm
tb = adsk.fusion.TemporaryBRepManager.get()

def P(X, Y, Z):
    """E-frame mm -> Fusion Point3D (cm)."""
    return adsk.core.Point3D.create(X * M, -Z * M, Y * M)

def V(X, Y, Z):
    return adsk.core.Vector3D.create(X, -Z, Y)

def box(X0, X1, Y0, Y1, Z0, Z1):
    cx, cy, cz = (X0 + X1) / 2, (Y0 + Y1) / 2, (Z0 + Z1) / 2
    obb = adsk.core.OrientedBoundingBox3D.create(P(cx, cy, cz), V(1, 0, 0), V(0, 1, 0),
                                                 (X1 - X0) * M, (Y1 - Y0) * M, (Z1 - Z0) * M)
    return tb.createBox(obb)

def cyl(p0, p1, r):
    return tb.createCylinderOrCone(p0, r * M, p1, r * M)

def cyl_z(X, Y, Z0, Z1, r):   # axis along E-Z
    return cyl(P(X, Y, Z0), P(X, Y, Z1), r)

def cyl_y(X, Z, Y0, Y1, r):   # axis along E-Y
    return cyl(P(X, Y0, Z), P(X, Y1, Z), r)

def cyl_x(Y, Z, X0, X1, r):   # axis along E-X
    return cyl(P(X0, Y, Z), P(X1, Y, Z), r)

def halfspace(pt, n, L=600.0):
    """Big box occupying the side of plane (pt, n) that n points to. pt/n in E-frame."""
    nn = math.sqrt(n[0]**2 + n[1]**2 + n[2]**2)
    n = (n[0] / nn, n[1] / nn, n[2] / nn)
    c = (pt[0] + n[0] * L / 2, pt[1] + n[1] * L / 2, pt[2] + n[2] * L / 2)
    # width direction: any perpendicular. All our normals lie in the Y-Z plane, so X works;
    # if n has an X component fall back to a computed perpendicular.
    if abs(n[0]) < 1e-9:
        w = (1.0, 0.0, 0.0)
    else:
        w = (-n[1], n[0], 0.0)
        wn = math.sqrt(w[0]**2 + w[1]**2)
        w = (w[0] / wn, w[1] / wn, 0.0)
    obb = adsk.core.OrientedBoundingBox3D.create(P(*c), V(*n), V(*w), L * M, L * M, L * M)
    return tb.createBox(obb)

def union(a, b):
    tb.booleanOperation(a, b, adsk.fusion.BooleanTypes.UnionBooleanType)
    return a

def cut(a, b):
    tb.booleanOperation(a, b, adsk.fusion.BooleanTypes.DifferenceBooleanType)
    return a

def inter(a, b):
    tb.booleanOperation(a, b, adsk.fusion.BooleanTypes.IntersectionBooleanType)
    return a

def get_or_make_comp(parent_comp, name):
    for o in parent_comp.occurrences:
        if o.component.name == name:
            return o
    occ = parent_comp.occurrences.addNewComponent(adsk.core.Matrix3D.create())
    occ.component.name = name
    return occ

def replace_body(comp, body, name):
    """Remove previous base features/bodies in comp and add body as a base feature."""
    for f in list(comp.features.baseFeatures):
        f.deleteMe()
    for b in list(comp.bRepBodies):
        b.deleteMe()
    bf = comp.features.baseFeatures.add()
    bf.startEdit()
    nb = comp.bRepBodies.add(body, bf)
    bf.finishEdit()
    nb.name = name
    return nb

def bb_mm(b):
    mn, mx = b.minPoint, b.maxPoint
    return [round(v * 10, 2) for v in (mn.x, mn.y, mn.z, mx.x, mx.y, mx.z)]

# ---------------------------------------------------------------------------------------------
# Head (display housing): thin tray + flat back cover. Inkplate as its STEP model has it -> USB-C on the RIGHT.
# Head frame: X 0..130.59 = PCB left->right seen from the front, Y up (0..75.23), Z toward the viewer,
# panel front at Z = 0.  Z levels: bezel front +2.4 . panel 0 . PCB back -2.45 . standoff tops -9.67 .
# cover -9.67..-11.67 (the cover rests on the Inkplate's four SMT standoffs).
# ---------------------------------------------------------------------------------------------
HEAD_R, HEAD_CAV_R, HEAD_R_FRONT = 5.0, 3.0, 1.2   # plan corner radius (outer / cavity), round on the bezel's front edge
#   (the bezel round is limited by the 2 mm wall and the 2.4 mm lip: 1.3 mm would break through at the cavity corner)
HEAD_ZF, HEAD_ZBACK = 2.4, -11.67
HEAD_X0, HEAD_X1, HEAD_Y0, HEAD_Y1 = -2.0, 132.6, -1.0, 76.2       # cavity
HEAD_LWALL, HEAD_RWALL, HEAD_WALL = 2.0, 7.3, 2.0                  # thick RIGHT wall (USB-C side) for a symmetric bezel
# --- how the cover holds the tray. The cover goes in from the back in a straight line, so only something that
#   engages after it is in can stop it coming out again: two tongues and two screws. Every tray feature here is a
#   cut in a wall, so the Inkplate still passes.
HEAD_STEP, HEAD_STEP_PLAY = 1.0, 0.15   # a step 1 mm into the walls' inner rear edge and 1 mm deep: the seat for the
#   cover's edge, whose outer millimetre is that much larger. It locates the cover and hides the gap; it holds nothing.
TONGUE_Y = ((14.0, 26.0), (49.2, 61.2)) # two tongues on the cover's left edge, on its inner face, 0.8 into slots
TONGUE_T, TONGUE_IN = 0.9, 0.8          #   in the thin wall. The step stops short of each slot, so 1 mm of wall stays
#   behind the tongue. The cover goes on tilted, tongues first, and swings down on to the standoffs.
EAR_X1, EAR_Y = 138.7, 9.2              # two ears on the cover's right corners, the full 2 mm thick, in pockets in the
EAR_SCREW = ((135.8, 3.4), (135.8, 71.83))   # thick wall that leave a 1 mm skirt outside. An M3 x 6 through each
INSERT_R, INSERT_DEPTH = 2.0, 6.0       #   goes into a heat-set insert in the wall, in line with the standoff screws.
#   The ears seat level with the standoff tops. The bezel lip stands HEAD_STEP_PLAY clear of the panel, and the
#   tongues and the cover's edge have the same play, so a wall that prints that much short or long still cannot
#   make the ear screws press the lip on to the glass.

def head_ear(i, grow, z0, z1):
    """Ear i (0 bottom, 1 top) grown by `grow`: a block at the cover's right corner, rounded to follow the head's."""
    lo, hi = HEAD_Y0 - HEAD_STEP + 0.2, HEAD_Y1 + HEAD_STEP - 0.2      # the cover's own edge, 0.2 inside the step
    y0, y1 = ((lo, EAR_Y), (hi - (EAR_Y - lo), hi))[i]
    e = box(HEAD_X1 - 1.0, EAR_X1 + grow, y0 - grow, y1 + grow, z0, z1)
    lim = HEAD_X1 + HEAD_RWALL - EAR_X1 - grow            # what is left of the wall outside the ear
    return inter(e, rrect_h(HEAD_X0, HEAD_X1 + HEAD_RWALL - lim, HEAD_Y0 - HEAD_WALL + lim, HEAD_Y1 + HEAD_WALL - lim,
                            z0, z1, HEAD_R - lim))
# There are no bosses of any kind inside the cavity, and there must never be. The Inkplate is 130.59 x 75.23 in a
# 134.6 x 77.2 cavity - 2 mm a side in X, because SW2 and the wake switch stand 0.85 mm past the board's left and
# right edges, and 1 mm top and bottom - and it goes in from the back, so its own footprint sweeps the whole
# cavity on the way to its seat. Anything standing in there, however far behind the board it ends up, is something
# the board has to pass through first. Four boss towers for the cover and two blocks for the dock screws were
# exactly that, and the first print could not be assembled (Sept 2026). The cover now screws to the Inkplate's own
# four M3 SMT standoffs, and the head is held down by the pogo connector's magnets rather than by screws.
# --- head-to-dock junction: an 8-pin magnetic pogo pair, mating along the head's Y as the head sits down ---
#   Both halves are panel-mount parts with a LIP, and that lip is how they are fixed: each goes in from inside its
#   own shell, the lip lands on a face and is glued to it, and only what has to make contact stands out. So the
#   male lives almost entirely inside the head - its nose fills the 2 mm bottom wall and stands PG_PROUD out of the
#   underside, the lip and the solder tails are in the cavity - and the female almost entirely inside a plinth in
#   the dock. Nothing hangs in the gap between the two any more.
#   Centred on the head, and so on the device: the thick wall puts the head's centre 5.3 right of the board's, and
#   head_matrix() moves the head that far left to sit centred on the dock. The head's two wires come from the VIN
#   and GND pads on the top edge (see the head wiring), 70 mm from the connector.
POGO_X = (HEAD_X0 - HEAD_LWALL + HEAD_X1 + HEAD_RWALL) / 2   # 67.95 in the head, 62.65 in the dock
POGO_Z = -6.00
#   Z is boxed in: the male's 8.00 lip and the female's 11.00 lip both sit BELOW the PCB's bottom edge where the
#   whole 0..-9.67 depth is free, but the male's 7.00 back band is at Y 0..1.4, alongside the board, and has to
#   pass between its back face (-2.45) and the back cover (-9.67). 7.00 in 7.22 leaves a tenth of a millimetre.
PG_PITCH, PG_CLR, PG_PROUD = 2.30, 0.20, 0.30
PG_M_LIP_L, PG_M_LIP_W, PG_M_LIP_T = 25.30, 8.00, 1.00      # male: lip (the glue face), then the two bands
PG_M_L, PG_M_W, PG_M_NOSE, PG_M_BACK, PG_M_TAIL = 24.30, 7.00, 2.30, 1.40, 1.50
PG_F_LIP_L, PG_F_LIP_W, PG_F_LIP_T = 28.30, 11.00, 0.90     # female: ditto, lip the widest band and in the middle
PG_F_L, PG_F_W, PG_F_TOP, PG_F_BOT, PG_F_TAIL = 25.30, 8.00, 2.00, 1.70, 1.40
PG_KEY_L, PG_KEY_W, PG_KEY_R = 9.92, 5.00, 0.70             # the contact block: a rounded rectangle with one
PG_NOTCH_R = 0.95                                           # semicircle cut into the middle of its S-end wall
PG_BOSS, PG_FIT = 1.00, 0.145                               # boss height; the male's pocket is the same shape
PG_POCKET = PG_BOSS + 0.15                                  # grown by PG_FIT all round (10.21 against 9.92)
PG_MAG_C, PG_MAG_R, PG_MAG_T = 8.65, 2.50, 1.20

PG_YM = HEAD_Y0 - HEAD_WALL - PG_PROUD                      # the mating plane, -3.30: where the two faces meet
M_Y0 = PG_YM                                                # male nose face
M_Y1 = M_Y0 + PG_M_NOSE                                     # -1.00, the cavity floor: the lip lands here
M_Y2 = M_Y1 + PG_M_LIP_T                                    #  0.00
M_Y3 = M_Y2 + PG_M_BACK                                     #  1.40
M_Y4 = M_Y3 + PG_M_TAIL                                     #  2.90, tail tips
F_Y0 = PG_YM                                                # female top face, against the male's nose
F_Y1 = F_Y0 - PG_F_TOP                                      # -5.30
F_Y2 = F_Y1 - PG_F_LIP_T                                    # -6.20, lip underside: the ledge it is glued to
F_Y3 = F_Y2 - PG_F_BOT                                      # -7.90
F_Y4 = F_Y3 - PG_F_TAIL                                     # -9.30, tail tips
PG_PLINTH_TOP = PG_YM - 0.15                                # the plinth's rim, 0.15 under the mating plane
PG_PLINTH_WALL = 2.20

PG_TAILS = {'GND': (3.45, -1.15), 'GND2': (1.15, -1.15), 'VBUS': (-1.15, -1.15), 'VBUS2': (-3.45, -1.15)}
#   (dx, dz) in the head: dz -1.15 is the row nearer the back cover. The dock carries only power over the junction,
#   each net on two adjacent contacts of that row (the pair is rated 1 A and the Inkplate's power-on spike is 1.66 A):
#   GND on the two nearest the USB-C end, VBUS on the other two (so that in the dock GND runs in front of VBUS, on the
#   side its splice is). The row nearer the board stays empty.
PG_WAYS = tuple((dx, dz) for dz in (1.15, -1.15) for dx in (-3.45, -1.15, 1.15, 3.45))   # all eight, as the part is bought

def pogo_tail(sig):
    dx, dz = PG_TAILS[sig]
    return POGO_X + dx, POGO_Z + dz

def pg_stad(L, W, y0, y1, g=0.0):
    """Stadium in plan, centred on the connector: straight sides, a full semicircular end at each end."""
    L, W = L + 2 * g, W + 2 * g
    r = W / 2.0
    b = box(POGO_X - L/2 + r, POGO_X + L/2 - r, y0, y1, POGO_Z - r, POGO_Z + r)
    union(b, cyl_y(POGO_X - L/2 + r, POGO_Z, y0, y1, r)); union(b, cyl_y(POGO_X + L/2 - r, POGO_Z, y0, y1, r))
    return b

def pg_key(g, y0, y1):
    """The keyed contact block: rounded rectangle, one semicircle out of the middle of its S-end wall.
    g = 0 is the female's boss, PG_FIT the male's pocket - the same shape grown all round."""
    L, W, r = PG_KEY_L + 2 * g, PG_KEY_W + 2 * g, PG_KEY_R
    b = box(POGO_X - L/2 + r, POGO_X + L/2 - r, y0, y1, POGO_Z - W/2, POGO_Z + W/2)
    union(b, box(POGO_X - L/2, POGO_X + L/2, y0, y1, POGO_Z - W/2 + r, POGO_Z + W/2 - r))
    for cx in (POGO_X - L/2 + r, POGO_X + L/2 - r):
        for cz in (POGO_Z - W/2 + r, POGO_Z + W/2 - r): union(b, cyl_y(cx, cz, y0, y1, r))
    cut(b, cyl_y(POGO_X + L/2, POGO_Z, y0 - 1.0, y1 + 1.0, PG_NOTCH_R - g))
    return b

def pg_contacts(y0, y1, r, ways=None):
    out = None
    for dx, dz in (PG_TAILS.values() if ways is None else ways):
        c = cyl_y(POGO_X + dx, POGO_Z + dz, y0, y1, r); out = c if out is None else union(out, c)
    return out

def pg_male_bodies(as_bought=False):
    """The male, in place in the head. as_bought: all eight ways, and the plungers standing free in the pocket."""
    ways = PG_WAYS if as_bought else PG_TAILS.values()
    b = pg_stad(PG_M_L, PG_M_W, M_Y0, M_Y1)                                  # nose, through the bottom wall
    union(b, pg_stad(PG_M_LIP_L, PG_M_LIP_W, M_Y1, M_Y2))                    # lip, landing on the cavity floor, glued
    union(b, pg_stad(PG_M_L, PG_M_W, M_Y2 - 0.01, M_Y3))                     # back band
    cut(b, pg_key(PG_FIT, M_Y0 - 0.01, M_Y0 + PG_POCKET))                    # the pocket, inset into the nose face
    mags = None
    for dx in (-PG_MAG_C, PG_MAG_C):
        cut(b, cyl_y(POGO_X + dx, POGO_Z, M_Y0 - 0.01, M_Y0 + PG_MAG_T, PG_MAG_R))
        m = cyl_y(POGO_X + dx, POGO_Z, M_Y0, M_Y0 + PG_MAG_T, PG_MAG_R)
        mags = m if mags is None else union(mags, m)
    fl = M_Y0 + PG_POCKET                                                    # pocket floor
    pins = pg_contacts(M_Y0, fl, 0.45, ways) if as_bought else pg_contacts(F_Y0 + PG_BOSS, fl + 0.01, 0.45, ways)
    #   fitted, the plungers are drawn COMPRESSED onto the pads: mated, the boss fills the pocket to within
    #   PG_POCKET - PG_BOSS, so that gap is all the travel the pins have left. The barrels live inside the plastic.
    tails = pg_contacts(M_Y3 - 0.01, M_Y4, 0.30, ways)                       # O0.60 x 1.50, into the cavity
    return b, mags, pins, tails

def pg_female_bodies(as_bought=False):
    """The female, in place in the dock. as_bought: all eight ways."""
    ways = PG_WAYS if as_bought else PG_TAILS.values()
    b = pg_stad(PG_F_L, PG_F_W, F_Y3, F_Y2)                                  # bottom band
    union(b, pg_stad(PG_F_LIP_L, PG_F_LIP_W, F_Y2, F_Y1))                    # lip, landing on the plinth's ledge, glued
    union(b, pg_stad(PG_F_L, PG_F_W, F_Y1 - 0.01, F_Y0))                     # top band
    union(b, pg_key(0.0, F_Y0 - 0.01, F_Y0 + PG_BOSS))                       # boss, into the male's pocket
    mags = None                                                              # buried: they do not break the face
    for dx in (-PG_MAG_C, PG_MAG_C):
        cut(b, cyl_y(POGO_X + dx, POGO_Z, F_Y3 - 1.0, F_Y0 - 0.50, PG_MAG_R))
        m = cyl_y(POGO_X + dx, POGO_Z, F_Y0 - 0.50 - PG_MAG_T, F_Y0 - 0.50, PG_MAG_R)
        mags = m if mags is None else union(mags, m)
    pads = pg_contacts(F_Y0 + PG_BOSS - 0.10, F_Y0 + PG_BOSS, 0.90, ways)    # O1.80, flush on the boss
    cut(pads, cyl_y(POGO_X + PG_KEY_L / 2, POGO_Z, F_Y0, F_Y0 + PG_BOSS + 1.0, PG_NOTCH_R))
    cut(b, tb.copy(pads))
    tails = pg_contacts(F_Y4, F_Y3 + 0.01, 0.35, ways)                       # O0.70 x 1.40, down into the plinth
    return b, mags, pads, tails

def build_pogo_head(headc):
    b, mags, pins, tails = pg_male_bodies()
    return add_bodies(headc, 'Pogo male (head)', [('pogo male body', b, 'housing'), ('pogo male magnets', mags, 'silver'),
                                                  ('pogo male pins', pins, 'gold'), ('pogo male tails', tails, 'silver')])

ESP32_VENT = (36.6, 56.6, 46.4, 72.4)   # back-cover grille: X span, then the Y band. Slots run ALONG X -
#   everything else about this object is horizontal (the shadow gap, the PM's vent strip), and one band spanning
#   low to high vents better than two: air enters at the bottom rows and leaves at the top ones.
#   The ESP32-WROVER sits at X 37.6..55.6, Y 43.4..75.4, and it is the only real heat source in the head: eight rows
#   over it, from Y 46.4, with the top row 3.6 under the cover's edge. The CR2032 holder (X 8.6..24.6) makes no heat
#   and stays unvented.

def rrect_h(x0, x1, y0, y1, z0, z1, r):
    """Rounded-rectangle prism in the head frame (corner centres inset by r)."""
    b = box(x0 + r, x1 - r, y0, y1, z0, z1)
    union(b, box(x0, x1, y0 + r, y1 - r, z0, z1))
    for (cx, cy) in [(x0 + r, y0 + r), (x1 - r, y0 + r), (x0 + r, y1 - r), (x1 - r, y1 - r)]:
        union(b, cyl_z(cx, cy, z0, z1, r))
    return b

def head_outline(clear, z0, z1):
    """The head's outer envelope, grown by `clear` - the dock uses it for the cradle pocket and the shell cutout,
    so the rounded corners of the head and of its opening match."""
    return rrect_h(HEAD_X0 - HEAD_LWALL - clear, HEAD_X1 + HEAD_RWALL + clear,
                   HEAD_Y0 - HEAD_WALL - clear, HEAD_Y1 + HEAD_WALL + clear, z0, z1, HEAD_R + clear)

def slots_y(body, X_from, X_to, Ylo, Yhi, Z0, Z1, pitch=3.4, w=2.2, skip=()):
    x = X_from
    while x + w <= X_to + 1e-6:
        if not any(a <= x + w and x <= b for (a, b) in skip):
            cut(body, box(x, x + w, Ylo, Yhi, Z0, Z1))
        x += pitch
    return body

def slots_x(body, Y_from, Y_to, Xlo, Xhi, Z0, Z1, pitch=3.4, w=2.2):
    y = Y_from
    while y + w <= Y_to + 1e-6:
        cut(body, box(Xlo, Xhi, y, y + w, Z0, Z1))
        y += pitch
    return body

def capsule_x(x0, x1, yc, r, z0, z1):
    """Stadium slot running along X: a box with a half-round at each end. Square-ended slots read as cut holes;
    the rounded ends are most of what makes a grille look drawn rather than punched, and cost nothing to print."""
    b = box(x0 + r, x1 - r, yc - r, yc + r, z0, z1)
    union(b, cyl_z(x0 + r, yc, z0, z1, r))
    union(b, cyl_z(x1 - r, yc, z0, z1, r))
    return b

def slots_x_round(body, X0, X1, Y_from, Y_to, Z0, Z1, pitch=3.4, w=2.2):
    y0 = Y_from
    while y0 + w <= Y_to + 1e-6:
        cut(body, capsule_x(X0, X1, y0 + w / 2.0, w / 2.0, Z0, Z1))
        y0 += pitch
    return body

def build_head_tray(headc):
    """Front shell: bezel + 4 walls, 14.1 mm deep, printed face-down."""
    X0, X1, Y0, Y1 = HEAD_X0, HEAD_X1, HEAD_Y0, HEAD_Y1
    ZF, ZLIP, ZBACK = HEAD_ZF, HEAD_STEP_PLAY, HEAD_ZBACK
    t = rrect_h(X0 - HEAD_LWALL, X1 + HEAD_RWALL, Y0 - HEAD_WALL, Y1 + HEAD_WALL, ZBACK, ZF, HEAD_R)
    cut(t, rrect_h(X0, X1, Y0, Y1, ZBACK - 1, ZLIP, HEAD_CAV_R))
    step = rrect_h(X0 - HEAD_STEP, X1 + HEAD_STEP, Y0 - HEAD_STEP, Y1 + HEAD_STEP,
                   ZBACK - 1, ZBACK + HEAD_STEP, HEAD_CAV_R + HEAD_STEP)        # the step the cover's edge lands in,
    for (ya, yb) in TONGUE_Y:                                                   # ... left whole behind each tongue
        cut(step, box(X0 - HEAD_STEP - 1, X0, ya - 1.0, yb + 1.0, ZBACK - 2, ZBACK + HEAD_STEP + 1))
    cut(t, step)
    ZT = ZBACK + 2.0                                                            # the cover's inner face
    for (ya, yb) in TONGUE_Y:                                                   # tongue slots in the thin wall
        cut(t, box(X0 - HEAD_STEP, X0 + 0.01, ya - 0.3, yb + 0.3, ZT - TONGUE_T - HEAD_STEP_PLAY, ZT + 0.25))
    for i, (sx, sy) in enumerate(EAR_SCREW):                                    # ear pockets and insert bores
        cut(t, head_ear(i, 0.2, ZBACK - 1, ZT))
        cut(t, cyl_z(sx, sy, ZT - 0.01, ZT + INSERT_DEPTH, INSERT_R))
    # --- display window: active area (X 10.68..125.24, Y 5.39..69.84) + 0.8 mm, 1 mm step outside ---
    AX0, AX1, AY0, AY1, MARG = 10.68, 125.24, 5.39, 69.84, 0.8
    cut(t, box(AX0 - MARG, AX1 + MARG, AY0 - MARG, AY1 + MARG, ZLIP - 1, ZF + 1))
    cut(t, box(AX0 - MARG - 1, AX1 + MARG + 1, AY0 - MARG - 1, AY1 + MARG + 1, ZF - 1.0, ZF + 1))
    # --- pogo male: a stadium hole through the bottom wall for its nose, and two ribs on the cavity floor that
    #     locate its lip. Everything behind the lip is in open cavity, so with the back cover off you solder the
    #     seven wires to the tails, push the part out through the hole and glue the lip to the floor. ---
    cut(t, pg_stad(PG_M_L, PG_M_W, Y0 - HEAD_WALL - 1.0, M_Y1 + 0.01, PG_CLR))
    for sgn in (-1, 1):                                       # ribs that locate the lip while the glue goes off
        xr = POGO_X + sgn * (PG_M_LIP_L / 2 + PG_CLR + 0.75)
        union(t, box(xr - 0.75, xr + 0.75, M_Y1 - 0.01, M_Y2 - 0.20, POGO_Z - 3.5, POGO_Z + 3.5))
    cut(t, pg_stad(PG_M_LIP_L - 3.0, PG_M_LIP_W - 3.0, M_Y1 - 0.15, M_Y1 + 0.01))   # glue relief: the lip lands on
    #   a 1.5 mm land round its rim and the glue has somewhere to go instead of squeezing out over the contacts
    # --- right wall (thick): USB-C, power button, microSD through stepped pockets ---
    RI = (X1 - 0.5, X1 + 2.0)                       # inner 2 mm skin
    RO = (X1 + 2.0, X1 + HEAD_RWALL + 1)            # outer pocket region
    cut(t, box(RI[0], RI[1], 9.53, 20.53, -6.6, -0.6)); cut(t, box(RO[0], RO[1], 8.03, 22.03, -8.0, 0.4))    # USB-C + plug overmold pocket
    cut(t, box(RI[0], RI[1], 22.03, 30.03, -5.5, -0.8)); cut(t, box(RO[0], RO[1], 20.53, 31.53, -7.5, 0.4))  # power button + finger pocket
    cut(t, box(RI[0], RI[1], 35.53, 52.53, -5.0, -1.2)); cut(t, box(RO[0], RO[1], 33.53, 54.53, -8.0, 0.4))  # microSD + finger pocket
    # --- left wall: wake button ---
    cut(t, box(X0 - HEAD_LWALL - 1, X0 + 0.5, 22.03, 30.03, -5.2, -1.0))
    # --- no vents in the walls: the head's only opening is the grille in the back cover, over the ESP32, where it
    #     faces up and back and is invisible from the front and sides ---
    occ = get_or_make_comp(headc, 'Head tray')
    return replace_body(occ.component, t, 'Head tray')

def build_head_cover(headc):
    """Flat back cover: sits inside the walls on the Inkplate's four M3 SMT standoffs and screws into them.
    Its outer millimetre is wider and lands in the step in the walls, which is what holds the tray - see the notes
    by the cavity constants for the step and for why there are no tray bosses."""
    ZO, ZI = HEAD_ZBACK, HEAD_ZBACK + 2.0
    c = rrect_h(HEAD_X0 + 0.2, HEAD_X1 - 0.2, HEAD_Y0 + 0.2, HEAD_Y1 - 0.2, ZO, ZI, HEAD_CAV_R - 0.2)
    e = HEAD_STEP - 0.2
    edge = rrect_h(HEAD_X0 - e, HEAD_X1 + e, HEAD_Y0 - e, HEAD_Y1 + e,
                   ZO, ZO + HEAD_STEP - HEAD_STEP_PLAY, HEAD_CAV_R + e)
    for (ya, yb) in TONGUE_Y:                                    # no wide edge where the wall stays whole
        cut(edge, box(HEAD_X0 - HEAD_STEP - 1, HEAD_X0 + 0.2, ya - 1.2, yb + 1.2, ZO - 1, ZI + 1))
    union(c, edge)
    for (ya, yb) in TONGUE_Y:
        union(c, box(HEAD_X0 - TONGUE_IN, HEAD_X0 + 0.3, ya, yb, ZI - TONGUE_T, ZI))
    for i, (sx, sy) in enumerate(EAR_SCREW):
        union(c, head_ear(i, 0.0, ZO, ZI))
        cut(c, cyl_z(sx, sy, ZO - 1, ZI + 1, 1.7))               # M3 clearance; the head sits on the ear
    for (x, y) in [(3.4, 3.4), (127.19, 3.4), (3.4, 71.83), (127.19, 71.83)]:   # the Inkplate's own standoffs
        cut(c, cyl_z(x, y, ZO - 1, ZI + 1, 1.7))                                 # M3 clearance
        cut(c, cyl_z(x, y, ZO - 1, ZO + 0.7, 3.1))                               # ... and a shallow counterbore, so
    #   the four heads sit nearly flush in a 2 mm cover instead of standing proud of the back
    cut(c, box(POGO_X - PG_M_LIP_L / 2 - 1.5, POGO_X + PG_M_LIP_L / 2 + 1.5, HEAD_Y0 - 1.0, M_Y2 + 0.4,
               ZI - 0.7, ZI + 1.0))     # relief for the male's lip, which overhangs the cover's inner face by 0.33
    vx0, vx1, vy0, vy1 = ESP32_VENT
    slots_x_round(c, vx0, vx1, vy0, vy1, ZO - 1, ZI + 1)         # grille over the ESP32 module
    occ = get_or_make_comp(headc, 'Head back cover')
    return replace_body(occ.component, c, 'Head back cover')

# ---------------------------------------------------------------------------------------------
# Dock: chassis (floor + cradle block + bay features, printed upright) inside a shell (top skin + 4 walls,
# printed upside down). Dock frame, written "B" in the helpers because D is already the depth axis: X as the head,
# D = depth from the front-bottom edge, H = height above the desk; Fusion world X_f = X, Y_f = D, Z_f = H. The front
# face is a 20-deg slab continuous with the head's bezel; the top skin is flat at H 30.5 to D 37.7, then slopes to
# H 25 at the rear. PM sits on the LEFT.
# The four sensor bays fill D 25..78, and the strip behind them carries, left to right, the AMS1117 that feeds the
# sensors, the TinyS3 that runs them, and the USB-C socket that powers everything - the rear wall's only opening.
#
# The shell's side and rear walls are drafted outward toward the desk and its plan corners are rounded,
# its bottom rim floats GAP above the desk so a continuous shadow gap replaces every visible grille, and the chassis
# is inset from the shell's inner wall so that gap is the bay's intake. Only the PMSA003I keeps real vents, in a
# recessed strip on the left wall opposite its inlet and outlet.
# ---------------------------------------------------------------------------------------------
B_X0, B_X1 = -10.6, 135.9           # outer at the top of the walls; the draft widens this toward the desk
#   1.3 mm outside the head's sides: the wall beside the head is 0.8 mm at the top of the walls and thickens down the
#   draft. Flush with the head, the draft would carry the wall out past its vertical sides to a knife edge.
B_XI0, B_XI1 = -8.6, 133.9          # bay interior (vertical inner walls)
B_D1 = 98.7                         # depth: the sensor bays, then the TinyS3's cradle lying across, behind the SCD41
B_DBAY0, B_DBAY1 = 25.0, 96.7       # bay interior depth range (front = cradle block's rear face)
H_FRONT, H_REAR = 33.9, 25.0        # top skin, outer: one plane from the front edge down to the rear, 5.15 deg, so
D_SLOPE = 0.0                       # printed upside down the whole skin lies on the bed. The rear is set by the
SLOPE = (H_FRONT - H_REAR) / (B_D1 - D_SLOPE)   # TinyS3's USB-C (1.5 mm under the skin); the wires arcing over the PM
#   header (H_OVER) have 1.4 mm under it, and the front is where that slope arrives.
#   Set by the connectors, not the boards: a Dupont housing standing on a straight header needs 14 mm for itself and
#   3.7 mm for the wire to turn (measured), so on a board at H 5.6 the wire's crown is at H 25.8, and the skin's
#   underside has to clear that wherever a housing stands - at the PM header (D 29.5) and the SCD41 header (D ~48).
#   At the rear, the TinyS3's USB-C is the highest thing: H 22.3 at D 89.3, with the skin 1.5 mm above it.
SKIN = 2.0
TILT = 20.0
GAP = 1.5                           # shadow gap: the shell's bottom rim floats this far above the desk
CH_INSET = 1.5                      # chassis inset from the shell's inner wall = the air path from the gap into the bay
CH_FRONT = 0.3                      # cradle block to the shell's front wall, square to it: the wall rests on it if pushed
DRAFT = 4.3                         # deg, side and rear walls flare toward the desk (2.0 mm over the height)
R_PLAN = 10.0                       # shell plan corner radius, at the top of the walls
C_TOP, C_RIM = 1.5, 0.8             # chamfers on the top edge and on the bottom rim. A 2 mm skin cannot carry a
                                    # fillet bigger than 1.17 mm (the arc breaks into the cavity at the corner),
                                    # but a 45 deg chamfer of leg c only eats (4-c)/sqrt(2), so 1.5 mm is safe.
R_CAV = R_PLAN - SKIN               # cavity corners, concentric with the outer ones -> constant wall
R_CH = R_CAV - CH_INSET             # chassis corners, concentric again -> constant gap
REC_DEPTH = 1.0                     # depth of the recessed vent strip on the left wall
HEAD_FRONT_H = 13.5                                    # head's front-bottom edge height. It was 12.0. Only the
#   female and its plinth sit in the joint now - the male is inside the head - so what the cradle has to find room
#   for is 6 mm of connector below the mating plane plus wire room under its tails, not the whole 13.2 mm pair.
#   The 20 deg tilt still spends depth across the connector's width, which is what the extra 1.5 buys.
HEAD_FRONT_D = HEAD_FRONT_H * math.tan(math.radians(TILT))   # ... and depth: the bezel plane passes through (D 0, H 0)
BLOCK_TOP_REAR = 14.0               # cradle block height behind the head (rear lip)
HEAD_CLR = 0.5                      # clearance round the head's outline in the cradle pocket and the shell's opening

def boxb(X0, X1, D0, D1, H0, H1):  return box(X0, X1, H0, H1, -D1, -D0)
def cylH(X, D, H0, H1, r):         return cyl_y(X, -D, H0, H1, r)
def coneH(X, D, H0, r0, H1, r1):   return tb.createCylinderOrCone(P(X, H0, -D), r0 * M, P(X, H1, -D), r1 * M)
def hs_b(pt, n):                   # dock-frame halfspace: (X, D, H) point and normal
    return halfspace((pt[0], pt[2], -pt[1]), (n[0], n[2], -n[1]))

def rrect_b(x0, x1, d0, d1, h0, h1, r):
    """Rounded-rectangle prism, corner centres inset by r."""
    b = boxb(x0 + r, x1 - r, d0, d1, h0, h1)
    union(b, boxb(x0, x1, d0 + r, d1 - r, h0, h1))
    for (cx, cd) in [(x0 + r, d0 + r), (x1 - r, d0 + r), (x0 + r, d1 - r), (x1 - r, d1 - r)]:
        union(b, cylH(cx, cd, h0, h1, r))
    return b

def drafted_rrect(x0, x1, d0, d1, h0, h1, r, draft_deg, h_ref):
    """Rounded-rectangle prism whose plan outline is (x0..x1, d0..d1) with radius r at H = h_ref and flares
    outward below it by tan(draft): corners become truncated cones, sides become tilted planes."""
    t = math.tan(math.radians(draft_deg))
    ra = lambda h: r + (h_ref - h) * t
    body = None
    for (cx, cd) in [(x0 + r, d0 + r), (x1 - r, d0 + r), (x0 + r, d1 - r), (x1 - r, d1 - r)]:
        c = coneH(cx, cd, h0, ra(h0), h1, ra(h1))
        body = c if body is None else union(body, c)
    sd = boxb(x0 + r, x1 - r, d0 - 40, d1 + 40, h0, h1)          # front / rear walls, drafted in D
    cut(sd, hs_b((0.0, d0, h_ref), (0.0, -1.0, t)))
    cut(sd, hs_b((0.0, d1, h_ref), (0.0, 1.0, t)))
    union(body, sd)
    sx = boxb(x0 - 40, x1 + 40, d0 + r, d1 - r, h0, h1)          # side walls, drafted in X
    cut(sx, hs_b((x0, 0.0, h_ref), (-1.0, 0.0, t)))
    cut(sx, hs_b((x1, 0.0, h_ref), (1.0, 0.0, t)))
    union(body, sx)
    return body

def top_chamfer_solid():
    """The top-edge chamfer, built into the solid rather than as a chamfer feature: a 45 deg drafted prism with its
    reference plane C_TOP under the skin, tilted with it. It takes exactly C_TOP off the top edge all the way round,
    wrapping the rounded corners, and leaves everything lower untouched (45 deg flares faster than the 4.3 deg wall
    draft)."""
    k = drafted_rrect(B_X0, B_X1, 0.0, B_D1, -20.0, H_FRONT + 6.0, R_PLAN, 45.0, H_FRONT - C_TOP)   # +6: at 45 deg the corner radius would reach zero 10 mm above the reference plane
    m = adsk.core.Matrix3D.create()
    m.setToRotation(-math.atan(SLOPE), adsk.core.Vector3D.create(1, 0, 0),
                    adsk.core.Point3D.create(0.0, D_SLOPE * M, (H_FRONT - C_TOP) * M))
    tb.transform(k, m)
    return k

def head_matrix(tilt_deg=TILT, front_d=HEAD_FRONT_D, front_h=HEAD_FRONT_H):
    rot = adsk.core.Matrix3D.create()
    rot.setToRotation(math.radians(-tilt_deg), adsk.core.Vector3D.create(1, 0, 0), adsk.core.Point3D.create(0, 0, 0))
    a = P(0.0, -3.0, HEAD_ZF); a.transformBy(rot)
    dx = (B_X0 + B_X1) / 2 - POGO_X                                                          # centres the head on the dock
    tr = adsk.core.Matrix3D.create(); tr.translation = adsk.core.Vector3D.create(dx * M, front_d * M - a.y, front_h * M - a.z)
    m = rot.copy(); m.transformBy(tr)
    return m

def head_point(mh, X, Y, Z):
    p = P(X, Y, Z); p.transformBy(mh); return p
def head_dir(mh, X, Y, Z):
    v = V(X, Y, Z); v.transformBy(mh); v.normalize(); return v
def head_volume(mh, clear, z0, z1):
    """The head's envelope, in dock-frame world position: the pocket and the shell's opening both come from this."""
    v = head_outline(clear, z0, z1)
    tb.transform(v, mh)
    return v
def skin_top(d):                    # outer top surface height at depth d
    return H_FRONT - SLOPE * (d - D_SLOPE)

# --- bay layout (mm) ---------------------------------------------------------
PM_X0, PM_D0 = -3.8, 27.0                     # PMSA003I X -3.8..31.8 (air face 4.8 mm from the left wall), D 27..77.8, header row at the FRONT
#   X -3.8: the chassis floor is inset 1.5 mm from the wall (CH_INSET), so the board edge and its two left bosses need
#   ~1 mm of floor under them; everything between the PM and the SCD41 compartment moved right with it
#   D 27 keeps the board's rear corner clear of the cavity's 10 mm rounded corner (2.9 mm at the tightest point)
PM_PINS = {k: PM_X0 + v for k, v in {'SET': 25.4, 'SDA': 20.32, 'SCL': 17.78, 'GND': 15.24, 'VIN': 10.16}.items()}   # straight header at D 29.54, housings standing up
SCD_X1, SCD_D0 = 72.8, 35.0                   # SCD41 X 49.9..72.8, D 35..60.4, sockets facing front / rear (centre X 61.4)
BME_X0, BME_D0 = 82.8, 53.5                   # BME688 X 82.8..120.8, D 53.5..75.5 (rear-right)
SHT_X0, SHT_D0 = 82.8, 26.5                   # SHTC3 X 82.8..120.8, D 26.5..48.5 (front-right, coolest corner)
AMS_X0, AMS_D0 = 8.0, 80.5                    # AMS1117 X 8..20.5, D 80.5..89, lying across behind the PM board, pins to the RIGHT
#   Left of the TinyS3's cradle, so both warm parts sit at the back, away from the SHTC3. Its three Dupont housings run
#   right over X 21.8..35.8, towards the cradle and the socket that feeds them, and stop 10 mm short of the cradle.
AMS_CLR = 0.5                                 # slip fit: 0.3 a side gave a 9.1 mm slot for an 8.5 mm board, and a printed
#   slot finishes 0.1-0.2 mm under nominal per wall, so it was not a fit you could count on. 9.5 mm is.
AMS_H = 6.0                                   # underside of the board: 2 mm higher than the other boards, so the SOT-223 clears
#   the floor by 2.3 mm instead of 0.3 and sits in a through-passage rather than a sealed slot
AMS_TAB = 2.5                                 # the side walls survive only as corner tabs this long; the rest is the passage
AMS_DOME = 1.2                                # the header's solder domes stand this proud of the board's underside
COMP = (47.3, 48.8, 74.3, 75.8, 30.0, 72.0, 73.5)
BAFFLE_D = (50.0, 51.5)
TRENCH = (42.0, 84.0, 9.5, 26.0)              # Now only a well for the pogo plinth (X 46.1..79.2), with about
#   4 mm of working room either side of it and the whole top open once the head is off. It used to run the full
#   width, back when seven loose wires crossed the joint and had to travel along it to reach the boards; they go
#   out the back of the plinth into the bay now, so the rest of the cradle block - and the wall behind it - stays.
RIBBON_X = 44.3                               # Qwiic lane, between the AMS pocket rib (42.8) and the compartment wall (47.3): the outer
#   conductor's bend at the front swings out towards the wall's corner, so the lane sits nearer the rib
RIBBON_XR = 126.0                             # lane for the BME688 -> SHTC3 ribbon: inboard of the chassis edge (132.4) so the
#   guide rib below, not the shell's inner wall, is what keeps the ribbon tidy. At 129.1 the ribbon overhung the edge and
#   could only be held in by fitting the shell over it.
RIB_XR = (128.5, 35.0, 67.0, 9.0)             # outer guide rib: X 128.5..chassis edge, D 35..67, up to H 9
#   Plan positions clear of every board, plug, ribbon and wire lane - and far enough in from the chassis edge that the
#   countersink on the underside keeps a full wall outside it. The first print had them at (126,30), (50,78.5) and
#   (126,79): 0.8, 0.7 and -0.6 mm of material outside the CSK_D/2 circle, the last one breaking clean out through the
#   rounded corner. The corner is the trap - the chassis corner is r 6.5, so out there the edge curves away on two sides
#   at once and the useful position is near the arc's centre, not near the corner. The two rear ones sit near the rear
#   corners' centres, (-0.6, 88.7) and (125.9, 88.7); the left one is the only pillar on the PM board's side.
SHELL_PILLARS = [(68.0, 30.0), (125.0, 30.0), (0.0, 88.7), (125.0, 88.7)]
CSK_D, CSK_H = 6.2, 1.4                       # countersink for the M3 flat heads, 90 deg: an ISO 7046 head is 5.5 (5.6
#   max) across, so 6.2 clears it, and taking 0.4 off the 6.6 first drawn is 0.2 mm more wall at every hole.
PILLAR_BOSS = 1.0                             # a boss on the chassis floor under each pillar, the pillar's own radius, so
#   the floor the screw head bears on is 1.6 mm above the cone, not 0.6; the pillar starts on top of it
AMS_POST = (AMS_X0 + 7.5, AMS_D0 + 4.25, 2.0, AMS_H + 1.4)   # on the board's centreline, between the two supports, so the
#   two rather than pivoting about the pad - landing on the board's top face, on bare board between the header and R1:
#   the pocket sets the board's height and the post only stops it lifting, so a print's 0.1 mm either way is fine
PM_BOSSES = [(PM_X0 + 2.54, PM_D0 + 2.54), (PM_X0 + 33.02, PM_D0 + 2.54), (PM_X0 + 2.75, PM_D0 + 48.3), (PM_X0 + 32.75, PM_D0 + 15.3)]   # Adafruit 4632 holes
PM_SEAL_D = (PM_D0 + 27.8, PM_D0 + 31.1)      # seal rib between the module's two ports (gap: 54.5..58.4)
PM_SEAL_W, PM_SEAL_H = PM_X0 - 0.2 - B_XI0, 19.0   # fills the gap to the module face (0.2 mm short of it), up to 1 mm above the module
PM_VENTS = ((PM_D0 + 14.4, PM_D0 + 27.5), (PM_D0 + 31.4, PM_D0 + 51.0))   # fan outlet (front) and inlet (rear)
VENT_H = (9.0, 20.0)                          # the recessed strip that carries them

# --- the TinyS3: ICs up, headers pointing down into two female header strips glued into a printed cradle ---
#   Dimensions from Unexpected Maker's STEP model: PCB 34.68 x 17.8 x 1.0, the USB-C 0.53 mm past the board's end
#   and 4.34 mm above its underside, the two rows 1.27 mm in from the long edges (15.24 apart) with pin 1 of both
#   4.06 mm from the USB-C end. The cradle is drawn in the board's own frame (x from the USB-C end, y from the J4
#   edge) and ts_box() puts it in the dock: lying across behind the SCD41 compartment, the USB-C at the right end and
#   J4 (12 pins: SCL, SDA, IO7, GND) at the rear. J3 (11 pins: GND, 5V) is at the front, with its 5V and GND nearest
#   the right end and the power socket beyond it. The wires solder to the strips' tails under the deck, on the bench.
TS_L, TS_W, TS_PCB = 34.68, 17.8, 1.0
TS_USB_OUT, TS_USB_TOP = 0.53, 4.34           # the USB-C past the board's end, and its top above the board's underside
TS_USB_Y = (4.45, 13.39)                      # its span across the board
TS_PIN0, TS_ROW_IN = 4.06, 1.27               # first pin from the USB-C end; each row in from its long edge
TS_J4, TS_J3 = 12, 11
TS_DECK = 5.0                                 # the strips' seat above the floor: their 3 mm legs end 2 mm off it
TS_LEG_CLR, TS_LEDGE_T = 0.6, 1.2             # a strip's outer edge rests on a ledge that stops this far from the row's
#   centre (0.28 clear of the legs), and is this thick, so a joint on the leg's lower half passes under it
TS_END_LAP = 0.67                             # a strip's two ends rest on blocks that reach this far under it: clear of the
#   end pins' legs, which are never wired (J3's VBAT and IO0, J4's IO35 and RX)
STRIP_H, STRIP_TAIL, SPACER_H = 8.5, 3.0, 2.5 # female strip (standard height), its tails, the TinyS3 header's spacer
STRIP_W = 2.5                                 # the strip's width: 2.4 measured, rounded up because the calipers are not precise
STRIP_CLR, POCKET_WALL, POCKET_H = 0.25, 1.2, 4.0   # the strips are glued: a slip fit, walls to half the strip's height
TS_H = 2.0 + TS_DECK + STRIP_H + SPACER_H     # 18.0, the TinyS3's underside
TS_EDGE_X = 81.0                              # the board's USB-C end: the cradle stops 3 mm short of the BME688 and 4 mm clear of the AMS1117's pocket
TS_DC = 84.85                                 # the board's centreline: the cradle's front edge 1 mm behind the SCD41 compartment

def ts_box(x0, x1, y0, y1, h0, h1):
    """A box given in the TinyS3's frame, placed in the dock: x runs left from the USB-C end, y forward from J4's edge."""
    return boxb(TS_EDGE_X - x1, TS_EDGE_X - x0, TS_DC + TS_W / 2 - y1, TS_DC + TS_W / 2 - y0, h0, h1)

def ts_row_y(j3):
    return TS_W - TS_ROW_IN if j3 else TS_ROW_IN

def ts_pin_x(k):
    return TS_PIN0 + 2.54 * k

TS_ROWS = ((False, TS_J4), (True, TS_J3))
TS_POCKET = STRIP_W / 2 + STRIP_CLR + POCKET_WALL    # a pocket's outside, from its row's centre

# --- USB-C power socket: the 24-pin female module (15.0 x 14.5, no holes), lying flat by the rear wall, right of the
#   TinyS3 and behind the BME688. Its receptacle is mid-mount, in a notch between two ears, so the tongue is at the
#   board's mid-plane. Its opening is the rear wall's only one. ---
PW_X, PW_H = 96.0, 8.0                        # centre, and the tongue's height: the opening's bottom stays 2.5 mm above the rim
PW_W, PW_L, PW_T = 15.0, 14.5, 1.0
PW_REC_W, PW_REC_T, PW_REC_L = 8.94, 3.26, 7.35
PW_MOUTH_D = B_DBAY1 - 0.3                    # just inside the rear wall, so the shell drops on past it
CC_SEAT_D0 = 88.1                             # the left ear's seat starts here, 0.3 behind the B5 resistor (USB-C to USB-C only)
PLUG_W_MAX, PLUG_T_MAX, PLUG_CLR = 12.35, 7.5, 0.25   # a USB-C plug's moulded body, as allowed for, and the opening's clearance round it

# --- status LED: a 3 mm diffused yellow LED (item 142) on IO6, behind a clear LEGO 1x1 round tile set flush in the
#   front face under the display's right end, where the head never hides it. The tile presses into the shell, front
#   sanded, so it glows evenly and the LED behind it does not show. It is thicker than the wall, so its back stands in a
#   shallow relief in the cradle block, which lets the shell still slide down over the block. The LED goes in from an
#   access pit that opens under the head: with the head off it is lowered in already wired, pushed forward until its
#   rim stops on a step, and glued; its wires run back along the pit's floor into the bay. ---
LED_X, LED_H = 118.0, 7.0                     # where the LED's axis meets the cradle block's face: halfway up the face
LED_BODY_D, LED_RIM_D, LED_RIM_T, LED_L = 3.0, 3.8, 1.0, 5.3   # a typical T-1 LED: body, rim, rim thickness, tip to rim's back
LED_CLR = 0.2                                 # the pocket, each side, on both diameters
LED_TIP = 1.2                                 # the LED's tip, behind the block's face: 0.3 clear of the tile's back
TILE_D, TILE_T = 7.8, 3.2                     # LEGO 1x1 round tile (35380 / 98138), the published sizes
TILE_FIT = 0.2                                # the shell's hole over the tile, on the diameter: a printed hole comes out
#   smaller than drawn, and 0.1 would not take the tile by hand. Raise this, not the tile, if a print is still tight
TILE_LEAD = 0.4                               # lead-in chamfer at the hole's mouth, so the tile finds the hole and seats flush
TILE_CLR = 0.25                               # the relief round the tile's back
LOGO_PILL_L, LOGO_PILL_H, LOGO_DEPTH = 35.0, 9.6, 0.8   # the logo's pill recess in the front face: its white pieces
#   (printed apart, 0.8 thick, 8 mm tall) are glued to its floor, flush with the face. It is centred across the
#   shell and halfway up the face, 0.9 mm of face above and below it.
LED_PIT = (5.0, 11.5, 2.3)                    # the access pit: half-width, front (D), floor (H). The front stays 0.6 behind the
#   LED's step, and the floor is under the rim's bore where the two meet, so the LED can be pushed straight in.

def build_ts_cradle(body):
    """The TinyS3's cradle: a pocket per header strip, made of an outer wall with a ledge under the strip's outer edge
    and a block under each end. Nothing stands between the two strips, down to the floor: their legs, and the wires
    soldered to them, hang in a channel that runs the cradle's length and is open at both ends."""
    fl, seat = 2.0 - 0.01, 2.0 + TS_DECK
    g = STRIP_W / 2 + STRIP_CLR
    for j3, n in TS_ROWS:
        y = ts_row_y(j3)
        out = 1 if j3 else -1                                                                # the strip's outer side, in y
        s0, s1 = ts_pin_x(0) - 1.27, ts_pin_x(n - 1) + 1.27
        p0, p1 = s0 - STRIP_CLR, s1 + STRIP_CLR
        w0, w1 = p0 - POCKET_WALL, p1 + POCKET_WALL
        yo, yw, yl = y + out * g, y + out * TS_POCKET, y + out * TS_LEG_CLR
        union(body, ts_box(w0, w1, min(yo, yw), max(yo, yw), fl, seat + POCKET_H))          # outer wall
        union(body, ts_box(p0, p1, min(yl, yo), max(yl, yo), seat - TS_LEDGE_T, seat))       # ledge
        for e0, e1 in ((w0, s0 + TS_END_LAP), (s1 - TS_END_LAP, w1)):                        # end blocks
            union(body, ts_box(e0, e1, y - TS_POCKET, y + TS_POCKET, fl, seat))
        for e0, e1 in ((w0, p0), (p1, w1)):                                                  # end walls
            union(body, ts_box(e0, e1, y - TS_POCKET, y + TS_POCKET, seat - 0.01, seat + POCKET_H))

def build_pw_holder(body):
    """The USB-C power socket's seat: a pad under each ear either side of the receptacle, side guides, and two corner
    stops at the pad edge, which leave the pads' middle free for the wires. Nothing else is under the board, so the
    B5 resistor has room; the left ear's pad starts behind it. Glued."""
    fl, h0 = 2.0 - 0.01, PW_H - PW_T / 2
    b0, b1 = PW_MOUTH_D - PW_L, PW_MOUTH_D
    ch = B_DBAY1 - CH_INSET
    wg = PW_W / 2 + 0.3                                                                      # the guides' inner faces: the ear
    for s in (-1, 1):                                                                        # pads run out to them, so no 0.3
        xe0, xe1 = sorted((PW_X + s * (PW_REC_W / 2 + 0.45), PW_X + s * wg))                 # slot is left under the board
        union(body, boxb(xe0, xe1, CC_SEAT_D0 if s < 0 else b0 - 0.3, ch, fl, h0))          # under the ears
        xg0, xg1 = sorted((PW_X + s * (PW_W / 2 + 0.3), PW_X + s * (PW_W / 2 + 1.5)))
        union(body, boxb(xg0, xg1, b0 - 1.5, ch, fl, PW_H + 1.5))                            # side guides
        xs0, xs1 = sorted((PW_X + s * (PW_W / 2 - 1.0), PW_X + s * (PW_W / 2 + 0.3)))
        union(body, boxb(xs0, xs1, b0 - 1.5, b0 - 0.3, fl, PW_H + 1.5))                      # corner stops
    cut(body, boxb(PW_X - wg, PW_X + wg, b0 - 0.3, PW_PAD_D1 + 0.3, h0 - 0.1, h0 + 0.1))       # 0.1 relief under the pad row

def rrect_bd(xc, hc, w, t, d0, d1, r):
    """Rounded rectangle in the X-H plane, extruded along D."""
    b = boxb(xc - w / 2 + r, xc + w / 2 - r, d0, d1, hc - t / 2, hc + t / 2)
    union(b, boxb(xc - w / 2, xc + w / 2, d0, d1, hc - t / 2 + r, hc + t / 2 - r))
    for cx in (xc - w / 2 + r, xc + w / 2 - r):
        for ch in (hc - t / 2 + r, hc + t / 2 - r):
            union(b, cyl_z(cx, ch, -d1, -d0, r))
    return b

def plug_opening():
    """The power plug's opening in the rear wall, from the receptacle's mouth outward."""
    return rrect_bd(PW_X, PW_H, PLUG_W_MAX + 2 * PLUG_CLR, PLUG_T_MAX + 2 * PLUG_CLR, PW_MOUTH_D, B_D1 + 10.0, 2.0)

def led_at(t, up=0.0):
    """E-frame point t mm back along the LED's axis from where it meets the cradle block's face, up mm off the axis
    in the axis's vertical plane."""
    c, s = math.cos(math.radians(TILT)), math.sin(math.radians(TILT))
    d = LED_H * s / c + (SKIN + CH_FRONT) / c + t * c + up * s
    return P(LED_X, LED_H - t * s + up * c, -d)

def led_pocket(body):
    """The tile's relief, the LED's stepped pocket and the access pit, cut from the cradle block."""
    c, s = math.cos(math.radians(TILT)), math.sin(math.radians(TILT))
    t_back = TILE_T - (SKIN + CH_FRONT)                                                     # the tile's back, behind the block's face
    w = TILE_D / 2 + TILE_CLR
    relief = boxb(LED_X - w, LED_X + w, -5.0, B_DBAY0, LED_H - w * c - t_back * s - 0.3,     # rising with the shell, the tile
                  LED_H + w * c + t_back / s)                                                # is clear of the face by the top
    inter(relief, hs_b((0.0, (SKIN + CH_FRONT + t_back + TILE_CLR) / c, 0.0), (0.0, -c, s)))
    cut(body, relief)
    step = LED_TIP + LED_L - LED_RIM_T                                                       # the rim stops here
    cut(body, cyl(led_at(LED_TIP - 0.5), led_at(step), LED_BODY_D / 2 + LED_CLR))
    cut(body, cyl(led_at(step), led_at(step + 2.3), LED_RIM_D / 2 + LED_CLR))                # ends just inside the pit, over its floor
    hw, d0, h0 = LED_PIT
    cut(body, boxb(LED_X - hw, LED_X + hw, d0, B_DBAY0 + 1.0, h0, H_FRONT + 1.0))

def tile_hole():
    """The shell's hole for the tile, with a lead-in at its mouth on the face."""
    r = (TILE_D + TILE_FIT) / 2
    face = -(SKIN + CH_FRONT)                                             # the shell's front face, along the LED's axis
    hole = cyl(led_at(face - 2.0), led_at(0.0), r)
    union(hole, tb.createCylinderOrCone(led_at(face - 0.01), (r + TILE_LEAD) * M, led_at(face + TILE_LEAD), r * M))
    return hole

def logo_centre():
    """The logo pill's centre: X across the shell, and its distance up the front face from the bezel plane's foot,
    halfway up the face. The face runs from the rim's chamfer to the head's opening, 11.5 mm along the slope."""
    c = math.cos(math.radians(TILT))
    lo, hi = GAP / c + C_RIM, HEAD_FRONT_H / c - HEAD_CLR
    return (B_X0 + B_X1) / 2, (lo + hi) / 2

def logo_recess():
    """The pill recess for the logo, LOGO_DEPTH into the front face and open outward."""
    c, s = math.cos(math.radians(TILT)), math.sin(math.radians(TILT))
    xc, sc = logo_centre()
    u_e, n_e = (0.0, c, -s), (0.0, s, c)                                  # E frame: up the face, and out of it
    def at(x, along, out): return (x, sc * c + along * u_e[1] + out * n_e[1], -sc * s + along * u_e[2] + out * n_e[2])
    r = LOGO_PILL_H / 2
    a = LOGO_PILL_L / 2 - r
    out0, out1 = -LOGO_DEPTH, 1.0
    obb = adsk.core.OrientedBoundingBox3D.create(P(*at(xc, 0.0, (out0 + out1) / 2)), V(1, 0, 0), V(*u_e),
                                                 2 * a * M, LOGO_PILL_H * M, (out1 - out0) * M)
    pill = tb.createBox(obb)
    for x in (xc - a, xc + a):
        union(pill, cyl(P(*at(x, 0.0, out0)), P(*at(x, 0.0, out1)), r))
    return pill

LOGO_COMP = 'Logo (white, printed apart)'
STENCIL_COMP = 'Logo stencil (tool, printed apart)'
STENCIL_T = LOGO_DEPTH + 0.8                  # the stencil: LOGO_DEPTH of it fills the recess round the pieces, the rest
STENCIL_FIT = 0.15                            # stands proud. It is this much smaller than the pill all round
STENCIL_ARCH = (14.3, 1.6, 1.2, 5.0, 1.5)     # a grab arch at each end, standing on the stencil's top face: its X from
#   the pill's centre, its width along X, each leg's width, the gap under the bar (a fingertip), and the bar's thickness.
#   It stands past the openings, on the solid end of the pill, so nothing blocks a piece going in; the bar spans the
#   pill's width there, so it prints as a short bridge.

def svg_part(dockc, comp_name, svg, thickness, piece_name):
    """A component holding one SVG extruded thickness mm, its pieces still lying in the XY plane at the origin.
    Returns (occurrence, sketch, the extrude's bodies). An outline inside an even number of others bounds solid;
    an odd number, a hole."""
    occ = None                                                             # the component is emptied and refilled, not
    for parent in (dockc, dock_electronics(dockc)):                        # replaced: a deleted component keeps its name
        for o in list(parent.occurrences):                                 # in the design until the file is saved
            if o.component.name.startswith(comp_name):
                if occ is None: occ = o
                elif not o.deleteMe(): raise RuntimeError('could not delete ' + o.component.name)
    if occ is None:
        occ = dockc.occurrences.addNewComponent(adsk.core.Matrix3D.create())
        occ.component.name = comp_name
    comp = occ.component
    for f in reversed(list(comp.features)):                                # newest first: deleting one takes with it
        try: f.deleteMe()                                                  # every later feature that depends on it
        except RuntimeError: pass
    for sk in list(comp.sketches): sk.deleteMe()
    for b in list(comp.bRepBodies): b.deleteMe()
    sk = comp.sketches.add(comp.xYConstructionPlane)
    sk.importSVG(os.path.join(os.path.dirname(os.path.abspath(__file__)), svg), 0.0, 0.0, 96.0 / 25.4)   # Fusion reads SVG units as 1/96 in
    def outline(prof):
        """The profile's outer loop as an ordered polygon (cm)."""
        loop = [l for l in prof.profileLoops if l.isOuter][0]
        poly = []
        for pc in loop.profileCurves:
            ev = pc.geometry.evaluator
            _, t0, t1 = ev.getParameterExtents()
            _, pts = ev.getStrokes(t0, t1, 0.0005)
            pts = [(p.x, p.y) for p in pts]
            if poly and (pts[0][0] - poly[-1][0]) ** 2 + (pts[0][1] - poly[-1][1]) ** 2 > (pts[-1][0] - poly[-1][0]) ** 2 + (pts[-1][1] - poly[-1][1]) ** 2:
                pts.reverse()
            poly += pts
        return poly
    def inside(pt, poly):
        x, y, n = pt[0], pt[1], False
        for (x0, y0), (x1, y1) in zip(poly, poly[1:] + poly[:1]):
            if (y0 > y) != (y1 > y) and x < x0 + (y - y0) * (x1 - x0) / (y1 - y0): n = not n
        return n
    profs = list(sk.profiles)
    polys = [outline(p) for p in profs]
    solid = adsk.core.ObjectCollection.create()
    for i, prof in enumerate(profs):
        if sum(inside(polys[i][0], q) for j, q in enumerate(polys) if j != i) % 2 == 0: solid.add(prof)
    ext = comp.features.extrudeFeatures.addSimple(solid, adsk.core.ValueInput.createByReal(thickness * M),
                                                   adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
    for i, bd in enumerate(ext.bodies): bd.name = '%s %d' % (piece_name, i + 1) if ext.bodies.count > 1 else piece_name
    sk.isVisible = False
    return occ, sk, list(ext.bodies)

def into_recess(comp, sk, bodies):
    """Move the part from the XY plane onto the recess floor, its SVG centred on the pill's centre. A Move feature,
    not the occurrence's transform, which the timeline resets."""
    bb = sk.boundingBox
    cx, cy = (bb.minPoint.x + bb.maxPoint.x) / 2, (bb.minPoint.y + bb.maxPoint.y) / 2
    c, s = math.cos(math.radians(TILT)), math.sin(math.radians(TILT))
    xc, sc = logo_centre()
    fl = (xc * M, (sc * s + LOGO_DEPTH * c) * M, (sc * c - LOGO_DEPTH * s) * M)   # the recess floor's centre (Fusion = dock X, D, H)
    u, n = (0.0, s, c), (0.0, -c, s)                                       # up the face, and out of it
    m = adsk.core.Matrix3D.create()
    m.setWithCoordinateSystem(adsk.core.Point3D.create(fl[0] - cx, fl[1] - cy * u[1], fl[2] - cy * u[2]),
                              adsk.core.Vector3D.create(1, 0, 0), adsk.core.Vector3D.create(*u), adsk.core.Vector3D.create(*n))
    coll = adsk.core.ObjectCollection.create()
    for b in bodies: coll.add(b)
    mv = comp.features.moveFeatures.createInput2(coll)
    mv.defineAsFreeMove(m)
    comp.features.moveFeatures.add(mv)

def build_logo(dockc):
    """The logo's white pieces (canary-logo.svg, 8 mm tall, traced for a 0.2 mm nozzle), LOGO_DEPTH thick, lying
    on the recess floor. A separate print: export these bodies and print them flat."""
    occ, sk, bodies = svg_part(dockc, LOGO_COMP, 'canary-logo.svg', LOGO_DEPTH, 'logo piece')
    into_recess(occ.component, sk, bodies)
    return occ, {b.name: 'white' for b in bodies}

def build_stencil(dockc):
    """The tool that places the pieces: the pill, STENCIL_FIT smaller all round, with an opening 0.15 clear of each
    piece. It drops into the recess, each piece is glued through it, and it lifts straight out by the two arches.
    Printed apart, recess side down, and hidden unless its light bulb is on."""
    occ, sk, bodies = svg_part(dockc, STENCIL_COMP, 'canary-stencil.svg', STENCIL_T, 'stencil')
    comp = occ.component
    xa, wa, wl, gap, tbar = STENCIL_ARCH
    bb = sk.boundingBox
    xc, yc = (bb.minPoint.x + bb.maxPoint.x) / 2, (bb.minPoint.y + bb.maxPoint.y) / 2
    r = LOGO_PILL_H / 2 - STENCIL_FIT                                      # the pill's rounded end: its edge closes in
    straight = LOGO_PILL_L / 2 - STENCIL_FIT - r                           # past this X, so the arch is measured there
    half = math.sqrt(max(r ** 2 - max(0.0, xa + wa / 2 - straight) ** 2, 0.25)) * M
    def rect(sk_, x0, x1, y0, y1):
        sk_.sketchCurves.sketchLines.addTwoPointRectangle(adsk.core.Point3D.create(x0, y0, 0), adsk.core.Point3D.create(x1, y1, 0))
    def raise_(sk_, start, height):
        coll = adsk.core.ObjectCollection.create()
        for prof in sk_.profiles: coll.add(prof)
        inp = comp.features.extrudeFeatures.createInput(coll, adsk.fusion.FeatureOperations.JoinFeatureOperation)
        inp.participantBodies = bodies
        inp.startExtent = adsk.fusion.OffsetStartDefinition.create(adsk.core.ValueInput.createByReal(start * M))
        inp.setOneSideExtent(adsk.fusion.DistanceExtentDefinition.create(adsk.core.ValueInput.createByReal(height * M)),
                             adsk.fusion.ExtentDirections.PositiveExtentDirection)
        comp.features.extrudeFeatures.add(inp)
        sk_.isVisible = False
    legs = comp.sketches.add(comp.xYConstructionPlane)
    for sgn in (-1.0, 1.0):
        for side in (-1.0, 1.0):
            rect(legs, xc + (sgn * xa - wa / 2) * M, xc + (sgn * xa + wa / 2) * M,
                 yc + side * half - (wl * M if side > 0 else 0.0), yc + side * half + (wl * M if side < 0 else 0.0))
    raise_(legs, STENCIL_T, gap)
    bar = comp.sketches.add(comp.xYConstructionPlane)
    for sgn in (-1.0, 1.0):
        rect(bar, xc + (sgn * xa - wa / 2) * M, xc + (sgn * xa + wa / 2) * M, yc - half, yc + half)
    raise_(bar, STENCIL_T + gap, tbar)
    into_recess(comp, sk, list(comp.bRepBodies))
    occ.isLightBulbOn = False
    return occ, {b.name: 'beige' for b in comp.bRepBodies}

def build_chassis(dockc, mh):
    body = boxb(B_XI0, B_XI1, SKIN, B_DBAY1, 0.0, 2.0)                                      # floor
    union(body, boxb(B_XI0, B_XI1, SKIN, B_DBAY0 + 0.01, 0.0, H_FRONT - SKIN))               # cradle block
    c, s = math.cos(math.radians(TILT)), math.sin(math.radians(TILT))
    cut(body, head_volume(mh, HEAD_CLR, HEAD_ZBACK - 0.3, HEAD_ZF + 0.3))                    # cradle pocket
    cut(body, boxb(B_XI0 - 1, B_XI1 + 1, 17.8, B_DBAY0 + 1, BLOCK_TOP_REAR, H_FRONT))        # low rear lip behind the head
    #   (no wire tunnel through the block: the PM's wires come from the TinyS3 behind it, not from the head)
    tx0, tx1, td0, td1 = TRENCH
    trench = boxb(tx0, tx1, td0, td1, 3.0, H_FRONT)
    cut(body, trench)     # (the island that used to protect the left dock screw is moot: the trench starts at 42)
    # --- pogo junction: a plinth standing in the trench, with the female dropped into it from above. Its lip
    #     lands on the ledge inside and is glued there; the boss stands PG_BOSS proud of the plinth's rim and goes
    #     up into the male's pocket. Built in the head frame, so it leans with the head and its rim is parallel to
    #     the head's underside. Open trench all round it, and a chamber under the tails that breaks out rearward,
    #     so the part goes in with its seven wires already soldered on. ---
    plinth = pg_stad(PG_F_LIP_L + 2 * (PG_CLR + PG_PLINTH_WALL), PG_F_LIP_W + 2 * (PG_CLR + PG_PLINTH_WALL),
                     -30.0, PG_PLINTH_TOP)
    tb.transform(plinth, mh)
    union(body, plinth)
    cut(body, boxb(B_X0 - 10, B_X1 + 10, -10.0, B_D1 + 10, -40.0, 0.0))                  # trim it to the desk
    cut(body, hs_b((0.0, (SKIN + CH_FRONT) / c, 0.0), (0.0, -c, s)))                     # CH_FRONT behind the shell's front wall; after the plinth, which reaches past it
    pk = pg_stad(PG_F_LIP_L, PG_F_LIP_W, F_Y2, PG_PLINTH_TOP + 1.0, PG_CLR)              # lip + top band bore
    union(pk, pg_stad(PG_F_L, PG_F_W, F_Y3, F_Y2 + 0.01, PG_CLR))                        # bottom band bore
    union(pk, pg_stad(PG_F_LIP_L - 3.0, PG_F_LIP_W - 3.0, F_Y2 - 0.15, F_Y2 + 0.01))     # glue relief in the ledge
    union(pk, box(POGO_X - 8.0, POGO_X + 8.0, F_Y4 - 2.0, F_Y3 + 0.01, POGO_Z - 5.0, POGO_Z + 5.0))   # tails
    union(pk, box(POGO_X - PG_F_LIP_L / 2 - PG_CLR, POGO_X + PG_F_LIP_L / 2 + PG_CLR, F_Y2, PG_PLINTH_TOP + 1.0,
                  POGO_Z, HEAD_ZF + 1.0))                                                # lip bore open to the front, above its ledge
    tb.transform(pk, mh)
    cut(body, pk)
    chamber_top = 7.5
    bore_back = head_point(mh, POGO_X, PG_PLINTH_TOP, POGO_Z - PG_F_LIP_W / 2 - PG_CLR)
    bore_back_d = bore_back.y / M - (bore_back.z / M - chamber_top) * math.tan(math.radians(TILT))
    px = bore_back.x / M                                                                     # the connector's X in the dock
    cut(body, boxb(px - 8.0, px + 8.0, 12.0, bore_back_d, 2.5, chamber_top))             # the tails' chamber out
    cut(body, boxb(px - 8.0, px + 8.0, bore_back_d - 0.01, B_DBAY0 + 1.0, 2.5, 5.5))     # through the plinth's back
    #   and into the open trench: where the seven wires leave, and how you see the joints. Under the plinth's back wall
    #   the roof drops to H 5.5, 1.1 mm over the wires in their low lane, so that wall is 2 mm thick rather than a wedge.
    # (no head screws: the head is held on its cradle by the pogo connector's two magnets)
    # --- inset from the shell's inner wall: this slot, open to the room under the shell's rim, is the bay's intake ---
    inter(body, rrect_b(B_XI0 + CH_INSET, B_XI1 - CH_INSET, SKIN + CH_INSET, B_DBAY1 - CH_INSET, -20.0, 100.0, R_CH))
    # board bosses
    bosses = {
        'pm':    (PM_BOSSES, 1.05),
        'scd41': ([(SCD_X1 - 2.54, 37.54), (SCD_X1 - 2.54, 57.86), (SCD_X1 - 20.32, 37.54), (SCD_X1 - 20.32, 57.86)], 1.05),
        'bme':   ([(85.85, 56.55), (117.75, 56.55), (85.85, 72.45), (117.75, 72.45)], 1.3),
        'shtc3': ([(85.85, 29.55), (117.75, 29.55), (85.85, 45.45), (117.75, 45.45)], 1.3),
    }
    for key, (pts, rp) in bosses.items():
        for (x, d) in pts: union(body, cylH(x, d, 2.0 - 0.01, 4.0, 2.6))
    for key, (pts, rp) in bosses.items():
        for (x, d) in pts: cut(body, cylH(x, d, 1.0, 5.0, rp))
    # SCD41 compartment: walls to the skin, mouth open toward the front of the bay
    lx0, lx1, rx0, rx1, d0, rd0, rd1 = COMP
    HW = H_FRONT
    union(body, boxb(lx0, lx1, d0, rd1, 2.0 - 0.01, HW)); union(body, boxb(rx0, rx1, d0, rd1, 2.0 - 0.01, HW)); union(body, boxb(lx0, rx1, rd0, rd1, 2.0 - 0.01, HW))
    cut(body, boxb(rx0 - 0.5, rx1 + 0.5, 60.1, 68.9, 4.0, 10.0))                             # SCD41 rear -> BME688 ribbon notch
    #   8.8 x 6: a JST-SH plug is 6.8 x 2.7 and has to be threaded through here, so the opening is the plug plus 1 mm a side
    union(body, boxb(rx1 - 0.01, B_XI1 - CH_INSET, BAFFLE_D[0], BAFFLE_D[1], 2.0 - 0.01, HW))   # baffle SHTC3 | BME688
    cut(body, boxb(119.7, 128.5, BAFFLE_D[0] - 0.5, BAFFLE_D[1] + 0.5, 4.0, 10.0))           # ribbon notch, plug width + 1 mm a side
    union(body, boxb(RIB_XR[0], B_XI1 - CH_INSET, RIB_XR[1], RIB_XR[2], 2.0 - 0.01, RIB_XR[3]))   # outer wall of the ribbon lane
    L, W, c, fl = 12.5, 8.5, AMS_CLR, 2.0 - 0.01                                           # the board, in its own frame: u along
    def ams_box(u0, u1, v0, v1, h0, h1):                                                     # it from the header end (the RIGHT end), v across
        return boxb(AMS_X0 + L - u1, AMS_X0 + L - u0, AMS_D0 + v0, AMS_D0 + v1, h0, h1)
    rt = AMS_H + 2.0                                                                         # top of the locating walls
    union(body, ams_box(0.9, 2.9, -c, W + c, fl, AMS_H - AMS_DOME))                          # header-end support: the three solder
    #   domes land on this. They are the one thing under that board whose height repeats copy to copy; the clear band between
    #   the domes and the SOT-223 is under a millimetre wide and moves about, so a pad that relied on it would not fit twice.
    #   Full pocket width, so the domes land on it wherever the board sits in its clearance.
    union(body, ams_box(10.4, L + c + 0.01, -c, 2.1, fl, AMS_H))                             # far-end supports, BEYOND the body of
    union(body, ams_box(10.4, L + c + 0.01, W - 2.1, W + c, fl, AMS_H))                      # U1: past u 10.4 the only thing
    #   under the board is the SOT-223's 3 mm tab, so there is 2.6 mm of bare PCB to bear on each side instead of the 1.0 mm
    #   beside the chip - and with AMS_CLR the board can sit 0.5 mm off centre, which that 1.0 mm could not have absorbed.
    union(body, ams_box(-c - 1.0, -c, -c - 1.0, W + c + 1.0, fl, rt))                        # end walls; the pins pass over the
    union(body, ams_box(L + c, L + c + 1.0, -c - 1.0, W + c + 1.0, fl, rt))                  # header end's
    for t0, t1 in ((-c, -c + AMS_TAB), (L + c - AMS_TAB, L + c)):                            # the sides are corner tabs only. What
        union(body, ams_box(t0, t1, -c - 1.0, -c, fl, rt))                                   # is left between them is the passage:
        union(body, ams_box(t0, t1, W + c, W + c + 1.0, fl, rt))                             # bay air crosses under the board, in one
    #   side and out the other, straight beneath the regulator. The floor stays solid - with the chassis flat on the desk a hole
    #   there would open into a dead pocket, and trapped air insulates about three times better than the 2 mm of PLA it replaced.
    build_ts_cradle(body)
    build_pw_holder(body)
    cut(body, hs_b((0.0, D_SLOPE, H_FRONT - SKIN - 0.3), (0.0, SLOPE, 1.0)))                # under the skin
    for (x, d) in SHELL_PILLARS:                                                             # shell screws, countersunk from below
        union(body, cylH(x, d, 2.0 - 0.01, 2.0 + PILLAR_BOSS, 3.5))                           # the boss the pillar stands on
        cut(body, cylH(x, d, -1.0, 2.0 + PILLAR_BOSS + 1.0, 1.7))
        cut(body, coneH(x, d, -0.01, CSK_D / 2, CSK_H, 1.7))
    led_pocket(body)
    occ = get_or_make_comp(dockc, 'Dock chassis')
    return replace_body(occ.component, body, 'Dock chassis')

def build_shell(dockc, mh):
    """Outer skin: rounded, drafted walls + sloped top, tilted front face continuous with the head's bezel,
    bottom rim floating GAP above the desk. Printed upside down."""
    c, sn = math.cos(math.radians(TILT)), math.sin(math.radians(TILT))
    outer = drafted_rrect(B_X0, B_X1, 0.0, B_D1, GAP, H_FRONT, R_PLAN, DRAFT, H_FRONT)
    cut(outer, hs_b((0.0, 0.0, 0.0), (0.0, -c, sn)))                                       # in front of the bezel plane
    cut(outer, hs_b((0.0, D_SLOPE, H_FRONT), (0.0, SLOPE, 1.0)))                            # above the sloped top
    inter(outer, top_chamfer_solid())                                                       # C_TOP chamfer on the top edge
    cavity = rrect_b(B_XI0, B_XI1, SKIN, B_DBAY1, GAP - 6.0, H_FRONT - SKIN, R_CAV)
    cut(cavity, hs_b((0.0, D_SLOPE, H_FRONT - SKIN), (0.0, SLOPE, 1.0)))                    # under the sloped skin
    cut(cavity, hs_b((0.0, SKIN / c, 0.0), (0.0, -c, sn)))                                  # keep the tilted front wall
    cut(outer, cavity)
    for (x, d) in SHELL_PILLARS:
        union(outer, cylH(x, d, 2.0 + PILLAR_BOSS, skin_top(d) - SKIN + 0.5, 3.5))          # standing on the chassis's boss
        cut(outer, cylH(x, d, 1.0, 2.0 + PILLAR_BOSS + 6.0, 2.0))                            # M3 heat-set insert from below, 6 deep
    cut(outer, head_volume(mh, HEAD_CLR, HEAD_ZBACK - 1.6, HEAD_ZF + 0.3))                  # head opening, corners matching the head; after the pillars, which reach into it
    pt = skin_top(AMS_POST[1]) - SKIN + 0.5                                                # AMS retainer: 4 mm, not 2.4 - it is a
    union(outer, cylH(AMS_POST[0], AMS_POST[1], AMS_POST[3], pt, AMS_POST[2]))               # 17 mm tower printed off the skin, and PLA is brittle
    union(outer, coneH(AMS_POST[0], AMS_POST[1], pt - 3.0, AMS_POST[2], pt, AMS_POST[2] + 1.4))   # flare at the root
    # --- PM seal rib: fills the 4.8 mm gap between the module's air face and this wall, between the two slot groups,
    #     so the fan's exhaust cannot run along that gap into its own inlet. It lives on the shell because the
    #     chassis is inset 1.5 mm from this wall and could only reach it as a detached island. The part that
    #     reaches over the chassis floor starts 0.2 mm above it so the shell still drops on freely. ---
    union(outer, boxb(B_XI0, B_XI0 + CH_INSET, PM_SEAL_D[0], PM_SEAL_D[1], GAP, PM_SEAL_H))            # in the shadow-gap channel
    union(outer, boxb(B_XI0 + CH_INSET - 0.01, B_XI0 + PM_SEAL_W, PM_SEAL_D[0], PM_SEAL_D[1], 2.2, PM_SEAL_H))   # over the floor
    # --- the only visible openings: one recessed strip on the left wall, carrying the PM's outlet and inlet slots ---
    t = math.tan(math.radians(DRAFT))
    rec = hs_b((B_X0 + REC_DEPTH, 0.0, H_FRONT), (-1.0, 0.0, t))
    inter(rec, boxb(B_X0 - 20.0, B_X1, PM_VENTS[0][0] - 2.0, PM_VENTS[1][1] + 2.0, VENT_H[0] - 1.5, VENT_H[1] + 1.5))
    cut(outer, rec)
    for (da, db) in PM_VENTS:
        d = da
        while d + 2.2 <= db: cut(outer, boxb(B_X0 - 20.0, B_XI0 + 0.5, d, d + 2.2, VENT_H[0], VENT_H[1])); d += 3.4
    # --- over the TinyS3's USB-C, a stop 1 mm clear of it: the board cannot lift off its strips with the shell on,
    #     and nothing presses on it. Then the power plug's opening, the rear wall's only hole. ---
    rd0 = TS_DC + TS_W / 2 - TS_USB_Y[1]
    union(outer, ts_box(-TS_USB_OUT, 7.0, TS_USB_Y[0], TS_USB_Y[1], TS_H + TS_USB_TOP + 1.0, skin_top(rd0) - SKIN + 0.5))
    cut(outer, plug_opening())
    cut(outer, tile_hole())
    cut(outer, logo_recess())
    occ = get_or_make_comp(dockc, 'Dock shell')
    return replace_body(occ.component, outer, 'Dock shell')

def build_pogo_dock(dockc, mh):
    b, mags, pads, tails = pg_female_bodies()
    for x in (b, mags, pads, tails): tb.transform(x, mh)
    return add_bodies(dockc, 'Pogo female (dock)', [('pogo female body', b, 'housing'), ('pogo female magnets', mags, 'silver'),
                                                    ('pogo female pads', pads, 'gold'), ('pogo female tails', tails, 'silver')])

def build_ts_strips(elecc):
    """The TinyS3 header's two spacers, the two female strips they plug into, and the strips' tails."""
    bodies = []
    deck = 2.0 + TS_DECK
    for (j3, n), name in zip(TS_ROWS, ('J4', 'J3')):
        y = ts_row_y(j3)
        s0, s1 = ts_pin_x(0) - 1.27, ts_pin_x(n - 1) + 1.27
        bodies.append(('strip %s' % name, ts_box(s0, s1, y - STRIP_W / 2, y + STRIP_W / 2, deck, deck + STRIP_H), 'housing'))
        bodies.append(('spacer %s' % name, ts_box(s0, s1, y - 1.27, y + 1.27, TS_H - SPACER_H, TS_H), 'black'))
        tails = None
        for k in range(n):
            t = ts_box(ts_pin_x(k) - 0.32, ts_pin_x(k) + 0.32, y - 0.32, y + 0.32, deck - STRIP_TAIL, deck)
            tails = t if tails is None else union(tails, t)
        bodies.append(('tails %s' % name, tails, 'gold'))
    return add_bodies(elecc, 'Header strips (TinyS3)', bodies)

def build_pw_socket(elecc):
    """The 24-pin USB-C module as a block-out: board with the receptacle's notch, receptacle, and both pad rows."""
    b0, b1 = PW_MOUTH_D - PW_L, PW_MOUTH_D
    h0, h1 = PW_H - PW_T / 2, PW_H + PW_T / 2
    pcb = boxb(PW_X - PW_W / 2, PW_X + PW_W / 2, b0, b1, h0, h1)
    cut(pcb, boxb(PW_X - PW_REC_W / 2 - 0.2, PW_X + PW_REC_W / 2 + 0.2, b1 - PW_REC_L - 0.05, b1 + 1.0, h0 - 1.0, h1 + 1.0))
    rec = rrect_bd(PW_X, PW_H, PW_REC_W, PW_REC_T, b1 - PW_REC_L, b1, 1.2)
    pads = None
    for row, z0, z1 in ((PW_PADS_TOP, h1, h1 + 0.05), (PW_PADS_BOT, h0 - 0.05, h0)):
        for xc, w, lab in row:
            p = boxb(xc - w / 2, xc + w / 2, PW_PAD_D0, PW_PAD_D1, z0, z1)
            pads = p if pads is None else union(pads, p)
    return add_bodies(elecc, 'USB-C power socket (24-pin module)',
                      [('PCB', pcb, 'pcb_green'), ('receptacle', rec, 'silver'), ('pads', pads, 'gold')])

def build_plug(elecc):
    """A USB-C plug's moulded body at its largest allowed size, seated in the power socket: the interference check
    shows whether it clears the rear wall."""
    return add_bodies(elecc, 'USB-C plug (toggle)', [
        ('plug', rrect_bd(PW_X, PW_H, PLUG_W_MAX, PLUG_T_MAX, PW_MOUTH_D, PW_MOUTH_D + 25.0, 1.5), 'white')])

def build_status_led(elecc):
    """The LED as fitted: dome, body, rim, and the first 2 mm of its two legs."""
    rb, t0, t1 = LED_BODY_D / 2, LED_TIP, LED_TIP + LED_L
    led = tb.createSphere(led_at(t0 + rb), rb * M)
    union(led, cyl(led_at(t0 + rb), led_at(t1 - LED_RIM_T), rb))
    union(led, cyl(led_at(t1 - LED_RIM_T), led_at(t1), LED_RIM_D / 2))
    legs = cyl(led_at(t1 - 0.5, -1.27), led_at(t1 + 2.0, -1.27), 0.25)
    union(legs, cyl(led_at(t1 - 0.5, 1.27), led_at(t1 + 2.0, 1.27), 0.25))
    return add_bodies(elecc, 'Status LED (3 mm)', [('LED', led, 'dark_yellow'), ('legs', legs, 'silver')])

def build_led_tile(elecc):
    """The LEGO tile as fitted, flush with the shell's face: the groove round its back and the hollow under it are
    approximate."""
    t0 = -(SKIN + CH_FRONT)
    t1, r = t0 + TILE_T, TILE_D / 2
    tile = cyl(led_at(t0), led_at(t1), r)
    groove = cyl(led_at(t1 - 0.5), led_at(t1 - 0.2), r + 0.1)
    cut(groove, cyl(led_at(t1 - 0.6), led_at(t1 - 0.1), r - 0.2))
    cut(tile, groove)
    cut(tile, cyl(led_at(t1 - 0.8), led_at(t1 + 0.1), 2.4))
    return add_bodies(elecc, 'LEGO 1x1 round tile (clear, sanded)', [('tile', tile, 'frosted')])

PG_REF_X, PG_REF_D, PG_REF_H = 175.0, (40.0, 62.0), 3.0   # the bought pair, laid face up beside the device: X centre, the male's and female's D centres, and the height each housing sits at

def build_pogo_ref(root):
    """The pair as bought, at root beside the device, hidden: all eight ways, and the male's plungers standing free.
    Built from the same code as the fitted pair, so it cannot drift from it."""
    male = [1.0, 0.0, 0.0, (PG_REF_X - POGO_X) * M, 0.0, -1.0, 0.0, (PG_REF_D[0] - POGO_Z) * M,
            0.0, 0.0, -1.0, (PG_REF_H + M_Y3) * M, 0.0, 0.0, 0.0, 1.0]
    female = [1.0, 0.0, 0.0, (PG_REF_X - POGO_X) * M, 0.0, 1.0, 0.0, (PG_REF_D[1] + POGO_Z) * M,
              0.0, 0.0, 1.0, (PG_REF_H - F_Y3) * M, 0.0, 0.0, 0.0, 1.0]
    specs = (('Pogo 8-pin male (ref)', pg_male_bodies(True), male, ('male housing', 'male magnets', 'male pins', 'male tails')),
             ('Pogo 8-pin female (ref)', pg_female_bodies(True), female, ('female housing', 'female magnets', 'female pads', 'female tails')))
    out = []
    for name, bodies, cells, labels in specs:
        m = adsk.core.Matrix3D.create(); m.setWithArray(cells)
        for x in bodies: tb.transform(x, m)
        occ, colmap = add_bodies(root, name, list(zip(labels, bodies, ('housing', 'silver', 'gold', 'silver'))))
        occ.isLightBulbOn = False
        out.append((occ, colmap))
    return out
# ---------------------------------------------------------------------------------------------
# Wiring layer: 'Head wiring (toggle)' (head frame) + 'Dock wiring (toggle)' (dock frame).
# Wires at their measured size, bent as a wire bends (see wire()), bundled where they travel together, and no
# two through each other. There is no slot between head and dock: the head's runs end on the pogo male's solder
# tails and the dock's on the female's, and the joint is the connector.
# ---------------------------------------------------------------------------------------------
QWIIC = ('black', 'red', 'blue', 'yellow')          # GND, 3V3, SDA, SCL

WIRE_D, QWIIC_D = 1.3, 1.0          # jumper wire and Qwiic conductor diameters, measured on the real cables
BEND_K, BEND_FLOOR = 4.0, 3.0       # bend radius: BEND_K x diameter where the straights leave room, and not under
#   BEND_FLOOR except at a solder joint. The floor is measured: a jumper turns within 3.7 mm over a housing.
BEND_LOG = []                       # (wire, radius, corner, diameter, at a joint) for every corner, for run()'s report

def _v(a, b): return (b[0] - a[0], b[1] - a[1], b[2] - a[2])
def _add(a, b): return (a[0] + b[0], a[1] + b[1], a[2] + b[2])
def _mul(a, s): return (a[0] * s, a[1] * s, a[2] * s)
def _dot(a, b): return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
def _norm(a): return math.sqrt(_dot(a, a))
def _unit(a): return _mul(a, 1.0 / _norm(a))
def _cross(a, b): return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])

def _turn(u0, u1):
    return math.acos(max(-1.0, min(1.0, _dot(u0, u1))))

def fit_bends(pts, want, lead=(0.0, 0.0)):
    """The largest radius up to want for each corner of polyline pts that its two straights leave room for. Two
    corners share the straight between them in proportion to what each wants; the first and last straights keep
    lead[0] and lead[1] clear, where a wire leaves a housing. Returns one radius per point, 0 at the ends."""
    n = len(pts)
    u = [_unit(_v(pts[k], pts[k + 1])) for k in range(n - 1)]
    tan_h = [0.0] + [math.tan(min(_turn(u[i - 1], u[i]), math.radians(179.0)) / 2) for i in range(1, n - 1)] + [0.0]
    t_want = [(want[i] if isinstance(want, (list, tuple)) else want) * tan_h[i] for i in range(n)]
    t_cap = list(t_want)
    for k in range(n - 1):
        room = _norm(_v(pts[k], pts[k + 1])) - (lead[0] if k == 0 else 0.0) - (lead[1] if k == n - 2 else 0.0) - 0.02
        need = t_want[k] + t_want[k + 1]
        if need > max(room, 0.0):
            s = max(room, 0.0) / need
            t_cap[k] = min(t_cap[k], t_want[k] * s); t_cap[k + 1] = min(t_cap[k + 1], t_want[k + 1] * s)
    return [t_cap[i] / tan_h[i] if tan_h[i] > 1e-9 else 0.0 for i in range(n)]

def wire(points, d=WIRE_D, name='wire', want=None, lead=(0.0, 0.0), joints=(), back=None, log_add=None, joint_ends=(False, False)):
    """A wire of diameter d along E-frame polyline points, each corner a torus sector of the radius fit_bends
    allows (want defaults to BEND_K * d, or one value per point); a corner with no room for a round is a sphere.
    Corner indices in joints are solder joints, as is every corner within JOINT_REACH of the first / last point
    when joint_ends says so (the wire is bent over its tail there). Every corner is logged to BEND_LOG, at back(point)
    if the caller works in another frame, with log_add[i] added to the radius (a bundle logs its centreline)."""
    keep = [i for i, p in enumerate(points) if i == 0 or _norm(_v(points[i - 1], p)) > 1e-6]
    pts = [points[i] for i in keep]
    r = d / 2
    if want is None:
        want = BEND_K * d
    elif isinstance(want, (list, tuple)):
        want = [want[i] for i in keep]
    joint = [keep[i] in joints or (0 < i < len(pts) - 1 and ((joint_ends[0] and _norm(_v(pts[i], pts[0])) < JOINT_REACH) or
                                                             (joint_ends[1] and _norm(_v(pts[i], pts[-1])) < JOINT_REACH)))
             for i in range(len(pts))]
    if any(joint):
        want = [JOINT_R if joint[i] else (want[i] if isinstance(want, list) else want) for i in range(len(pts))]
    radii = fit_bends(pts, want, lead)
    u = [_unit(_v(pts[k], pts[k + 1])) for k in range(len(pts) - 1)]
    parts, start = [], pts[0]
    for i in range(1, len(pts) - 1):
        th = _turn(u[i - 1], u[i])
        if th < 1e-6:
            continue
        R = radii[i]
        BEND_LOG.append((name, round(R + (log_add[keep[i]] if log_add else 0.0), 2), back(pts[i]) if back else pts[i], d, joint[i]))
        if R < r * 1.05 or th > math.radians(179.0):
            parts += [cyl(P(*start), P(*pts[i]), r), tb.createSphere(P(*pts[i]), r * M)]
            start = pts[i]
            continue
        t = R * math.tan(th / 2)
        a, b = _add(pts[i], _mul(u[i - 1], -t)), _add(pts[i], _mul(u[i], t))
        centre = _add(a, _mul(_unit(_add(u[i], _mul(u[i - 1], -math.cos(th)))), R))
        if _norm(_v(start, a)) > 1e-4:
            parts.append(cyl(P(*start), P(*a), r))
        arc = torus(centre, _unit(_cross(u[i - 1], u[i])), R, r)
        inter(arc, halfspace(centre, u[i - 1])); inter(arc, halfspace(centre, _mul(u[i], -1.0)))
        parts.append(arc)
        start = b
    if _norm(_v(start, pts[-1])) > 1e-4:
        parts.append(cyl(P(*start), P(*pts[-1]), r))
    body = parts[0]
    for p in parts[1:]:
        union(body, p)
    return body

def torus(centre, axis, R, r):
    """A torus of ring radius R and tube radius r about axis through centre (E frame). Built on the Z axis at the
    origin and moved, because createTorus itself leaves the ring at the origin for one axis direction."""
    t = tb.createTorus(P(0.0, 0.0, 0.0), V(0.0, 0.0, 1.0), R * M, r * M)
    m = adsk.core.Matrix3D.create()
    m.setToRotateTo(V(0.0, 0.0, 1.0), V(*axis))
    m.translation = P(*centre).asVector()
    tb.transform(t, m)
    return t

JOINT_REACH, JOINT_R = 3.1, 1.0     # a corner this close to a wire's end on a tail is part of the solder joint, and is
#   bent to JOINT_R there - over pliers, on a tinned wire - so it leaves the straight before it to the corner before that

def _rot(v, n, th):
    """v rotated by th about unit axis n (Rodrigues)."""
    c, s = math.cos(th), math.sin(th)
    return _add(_add(_mul(v, c), _mul(_cross(n, v), s)), _mul(n, _dot(n, v) * (1 - c)))

def bundle(centre, offsets, e1):
    """Parallel offsets of E-frame polyline centre, one per (a, b) in offsets, measured in a frame (e1, e2) across
    the first straight that is carried round every corner and never twists, so no two offsets ever cross.
    Returns (polylines, inward): inward[k][i] is offset k's distance towards the inside of corner i, which is what
    its bend radius there is short of the centreline's (negative outside it)."""
    pts = [p for i, p in enumerate(centre) if i == 0 or _norm(_v(centre[i - 1], p)) > 1e-6]
    n_pts = len(pts)
    u = [_unit(_v(pts[k], pts[k + 1])) for k in range(n_pts - 1)]
    e1 = _unit(_add(e1, _mul(u[0], -_dot(e1, u[0]))))
    frames = [(e1, _cross(u[0], e1))]
    axes = [None]
    for i in range(1, n_pts - 1):
        th = _turn(u[i - 1], u[i])
        if th < 1e-6:
            frames.append(frames[-1]); axes.append(None); continue
        n = _unit(_cross(u[i - 1], u[i]))
        frames.append((_rot(frames[-1][0], n, th), _rot(frames[-1][1], n, th)))
        axes.append(n)
    polys, inward = [], []
    for a, b in offsets:
        poly, inw = [], [0.0]
        O = _add(_mul(frames[0][0], a), _mul(frames[0][1], b))
        poly.append(_add(pts[0], O))
        for i in range(1, n_pts - 1):
            n = axes[i]
            if n is None:
                poly.append(_add(pts[i], O)); inw.append(0.0); continue
            left0, left1 = _cross(n, u[i - 1]), _cross(n, u[i])
            s = _dot(O, left0)
            q = _add(_add(pts[i], _mul(n, _dot(O, n))), _mul(_add(left0, left1), s / (1.0 + _dot(u[i - 1], u[i]))))
            poly.append(q); inw.append(s)
            O = _add(_mul(frames[i][0], a), _mul(frames[i][1], b))
        poly.append(_add(pts[-1], O)); inw.append(0.0)
        polys.append(poly); inward.append(inw)
    return polys, inward

def bundle_wants(centre, inward, want, lead=(0.0, 0.0)):
    """The per-corner radii of a bundle's centreline, and for each offset the radius its own polyline gets: the
    centreline's less its inward distance. Returns (per-offset want lists, per-offset log_add lists)."""
    pts = [p for i, p in enumerate(centre) if i == 0 or _norm(_v(centre[i - 1], p)) > 1e-6]
    R = fit_bends(pts, want, lead)
    R[0] = R[-1] = want                      # the bundle's ends are corners of the wires that carry on past them
    wants = [[R[i] - inw[i] for i in range(len(pts))] for inw in inward]
    adds = [[inw[i] for i in range(len(pts))] for inw in inward]
    return wants, adds

def to_e(p):    return (p[0], p[2], -p[1])          # dock (X, D, H) -> E (X, H, -D)
def to_b(p):    return (p[0], -p[2], p[1])

def wire_b(points, d=WIRE_D, **kw):
    """wire() along a dock-frame polyline (X, D, H); E-frame is (X, H, -D)."""
    return wire([to_e(p) for p in points], d, back=to_b, **kw)

def ribbon(name, pts, e1, cols=QWIIC, pitch=QWIIC_D + 0.1, want=BEND_K * QWIIC_D, lead=(0.0, 0.0), frame='E'):
    """A Qwiic ribbon along polyline pts: its conductors side by side across e1 at pitch, in the standard
    black / red / blue / yellow order (cols names the ones present - a cut conductor is left out - by that order),
    each a parallel offset of the centreline that bends concentrically with it. In the dock frame when frame='B'."""
    if frame == 'B':
        pts, e1 = [to_e(p) for p in pts], to_e(e1)
    offs = [((QWIIC.index(c) - 1.5) * pitch, 0.0) for c in cols]
    polys, inward = bundle(pts, offs, e1)
    wants, adds = bundle_wants(pts, inward, want, lead)
    out = []
    for k, col in enumerate(cols):
        nm = '%s %s' % (name, col)
        out.append((nm, wire(polys[k], QWIIC_D, name=nm, want=wants[k], lead=lead, log_add=adds[k],
                             back=to_b if frame == 'B' else None), col))
    return out

def ribbon_b(name, pts, **kw):
    """ribbon() along a dock-frame (X, D, H) polyline, lying flat: spread across the first straight, horizontally."""
    a, b = pts[0], pts[1]
    e1 = (0.0, 1.0, 0.0) if abs(b[0] - a[0]) > 1e-6 else (1.0, 0.0, 0.0)
    return ribbon(name, pts, e1, frame='B', **kw)

# --- head-frame connector helpers ---
def ra_header(x0, n, y_pad, z_pcb, pin_dir, pins_toward_pcb_side=-1):
    s = pins_toward_pcb_side
    zb0, zb1 = z_pcb, z_pcb + s * 2.54
    block = box(x0 - 1.27, x0 + 2.54 * (n - 1) + 1.27, y_pad - 1.27, y_pad + 1.27, min(zb0, zb1), max(zb0, zb1))
    zc = z_pcb + s * (4.5 - 0.32)
    y_start = y_pad + pin_dir * 1.27
    y_end = y_start + pin_dir * 6.0
    pins = None
    for k in range(n):
        x = x0 + 2.54 * k
        p = box(x - 0.32, x + 0.32, min(y_start, y_end), max(y_start, y_end), zc - 0.32, zc + 0.32)
        pins = p if pins is None else union(pins, p)
    return block, pins, zc, y_start

def dupont(x, y_start, pin_dir, zc):
    y1 = y_start + pin_dir * 14.0
    return box(x - 1.27, x + 1.27, min(y_start, y1), max(y_start, y1), zc - 1.27, zc + 1.27)

# A mated JST-SH plug mostly disappears into its socket: only about 2 mm of the housing stays outside the socket
# face (measured on the real cables), not the ~6.5 mm of a free-standing plug. PLUG_W x PLUG_T is the housing
# section - the same 6.8 x 2.7 every cable passage in the chassis is sized around.
PLUG_OUT, PLUG_W, PLUG_T = 2.0, 6.8, 2.7

def jst_plug_y(y_face, x_c, z_pcb, open_dir_y, z_sign=-1):
    y1 = y_face + open_dir_y * PLUG_OUT
    return box(x_c - PLUG_W / 2, x_c + PLUG_W / 2, min(y_face, y1), max(y_face, y1),
               min(z_pcb, z_pcb + z_sign * PLUG_T), max(z_pcb, z_pcb + z_sign * PLUG_T))

# --- dock-frame connector helpers ---
def ra_header_b(x0, n, d_pad, h_pcb, pin_dir, up=1):
    """Right-angle header on a board face at H = h_pcb; up = +1 components above the board, -1 below.
    Pins run along D in pin_dir; returns (block, pins, pin_h, d_start)."""
    hb0, hb1 = h_pcb, h_pcb + up * 2.54
    block = boxb(x0 - 1.27, x0 + 2.54 * (n - 1) + 1.27, d_pad - 1.27, d_pad + 1.27, min(hb0, hb1), max(hb0, hb1))
    hc = h_pcb + up * (4.5 - 0.32)
    d_start = d_pad + pin_dir * 1.27
    d_end = d_start + pin_dir * 6.0
    pins = None
    for k in range(n):
        x = x0 + 2.54 * k
        p = boxb(x - 0.32, x + 0.32, min(d_start, d_end), max(d_start, d_end), hc - 0.32, hc + 0.32)
        pins = p if pins is None else union(pins, p)
    return block, pins, hc, d_start

def dupont_b(x, d_start, pin_dir, hc):
    d1 = d_start + pin_dir * 14.0
    return boxb(x - 1.27, x + 1.27, min(d_start, d1), max(d_start, d1), hc - 1.27, hc + 1.27)

def plug_bx(x_face, d_c, h_pcb, open_dir_x, up=1):
    x1 = x_face + open_dir_x * PLUG_OUT
    return boxb(min(x_face, x1), max(x_face, x1), d_c - PLUG_W / 2, d_c + PLUG_W / 2,
                min(h_pcb, h_pcb + up * PLUG_T), max(h_pcb, h_pcb + up * PLUG_T))

def plug_bd(d_face, x_c, h_pcb, open_dir_d, up=1):
    d1 = d_face + open_dir_d * PLUG_OUT
    return boxb(x_c - PLUG_W / 2, x_c + PLUG_W / 2, min(d_face, d1), max(d_face, d1),
                min(h_pcb, h_pcb + up * PLUG_T), max(h_pcb, h_pcb + up * PLUG_T))

def add_bodies(parent_comp, comp_name, bodies):
    occ = get_or_make_comp(parent_comp, comp_name)
    comp = occ.component
    for f in list(comp.features.baseFeatures): f.deleteMe()
    for b in list(comp.bRepBodies): b.deleteMe()
    bf = comp.features.baseFeatures.add(); bf.startEdit()
    for name, body, col in bodies:
        nb = comp.bRepBodies.add(body, bf); nb.name = name
    bf.finishEdit()
    return occ, {name: col for name, body, col in bodies}

# --- head wiring (head frame): two wires from the Inkplate's power pads to the pogo male's tails ---
#   VBUS goes to PAD3 (VIN) and GND to PAD5, the 4 x 4 mm pads on the top edge above the reset button, both on the
#   component side, which faces the cover. Soldered's advice for this circuit is 5 V on VIN (forum thread 1934); it
#   reaches the charger's output through the source-select transistor, which they say is harmless. Each wire lies
#   along its pad, drops to a lane just off the cover and runs down the board in its own column - GND's between the
#   bulk capacitor and the reset button, VBUS's clear of everything - to a lane along the bottom edge and left to
#   its tail. Both nets are on the row nearer the cover: GND's wire at Z_NEAR reaches the outermost tail, VBUS's
#   runs under the two GND tails at Z_FAR and rises onto its own. A bare bridge joins each pair.
PAD_VIN, PAD_GND = (92.59, 72.2), (76.59, 72.2)   # PAD3 and PAD5, head frame, from the KiCad board
Y_NEAR, Z_NEAR = 5.8, -7.4         # GND's bottom lane: the wire meets its tail's tip (Y 2.9, Z -7.15) nearly in line
Y_FAR, Z_FAR = 8.2, -8.85          # VBUS's bottom lane: 0.17 off the cover, 0.75 under the two GND tails it passes
Y_TAIL_A, Y_TAIL_B = M_Y4, F_Y4    # the tail tips: the male's up inside the head's cavity, the female's down inside
#   its plinth. Both parts go in with their wires already soldered on.
Y_END = 2.4                        # a wire's end lies along the last 0.5 mm of its tail

def bridge(p0, p1):
    """A bare link between two adjacent tails: a wire's stripped end, laid across the tips and soldered to both."""
    return cyl(P(*p0), P(*p1), 0.3)

def build_head_wiring(headc):
    ZPAD = -2.45 - WIRE_D / 2                                              # lying on the pad
    bodies = []
    def add(name, pts, col, **kw):
        bodies.append((name, wire(pts, WIRE_D, name=name, joint_ends=(True, True), **kw), col))
    tx = {sig: pogo_tail(sig)[0] for sig in PG_TAILS}
    zt = pogo_tail('VBUS')[1]
    px, py = PAD_VIN
    add('wire VBUS: VIN pad -> pogo', [(px, py + 1.3, ZPAD), (px, py - 1.7, ZPAD), (px, py - 6.0, Z_FAR), (px, Y_FAR, Z_FAR),
                                       (tx['VBUS'], Y_FAR, Z_FAR), (tx['VBUS'], 3.2, Z_FAR), (tx['VBUS'], Y_END, zt)], 'red')
    px, py = PAD_GND
    add('wire GND: GND pad -> pogo', [(px, py + 1.3, ZPAD), (px, py - 1.7, ZPAD), (px, py - 6.0, Z_NEAR), (px, 12.0, Z_NEAR),
                                      (tx['GND'], Y_NEAR, Z_NEAR), (tx['GND'], Y_END, zt)], 'black')
    for a, b in (('VBUS', 'VBUS2'), ('GND', 'GND2')):
        bodies.append(('bridge %s-%s' % (a, b), bridge((tx[a], Y_END, zt), (tx[b], Y_END, zt)), 'silver'))
    return add_bodies(headc, 'Head wiring (toggle)', bodies)

# --- dock wiring (dock frame X, D, H): the dock's wires; HARDWARE.md section 8 has the circuit ---
#   Power comes from the USB-C socket through two splices, VBUS and GND, which feed the TinyS3, the AMS1117, the
#   pogo female and (GND only) the status LED. The TinyS3's cradle channel, open at both ends under the board, is the dock's main
#   duct: every wire that crosses the strip behind the sensors goes through it, in layers by height (the J3 joints
#   lowest, then the pogo pair, the AMS pair, and the LED pair just under the board). The chain's only ground return
#   is cable 1's GND conductor: under 300 mA at worst on 28 AWG, a few millivolts. Wires that travel together are
#   bundles, so their bends are concentric and they never cross.
#   The socket board (item 77, measured 2026-09-17) has one pad row on each face along its front edge, 1.5 mm
#   tall: ten on top (A11, A10, A8, A7, A6, A5, V, A3, A2 and a wide end pad) and nine underneath (B11..B2 and a 2.5 mm
#   G pad, which lies on the holder). So VBUS has one usable pad, V, and GND one, the wide end pad on top, taken as
#   ground. Each takes ONE wire, its stub, which runs over the board and along the channel to a splice in the channel's
#   middle - the wires twisted and soldered end to end under heat-shrink - and the branches leave the splice from both
#   ends: VBUS to the TinyS3's 5V leg (back to the right), the AMS1117's IN and the pogo (left); GND to the TinyS3's
#   GND leg and the LED (right), the AMS1117's GND and the pogo (left). One wire per joint everywhere.
PW_PADS_TOP = [(89.5, 1.0, 'A11'), (90.95, 1.0, 'A10'), (92.4, 1.0, 'A8'), (93.85, 1.0, 'A7'), (95.3, 1.0, 'A6'), (96.75, 1.0, 'A5'),
               (98.3, 1.5, 'V'), (99.8, 1.0, 'A3'), (101.1, 1.0, 'A2'), (102.5, 1.8, 'G')]   # X centre, width, label; from the photo
PW_PADS_BOT = [(90.15, 2.5, 'G'), (92.35, 1.0, 'B2'), (93.8, 1.0, 'B3'), (95.25, 1.0, 'B5'), (96.7, 1.0, 'B6'), (98.15, 1.0, 'B7'),
               (99.6, 1.0, 'B8'), (101.05, 1.0, 'B10'), (102.5, 1.0, 'B11')]   # the underside's row as seen from above: the
#   vendor's picture of that face, mirrored, at the top row's pitch. Its G pad is under A11, at the other end from the top's.
PW_PAD_D0, PW_PAD_D1 = 82.2, 83.7             # the row's depth
PW_PAD_V, PW_PAD_G = 98.3, 102.5              # where the two stubs start
PW_PAD_H = PW_H + PW_T / 2 + 0.05 + WIRE_D / 2   # a wire lying on a pad (the pads stand 0.05 off the board)
CH_X0, CH_X1 = 46.3, 79.66                    # the cradle channel's ends (the strips' pocket walls)
H_CH_LOW = 4.6                                # a joint on a leg's lower half, and the PM group's layer in the channel
H_POGO_CH, H_AMS_CH, H_LED_CH = 8.5, AMS_H + 1.4 + 4.5 - 0.32, 15.8     # channel layers: pogo pair, AMS pair (at the housings), LED pair
H_LOW, H_FLOOR = 3.9, 3.15                    # under the plinth's back wall (roof 5.5), and on the chamber floor
SPLICE_X0, SPLICE_X1, SPLICE_R = 60.0, 68.0, 1.75   # the two splices, along X in the channel's middle, above the pogo pair
SPL_G, SPL_V = (82.5, 11.8), (87.5, 11.8)     # (D, H) of the GND splice's axis (front) and the VBUS splice's (rear)
SLOT = 0.7                                    # a wire's end sits this far off the splice's axis, in D and in H

RES_L, RES_R, LEAD_R = 6.3, 1.25, 0.3           # a 1/4 W metal-film resistor: body length and radius, lead radius
RES_BANDS = {'1k': ('brown', 'band_black', 'band_black', 'brown', 'brown'), '5k1': ('green', 'brown', 'band_black', 'brown', 'brown')}
CC_H = PW_H - PW_T / 2 - 0.1 - RES_R            # a CC resistor's axis: its body 0.1 under the board's underside
LEAD_UNDER = PW_H - PW_T / 2 - 0.05 - LEAD_R    # a lead lying on an underside pad

def resistor(tag, value, x0, d, h):
    """A resistor's body along X from x0, at (d, h), with its five colour bands; (name, body, colour) triples."""
    out = [('%s body' % tag, cyl(P(*to_e((x0, d, h))), P(*to_e((x0 + RES_L, d, h))), RES_R), 'res_blue')]
    for k, (at, col) in enumerate(zip((0.9, 1.8, 2.7, 3.6, 5.3), RES_BANDS[value])):
        out.append(('%s band %d' % (tag, k + 1), cyl(P(*to_e((x0 + at - 0.22, d, h))), P(*to_e((x0 + at + 0.22, d, h))), RES_R + 0.04), col))
    return out

def lead(pts):
    """A bare resistor lead along dock-frame points, with sharp bends."""
    b = None
    for a, c in zip(pts, pts[1:]):
        seg = cyl(P(*to_e(a)), P(*to_e(c)), LEAD_R)
        b = seg if b is None else union(b, seg)
        union(b, tb.createSphere(P(*to_e(c)), LEAD_R * M))
    return b

def peel(poly, wants, adds, x_peel, tail, d):
    """A bundle member's polyline cut where its last straight (along X) reaches x_peel, then its own points tail.
    Returns (points, want list, log_add list) for wire()."""
    a, b = poly[-2], poly[-1]
    f = (x_peel - a[0]) / (b[0] - a[0])
    p = (x_peel, a[1] + f * (b[1] - a[1]), a[2] + f * (b[2] - a[2]))
    return (poly[:-1] + [p] + tail, wants[:-1] + [BEND_K * d] * (1 + len(tail)), adds[:-1] + [0.0] * (1 + len(tail)))

def build_dock_wiring(dockc, mh):
    bodies = []
    def add(name, pts, col, d=WIRE_D, **kw):
        kw.setdefault('joint_ends', (True, True))
        bodies.append((name, wire_b(pts, d, name=name, **kw), col))
    def add_bundle(name_cols, centre, offsets, e1, tails, heads, d, want=None, lead=(0.0, 0.0), joint_ends=(True, True), r_first_tail=None):
        """A bundle along dock-frame centreline centre; member k (name, colour) is offset offsets[k] across e1, runs
        from heads[k] (its own points before the bundle) to tails[k] (after it; when tails[k] is (x_peel, pts) it
        leaves the bundle's last straight at x_peel). r_first_tail[k] is the radius of member k's bend onto its tail."""
        d_ = d if isinstance(d, (list, tuple)) else [d] * len(offsets)
        ce = [to_e(p) for p in centre]
        polys, inward = bundle(ce, [(o, 0.0) for o in offsets], to_e(e1))
        w = want or BEND_K * max(d_)
        wants, adds = bundle_wants(ce, inward, w, lead)
        for k, (name, col) in enumerate(name_cols):
            poly, wk, ak = polys[k], wants[k], adds[k]
            tail = tails[k]
            if isinstance(tail, tuple) and len(tail) == 2 and isinstance(tail[0], float):
                pts, wk, ak = peel(poly, wk, ak, tail[0], [to_e(p) for p in tail[1]], d_[k])
                if r_first_tail and k in r_first_tail: wk[len(poly)] = r_first_tail[k]
            else:
                pts = poly + [to_e(p) for p in tail]; wk = wk + [BEND_K * d_[k]] * len(tail); ak = ak + [0.0] * len(tail)
            hd = [to_e(p) for p in heads[k]]
            pts = hd + pts; wk = [BEND_K * d_[k]] * len(hd) + wk; ak = [0.0] * len(hd) + ak
            bodies.append((name, wire(pts, d_[k], name=name, want=wk, log_add=ak, back=to_b, lead=lead, joint_ends=joint_ends), col))
    def jn(sig):
        """A wire's end on the female's tail: 0.25 up the tail from its tip."""
        x, z = pogo_tail(sig)
        p = head_point(mh, x, Y_TAIL_B + 0.25, z)
        return (round(p.x * 10, 3), round(p.y * 10, 3), round(p.z * 10, 3))
    def tail_start(sig, turn_d):
        """From the tail's tip down to the chamber floor, back along it, up to H_LOW and on to the trench."""
        jx, jd, jh = jn(sig)
        return [(jx, jd, jh - 0.25), (jx, jd + 0.3, H_FLOOR), (jx, 14.5, H_FLOOR), (jx, 18.0, H_LOW), (jx, turn_d, H_LOW)]
    # ---- the pogo pair: each wire meets its tail's tip end-on from below, drops to the chamber's floor, runs back
    #      along it and rises to H_LOW under the plinth's back wall. In the trench they become a bundle: left along
    #      the trench, forward up the strip between the PM board and the SCD41 compartment (under the ribbon at H 7.1,
    #      over the PM group), up to H_POGO_CH and along the channel to the left ends of the splices. Bare bridges
    #      join the second tail of each net. ----
    add_bundle([('wire GND: pogo -> splice', 'black'), ('wire VBUS: pogo -> splice', 'red')],
               [(58.0, 22.25, H_LOW), (43.95, 22.25, H_LOW), (43.95, 30.0, 5.5), (43.95, 62.0, 5.5), (43.95, 72.0, H_POGO_CH),
                (43.95, 86.25, H_POGO_CH), (56.5, 86.25, H_POGO_CH)],
               [0.75, -0.75], (0.0, 1.0, 0.0),
               [[(SPLICE_X0 + 0.2, SPL_G[0] + SLOT, SPL_G[1] - SLOT)], [(SPLICE_X0 + 0.2, SPL_V[0] - SLOT, SPL_V[1] - SLOT)]],
               [tail_start('GND', 23.0), tail_start('VBUS', 21.5)], WIRE_D)
    for a, b in (('VBUS', 'VBUS2'), ('GND', 'GND2')):
        xa, d, h = jn(a); xb = jn(b)[0]
        bodies.append(('bridge %s-%s' % (a, b), bridge(to_e((xa, d, h)), to_e((xb, d, h))), 'silver'))
    # ---- the two splices, and the stubs from the socket's pads. The V stub goes rearward onto the board, turns left
    #      behind the pad row at D 87.5 and climbs over the holder's guide into the channel; the G stub goes left along
    #      the pad row at 10.6 (over the V joint) and over the guide. Each ends on the right end face of its splice. ----
    for name, (d, h) in (('splice GND', SPL_G), ('splice VBUS', SPL_V)):
        bodies.append((name, wire_b([(SPLICE_X0, d, h), (SPLICE_X1, d, h)], 2 * SPLICE_R, name=name), 'black'))
    add('wire VBUS: V pad -> splice', [(PW_PAD_V, PW_PAD_D0, PW_PAD_H), (PW_PAD_V, 86.0, PW_PAD_H), (96.0, 87.5, 10.4), (88.5, 87.5, 10.4),
                                       (72.0, SPL_V[0] + SLOT, SPL_V[1] + SLOT), (SPLICE_X1 - 0.2, SPL_V[0] + SLOT, SPL_V[1] + SLOT)], 'red')
    add('wire GND: G pad -> splice', [(PW_PAD_G, PW_PAD_D0 + 0.2, PW_PAD_H), (100.5, PW_PAD_D0 + 0.2, 10.6), (89.5, PW_PAD_D0, 10.6), (86.0, PW_PAD_D0, 10.9),
                                      (80.0, 82.0, 11.5), (SPLICE_X1 - 0.2, SPL_G[0] - SLOT, SPL_G[1] + SLOT)], 'black')
    # ---- USB-C to USB-C only: a 5.1 k resistor from each CC pad to GND, soldered before the board goes in. B5's lies
    #      under the board, in front of the left ear's pad, leads bent forward onto B5 and the underside G pad. A5's hangs in front
    #      of the board's edge: one lead up round the edge onto A5, the other back under the board onto the same G pad,
    #      beside the first resistor's lead, both soldered in one go. ----
    D_B5, D_A5 = 86.5, 80.3
    x_b5 = [x for x, w, lab in PW_PADS_BOT if lab == 'B5'][0]
    x_a5 = [x for x, w, lab in PW_PADS_TOP if lab == 'A5'][0]
    h_on = PW_PAD_H - WIRE_D / 2 + LEAD_R                                              # a lead lying on a top pad
    x0 = x_b5 + 0.3 - RES_L
    bodies += resistor('5k1 B5', '5k1', x0, D_B5, CC_H)
    bodies.append(('5k1 B5 lead G', lead([(x0, D_B5, CC_H), (x0 - 0.3, D_B5, CC_H), (x0 - 0.3, 85.0, CC_H), (89.6, 83.9, LEAD_UNDER), (89.6, 82.5, LEAD_UNDER)]), 'silver'))
    bodies.append(('5k1 B5 lead B5', lead([(x0 + RES_L, D_B5, CC_H), (x0 + RES_L + 0.3, D_B5, CC_H), (x0 + RES_L + 0.3, 85.0, CC_H),
                                           (x_b5, 83.9, LEAD_UNDER), (x_b5, 82.5, LEAD_UNDER)]), 'silver'))
    x0 = x_a5 - 0.15 - RES_L
    d_edge = PW_MOUTH_D - PW_L - 0.65                                                     # 0.35 in front of the board's edge
    bodies += resistor('5k1 A5', '5k1', x0, D_A5, CC_H)
    bodies.append(('5k1 A5 lead G', lead([(x0, D_A5, CC_H), (x0 - 0.3, D_A5, CC_H), (x0 - 0.3, 81.4, CC_H), (90.7, 82.6, LEAD_UNDER), (90.7, 83.5, LEAD_UNDER)]), 'silver'))
    bodies.append(('5k1 A5 lead A5', lead([(x0 + RES_L, D_A5, CC_H), (x_a5 + 0.15, D_A5, CC_H), (x_a5 + 0.15, d_edge, CC_H), (x_a5 + 0.15, d_edge, h_on),
                                           (x_a5, PW_PAD_D0, h_on), (x_a5, PW_PAD_D1 - 0.2, h_on)]), 'silver'))
    # ---- the splices to the TinyS3: 5V on J3 pin 3 and GND on J3 pin 2, each soldered to the leg's lower half pointing
    #      into the channel. Both leave the right end of their splice, cross down to the front and turn onto their legs. ----
    xj = {k: TS_EDGE_X - ts_pin_x(k - 1) for k in (2, 3)}                        # J3 pin k's leg
    d_j3 = TS_DC + TS_W / 2 - ts_row_y(True)                                     # 77.22, the row
    d_end3 = d_j3 + 0.32 + WIRE_D / 2                                            # a joint's end, 0.97 behind it
    add('wire 5V: splice -> TinyS3 J3.3', [(SPLICE_X1 + 0.2, SPL_V[0] - SLOT, SPL_V[1] - SLOT), (xj[3], 84.8, 6.2), (xj[3], d_end3, H_CH_LOW)], 'red')
    add('wire GND: splice -> TinyS3 J3.2', [(SPLICE_X1 + 0.2, SPL_G[0] + SLOT, SPL_G[1] - SLOT), (xj[2], 82.6, 5.2), (xj[2], d_end3, H_CH_LOW)], 'black')
    # ---- the splices to the AMS1117: IN on the rear pin, GND on the front one, straight along the channel from the
    #      left end of their splices and into the housings at pin height ----
    ams_d = {'IN': AMS_D0 + 4.25 + 2.54, 'OUT': AMS_D0 + 4.25, 'GND': AMS_D0 + 4.25 - 2.54}
    x_open = AMS_X0 + 12.5 + 1.27 + 14.0                                         # the housings' open ends
    hams = H_AMS_CH
    for name, dd in ams_d.items():
        bodies.append(('Dupont AMS %s' % name, boxb(AMS_X0 + 12.5 + 1.27, x_open, dd - 1.27, dd + 1.27, hams - 1.27, hams + 1.27), 'dupont'))
    add('wire VBUS: splice -> AMS IN', [(SPLICE_X0 - 0.2, SPL_V[0] + SLOT, SPL_V[1] - SLOT), (52.0, SPL_V[0] + SLOT, 11.3), (CH_X0, ams_d['IN'], hams),
                                       (x_open + 0.5, ams_d['IN'], hams), (x_open - 1.0, ams_d['IN'], hams)], 'red', lead=(0.0, 1.0))
    add('wire GND: splice -> AMS GND', [(SPLICE_X0 - 0.2, SPL_G[0] - SLOT, SPL_G[1] - SLOT), (52.0, SPL_G[0] - SLOT, 11.3), (CH_X0, ams_d['GND'], hams),
                                       (x_open + 0.5, ams_d['GND'], hams), (x_open - 1.0, ams_d['GND'], hams)], 'black', lead=(0.0, 1.0))
    # ---- the TinyS3 to the PMSA003I: cable 1 (SCL, SDA, GND off J4 pins 5, 6, 10, three Qwiic conductors) and SET
    #      (J4 pin 7). Each solders to the leg's lower half pointing into the channel, runs 1 mm off the leg and turns
    #      left onto its lane: the further left a leg, the nearer its lane to the row, so no wire's short leg crosses
    #      another's lane. From there they are one bundle: left along the channel, forward up the strip, up over the
    #      ribbon to H 10, and left along the front of the bay, where each peels off: SCL, SDA and GND climb at the
    #      two lines between the SET housing and the PM's socket B onto their own over-lanes at H_OVER, run left and
    #      drop into their housings; SET, the last housing in the row, climbs at its own X and hairpins over it. ----
    H_PM = 4.0 + 1.6
    d_hdr = PM_D0 + 2.54
    bodies.append(('PM straight header 7-pin', boxb(PM_PINS['VIN'] - 1.27, PM_PINS['SET'] + 1.27, d_hdr - 1.27, d_hdr + 1.27, H_PM, H_PM + 2.54), 'housing'))
    pins = None
    for k in range(7):
        x = PM_PINS['VIN'] + 2.54 * k
        p = boxb(x - 0.32, x + 0.32, d_hdr - 0.32, d_hdr + 0.32, H_PM + 2.54, H_PM + 8.5)
        pins = p if pins is None else union(pins, p)
    bodies.append(('PM header pins', pins, 'silver'))
    h_top = H_PM + 2.54 + 14.0
    for name, x in PM_PINS.items():
        bodies.append(('Dupont PM %s' % name, boxb(x - 1.27, x + 1.27, d_hdr - 1.27, d_hdr + 1.27, H_PM + 2.54, h_top), 'dupont'))
    H_OVER, R_OVER = 26.8, 3.5               # the over-lanes, 1.4 mm under the skin; the bend onto the inner one, 2 mm from SET's hairpin
    XE_IN, XE_OUT = 23.6, 25.1               # the two climb lines, between the SET housing and the PM's socket B
    d_j4 = TS_DC + TS_W / 2 - ts_row_y(False)                                    # 92.48, the J4 row
    J4_PIN = {'SCL': 5, 'SDA': 6, 'SET': 7, 'IO6': 8, 'GND1': 10}
    xl = {k: TS_EDGE_X - ts_pin_x(n - 1) for k, n in J4_PIN.items()}             # each leg's X
    D_PM_CH, D_PM_FRONT = 87.0, 34.84        # the bundle's centreline in the channel (GND's lane 0.2 clear of the J4 pocket's end block) and along the front
    d_up = d_hdr + 2 * BEND_FLOOR            # SET's climb, two floor bends from the housing
    h_hp = h_top - 0.2 + BEND_FLOOR          # ... and the top of its hairpin
    grp = (('GND1', 'black', QWIIC_D, 2.1, 'GND'), ('SET', 'white', WIRE_D, 0.7, 'SET'), ('SDA', 'blue', QWIIC_D, -0.7, 'SDA'), ('SCL', 'yellow', QWIIC_D, -2.1, 'SCL'))
    heads, tails = [], []
    for sig, col, d, off, pin in grp:
        x = PM_PINS[pin]
        heads.append([(xl[sig], d_j4 - 0.32 - d / 2, H_CH_LOW), (xl[sig], D_PM_CH + off, H_CH_LOW)])
        if sig == 'SET':
            tails.append([(x, d_up, h_hp), (x, d_hdr, h_hp), (x, d_hdr, h_top - 0.2)])
        else:
            xe = XE_IN if sig == 'SCL' else XE_OUT
            tails.append((xe, [(xe, D_PM_FRONT + off, H_OVER), (x, D_PM_FRONT + off, H_OVER), (x, d_hdr, h_top - 0.2)]))
    add_bundle([('wire %s: TinyS3 J4.%d -> PM %s' % (sig, J4_PIN[sig], pin), col) for sig, col, d, off, pin in grp],
               [(53.0, D_PM_CH, H_CH_LOW), (38.75, D_PM_CH, H_CH_LOW), (38.75, 55.0, H_CH_LOW), (38.75, 40.0, 10.0), (38.75, D_PM_FRONT, 10.0),
                (PM_PINS['SET'], D_PM_FRONT, 10.0)],
               [off for _, _, _, off, _ in grp], (0.0, 1.0, 0.0), tails, heads, [d for _, _, d, _, _ in grp], want=BEND_K * WIRE_D,
               joint_ends=(True, False), r_first_tail={3: R_OVER})
    # ---- AMS OUT -> PM VIN: out of the middle housing, up over the AMS GND wire onto X 42, forward at H 13.3 over the
    #      PM group's lanes and just left of the pogo pair's, up to a lane under the skin, across over the PM module and
    #      down into its VIN housing ----
    xo = 42.0
    add('wire 3V3: AMS OUT -> PM VIN', [(x_open - 1.0, ams_d['OUT'], hams), (39.5, ams_d['OUT'], hams), (xo, ams_d['OUT'] - 1.75, 13.3), (xo, 43.0, 13.3),
                                        (xo, 43.0, 25.2), (PM_PINS['VIN'], 41.5, 25.2), (PM_PINS['VIN'], d_hdr, 25.2), (PM_PINS['VIN'], d_hdr, h_top - 0.2)],
        'red', lead=(1.0, 0.0), joint_ends=(False, False))
    # ---- the status LED: IO6 (J4 pin 8) through a 1 k resistor to the upper leg, GND from the splice to the lower one.
    #      A bundle from the pit: rearward over the SHTC3's right end, left of the shell pillar at (125, 30) onto the
    #      ribbon lane at X 126 - over the ribbon, under the baffle notch's roof - up to H_LED_CH past the BME688, and
    #      across the bay behind it. The resistor is spliced into IO6 on that last straight, with heat-shrink over each
    #      lead's joint; the bundle is spaced for its body. At X 86 they part: IO6 turns into the channel's right end at
    #      H_LED_CH and drops onto its leg; GND comes down to 13.5, runs along D 83.4 and ends on the GND splice's right end. ----
    t1 = LED_TIP + LED_L
    def leg(up):
        p = led_at(t1 + 2.0, up); return (p.x / M, p.y / M, p.z / M)                # Fusion (x, y, z) = dock (X, D, H)
    hi, lo = leg(1.27), leg(-1.27)
    D_LED, LED_OFF = 78.1, 1.1                                                      # the straight behind the BME688, and each wire's offset
    X_IO6, X_LEDG = 118.2 - LED_OFF, 118.2 + LED_OFF                               # the bundle's two lanes as it leaves the pit
    RES_X = 104.0                                                                   # the 1 k resistor's centre (item 167)
    SHRINK_L, SHRINK_R = 6.0, 1.0                                                   # heat-shrink over a lead and its joint, from the body's end
    d_io6 = D_LED - LED_OFF
    bodies += resistor('resistor 1k', '1k', RES_X - RES_L / 2, d_io6, H_LED_CH)
    for k, x in ((1, RES_X - RES_L / 2), (2, RES_X + RES_L / 2)):
        x1 = x - SHRINK_L if k == 1 else x + SHRINK_L
        bodies.append(('heat-shrink 1k %d' % k, wire_b([(min(x, x1), d_io6, H_LED_CH), (max(x, x1), d_io6, H_LED_CH)], 2 * SHRINK_R, name='shrink'), 'black'))
    add_bundle([('wire IO6: TinyS3 J4.8 -> LED (via 1k)', 'yellow'), ('wire GND: splice -> LED', 'black')],
               [(118.2, 26.0, 6.4), (118.2, 34.0, 10.0), (118.2, 41.0, 10.0), (125.3, 44.5, 9.0), (125.3, 53.0, 9.0), (125.3, 66.0, H_LED_CH),
                (125.3, D_LED, H_LED_CH), (86.0, D_LED, H_LED_CH)],
               [-LED_OFF, LED_OFF], (1.0, 0.0, 0.0),
               [[(80.8, d_io6, H_LED_CH), (80.8, 90.4, H_LED_CH), (xl['IO6'], 90.4, H_LED_CH), (xl['IO6'], 90.4, 11.0), (xl['IO6'], 90.4, H_CH_LOW),
                 (xl['IO6'], d_j4 - 0.32 - WIRE_D / 2, H_CH_LOW)],
                [(82.2, 83.4, 13.5), (70.0, 83.4, 13.5), (SPLICE_X1 + 0.2, SPL_G[0] + SLOT, SPL_G[1] + SLOT)]],
               [[(hi[0], hi[1], hi[2]), (X_IO6, 15.0, hi[2]), (X_IO6, 22.6, hi[2])],
                [(lo[0], lo[1], 3.0), (X_LEDG, 14.2, 3.4), (X_LEDG, 20.0, 3.4)]], WIRE_D)
    # ---- Qwiic chain: PM (socket on its inner edge) -> SCD41 front -> SCD41 rear -> BME688 left -> BME688 right -> SHTC3 right ----
    H_B = 4.0 + 1.6; H_R = H_B + 1.5
    scd_xs = SCD_X1 - 11.4                     # X 59.9
    x_pm_face = PM_X0 + 35.6 - 0.4; d_pm_sock = PM_D0 + 8.9
    bodies.append(('plug PM socket', plug_bx(x_pm_face, d_pm_sock, H_B, +1), 'white'))
    bodies.append(('plug SCD41 front', plug_bd(SCD_D0, scd_xs, H_B, -1), 'white'))
    bodies += ribbon_b('Qwiic PM -> SCD41', [(x_pm_face + PLUG_OUT, d_pm_sock, H_R), (RIBBON_X, d_pm_sock, H_R), (RIBBON_X, 27.5, H_R), (scd_xs, 27.5, H_R), (scd_xs, SCD_D0 - PLUG_OUT, H_R)])
    bodies.append(('plug SCD41 rear', plug_bd(SCD_D0 + 25.4, scd_xs, H_B, +1), 'white'))
    bodies.append(('plug BME688 left', plug_bx(BME_X0, BME_D0 + 11.0, H_B, -1), 'white'))
    bodies += ribbon_b('Qwiic SCD41 -> BME688', [(scd_xs, SCD_D0 + 25.4 + PLUG_OUT, H_R), (scd_xs, 69.5, H_R), (68.0, 69.5, H_R), (74.0, BME_D0 + 11.0, H_R), (BME_X0 - PLUG_OUT, BME_D0 + 11.0, H_R)], lead=(1.0, 1.0))
    bodies.append(('plug BME688 right', plug_bx(BME_X0 + 38.0, BME_D0 + 11.0, H_B, +1), 'white'))
    bodies.append(('plug SHTC3 right', plug_bx(SHT_X0 + 38.0, SHT_D0 + 11.0, H_B, +1), 'white'))
    bodies += ribbon_b('Qwiic BME688 -> SHTC3', [(BME_X0 + 38.0 + PLUG_OUT, BME_D0 + 11.0, H_R), (RIBBON_XR, BME_D0 + 11.0, H_R), (RIBBON_XR, SHT_D0 + 11.0, H_R), (SHT_X0 + 38.0 + PLUG_OUT, SHT_D0 + 11.0, H_R)])
    return add_bodies(dockc, 'Dock wiring (toggle)', bodies)

# ---------------------------------------------------------------------------------------------
# Finishing features: the plan corners and the draft are modelled as solids (above), but the rounds that run
# across faces - the shell's top edge and the bezel's front edge - are Fusion fillet features applied to the
# finished base-feature body. Edges are picked geometrically so the script stays re-runnable.
# ---------------------------------------------------------------------------------------------

def clear_fillets(comp):
    for coll in (comp.features.filletFeatures, comp.features.chamferFeatures):
        for f in list(coll): f.deleteMe()

def face_by_normal(body, nx, ny, nz, tol=0.9):
    """The largest planar face whose outward normal points roughly along (nx, ny, nz)."""
    v = adsk.core.Vector3D.create(nx, ny, nz)
    best, best_area = None, -1.0
    for f in body.faces:
        if not isinstance(f.geometry, adsk.core.Plane):
            continue
        ok, n = f.evaluator.getNormalAtPoint(f.pointOnFace)
        if ok and n.dotProduct(v) > tol and f.area > best_area:
            best, best_area = f, f.area
    return best

def loop_bbox(loop):
    bb = None
    for e in loop.edges:
        bb = e.boundingBox.copy() if bb is None else bb
        bb.combine(e.boundingBox)
    return bb

def outer_loop_edges(face):
    """Edges of the face's outermost loop (the one with the largest bounding box)."""
    best, best_span = None, -1.0
    for lp in face.loops:
        bb = loop_bbox(lp)
        if bb is None: continue
        span = (bb.maxPoint.x - bb.minPoint.x) + (bb.maxPoint.y - bb.minPoint.y) + (bb.maxPoint.z - bb.minPoint.z)
        if span > best_span: best, best_span = lp, span
    return list(best.edges) if best else []

def edge_mid(e):
    bb = e.boundingBox
    return ((bb.minPoint.x + bb.maxPoint.x) * 5.0, (bb.minPoint.y + bb.maxPoint.y) * 5.0,
            (bb.minPoint.z + bb.maxPoint.z) * 5.0)          # mm, component-local

def add_fillet(comp, edges, r_mm, tangent=False):
    """Fillet the given edges; report rather than raise, so one impossible radius cannot abort the whole build."""
    if not edges: return 'no edges'
    coll = adsk.core.ObjectCollection.create()
    for e in edges: coll.add(e)
    fi = comp.features.filletFeatures.createInput()
    fi.isRollingBallCorner = True
    fi.edgeSetInputs.addConstantRadiusEdgeSet(coll, adsk.core.ValueInput.createByReal(r_mm * M), tangent)
    try:
        comp.features.filletFeatures.add(fi)
        return coll.count
    except Exception as ex:
        return 'FAILED r=%g n=%d: %s' % (r_mm, coll.count, str(ex).strip().split(chr(10))[0][:90])

def add_chamfer(comp, edges, d_mm, tangent=False):
    if not edges: return 'no edges'
    coll = adsk.core.ObjectCollection.create()
    for e in edges: coll.add(e)
    ci = comp.features.chamferFeatures.createInput2()
    ci.chamferEdgeSets.addEqualDistanceChamferEdgeSet(coll, adsk.core.ValueInput.createByReal(d_mm * M), tangent)
    try:
        comp.features.chamferFeatures.add(ci)
        return coll.count
    except Exception as ex:
        return 'FAILED d=%g n=%d: %s' % (d_mm, coll.count, str(ex).strip().split(chr(10))[0][:90])

def describe(body, want_z):
    """Planar faces pointing roughly along +/-Z, for diagnosing which one the fillet picked."""
    out = []
    for f in body.faces:
        if not isinstance(f.geometry, adsk.core.Plane): continue
        ok, n = f.evaluator.getNormalAtPoint(f.pointOnFace)
        if ok and n.z * want_z > 0.9:
            bb = f.boundingBox
            out.append({'area': round(f.area * 100, 1), 'loops': f.loops.count, 'edges': f.edges.count,
                        'bb': [round(v * 10, 1) for v in (bb.minPoint.x, bb.minPoint.y, bb.minPoint.z, bb.maxPoint.x, bb.maxPoint.y, bb.maxPoint.z)]})
    return sorted(out, key=lambda r: -r['area'])[:4]

def finish_shell(occ):
    """Soften the two edges that read from across the room: the top edge (where the sloped skin meets the side and
    rear walls) and the bottom rim inside the shadow gap. Chamfers, not fillets - see C_TOP."""
    comp = occ.component
    out = {}
    rim = face_by_normal(comp.bRepBodies.item(0), 0.0, 0.0, -1.0, tol=0.999)   # flat rim at H = GAP, not the sloped ceiling
    if rim is not None:
        out['rim_edges'] = add_chamfer(comp, outer_loop_edges(rim), C_RIM)
    return out          # the top-edge chamfer is part of the solid (top_chamfer_solid), not a feature

def finish_tray(occ):
    """2 mm round on the bezel's outer edge, all the way round."""
    comp = occ.component
    body = comp.bRepBodies.item(0)
    front = face_by_normal(body, 0.0, -1.0, 0.0)             # head-local: +Z_e is -Y_f
    if front is None: return {'tray': 'no front face'}
    return {'bezel_edges': add_fillet(comp, outer_loop_edges(front), HEAD_R_FRONT)}

import json, os, tempfile, urllib.request

STEP_URLS = {
    'inkplate5gen2.step': 'https://raw.githubusercontent.com/SolderedElectronics/Soldered-Inkplate-5-Gen2-hardware-design/main/OUTPUTS/V1.1.0/Soldered%20Inkplate%205%20Gen2%203D.step',
    'pmsa003i.step': 'https://raw.githubusercontent.com/adafruit/Adafruit_CAD_Parts/main/4632%20PMSA003I/4632%20PMSA003I.step',
    'scd41.step': 'https://raw.githubusercontent.com/adafruit/Adafruit_CAD_Parts/main/5187%20SCD-40%20C02%20Sensor/5187%20SCD-40%20C02%20Sensor.step',
    'tinys3.step': 'https://raw.githubusercontent.com/UnexpectedMaker/esp32s3/main/3d%20models/TinyS3/TinyS3.STEP',
}
TS_NAME = 'TinyS3 (Unexpected Maker)'

def mat(rows):
    m = adsk.core.Matrix3D.create()
    vals = []
    for r in rows: vals += r
    vals += [0, 0, 0, 1]
    vals[3] *= M; vals[7] *= M; vals[11] *= M
    m.setWithArray(vals)
    return m

# rows = 3x4 matrices mapping each model's own frame into the Fusion frame (translation in mm)
HEAD_PLACEMENTS = {     # head frame: X_f = X, Y_f = -Z, Z_f = Y (USB-C on the right, expander row along the bottom edge)
    'Soldered Inkplate': [[-1,0,0,130.59],[0,0,1,0.85],[0,1,0,0]],
}
BASE_PLACEMENTS = {     # PM on the left with its header at the front
    'Adafruit PMSA003I': [[1,0,0,PM_X0],[0,1,0,PM_D0],[0,0,1,4.0]],       # air face 1 mm from the left wall, header row at the front
    'Adafruit SCD41':    [[0,-1,0,SCD_X1],[1,0,0,SCD_D0],[0,0,1,4.0]],    # vertical in its compartment: sockets face front / rear
    'BME688':            [[1,0,0,82.8],[0,1,0,53.5],[0,0,1,4.0]],         # rear-right
    'SHTC3':             [[1,0,0,82.8],[0,1,0,26.5],[0,0,1,4.0]],         # front-right, coolest corner
    'AMS1117':           [[1,0,0,AMS_X0],[0,1,0,AMS_D0],[0,0,1,AMS_H]],            # across: header end on the right, pins pointing right, chip underneath
    'TinyS3':            [[-1,0,0,TS_EDGE_X],[0,-1,0,TS_DC+TS_W/2],[0,0,1,TS_H]],   # the model's frame is ts_box()'s: x to the left, y forward
}

def lbox(x0, x1, y0, y1, z0, z1):
    c = adsk.core.Point3D.create((x0+x1)/2*M, (y0+y1)/2*M, (z0+z1)/2*M)
    obb = adsk.core.OrientedBoundingBox3D.create(c, adsk.core.Vector3D.create(1,0,0), adsk.core.Vector3D.create(0,1,0),
                                                 (x1-x0)*M, (y1-y0)*M, (z1-z0)*M)
    return tb.createBox(obb)

def lcyl(x, y, z0, z1, r):
    return tb.createCylinderOrCone(adsk.core.Point3D.create(x*M, y*M, z0*M), r*M, adsk.core.Point3D.create(x*M, y*M, z1*M), r*M)

def soldered_38x22(header_y, sensor_wh, slots, reg_xy):
    """Soldered 38 x 22 mm breakout (SHTC3 333032, BME688 333203), measured off the docs.soldered.com pinout drawings.
    Local frame: x 0..38, y 0..22 as drawn, z up = component side. Four M3 holes on a 32 x 16 pitch inset 3.05 mm,
    JST-SH sockets 0.5..5.5 mm in from each short edge, centred; 4-pin 2.54 mm header 1.6 mm from one long edge."""
    L, W, T, R = 38.0, 22.0, 1.6, 2.0
    pcb = lbox(0, L, 0, W, 0, T)
    for (x0, x1, y0, y1) in [(0, R, 0, R), (L-R, L, 0, R), (0, R, W-R, W), (L-R, L, W-R, W)]:
        tb.booleanOperation(pcb, lbox(x0, x1, y0, y1, -1, T+1), adsk.fusion.BooleanTypes.DifferenceBooleanType)
    for (cx, cy) in [(R, R), (L-R, R), (R, W-R), (L-R, W-R)]:
        tb.booleanOperation(pcb, lcyl(cx, cy, 0, T, R), adsk.fusion.BooleanTypes.UnionBooleanType)
    for (hx, hy) in [(3.05, 3.05), (L-3.05, 3.05), (3.05, W-3.05), (L-3.05, W-3.05)]:
        tb.booleanOperation(pcb, lcyl(hx, hy, -1, T+1, 1.6), adsk.fusion.BooleanTypes.DifferenceBooleanType)
    for k in range(4):
        tb.booleanOperation(pcb, lcyl(15.24 + 2.54*k, header_y, -1, T+1, 0.75), adsk.fusion.BooleanTypes.DifferenceBooleanType)
    for (sx0, sx1, sy0, sy1) in slots:
        tb.booleanOperation(pcb, lbox(sx0, sx1, sy0, sy1, -1, T+1), adsk.fusion.BooleanTypes.DifferenceBooleanType)
    sw, sh, sz = sensor_wh
    rx, ry = reg_xy
    return [('PCB', pcb),
            ('JST-SH A', lbox(0.5, 5.5, 8.0, 14.0, T, T+3.0)),
            ('JST-SH B', lbox(L-5.5, L-0.5, 8.0, 14.0, T, T+3.0)),
            ('sensor', lbox(19-sw/2, 19+sw/2, 11-sh/2, 11+sh/2, T, T+sz)),
            ('regulator SOT-23', lbox(rx-1.5, rx+1.5, ry-1.5, ry+1.5, T, T+1.1))]

def ams1117_module():
    """AMS1117-3.3 breakout as measured: PCB 12.5 x 8.5 x 1.4, no mounting holes. Local frame: x 0..12.5 with the
    right-angle header at x = 12.5, y 0..8.5, z up = header/silkscreen side. SOT-223 on the underside (1.7 tall);
    header stack 7.1 mm overall including the solder domes below the board; pins reach 7 mm past the edge."""
    L, W, T = 12.5, 8.5, 1.4
    bodies = [('PCB', lbox(0, L, 0, W, 0, T)), ('header body', lbox(L-2.54, L, W/2-3.81, W/2+3.81, T, 5.9))]
    for k in range(3):
        yc = W/2 + (k-1)*2.54
        bodies.append(('pin %d' % (k+1), lbox(L, L+7.0, yc-0.32, yc+0.32, 5.26, 5.9)))
        bodies.append(('solder dome %d' % (k+1), lcyl(L-1.9, yc, -1.2, 0.0, 0.9)))   # 1.2 proud of the underside (measured)
    bodies += [('AMS1117 SOT-223', lbox(2.3, 5.8, 1.0, 7.5, -1.7, 0.0)), ('SOT-223 tab', lbox(0.4, 2.3, 2.75, 5.75, -0.3, 0.0)),
               ('R1 0603', lbox(1.0, 2.0, 5.5, 7.5, T, T+0.6))]
    return bodies

def board_component(devc, name, bodies):
    occ = devc.occurrences.addNewComponent(adsk.core.Matrix3D.create())
    occ.component.name = name
    bf = occ.component.features.baseFeatures.add(); bf.startEdit()
    for bname, body in bodies:
        nb = occ.component.bRepBodies.add(body, bf); nb.name = bname
    bf.finishEdit()
    return occ


DOCK_ELEC = 'Dock electronics (toggle)'

def dock_electronics(dockc):
    """The dock's boards, pogo female and wiring, in one component: its light bulb leaves the bare chassis and shell.
    Anything an older build left directly in the dock moves into it."""
    occ = get_or_make_comp(dockc, DOCK_ELEC)
    for o in list(dockc.occurrences):
        if o.component.name not in ('Dock chassis', 'Dock shell', DOCK_ELEC) and not o.component.name.startswith('Logo'):
            o.moveToComponent(occ)                                          # the logo and its stencil belong to the shell
    return occ.component

def parts(top):
    """A top assembly's parts, with the contents of the dock's electronics listed in the group's place."""
    for c in top.childOccurrences:
        if c.component.name == DOCK_ELEC: yield from c.childOccurrences
        else: yield c

def setup_components(app, des, head, dock):
    """Import the Inkplate into the head and the Adafruit boards into the dock's electronics (STEP downloads), build
    the Soldered and AMS1117 block-outs, then place everything."""
    headc, elecc = head.component, dock_electronics(dock.component)
    have = [o.component.name for o in headc.occurrences] + [o.component.name for o in elecc.occurrences]
    d = os.path.join(tempfile.gettempdir(), 'envmon_step'); os.makedirs(d, exist_ok=True)
    im = app.importManager
    targets = {'inkplate5gen2.step': ('Soldered Inkplate', headc), 'pmsa003i.step': ('Adafruit PMSA003I', elecc), 'scd41.step': ('PCB Component', elecc),
               'tinys3.step': ('TinyS3 1', elecc)}
    renamed = {'PCB Component': 'Adafruit SCD41', 'TinyS3 1': TS_NAME}
    for fn, url in STEP_URLS.items():
        key, target = targets[fn]
        if any(n.startswith(key) or n.startswith(renamed.get(key, key)) for n in have): continue
        p = os.path.join(d, fn)
        if not os.path.exists(p):
            req = urllib.request.Request(url, headers={'User-Agent': 'fusion'})
            with urllib.request.urlopen(req, timeout=180) as r, open(p, 'wb') as f: f.write(r.read())
        opts = im.createSTEPImportOptions(p); opts.isViewFit = False
        im.importToTarget(opts, target)
    for o in elecc.occurrences:
        if o.component.name.startswith('PCB Component'): o.component.name = 'Adafruit SCD41 (5190)'
        if o.component.name.startswith('TinyS3 1'): o.component.name = TS_NAME
    if not any(n.startswith('BME688') for n in have):
        board_component(elecc, 'BME688 (Soldered 333203)', soldered_38x22(
            header_y=1.6, sensor_wh=(3.0, 3.0, 0.93), slots=[(15, 23, 6.8, 7.8), (15, 23, 14.2, 15.2)], reg_xy=(9, 6)))
    if not any(n.startswith('SHTC3') for n in have):
        board_component(elecc, 'SHTC3 (Soldered 333032)', soldered_38x22(
            header_y=20.4, sensor_wh=(2.0, 2.0, 0.75), slots=[(15, 23, 6.8, 7.8), (15, 23, 14.2, 15.2), (15, 16, 6.8, 15.2)], reg_xy=(9, 16)))
    if not any(n.startswith('AMS1117') for n in have):
        board_component(elecc, 'AMS1117-3.3 module', ams1117_module())
    for o in headc.occurrences:
        for key, rows in HEAD_PLACEMENTS.items():
            if o.component.name.startswith(key): o.transform = mat(rows)
    for o in elecc.occurrences:
        for key, rows in BASE_PLACEMENTS.items():
            if o.component.name.startswith(key): o.transform = mat(rows)
    if des.snapshots.hasPendingSnapshot: des.snapshots.add()

# The black parts are drawn as mid greys, not black: these appearances copy Fusion's matte-black plastic, whose
# shader darkens the dock colour a long way, so a true black connector or wire loses every edge and shading cue
# against the boards (which are #404040) and reads as one solid blob. 88..105 renders as dark grey on screen.
COLS = {'housing': (88, 88, 88), 'black': (100, 100, 100), 'silver': (205, 205, 210), 'red': (200, 30, 30), 'yellow': (220, 190, 30),
        'white': (240, 240, 235), 'blue': (30, 80, 200), 'purple': (120, 60, 170), 'pcb_blue': (30, 90, 190), 'beige': (226, 208, 170),
        'gold': (216, 176, 70), 'dupont': (105, 105, 105), 'pm_blue': (30, 110, 185), 'pcb_green': (30, 140, 90),
        'dark_yellow': (170, 130, 20), 'res_blue': (95, 150, 205), 'band_black': (25, 25, 25), 'brown': (115, 65, 30),
        'green': (30, 150, 60)}
LIB_COLS = {'frosted': 'Plastic - Translucent Matte (White)'}   # parts drawn in a library finish rather than a flat colour

def ic_grey(des, app):
    """The colour the Inkplate's own STEP model gives its IC packages (the SOT-23 and TSSOP bodies): Opaque(64,64,64).
    Reused verbatim for the black PCBs so the boards read as one family rather than as pure black cut-outs."""
    for a in des.appearances:
        if a.name == 'Opaque(64,64,64)': return a
    return appearance(des, app, 'col ic grey', (64, 64, 64))

def appearance(des, app, name, rgb):
    for a in des.appearances:
        if a.name == name: return a
    lib = [l for l in app.materialLibraries if l.name == 'Fusion Appearance Library'][0]
    black = [a for a in lib.appearances if a.name.startswith('Plastic - Matte (Black)')][0]
    a = des.appearances.addByCopy(black, name)
    for p in a.appearanceProperties:
        cp = adsk.core.ColorProperty.cast(p)
        if cp:
            try: cp.value = adsk.core.Color.create(rgb[0], rgb[1], rgb[2], 255)
            except Exception: pass
    return a

def library_appearance(des, app, name):
    for a in des.appearances:
        if a.name == name: return a
    lib = [l for l in app.materialLibraries if l.name == 'Fusion Appearance Library'][0]
    return des.appearances.addByCopy(lib.appearances.itemByName(name), name)

def colour_all(des, app, headc, elecc, wiring):
    def ap(col):
        return library_appearance(des, app, LIB_COLS[col]) if col in LIB_COLS else appearance(des, app, 'col ' + col, COLS[col])
    grey = ic_grey(des, app)                   # the Inkplate STEP model's own IC colour, reused for every IC and PCB
    for o in elecc.occurrences:
        n = o.component.name
        if n.startswith(('BME688', 'SHTC3')):
            for b in o.component.bRepBodies:
                if b.name == 'PCB':               b.appearance = ap('purple')
                elif b.name.startswith('JST-SH'): b.appearance = ap('beige')
                else:                             b.appearance = grey      # sensor and regulator block-outs
        elif n.startswith('AMS1117'):
            for b in o.component.bRepBodies:
                b.appearance = ap('pcb_blue' if b.name == 'PCB' else 'silver' if b.name.startswith(('pin', 'solder')) else 'housing')
        elif n.startswith(('Adafruit SCD41', 'Adafruit PMSA')):
            def walk(oc):
                cn = oc.component.name
                for b in oc.component.bRepBodies:
                    if cn.startswith('JST_SH4'):   b.appearance = ap('beige')
                    elif cn.startswith('Board'):   b.appearance = grey        # the bare PCB, in the Inkplate's IC grey
                    elif cn.startswith('PMSA003i'):
                        b.appearance = ap('pm_blue') if b.name in ('Body1', 'Body3') else grey   # blue shell; fan cover as the PCB
                for c in oc.childOccurrences: walk(c)
            walk(o)
    for occ, colmap in wiring:
        for b in occ.component.bRepBodies:
            b.appearance = ap(colmap[b.name])

def insertion_sweep(tray_body):
    """What the Inkplate would have to pass through to reach its seat. It goes in from the back along Z, so sweep
    its own footprint from the cavity mouth up to its back face and intersect that with the tray. Anything at all
    here means the head cannot be assembled, however much clearance the board has once it is seated - which is
    exactly how four cover bosses and two screw blocks got as far as a printed part (Sept 2026)."""
    prism = rrect_h(0.0, 130.59, 0.0, 75.23, HEAD_ZBACK, -2.45, 3.0)
    tb.booleanOperation(prism, tb.copy(tray_body), adsk.fusion.BooleanTypes.IntersectionBooleanType)
    return round(prism.volume * 1000, 2)

def cover_pullout(tray_body, cover_body):
    """What stops the cover, and the Inkplate screwed to it, from dropping straight out of the back of the tray:
    the cover moved 0.5 mm backwards, intersected with the tray. It must be more than 0 - hold the head with the
    panel facing up and this is all that carries the Inkplate."""
    moved = tb.copy(cover_body)
    m = adsk.core.Matrix3D.create(); m.translation = V(0, 0, -0.5 * M)
    tb.transform(moved, m)
    tb.booleanOperation(moved, tb.copy(tray_body), adsk.fusion.BooleanTypes.IntersectionBooleanType)
    return round(moved.volume * 1000, 2)

def interference(des, root):
    names = {}
    def key(b): return (b.name, b.parentComponent.name, round(b.volume, 6))
    coll = adsk.core.ObjectCollection.create()
    def collect(o, minvol, label):
        for b in o.bRepBodies:
            if b.volume >= minvol: coll.add(b); names[key(b)] = label + '/' + b.name
        for c in o.childOccurrences: collect(c, minvol, label + '/' + c.component.name[:14])
    big_ink = ('PCB', 'ED05', 'Standoff', 'USB-C', 'K2-1114', 'HYC77', 'easyC', 'CR2032', 'ESP32', 'JST-2pin', 'SOP-16', 'SMD Switch', 'WQFN', 'TSSOP', 'SOP', 'SOT', 'JST', 'AVX', 'LQH', 'NR40', 'SOLID', 'COMPOUND')
    for top in root.occurrences:
        for c in parts(top):
            n = c.component.name
            if n.startswith('Soldered Inkplate'):
                for k in c.childOccurrences:
                    if k.component.name.startswith(big_ink): collect(k, 0.002, 'Inkplate/' + k.component.name[:14])
            elif 'wiring' in n:
                for b in c.bRepBodies: coll.add(b); names[key(b)] = 'WIRING/' + b.name
            else:
                collect(c, 0.0005, n[:18])
    inp = des.createInterferenceInput(coll); inp.areCoincidentFacesIncluded = False
    res = des.analyzeInterference(inp)
    hits = []
    if res:
        for i in range(res.count):
            r = res.item(i)
            a = names.get(key(r.entityOne), r.entityOne.name); b = names.get(key(r.entityTwo), r.entityTwo.name)
            if a.startswith('Inkplate/') and b.startswith('Inkplate/'): continue
            if a.startswith('WIRING/') and b.startswith('WIRING/'): continue
            if a.split('/')[0] == b.split('/')[0]: continue   # bodies of one part touching each other
            if ('WIRING/' in a + b) and ('tails' in a + b or 'legs' in a + b): continue   # a wire soldered to a tail or a leg touches it
            if 'Dupont' in a + b and '/pin' in a + b: continue            # a housing on a pin contains it
            ib = r.interferenceBody
            bb = ib.boundingBox if ib else None
            hits.append({'a': a, 'b': b, 'mm3': round(ib.volume * 1000, 3) if ib else None,
                         'box': [round(v * 10, 1) for v in (bb.minPoint.x, bb.minPoint.y, bb.minPoint.z, bb.maxPoint.x, bb.maxPoint.y, bb.maxPoint.z)] if bb else None})
    return hits

def wiring_report(root):
    """Every wire-on-wire overlap in the two wiring layers (mm3; must be empty), and every bend that did not get
    BEND_K x diameter: 'forced' is at or above BEND_FLOOR, 'under_floor' is below it (must be empty), 'joints'
    are the solder joints, which may be sharp. Positions are in each layer's own frame."""
    rows = {'overlaps': [], 'forced': [], 'under_floor': [], 'joints': []}
    for top in root.occurrences:
        for c in parts(top):
            if 'wiring' not in c.component.name:
                continue
            ws = [b for b in c.bRepBodies if b.name.startswith(('wire', 'Qwiic'))]
            for i in range(len(ws)):
                for j in range(i + 1, len(ws)):
                    if not ws[i].boundingBox.intersects(ws[j].boundingBox):
                        continue
                    x = tb.copy(ws[i]); tb.booleanOperation(x, tb.copy(ws[j]), adsk.fusion.BooleanTypes.IntersectionBooleanType)
                    if x.lumps.count and x.volume * 1000 > 0.001:
                        bb = x.boundingBox
                        rows['overlaps'].append([ws[i].name, ws[j].name, round(x.volume * 1000, 3),
                                                 [round(v * 10, 1) for v in (bb.minPoint.x, bb.minPoint.y, bb.minPoint.z, bb.maxPoint.x, bb.maxPoint.y, bb.maxPoint.z)]])
    for name, R, p, d, joint in BEND_LOG:
        row = [name, R, [round(v, 1) for v in p]]
        if joint: rows['joints'].append(row)
        elif R < BEND_FLOOR - 0.05: rows['under_floor'].append(row)
        elif R < BEND_K * d - 0.05: rows['forced'].append(row)
    return rows

PRINT_MIN_WALL, PRINT_WARN_WALL, PRINT_MIN_EDGE_DEG = 0.45, 0.8, 30.0   # 0.4 mm nozzle: one line is ~0.45 wide, two ~0.8
PRINTED_PARTS = ('Head tray', 'Head back cover', 'Dock chassis', 'Dock shell')

def _side(body, p):
    c = body.pointContainment(p)
    PC = adsk.fusion.PointContainment
    return 'in' if c == PC.PointInsidePointContainment else 'out' if c == PC.PointOutsidePointContainment else 'on'

def _thin_kind(body, p1, p2):
    """'wall' if solid runs from p1 to p2 with air just beyond each, 'gap' for the reverse, 'touch' if they coincide,
    None if the two faces only meet across a corner of thicker material. Probed along the segment and 0.02 mm to each
    side of it, because the nearest points often land on an edge, where containment reads 'on'."""
    seg = adsk.core.Vector3D.create(p2.x - p1.x, p2.y - p1.y, p2.z - p1.z)
    if seg.length < 1e-6:
        return 'touch'
    u = seg.copy(); u.normalize()
    v = u.crossProduct(adsk.core.Vector3D.create(0, 1, 0) if abs(u.x) > 0.9 else adsk.core.Vector3D.create(1, 0, 0)); v.normalize()
    w = u.crossProduct(v); w.normalize()
    eps = 0.002 / seg.length
    for ox, oy, oz in ((0, 0, 0), (v.x, v.y, v.z), (-v.x, -v.y, -v.z), (w.x, w.y, w.z), (-w.x, -w.y, -w.z)):
        def at(t):
            return _side(body, adsk.core.Point3D.create(p1.x + seg.x * t + ox * 0.002, p1.y + seg.y * t + oy * 0.002, p1.z + seg.z * t + oz * 0.002))
        mid, ends = {at(0.25), at(0.5), at(0.75)}, (at(-eps), at(1 + eps))
        if mid == {'in'} and ends == ('out', 'out'): return 'wall'
        if mid == {'out'} and ends == ('in', 'in'): return 'gap'
    return None

def _worst_per_cell(rows, key):
    """The worst row in each 3 mm cell, so one long thin wall reads as a few rows rather than hundreds."""
    cells = {}
    for r in rows:
        cell = tuple(int(c // 3) for c in r['at']) + (r['kind'],)
        if cell not in cells or r[key] < cells[cell][key]: cells[cell] = r
    return sorted(cells.values(), key=lambda r: r[key])

def _knife_edges(body, loc):
    """Edges whose two faces meet at under PRINT_MIN_EDGE_DEG: 'knife' with solid in the wedge, 'slot' with air."""
    lim = -math.cos(math.radians(PRINT_MIN_EDGE_DEG))
    rows = []
    for e in body.edges:
        if e.faces.count != 2: continue
        fa, fb = e.faces.item(0), e.faces.item(1)
        ok, t0, t1 = e.evaluator.getParameterExtents()
        if not ok: continue
        worst = None
        for k in (0.2, 0.5, 0.8):
            ok, pt = e.evaluator.getPointAtParameter(t0 + (t1 - t0) * k)
            if not ok: continue
            ok1, na = fa.evaluator.getNormalAtPoint(pt)
            ok2, nb = fb.evaluator.getNormalAtPoint(pt)
            if not (ok1 and ok2): continue
            dot = max(-1.0, min(1.0, na.dotProduct(nb)))
            if dot > lim: continue
            s = adsk.core.Vector3D.create(-(na.x + nb.x), -(na.y + nb.y), -(na.z + nb.z))
            kind = 'degenerate'
            if s.length > 1e-9:
                s.normalize(); s.scaleBy(0.005)
                probe = pt.copy(); probe.translateBy(s)
                kind = {'in': 'knife', 'out': 'slot', 'on': 'on'}[_side(body, probe)]
            deg = 180.0 - math.degrees(math.acos(dot))
            if worst is None or deg < worst['deg']: worst = {'deg': round(deg, 1), 'kind': kind, 'at': loc(pt)}
        if worst: rows.append(worst)
    return _worst_per_cell(rows, 'deg')

def _thin_walls(body, loc, measure):
    """Walls and gaps under PRINT_WARN_WALL between two faces that face each other and share no edge or corner."""
    faces = list(body.faces)
    boxes, boundary = [], []
    for f in faces:
        bb = f.boundingBox
        boxes.append((bb.minPoint.x, bb.minPoint.y, bb.minPoint.z, bb.maxPoint.x, bb.maxPoint.y, bb.maxPoint.z))
        ids = {('e', e.tempId) for e in f.edges}
        ids.update(('v', v.tempId) for v in f.vertices)
        boundary.append(ids)
    g = PRINT_WARN_WALL / 10
    rows = []
    for i, a in enumerate(boxes):
        for j in range(i + 1, len(faces)):
            c = boxes[j]
            if c[0] > a[3] + g or a[0] > c[3] + g or c[1] > a[4] + g or a[1] > c[4] + g or c[2] > a[5] + g or a[2] > c[5] + g: continue
            if boundary[i] & boundary[j]: continue
            r = measure.measureMinimumDistance(faces[i], faces[j])
            if r.value * 10 >= PRINT_WARN_WALL: continue
            p1, p2 = r.positionOne, r.positionTwo
            ok1, n1 = faces[i].evaluator.getNormalAtPoint(p1)
            ok2, n2 = faces[j].evaluator.getNormalAtPoint(p2)
            if not (ok1 and ok2) or n1.dotProduct(n2) > -0.5: continue
            kind = _thin_kind(body, p1, p2)
            if kind:
                mid = adsk.core.Point3D.create((p1.x + p2.x) / 2, (p1.y + p2.y) / 2, (p1.z + p2.z) / 2)
                rows.append({'mm': round(r.value * 10, 2), 'kind': kind, 'at': loc(mid)})
    return _worst_per_cell(rows, 'mm')

def printability(app, head, dock):
    """Knife edges and thin walls or gaps in the four printed parts, for a 0.4 mm nozzle. Positions are in each
    part's own frame (head X, Y, Z; dock X, D, H). 'knives' and 'fail' must be empty."""
    measure = app.measureManager
    out = {}
    for top, is_head in ((head, True), (dock, False)):
        inv = top.transform2.copy(); inv.invert()
        def loc(p, inv=inv, is_head=is_head):
            q = p.copy(); q.transformBy(inv)
            x, y, z = q.x * 10, q.y * 10, q.z * 10
            return [round(v, 1) for v in ((x, z, -y) if is_head else (x, y, z))]
        for occ in top.childOccurrences:
            if occ.component.name not in PRINTED_PARTS: continue
            body = occ.bRepBodies.item(0)
            thin = _thin_walls(body, loc, measure)
            out[occ.component.name] = {'knives': _knife_edges(body, loc),
                                       'fail': [r for r in thin if r['mm'] < PRINT_MIN_WALL],
                                       'warn': [r for r in thin if r['mm'] >= PRINT_MIN_WALL]}
    return out


BUILD_WIRING = True     # the two wiring layers: the head's two pogo wires, and the dock's. False leaves both out and removes any found

def run(context):
    """Build the whole thing, from scratch or over an earlier build: downloads the reference models, places every
    board, builds the four printed parts (and the wiring layers, with BUILD_WIRING), then tilts the head into the dock."""
    app = adsk.core.Application.get()
    des = adsk.fusion.Design.cast(app.activeProduct)
    root = des.rootComponent
    head = get_or_make_comp(root, 'Head')
    dock = get_or_make_comp(root, 'Dock')
    for top in (head, dock):
        for o in parts(top): clear_fillets(o.component)
    head.transform = adsk.core.Matrix3D.create()
    if des.snapshots.hasPendingSnapshot: des.snapshots.add()
    setup_components(app, des, head, dock)
    elec = dock_electronics(dock.component)          # toggle its light bulb to see the bare chassis and shell
    del BEND_LOG[:]                                 # the module can outlive one run in Fusion's script runner
    mh = head_matrix()
    t  = build_head_tray(head.component)
    c  = build_head_cover(head.component)
    ch = build_chassis(dock.component, mh)
    sh = build_shell(dock.component, mh)
    logo = build_logo(dock.component)               # a separate white print, glued into the shell's recess
    sten = build_stencil(dock.component)            # and the tool that places it (hidden)
    if BUILD_WIRING:                                # toggle these two components' light bulbs to hide the wiring
        wiring = [build_head_wiring(head.component), build_dock_wiring(elec, mh)]
    else:
        wiring = []
        for grp in (head.component, dock.component, elec):
            for o in list(grp.occurrences):
                if 'wiring' in o.component.name: o.deleteMe()
    p1 = build_pogo_head(head.component)            # the two halves of the junction, as bought
    p2 = build_pogo_dock(elec, mh)
    for o in list(elec.occurrences):
        if o.component.name == 'USB-C plugs (toggle)': o.deleteMe()
    fitted = [build_ts_strips(elec), build_pw_socket(elec), build_plug(elec), build_status_led(elec), build_led_tile(elec)]
    refs = build_pogo_ref(root)
    colour_all(des, app, head.component, elec, wiring + [p1, p2] + fitted + refs + [logo, sten])
    fin = {}
    fin.update(finish_shell([o for o in dock.component.occurrences if o.component.name == 'Dock shell'][0]))
    fin.update(finish_tray([o for o in head.component.occurrences if o.component.name == 'Head tray'][0]))
    head.transform = mh                             # the head is the only tilted assembly
    if des.snapshots.hasPendingSnapshot: des.snapshots.add()
    app.activeViewport.fit()
    lumps = {}
    for top in (head, dock):
        for o in top.component.occurrences:
            if o.component.bRepBodies.count == 1 and 'wiring' not in o.component.name and 'Logo' not in o.component.name and 'stencil' not in o.component.name:
                lumps[o.component.name] = o.component.bRepBodies.item(0).lumps.count
    print(json.dumps({'lumps_must_all_be_1': lumps, 'inkplate_insertion_blocked_mm3': insertion_sweep(t), 'cover_pullout_blocked_mm3': cover_pullout(t, c), 'head tray': bb_mm(t.boundingBox), 'head cover': bb_mm(c.boundingBox),
                      'dock chassis': bb_mm(ch.boundingBox), 'dock shell': bb_mm(sh.boundingBox),
                      'finish': fin, 'interference': interference(des, root), 'printability': printability(app, head, dock),
                      'wiring': wiring_report(root)}))
