# Shared geometry helpers for the Inkplate env-monitor enclosure.
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
# Head (display housing): thin tray + flat back cover. Inkplate rotated 180 deg -> USB-C on the LEFT.
# Head frame: X 0..130.59 = PCB left->right seen from the front, Y up (0..75.23), Z toward the viewer,
# panel front at Z = 0.  Z levels: bezel front +2.4 . panel 0 . PCB back -2.45 . standoff tops -9.67 .
# cover -9.67..-11.67 (the cover rests on the Inkplate's four SMT standoffs).
# ---------------------------------------------------------------------------------------------
HEAD_R, HEAD_CAV_R, HEAD_R_FRONT = 5.0, 3.0, 1.2   # plan corner radius (outer / cavity), round on the bezel's front edge
#   (the bezel round is limited by the 2 mm wall and the 2.4 mm lip: 1.3 mm would break through at the cavity corner)
HEAD_ZF, HEAD_ZBACK = 2.4, -11.67
HEAD_X0, HEAD_X1, HEAD_Y0, HEAD_Y1 = -2.0, 132.6, -1.0, 76.2       # cavity
HEAD_LWALL, HEAD_RWALL, HEAD_WALL = 7.3, 2.0, 2.0                  # thick LEFT wall (USB-C side) for a symmetric bezel
# There are no bosses of any kind inside the cavity, and there must never be. The Inkplate is 130.59 x 75.23 in a
# 134.6 x 77.2 cavity - 2 mm a side in X, because SW2 and the wake switch stand 0.85 mm past the board's left and
# right edges, and 1 mm top and bottom - and it goes in from the back, so its own footprint sweeps the whole
# cavity on the way to its seat. Anything standing in there, however far behind the board it ends up, is something
# the board has to pass through first. Four boss towers for the cover and two blocks for the base screws were
# exactly that, and the first print could not be assembled (Sept 2026). The cover now screws to the Inkplate's own
# four M3 SMT standoffs, and the head is held down by the pogo connector's magnets rather than by screws.
# --- head-to-base junction: an 8-pin magnetic pogo pair, mating along the head's Y as the head sits down ---
#   Both halves are panel-mount parts with a LIP, and that lip is how they are fixed: each goes in from inside its
#   own shell, the lip lands on a face and is glued to it, and only what has to make contact stands out. So the
#   male lives almost entirely inside the head - its nose fills the 2 mm bottom wall and stands PG_PROUD out of the
#   underside, the lip and the solder tails are in the cavity - and the female almost entirely inside a plinth in
#   the base. Nothing hangs in the gap between the two any more.
#   Centred on the device in X (-10.6..135.9): everything that feeds the head half is right of centre (the expander
#   row at 90.7, the easyC cable at 99..103, the ESP32 ground at 45) and everything the base half feeds is left of
#   it (the PM header at 6.4..21.6, the AMS at 37..42), so no run doubles back on itself.
POGO_X, POGO_Z = 62.65, -6.00
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

PG_TAILS = {'SCL': (-3.45, 1.15), 'SDA': (-1.15, 1.15), 'VIN': (1.15, 1.15), 'GNDC': (3.45, 1.15),
            'SET': (-1.15, -1.15), 'GND': (1.15, -1.15), 'GND2': (3.45, -1.15)}   # (-3.45, -1.15) is the empty way
#   (dx, dz) in the head: dz +1.15 is the row nearer the board, -1.15 the row nearer the back cover. Which signal
#   takes which way is set by what a wire can reach in the head, and by the order the wires must turn in the
#   base - see the two wiring builders - not by the electronics.
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
    union(b, pg_stad(PG_M_LIP_L, PG_M_LIP_W, M_Y1 - 0.01, M_Y2))             # lip, glued to the cavity floor
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
    """The female, in place in the base. as_bought: all eight ways."""
    ways = PG_WAYS if as_bought else PG_TAILS.values()
    b = pg_stad(PG_F_L, PG_F_W, F_Y3, F_Y2)                                  # bottom band
    union(b, pg_stad(PG_F_LIP_L, PG_F_LIP_W, F_Y2 - 0.01, F_Y1))             # lip, glued to the plinth's ledge
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

ESP32_VENT = (74.0, 94.0, 14.0, 40.0)   # back-cover grille: X span, then the Y band. Slots run ALONG X -
#   everything else about this object is horizontal (the shadow gap, the PM's vent strip), and one band spanning
#   low to high vents better than two: air enters at the bottom rows and leaves at the top ones.
#   The ESP32-WROVER sits at X 75..93, Y -0.2..31.8 once the Inkplate is rotated 180 deg, and it is the only real heat
#   source in the head. The bands used to be at X 104..124, which is directly over the CR2032 holder (X 106..122) -
#   venting the one part of the board that makes no heat, and dropping debris onto a lithium cell. They start at Y 14
#   to stay clear of the wire lanes that cross the board at Y 3..11, or you would see cables through the slots.

def rrect_h(x0, x1, y0, y1, z0, z1, r):
    """Rounded-rectangle prism in the head frame (corner centres inset by r)."""
    b = box(x0 + r, x1 - r, y0, y1, z0, z1)
    union(b, box(x0, x1, y0 + r, y1 - r, z0, z1))
    for (cx, cy) in [(x0 + r, y0 + r), (x1 - r, y0 + r), (x0 + r, y1 - r), (x1 - r, y1 - r)]:
        union(b, cyl_z(cx, cy, z0, z1, r))
    return b

def head_outline(clear, z0, z1):
    """The head's outer envelope, grown by `clear` - the base uses it for the cradle pocket and the shell cutout,
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
    """Front shell: bezel + 4 walls, 14.1 mm deep, printed face-down. Inkplate rotated 180 deg."""
    X0, X1, Y0, Y1 = HEAD_X0, HEAD_X1, HEAD_Y0, HEAD_Y1
    ZF, ZLIP, ZBACK = HEAD_ZF, 0.0, HEAD_ZBACK
    t = rrect_h(X0 - HEAD_LWALL, X1 + HEAD_RWALL, Y0 - HEAD_WALL, Y1 + HEAD_WALL, ZBACK, ZF, HEAD_R)
    cut(t, rrect_h(X0, X1, Y0, Y1, ZBACK - 1, ZLIP, HEAD_CAV_R))
    # --- display window: active area (rotated: X 5.35..119.91, Y 5.39..69.84) + 0.8 mm, 1 mm step outside ---
    AX0, AX1, AY0, AY1, MARG = 5.35, 119.91, 5.39, 69.84, 0.8
    cut(t, box(AX0 - MARG, AX1 + MARG, AY0 - MARG, AY1 + MARG, ZLIP - 1, ZF + 1))
    cut(t, box(AX0 - MARG - 1, AX1 + MARG + 1, AY0 - MARG - 1, AY1 + MARG + 1, ZF - 1.0, ZF + 1))
    # --- relief in the bezel lip for the solder tails of the expander header (now on the TOP edge, X 89.4..102.1) ---
    cut(t, box(88.0, 104.0, 72.0, 74.9, -0.5, ZF - 1.0))
    cut(t, box(42.5, 50.0, 72.0, 74.9, -0.5, ZF - 1.0))            # ... and for the ESP32-group header (GND at X 44.97)
    # --- pogo male: a stadium hole through the bottom wall for its nose, and two ribs on the cavity floor that
    #     locate its lip. Everything behind the lip is in open cavity, so with the back cover off you solder the
    #     seven wires to the tails, push the part out through the hole and glue the lip to the floor. ---
    cut(t, pg_stad(PG_M_L, PG_M_W, Y0 - HEAD_WALL - 1.0, M_Y1 + 0.01, PG_CLR))
    for sgn in (-1, 1):                                       # ribs that locate the lip while the glue goes off
        xr = POGO_X + sgn * (PG_M_LIP_L / 2 + PG_CLR + 0.75)
        union(t, box(xr - 0.75, xr + 0.75, M_Y1 - 0.01, M_Y2 - 0.20, POGO_Z - 3.5, POGO_Z + 3.5))
    cut(t, pg_stad(PG_M_LIP_L - 3.0, PG_M_LIP_W - 3.0, M_Y1 - 0.15, M_Y1 + 0.01))   # glue relief: the lip lands on
    #   a 1.5 mm land round its rim and the glue has somewhere to go instead of squeezing out over the contacts
    # --- left wall (thick): USB-C, power button, microSD through stepped pockets ---
    LI = (X0 - 2.0, X0 + 0.5)                       # inner 2 mm skin
    LO = (X0 - HEAD_LWALL - 1, X0 - 2.0)            # outer pocket region
    cut(t, box(LI[0], LI[1], 54.7, 65.7, -6.6, -0.6)); cut(t, box(LO[0], LO[1], 53.2, 67.2, -8.0, 0.4))   # USB-C + plug overmold pocket
    cut(t, box(LI[0], LI[1], 45.2, 53.2, -5.5, -0.8)); cut(t, box(LO[0], LO[1], 43.7, 54.7, -7.5, 0.4))   # power button + finger pocket
    cut(t, box(LI[0], LI[1], 22.7, 39.7, -5.0, -1.2)); cut(t, box(LO[0], LO[1], 20.7, 41.7, -8.0, 0.4))   # microSD + finger pocket
    # --- right wall: wake button ---
    cut(t, box(X1 - 0.5, X1 + HEAD_RWALL + 1, 45.2, 53.2, -5.2, -1.0))
    # --- no vents in the walls: the head's only opening is the grille in the back cover, over the ESP32, where it
    #     faces up and back and is invisible from the front and sides ---
    occ = get_or_make_comp(headc, 'Head tray')
    return replace_body(occ.component, t, 'Head tray')

def build_head_cover(headc):
    """Flat back cover: sits inside the walls on the Inkplate's four M3 SMT standoffs and screws into them.
    That is the only thing holding it - see the note by the cavity constants for why there are no tray bosses."""
    ZO, ZI = HEAD_ZBACK, HEAD_ZBACK + 2.0
    c = rrect_h(HEAD_X0 + 0.2, HEAD_X1 - 0.2, HEAD_Y0 + 0.2, HEAD_Y1 - 0.2, ZO, ZI, HEAD_CAV_R - 0.2)
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
# Base: chassis (floor + cradle block + bay features, printed upright) inside a shell (top skin + 4 walls,
# printed upside down). Base frame "B": X as the head, D = depth from the front-bottom edge, H = height above the
# desk; Fusion world X_f = X, Y_f = D, Z_f = H. The front face is a 20-deg slab continuous with the head's bezel;
# the top skin slopes from H 30.5 behind the head to H 25 at the rear. PM sits on the LEFT.
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
B_D1 = 86.0                         # depth
B_DBAY0, B_DBAY1 = 25.0, 84.0       # bay interior depth range (front = cradle block's rear face)
H_FRONT, H_REAR = 30.5, 25.0        # top skin, outer, at D 25 and at the rear
#   Set by the connectors, not the boards: a Dupont housing standing on a straight header needs 14 mm for itself and
#   3.7 mm for the wire to turn (measured), so on a board at H 5.6 the wire's crown is at H 25.8, and the skin's
#   underside has to clear that wherever a housing stands - at the PM header (D 29.5) and the SCD41 header (D ~48).
#   At 27 / 21.5 the PM housings were 1 mm short and the wire kinked against the skin.
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
TUN_X0, TUN_X1 = 9.0, 42.0          # a tunnel through the cradle block at the trench's floor level, from the PM's
TUN_D0, TUN_D1 = 20.5, 24.0         #   leftmost housing to the trench: the four PM wires run out of the trench
TUN_H0, TUN_H1 = 3.0, 7.0           #   into it with no climb, in two layers
TUN_MOUTH = (9.5, 28.5, 3.2)        # (X, X, radius): behind TUN_D0 the block is open to the PM side here, floor to
TUN_MOUTH_TOP = 10.5                #   TUN_MOUTH_TOP. Its far end is rounded tangent to the tunnel, and that is
#   where the tunnel ends - so a wire pushed along the tunnel meets a curve that turns it out towards the PM, not a
#   corner. The mouth stops short of the block's top because the head's pocket leans back into it: at the top the
#   wall in front would feather to nothing. In front of TUN_D0 the block is untouched, so the head's back still
#   lands on a full-height wall, and from the mouth back to the trench the tunnel runs through solid block.
HEAD_CLR = 0.5                      # clearance round the head's outline in the cradle pocket and the shell's opening

def boxb(X0, X1, D0, D1, H0, H1):  return box(X0, X1, H0, H1, -D1, -D0)
def cylH(X, D, H0, H1, r):         return cyl_y(X, -D, H0, H1, r)
def coneH(X, D, H0, r0, H1, r1):   return tb.createCylinderOrCone(P(X, H0, -D), r0 * M, P(X, H1, -D), r1 * M)
def hs_b(pt, n):                   # base-frame halfspace: (X, D, H) point and normal
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
    """The top-edge chamfer, built into the solid rather than as a chamfer feature: a 45 deg drafted prism whose
    reference plane is rotated onto the sloped top, C_TOP below it. Intersecting the shell with it takes exactly
    C_TOP off the top edge all the way round, wrapping the rounded corners, and leaves everything lower untouched
    (45 deg flares faster than the 4.3 deg wall draft below the reference plane)."""
    slope = (H_FRONT - H_REAR) / (B_D1 - B_DBAY0)
    k = drafted_rrect(B_X0, B_X1, 0.0, B_D1, -20.0, H_FRONT + 6.0, R_PLAN, 45.0, H_FRONT - C_TOP)   # +6: at 45 deg the corner radius would reach zero 10 mm above the reference plane
    m = adsk.core.Matrix3D.create()
    m.setToRotation(-math.atan(slope), adsk.core.Vector3D.create(1, 0, 0),
                    adsk.core.Point3D.create(0.0, B_DBAY0 * M, (H_FRONT - C_TOP) * M))
    tb.transform(k, m)
    return k

def head_matrix(tilt_deg=TILT, front_d=HEAD_FRONT_D, front_h=HEAD_FRONT_H):
    rot = adsk.core.Matrix3D.create()
    rot.setToRotation(math.radians(-tilt_deg), adsk.core.Vector3D.create(1, 0, 0), adsk.core.Point3D.create(0, 0, 0))
    a = P(0.0, -3.0, HEAD_ZF); a.transformBy(rot)
    tr = adsk.core.Matrix3D.create(); tr.translation = adsk.core.Vector3D.create(0, front_d * M - a.y, front_h * M - a.z)
    m = rot.copy(); m.transformBy(tr)
    return m

def head_point(mh, X, Y, Z):
    p = P(X, Y, Z); p.transformBy(mh); return p
def head_dir(mh, X, Y, Z):
    v = V(X, Y, Z); v.transformBy(mh); v.normalize(); return v
def head_volume(mh, clear, z0, z1):
    """The head's envelope, in base-frame world position: the pocket and the shell's opening both come from this."""
    v = head_outline(clear, z0, z1)
    tb.transform(v, mh)
    return v
def skin_top(d):                    # outer top surface height at depth d (flat at H_FRONT ahead of the bay)
    return H_FRONT if d <= B_DBAY0 else H_FRONT - (H_FRONT - H_REAR) * (d - B_DBAY0) / (B_D1 - B_DBAY0)

# --- bay layout (mm) ---------------------------------------------------------
PM_X0, PM_D0 = -3.8, 27.0                     # PMSA003I X -3.8..31.8 (air face 4.8 mm from the left wall), D 27..77.8, header row at the FRONT
#   X -3.8: the chassis floor is inset 1.5 mm from the wall (CH_INSET), so the board edge and its two left bosses need
#   ~1 mm of floor under them; everything between the PM and the SCD41 compartment moved right with it
#   D 27 keeps the board's rear corner clear of the cavity's 10 mm rounded corner (2.9 mm at the tightest point)
PM_PINS = {k: PM_X0 + v for k, v in {'SET': 25.4, 'SDA': 20.32, 'SCL': 17.78, 'GND': 15.24, 'VIN': 10.16}.items()}   # straight header at D 29.54, housings standing up
SCD_X1, SCD_D0 = 72.8, 35.0                   # SCD41 X 49.9..72.8, D 35..60.4, sockets facing front / rear (centre X 61.4)
BME_X0, BME_D0 = 82.8, 53.5                   # BME688 X 82.8..120.8, D 53.5..75.5 (rear-right)
SHT_X0, SHT_D0 = 82.8, 26.5                   # SHTC3 X 82.8..120.8, D 26.5..48.5 (front-right, coolest corner)
AMS_X1, AMS_D0 = 43.8, 61.0                   # AMS1117 X 35.3..43.8, D 61..73.5, pins toward the HEAD (-D)
#   X 43.8 centres the mount in the strip: 2.0 mm to the PM board on one side, 2.0 mm to the compartment wall on the other
#   (it used to sit 0.2 mm off the PM board with 4.2 mm spare on the far side)
#   D 61 puts its back edge flush with the SCD41 compartment's rear wall, and - the reason for it - pushes the Dupont
#   housings back to D 47..61, clear of the PM -> SCD41 ribbon that crosses the strip at D 35.9
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
#   at once and the useful position is nearer the arc's centre (125.9, 76), not nearer the corner. Each one now keeps
#   >= 1.8 mm, limited by the board it sits beside (0.5..0.7 mm of drop-on clearance to the SCD41 compartment's rear
#   wall, the SHTC3 and the BME688 respectively).
SHELL_PILLARS = [(68.0, 30.0), (125.0, 30.0), (50.0, 77.5), (125.0, 76.0)]
CSK_D, CSK_H = 6.2, 1.4                       # countersink for the M3 flat heads, 90 deg: an ISO 7046 head is 5.5 (5.6
#   max) across, so 6.2 clears it, and taking 0.4 off the 6.6 first drawn is 0.2 mm more wall at every hole and 0.6 mm
#   rather than 0.4 of floor left above the cone.
AMS_POST = (AMS_X1 - 4.25, AMS_D0 + 5.0, 2.0, AMS_H + 1.4 - 0.15)   # on the board's centreline, between the two supports, so the
#   two rather than pivoting about the pad - 0.15 mm of preload, on bare board between the header and R1
PM_BOSSES = [(PM_X0 + 2.54, PM_D0 + 2.54), (PM_X0 + 33.02, PM_D0 + 2.54), (PM_X0 + 2.75, PM_D0 + 48.3), (PM_X0 + 32.75, PM_D0 + 15.3)]   # Adafruit 4632 holes
PM_SEAL_D = (PM_D0 + 27.8, PM_D0 + 31.1)      # seal rib between the module's two ports (gap: 54.5..58.4)
PM_SEAL_W, PM_SEAL_H = PM_X0 - 0.2 - B_XI0, 19.0   # fills the gap to the module face (0.2 mm short of it), up to 1 mm above the module
PM_VENTS = ((PM_D0 + 14.4, PM_D0 + 27.5), (PM_D0 + 31.4, PM_D0 + 51.0))   # fan outlet (front) and inlet (rear)
VENT_H = (9.0, 20.0)                          # the recessed strip that carries them

def build_chassis(basec, mh):
    body = boxb(B_XI0, B_XI1, SKIN, B_DBAY1, 0.0, 2.0)                                      # floor
    union(body, boxb(B_XI0, B_XI1, SKIN, B_DBAY0 + 0.01, 0.0, H_FRONT - SKIN))               # cradle block
    c, s = math.cos(math.radians(TILT)), math.sin(math.radians(TILT))
    cut(body, head_volume(mh, HEAD_CLR, HEAD_ZBACK - 0.3, HEAD_ZF + 0.3))                    # cradle pocket
    cut(body, boxb(B_XI0 - 1, B_XI1 + 1, 17.8, B_DBAY0 + 1, BLOCK_TOP_REAR, H_FRONT))        # low rear lip behind the head
    cut(body, boxb(TUN_X0, TUN_X1, TUN_D0, TUN_D1, TUN_H0, TUN_H1))                          # wire tunnel at floor level
    mx0, mx1, mr = TUN_MOUTH
    mouth = boxb(mx0, mx1, TUN_D0, B_DBAY0 + 1, TUN_H0, TUN_MOUTH_TOP)                       # mouth, open to the PM,
    union(mouth, cylH(mx0, TUN_D0 + mr, TUN_H0, TUN_MOUTH_TOP, mr))                          # its far end rounded
    cut(body, mouth)                                                                         # into the tunnel. One
    #   tool, so the arc meets the flat of it tangentially: cut apart, the two faces cross and leave a fin
    tx0, tx1, td0, td1 = TRENCH
    trench = boxb(tx0, tx1, td0, td1, 3.0, H_FRONT)
    cut(body, trench)     # (the island that used to protect the left base screw is moot: the trench starts at 42)
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
    cut(body, boxb(POGO_X - 8.0, POGO_X + 8.0, 12.0, bore_back_d, 2.5, chamber_top))     # the tails' chamber out
    cut(body, boxb(POGO_X - 8.0, POGO_X + 8.0, bore_back_d - 0.01, B_DBAY0 + 1.0, 2.5, 5.5))   # through the plinth's back
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
    ax0, ax1, ad0, ad1 = AMS_X1 - 8.5, AMS_X1, AMS_D0, AMS_D0 + 12.5
    px0, px1, pd0, pd1 = ax0 - AMS_CLR, ax1 + AMS_CLR, ad0 - AMS_CLR, ad1 + AMS_CLR          # pocket = board + AMS_CLR a side
    rt = AMS_H + 2.0                                                                         # top of the locating walls
    union(body, boxb(px0, px1, ad0 + 0.9, ad0 + 2.9, 2.0 - 0.01, AMS_H - AMS_DOME))          # front support: the three solder
    #   domes land on this. They are the one thing under that board whose height repeats copy to copy; the clear band between
    #   the domes and the SOT-223 is under a millimetre wide and moves about, so a pad that relied on it would not fit twice.
    #   Full pocket width, so the domes land on it wherever the board sits in its clearance.
    union(body, boxb(px0, ax0 + 2.1, ad0 + 10.4, pd1 + 0.01, 2.0 - 0.01, AMS_H))             # rear supports, BEHIND the body of
    union(body, boxb(ax1 - 2.1, px1, ad0 + 10.4, pd1 + 0.01, 2.0 - 0.01, AMS_H))             # U1: past D +10.4 the only thing
    #   under the board is the SOT-223's 3 mm tab, so there is 2.6 mm of bare PCB to bear on each side instead of the 1.0 mm
    #   beside the chip - and with AMS_CLR the board can sit 0.5 mm off centre, which that 1.0 mm could not have absorbed.
    union(body, boxb(px0 - 1.0, px1 + 1.0, pd0 - 1.0, pd0, 2.0 - 0.01, rt))                  # front wall
    union(body, boxb(px0 - 1.0, px1 + 1.0, pd1, pd1 + 1.0, 2.0 - 0.01, rt))                  # rear wall
    for t0, t1 in ((pd0, pd0 + AMS_TAB), (pd1 - AMS_TAB, pd1)):                              # the sides are corner tabs only. What
        union(body, boxb(px0 - 1.0, px0, t0, t1, 2.0 - 0.01, rt))                            # is left between them is the passage:
        union(body, boxb(px1, px1 + 1.0, t0, t1, 2.0 - 0.01, rt))                            # bay air crosses under the board, in one
    #   side and out the other, straight beneath the regulator. The floor stays solid - with the chassis flat on the desk a hole
    #   there would open into a dead pocket, and trapped air insulates about three times better than the 2 mm of PLA it replaced.
    cut(body, hs_b((0.0, B_DBAY0, H_FRONT - SKIN - 0.3), (0.0, (H_FRONT - H_REAR) / (B_D1 - B_DBAY0), 1.0)))   # under the sloped skin
    for (x, d) in SHELL_PILLARS:                                                             # shell screws, countersunk from below
        cut(body, cylH(x, d, -1.0, 3.0, 1.7))
        cut(body, coneH(x, d, -0.01, CSK_D / 2, CSK_H, 1.7))
    occ = get_or_make_comp(basec, 'Base chassis')
    return replace_body(occ.component, body, 'Base chassis')

def build_shell(basec, mh):
    """Outer skin: rounded, drafted walls + sloped top, tilted front face continuous with the head's bezel,
    bottom rim floating GAP above the desk. Printed upside down."""
    c, sn = math.cos(math.radians(TILT)), math.sin(math.radians(TILT))
    slope = (H_FRONT - H_REAR) / (B_D1 - B_DBAY0)
    outer = drafted_rrect(B_X0, B_X1, 0.0, B_D1, GAP, H_FRONT, R_PLAN, DRAFT, H_FRONT)
    cut(outer, hs_b((0.0, 0.0, 0.0), (0.0, -c, sn)))                                       # in front of the bezel plane
    cut(outer, hs_b((0.0, B_DBAY0, H_FRONT), (0.0, slope, 1.0)))                            # above the sloped top
    inter(outer, top_chamfer_solid())                                                       # C_TOP chamfer on the top edge
    cavity = rrect_b(B_XI0, B_XI1, SKIN, B_DBAY1, GAP - 6.0, H_FRONT - SKIN, R_CAV)
    cut(cavity, hs_b((0.0, B_DBAY0, H_FRONT - SKIN), (0.0, slope, 1.0)))                    # under the sloped skin
    cut(cavity, hs_b((0.0, SKIN / c, 0.0), (0.0, -c, sn)))                                  # keep the tilted front wall
    cut(outer, cavity)
    for (x, d) in SHELL_PILLARS:
        union(outer, cylH(x, d, 2.0, skin_top(d) - SKIN + 0.5, 3.5))
        cut(outer, cylH(x, d, 1.0, 8.0, 2.0))                                               # M3 heat-set insert from below
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
    occ = get_or_make_comp(basec, 'Base shell')
    return replace_body(occ.component, outer, 'Base shell')

def build_pogo_base(basec, mh):
    b, mags, pads, tails = pg_female_bodies()
    for x in (b, mags, pads, tails): tb.transform(x, mh)
    return add_bodies(basec, 'Pogo female (base)', [('pogo female body', b, 'housing'), ('pogo female magnets', mags, 'silver'),
                                                    ('pogo female pads', pads, 'gold'), ('pogo female tails', tails, 'silver')])

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
# Wiring layer: 'Head wiring (toggle)' (head frame) + 'Base wiring (toggle)' (base frame).
# Wires at their measured size, bent as a wire bends (see wire()), bundled where they travel together, and no
# two through each other. There is no slot between head and base: the head's runs end on the pogo male's solder
# tails and the base's on the female's, and the joint is the connector.
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

def to_e(p):    return (p[0], p[2], -p[1])          # base (X, D, H) -> E (X, H, -D)
def to_b(p):    return (p[0], -p[2], p[1])

def wire_b(points, d=WIRE_D, **kw):
    """wire() along a base-frame polyline (X, D, H); E-frame is (X, H, -D)."""
    return wire([to_e(p) for p in points], d, back=to_b, **kw)

def ribbon(name, pts, e1, cols=QWIIC, pitch=QWIIC_D + 0.1, want=BEND_K * QWIIC_D, lead=(0.0, 0.0), frame='E'):
    """A Qwiic ribbon along polyline pts: its conductors side by side across e1 at pitch, in the standard
    black / red / blue / yellow order (cols names the ones present - a cut conductor is left out - by that order),
    each a parallel offset of the centreline that bends concentrically with it. In the base frame when frame='B'."""
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
    """ribbon() along a base-frame (X, D, H) polyline, lying flat: spread across the first straight, horizontally."""
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

# --- base-frame connector helpers ---
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

# --- head wiring (head frame): where the seven conductors run behind the Inkplate, and how each reaches its tail ---
#   Space behind the board is Z -2.45 (its back) to -9.67 (the cover). Along the bottom edge the AVX bulk capacitor
#   (X 62.5..67, Y 4.17..11.57, down to Z -5.5) sits right over the connector and the ESP32 module (X 75..93, Y to
#   31.5, down to Z -5.9) over the right-hand end, so everything runs in two layers under both: cable 1's ribbon
#   at Z_TOP, the jumpers at Z_BOT, and the run's centreline at Y_RUN.
#   The tails point +Y out of the male's body (Y 1.4) and stop at Y 2.9, in two rows 2.3 mm apart in X and Z. The
#   capacitor leaves only 1.27 mm above the tips of the row nearer the board, so the two ways under it cannot be
#   reached from above at all: each takes a wire that comes in along the FRONT_LANE - between the tail tips, the
#   capacitor and the board - one from each side, and is bent down onto its tail there. The two ways on that row
#   clear of the capacitor take cable 1's SDA and SCL straight down onto the tail, lying along it. The row nearer
#   the cover is reached from behind, on lines at Z_BOT, one wire per line: a wire on a line can only end at the
#   first tail it meets, so each of the three needs its own line, and the three run in from the right, from the
#   same run. That is what fixes PG_TAILS: cable 1 on the row nearer the board, VIN - the one wire that comes
#   from the left - on that row's way under the capacitor, and the three jumpers behind.
Z_TOP, Z_BOT = -7.25, -8.75        # the two layers of the run along the bottom edge, 1.5 apart: 0.85 under the ESP32, 0.27 off the cover
Y_RUN = 7.0                        # the run's centreline, under the capacitor
X_BUNDLE = 96.0                    # where the right-hand group comes down: right of the ESP32, left of the coin cell holder
FRONT_LANE = (3.45, -3.85)         # (Y, Z): 0.07 short of the capacitor, 0.05 in front of the tails, 0.75 off the board
Z_LIE = -5.8                       # a wire lying along a tail of the row nearer the board sits 0.95 behind the tail's centre,
#   in the gap between the rows
Y_TAIL_A, Y_TAIL_B = M_Y4, F_Y4                     # the tail tips: the male's up inside the head's cavity, the
#   female's down inside its plinth. Both parts go in with their wires already soldered on, so what matters is
#   that each run reaches its own tail from a direction a soldering iron could have got to first.

def peel(poly, wants, adds, x_peel, tail, d):
    """A bundle member's polyline cut where its last straight (along X) reaches x_peel, then its own points tail.
    Returns (points, want list, log_add list) for wire()."""
    a, b = poly[-2], poly[-1]
    f = (x_peel - a[0]) / (b[0] - a[0])
    p = (x_peel, a[1] + f * (b[1] - a[1]), a[2] + f * (b[2] - a[2]))
    return (poly[:-1] + [p] + tail, wants[:-1] + [BEND_K * d] * (1 + len(tail)), adds[:-1] + [0.0] * (1 + len(tail)))

def build_head_wiring(headc):
    bodies = []
    ZPCB = -2.45
    blk, pins, zc, ys = ra_header(90.69, 5, 73.73, ZPCB, -1, -1)          # expander row along the top edge, pins down
    bodies += [('Inkplate R/A header GND..P1_3', blk, 'housing'), ('Inkplate header pins', pins, 'silver')]
    bodies.append(('Dupont P1_3 (SET)', dupont(100.85, ys, -1, zc), 'dupont'))
    bodies.append(('Dupont GND', dupont(90.69, ys, -1, zc), 'dupont'))
    blk2, pins2, _, _ = ra_header(44.97, 2, 73.73, ZPCB, -1, -1)          # ESP32-group GND (+3V3 unused): the second ground return
    bodies += [('Inkplate R/A header ESP32 GND', blk2, 'housing'), ('Inkplate header pins ESP32', pins2, 'silver')]
    bodies.append(('Dupont GND2', dupont(44.97, ys, -1, zc), 'dupont'))
    ye = ys - 14.0
    XK3, ZK3 = 100.0, ZPCB - PLUG_T / 2
    bodies.append(('easyC plug (K3)', jst_plug_y(43.83, XK3, ZPCB, +1), 'white'))
    def add(name, pts, col, d=WIRE_D, joint_ends=(False, True), **kw):
        bodies.append((name, wire(pts, d, name=name, joint_ends=joint_ends, **kw), col))
    YF, ZF_ = FRONT_LANE
    def tail_pt(sig, y=2.2):
        tx, tz = pogo_tail(sig); return (tx, y, tz)
    # ---- the right-hand group: SET and GND off the expander row, GND2 off the ESP32 header across the top of the
    #      board, and cable 1 out of easyC K3, come down together ----
    #   Cable 1 leaves its plug pointing up the board and turns back on itself, a loop of the ribbon's own radius
    #   to the left (to the right is the coin cell holder), drops behind the ESP32's depth before it reaches the
    #   module, and rides on the two jumpers along the bottom edge. Each conductor leaves the run at its tail's X.
    rib_c = [(XK3, 45.83, ZK3), (XK3, 51.5, ZK3), (XK3 - 8.0, 51.5, ZK3), (XK3 - 8.0, 46.5, ZK3),
             (XK3 - 8.0, 35.0, Z_TOP), (X_BUNDLE, 16.0, Z_TOP), (X_BUNDLE, Y_RUN, Z_TOP), (50.0, Y_RUN, Z_TOP)]
    cols = ('black', 'blue', 'yellow')                                     # cable 1's red is cut at the plug
    polys, inward = bundle(rib_c, [((QWIIC.index(c) - 1.5) * (QWIIC_D + 0.1), 0.0) for c in cols], (1.0, 0.0, 0.0))
    wants, adds = bundle_wants(rib_c, inward, BEND_K * QWIIC_D, (1.0, 0.0))
    ends = {'black': ('GNDC', 75.0, [(68.5, YF, ZF_), (66.1, YF, ZF_), tail_pt('GNDC')]),      # in along the front lane
            'blue': ('SDA', 61.5, [(61.5, 2.1, Z_LIE)]),                                        # straight down onto the tail
            'yellow': ('SCL', 59.2, [(59.2, 2.1, Z_LIE)])}
    for k, col in enumerate(cols):
        sig, xp, tail = ends[col]
        pts, w, la = peel(polys[k], wants[k], adds[k], xp, tail, QWIIC_D)
        add('wire %s: easyC -> pogo' % sig, pts, col, QWIIC_D, want=w, log_add=la, lead=(1.0, 0.0))
    jmp_c = [(X_BUNDLE, 30.0, Z_BOT), (X_BUNDLE, Y_RUN, Z_BOT), (50.0, Y_RUN, Z_BOT)]
    polys, inward = bundle(jmp_c, [(2.25, 0.0), (0.75, 0.0), (-0.75, 0.0)], (1.0, 0.0, 0.0))
    wants, adds = bundle_wants(jmp_c, inward, BEND_K * WIRE_D)
    #   Three jumpers side by side under the ribbon, GND2 outermost, then GND, then SET: after the corner that is
    #   their order from the edge, and each leaves the run on a 30 deg slant to its own line behind the tails -
    #   the outer one to the near line and the near tail, and so on - so no slant crosses a wire still running.
    #   They start in the opposite order across the board, so on the way to their places every pair crosses,
    #   each at its own depth: GND2 comes across the top of the board from the ESP32 header and slants in at
    #   Z_BOT under both; SET keeps its housing's depth until it is in line; GND rises out of its housing to just
    #   under cable 1's loop, crosses over both - and over the easyC socket, which it clears on the way down - and
    #   comes down last.
    pts, w, la = peel(polys[0], wants[0], adds[0], 73.2, [(68.6, 2.1, Z_BOT), (66.1, 2.1, Z_BOT), tail_pt('GND2', 2.1)], WIRE_D)
    add('wire GND2: ESP32 GND -> pogo', [(44.97, ye, zc), (44.97, 52.5, zc), (88.0, 47.0, Z_BOT), (X_BUNDLE + 2.25, 40.0, Z_BOT)] + pts, 'black',
        want=[BEND_K * WIRE_D] * 4 + w, log_add=[0.0] * 4 + la, lead=(1.0, 0.0))
    pts, w, la = peel(polys[1], wants[1], adds[1], 70.9, [(66.3, 3.6, Z_BOT), (63.8, 3.6, Z_BOT), tail_pt('GND', 2.4)], WIRE_D)
    add('wire GND: expander GND -> pogo', [(90.69, ye, zc), (90.69, 54.5, zc), (96.0, 51.0, -5.1), (102.0, 47.5, -5.1), (100.0, 43.5, -6.4),
                                           (X_BUNDLE + 0.75, 38.0, -7.0)] + pts, 'black',
        want=[BEND_K * WIRE_D] * 6 + w, log_add=[0.0] * 6 + la, lead=(1.0, 0.0))
    pts, w, la = peel(polys[2], wants[2], adds[2], 68.6, [(64.0, 5.1, Z_BOT), (61.5, 5.1, Z_BOT), tail_pt('SET', 2.6)], WIRE_D)
    add('wire SET: P1_3 -> pogo', [(100.85, ye, zc), (100.85, 50.0, zc), (X_BUNDLE - 0.75, 42.0, zc)] + pts, 'white',
        want=[BEND_K * WIRE_D] * 3 + w, log_add=[0.0] * 3 + la, lead=(1.0, 0.0))
    # ---- VIN, the one wire from the left: off its pad, along the front lane and down onto its tail ----
    add('wire VIN: VIN pad -> pogo', [(37.99, 3.03, ZPCB), (37.99, 3.03, ZF_), (44.0, YF, ZF_), (63.8, YF, ZF_), tail_pt('VIN')], 'red',
        joint_ends=(True, True))
    return add_bodies(headc, 'Head wiring (toggle)', bodies)

def build_base_wiring(basec, mh):
    bodies = []
    def jn(sig):
        """Where a wire picks up in the base: on its own solder tail under the pogo connector's base half."""
        x, z = pogo_tail(sig)
        p = head_point(mh, x, Y_TAIL_B + 0.25, z)
        return (round(p.x * 10, 3), round(p.y * 10, 3), round(p.z * 10, 3))
    # ---- the junction: seven wires leave the female's tails in one layer at H_LOW, each in its own X lane, and run
    #      back out of the chamber under the plinth's back wall (roof H 5.5, so one layer is all that fits) into the
    #      trench. There each one turns: the one for the SCD41 to the right, the rest to the left, in order - the
    #      further right a wire's lane, the further back it turns, so its bend passes behind the bends of the wires
    #      to its left and crosses none of their straights. LANE_X is the tail's X nudged sideways, so a wire from
    #      the front row runs between the tails of the back row rather than under one; TURN_D is where each one
    #      turns, D 21.5 / 23.0 the tunnel's two lanes, 26 and up in the bay behind the cradle block. ----
    H_LOW, H_UP = 3.9, 5.6                   # the one layer under the breakout's roof, and the layer above it out in the open
    H_FLOOR = 3.15                           # on the chamber's floor (2.5), where the back-row wires start
    LANE_X = {'SCL': 57.8, 'SDA': 59.3, 'SET': 60.8, 'VIN': 62.3, 'GND': 63.8, 'GNDC': 65.3, 'GND2': 66.8}
    #   1.5 apart. GND2's is the rightmost lane, so that it can turn right across nothing.
    TURN_D = {'SCL': 21.5, 'SDA': 23.0, 'SET': 24.5, 'VIN': 26.0, 'GND': 27.5, 'GNDC': 29.0}
    PASS_X = {'SDA': 59.6, 'VIN': 62.6, 'GNDC': 65.0}
    #   The tails stand in two rows 2.2 mm apart, the back row's tips 0.8 lower, under a body that slopes down
    #   behind them to H 4.7 at D 14.5. A back-row wire meets its tail's tip end-on from below, drops to the
    #   chamber's floor and runs off along it, rising to H_LOW once it is out from under the body. A front-row wire
    #   has that tail and its wire 2.2 mm behind its own: it stays at its tail's height, steps sideways to PASS_X -
    #   midway between two back-row tails - slips between them, under the body and over their wires, and comes
    #   down to H_LOW in its own lane. Body and wires leave it under 0.1 mm the whole way. SCL has no tail behind
    #   it (the empty way) and simply drops.
    def start(sig):
        jx, jd, jh = jn(sig); x = LANE_X[sig]
        if sig in PASS_X:
            xp = PASS_X[sig]
            pts = [(jx, jd, jh), (xp, 11.0, jh - 0.05), (xp, 11.82, 5.05), (xp, 14.0, 4.05), (x, 16.0, H_LOW)]
        elif sig == 'SCL':
            pts = [(jx, jd, jh), (x, jd + 1.7, H_LOW)]
        else:
            pts = [(jx, jd, jh - 0.25), (jx, jd + 0.3, H_FLOOR), (x, 14.5, H_FLOOR), (x, 18.0, H_LOW)]
        return pts + ([(x, TURN_D[sig], H_LOW)] if sig in TURN_D else [])
    def add(name, pts, col, **kw):
        bodies.append((name, wire_b(pts, name=name, joint_ends=(True, False), **kw), col))
    # ---- PMSA003I: straight 7-pin header on its FRONT edge (D 32.54), housings standing up ----
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
    # ---- AMS1117: rotated 180 deg in plan, so the pins face the HEAD and the housings run D 36.5..50.5.
    #      With the pins at the rear, the head's VIN/GND had to travel back to D 78.9 and the regulator's outputs all the
    #      way forward again to the PM header at D 29.5 - about 100 mm of round trip, and two long lanes up the strip,
    #      that this removes. The rotation swaps VIN and GND in X. ----
    hams = AMS_H + 1.4 + 4.5 - 0.32
    ams_x = {'VIN': AMS_X1 - 6.79, 'OUT': AMS_X1 - 4.25, 'GND': AMS_X1 - 1.71}
    for name, x in ams_x.items():
        bodies.append(('Dupont AMS %s' % name, dupont_b(x, AMS_D0, -1, hams), 'dupont'))
    D_IN = AMS_D0 - 14.0 + 0.3                 # open end of the housings, where every wire goes in
    # ---- the four PM wires: along the tunnel in two lanes and two layers, out of the mouth's right-hand end, up
    #      past the right-hand end of the housing row, and into the housings from above. A housing is entered from
    #      the top, so a wire must come down into it, and there is no room to turn back over it from the front:
    #      the head's back cover leans over the header row from that side. So three of them climb behind the
    #      housing row to a lane at H_OVER, run back over the housings, and drop into their own; SET, whose housing
    #      is the last in the row, climbs behind it and hairpins over. ----
    H_OVER = 26.8                            # over the housings (22.1) and over SET's hairpin (crown 25.6); skin at 27.8
    R_OVER = 3.5                             # the bend onto that lane, 2 mm from SET's hairpin: a fuller one would sweep into it
    XE_IN, XE_OUT = 23.6, 25.1               # the two X at which wires leave the tunnel's lanes: between the SET housing and the PM's socket B
    RISE = 0.62                              # the climb out of the mouth: 32 deg, 0.4 over the board's front edge
    def exit_leg(sig, x, d_up):
        dl, hl = TUN_LANES[sig]
        return [(x, dl, hl), (x, d_up, hl + (d_up - dl) * RISE)]
    TUN_LANES = {'SET': (21.5, H_LOW), 'GNDC': (23.0, H_LOW), 'SCL': (21.5, H_UP), 'SDA': (23.0, H_UP)}
    #   (D, H) in the tunnel: the two that turn first, cable 1's SCL and SDA, rise to H_UP in the trench and go in on
    #   top; SET and GNDC turn later, further back, and cross under them to the floor lanes
    # SCL: lower lane, inner; up the inside line behind the row, leaning forward to the outermost over-lane
    x = PM_PINS['SCL']
    pts = start('SCL') + [(52.9, 21.5, H_LOW), (47.4, 21.5, H_UP)] + exit_leg('SCL', XE_IN, 31.0) + [(XE_IN, 31.0, H_OVER), (x, 31.0, H_OVER), (x, d_hdr, h_top - 0.2)]
    add('wire SCL: pogo -> PM SCL', pts, 'yellow', want=[5.2] * (len(pts) - 3) + [R_OVER, 5.2, 5.2])
    # SDA: upper lane, outer; straight up the outside line to the nearest over-lane
    x = PM_PINS['SDA']
    add('wire SDA: pogo -> PM SDA', start('SDA') + [(54.4, 23.0, H_LOW), (48.65, 23.0, H_UP)] + exit_leg('SDA', XE_OUT, 29.5)
        + [(XE_OUT, 29.5, H_OVER), (x, 29.5, H_OVER), (x, d_hdr, h_top - 0.2)], 'blue')
    # SET: floor lane, inner; crosses to it under SDA's lane in the trench. Out of the mouth it slants to its pin's X
    #   behind the housing, climbs, and hairpins over the housing top (the top leg is the housing's own depth from
    #   the climb, so the two bends share it: 3.2 mm each)
    x = PM_PINS['SET']
    d_up = d_hdr + 2 * BEND_FLOOR
    h_hp = h_top - 0.2 + BEND_FLOOR
    add('wire SET: pogo -> PM SET', start('SET') + [(51.3, 24.5, H_LOW), (44.1, 21.5, H_LOW)]
        + exit_leg('SET', XE_IN, d_up) + [(x, d_up, H_LOW + (d_up - 21.5) * RISE + 5.0), (x, d_up, h_hp), (x, d_hdr, h_hp), (x, d_hdr, h_top - 0.2)], 'white')
    # GNDC: turns last, clear of the shell pillar at (68, 30), and crosses to the outer floor lane under the two AMS
    #   wires, which have risen to H_UP by then; out of the mouth it takes the outside line up to the farthest
    #   over-lane and the farthest pin
    x = PM_PINS['GND']
    pts = start('GNDC') + [(52.0, 29.0, H_LOW), (43.4, 23.0, H_LOW)] + exit_leg('GNDC', XE_OUT, 32.5) + [(XE_OUT, 32.5, H_OVER), (x, 32.5, H_OVER), (x, d_hdr, h_top - 0.2)]
    add('wire GNDC: pogo -> PM GND', pts, 'black', want=[5.2] * (len(pts) - 3) + [R_OVER, 5.2, 5.2])
    # ---- head VIN / GND -> AMS IN / GND: along the bay's front under the ribbon, up at the pin's X, straight in ----
    for sig, pin, col, x_rise in (('VIN', 'VIN', 'red', 57.4), ('GND', 'GND', 'black', 58.9)):
        x = ams_x[pin]; dt = TURN_D[sig]
        add('wire %s: pogo -> AMS %s' % (sig, 'IN' if sig == 'VIN' else 'GND'),
            start(sig) + [(x_rise, dt, H_LOW), (x_rise - 5.75, dt, H_UP), (x, dt, H_UP), (x, dt, hams), (x, D_IN, hams)], col, lead=(0.0, 1.0))
    # ---- second ground return: ESP32-group GND -> a straight header on the SCD41, housing standing in the compartment ----
    SCD_HX, SCD_HD = SCD_X1 - 2.0, SCD_D0 + 12.7          # 5-pin header 2 mm in from the board's right edge, GND the middle pin
    H_S = 4.0 + 1.57
    bodies.append(('SCD41 straight header 5-pin', boxb(SCD_HX - 1.27, SCD_HX + 1.27, SCD_HD - 2 * 2.54 - 1.27, SCD_HD + 2 * 2.54 + 1.27, H_S, H_S + 2.54), 'housing'))
    spins = None
    for k in range(-2, 3):
        p = boxb(SCD_HX - 0.32, SCD_HX + 0.32, SCD_HD + 2.54 * k - 0.32, SCD_HD + 2.54 * k + 0.32, H_S + 2.54, H_S + 8.5)
        spins = p if spins is None else union(spins, p)
    bodies.append(('SCD41 header pins', spins, 'silver'))
    s_top = H_S + 2.54 + 14.0
    bodies.append(('Dupont SCD41 GND', boxb(SCD_HX - 1.27, SCD_HX + 1.27, SCD_HD - 1.27, SCD_HD + 1.27, H_S + 2.54, s_top), 'dupont'))
    #   the rightmost lane, so it turns right, crossing nothing: slants to X 72.5 - past the shell pillar at (68, 30) and
    #   inside the compartment's right wall - runs in through the compartment's open front, climbs in front of the
    #   board to H 25.2 (the skin is at 27.9 there) and eases over to the header's X on the way back to it
    H_SCD = 25.2
    add('wire GND2: pogo -> SCD41 GND', start('GND2') + [(LANE_X['GND2'], 20.5, H_LOW), (72.5, 26.2, H_LOW), (72.5, 33.5, H_LOW), (72.5, 33.5, H_SCD),
                                                             (SCD_HX, 40.0, H_SCD), (SCD_HX, SCD_HD, H_SCD), (SCD_HX, SCD_HD, s_top - 0.2)], 'black')
    # ---- AMS OUT -> PM VIN: out of the housing, up to a lane under the skin, forward over the module and down into the housing ----
    xo = ams_x['OUT']
    add('wire 3V3: AMS OUT -> PM VIN', [(xo, D_IN, hams), (xo, 41.5, hams), (xo, 41.5, 25.2), (PM_PINS['VIN'], 41.5, 25.2), (PM_PINS['VIN'], d_hdr, 25.2),
                                        (PM_PINS['VIN'], d_hdr, h_top - 0.2)], 'red', lead=(1.0, 0.0))
    #   (no AMS GND -> PM GND wire any more: the PM's ground comes down cable 1, so the regulator's GND pin has one crimp)
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
    return add_bodies(basec, 'Base wiring (toggle)', bodies)

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
}

def mat(rows):
    m = adsk.core.Matrix3D.create()
    vals = []
    for r in rows: vals += r
    vals += [0, 0, 0, 1]
    vals[3] *= M; vals[7] *= M; vals[11] *= M
    m.setWithArray(vals)
    return m

# rows = 3x4 matrices mapping each model's own frame into the Fusion frame (translation in mm)
HEAD_PLACEMENTS = {     # head frame: X_f = X, Y_f = -Z, Z_f = Y (rotated 180 deg: USB-C on the left, expander row along the top edge)
    'Soldered Inkplate': [[1,0,0,0],[0,0,1,0.85],[0,-1,0,75.23]],
}
BASE_PLACEMENTS = {     # PM on the left with its header at the front
    'Adafruit PMSA003I': [[1,0,0,PM_X0],[0,1,0,PM_D0],[0,0,1,4.0]],       # air face 1 mm from the left wall, header row at the front
    'Adafruit SCD41':    [[0,-1,0,SCD_X1],[1,0,0,SCD_D0],[0,0,1,4.0]],    # vertical in its compartment: sockets face front / rear
    'BME688':            [[1,0,0,82.8],[0,1,0,53.5],[0,0,1,4.0]],         # rear-right
    'SHTC3':             [[1,0,0,82.8],[0,1,0,26.5],[0,0,1,4.0]],         # front-right, coolest corner
    'AMS1117':           [[0,1,0,AMS_X1-8.5],[-1,0,0,AMS_D0+12.5],[0,0,1,AMS_H]],  # rotated 180: pins toward the head (-D), chip underneath
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


BASE_ELEC = 'Base electronics (toggle)'

def base_electronics(basec):
    """The base's boards, pogo female and wiring, in one component: its light bulb leaves the bare chassis and shell.
    Anything an older build left directly in the base moves into it."""
    occ = get_or_make_comp(basec, BASE_ELEC)
    for o in list(basec.occurrences):
        if o.component.name not in ('Base chassis', 'Base shell', BASE_ELEC): o.moveToComponent(occ)
    return occ.component

def parts(top):
    """A top assembly's parts, with the contents of the base's electronics listed in the group's place."""
    for c in top.childOccurrences:
        if c.component.name == BASE_ELEC: yield from c.childOccurrences
        else: yield c

def setup_components(app, des, head, base):
    """Import the Inkplate into the head and the Adafruit boards into the base's electronics (STEP downloads), build
    the Soldered and AMS1117 block-outs, then place everything."""
    headc, elecc = head.component, base_electronics(base.component)
    have = [o.component.name for o in headc.occurrences] + [o.component.name for o in elecc.occurrences]
    d = os.path.join(tempfile.gettempdir(), 'envmon_step'); os.makedirs(d, exist_ok=True)
    im = app.importManager
    targets = {'inkplate5gen2.step': ('Soldered Inkplate', headc), 'pmsa003i.step': ('Adafruit PMSA003I', elecc), 'scd41.step': ('PCB Component', elecc)}
    for fn, url in STEP_URLS.items():
        key, target = targets[fn]
        if any(n.startswith(key) or (n.startswith('Adafruit SCD41') and key == 'PCB Component') for n in have): continue
        p = os.path.join(d, fn)
        if not os.path.exists(p):
            req = urllib.request.Request(url, headers={'User-Agent': 'fusion'})
            with urllib.request.urlopen(req, timeout=180) as r, open(p, 'wb') as f: f.write(r.read())
        opts = im.createSTEPImportOptions(p); opts.isViewFit = False
        im.importToTarget(opts, target)
    for o in elecc.occurrences:
        if o.component.name.startswith('PCB Component'): o.component.name = 'Adafruit SCD41 (5190)'
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
# shader darkens the base colour a long way, so a true black connector or wire loses every edge and shading cue
# against the boards (which are #404040) and reads as one solid blob. 88..105 renders as dark grey on screen.
COLS = {'housing': (88, 88, 88), 'black': (100, 100, 100), 'silver': (205, 205, 210), 'red': (200, 30, 30), 'yellow': (220, 190, 30),
        'white': (240, 240, 235), 'blue': (30, 80, 200), 'purple': (120, 60, 170), 'pcb_blue': (30, 90, 190), 'beige': (226, 208, 170),
        'gold': (216, 176, 70), 'dupont': (105, 105, 105), 'pm_blue': (30, 110, 185)}

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
    base = [a for a in lib.appearances if a.name.startswith('Plastic - Matte (Black)')][0]
    a = des.appearances.addByCopy(base, name)
    for p in a.appearanceProperties:
        cp = adsk.core.ColorProperty.cast(p)
        if cp:
            try: cp.value = adsk.core.Color.create(rgb[0], rgb[1], rgb[2], 255)
            except Exception: pass
    return a

def colour_all(des, app, headc, elecc, wiring):
    def ap(col): return appearance(des, app, 'col ' + col, COLS[col])
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
            if ('WIRING/' in a + b) and 'tails' in a + b: continue        # a wire soldered to a pogo tail touches it
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
PRINTED_PARTS = ('Head tray', 'Head back cover', 'Base chassis', 'Base shell')

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

def printability(app, head, base):
    """Knife edges and thin walls or gaps in the four printed parts, for a 0.4 mm nozzle. Positions are in each
    part's own frame (head X, Y, Z; base X, D, H). 'knives' and 'fail' must be empty."""
    measure = app.measureManager
    out = {}
    for top, is_head in ((head, True), (base, False)):
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


def run(context):
    """Build the whole thing from scratch in an empty design: downloads the reference models, places every board,
    builds the four printed parts and the two wiring layers, then tilts the head into the base."""
    app = adsk.core.Application.get()
    des = adsk.fusion.Design.cast(app.activeProduct)
    root = des.rootComponent
    head = get_or_make_comp(root, 'Head')
    base = get_or_make_comp(root, 'Base')
    for top in (head, base):
        for o in parts(top): clear_fillets(o.component)
    head.transform = adsk.core.Matrix3D.create()
    if des.snapshots.hasPendingSnapshot: des.snapshots.add()
    setup_components(app, des, head, base)
    elec = base_electronics(base.component)          # toggle its light bulb to see the bare chassis and shell
    del BEND_LOG[:]                                 # the module can outlive one run in Fusion's script runner
    mh = head_matrix()
    t  = build_head_tray(head.component)
    c  = build_head_cover(head.component)
    ch = build_chassis(base.component, mh)
    sh = build_shell(base.component, mh)
    w1 = build_head_wiring(head.component)          # toggle these two components' light bulbs to hide the wiring
    w2 = build_base_wiring(elec, mh)
    p1 = build_pogo_head(head.component)            # the two halves of the junction, as bought
    p2 = build_pogo_base(elec, mh)
    refs = build_pogo_ref(root)
    colour_all(des, app, head.component, elec, [w1, w2, p1, p2] + refs)
    fin = {}
    fin.update(finish_shell([o for o in base.component.occurrences if o.component.name == 'Base shell'][0]))
    fin.update(finish_tray([o for o in head.component.occurrences if o.component.name == 'Head tray'][0]))
    head.transform = mh                             # the head is the only tilted assembly
    if des.snapshots.hasPendingSnapshot: des.snapshots.add()
    app.activeViewport.fit()
    lumps = {}
    for top in (head, base):
        for o in top.component.occurrences:
            if o.component.bRepBodies.count == 1 and 'wiring' not in o.component.name:
                lumps[o.component.name] = o.component.bRepBodies.item(0).lumps.count
    print(json.dumps({'lumps_must_all_be_1': lumps, 'inkplate_insertion_blocked_mm3': insertion_sweep(t), 'head tray': bb_mm(t.boundingBox), 'head cover': bb_mm(c.boundingBox),
                      'base chassis': bb_mm(ch.boundingBox), 'base shell': bb_mm(sh.boundingBox),
                      'finish': fin, 'interference': interference(des, root), 'printability': printability(app, head, base),
                      'wiring': wiring_report(root)}))
