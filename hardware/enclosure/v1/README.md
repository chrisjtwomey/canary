# Enclosure

Desk enclosure for the Inkplate 5 Gen2 and the four sensor boards: a thin display head tilted 20° back, standing
in a low sensor base that extends behind it. Rounded plan corners, drafted walls, a continuous shadow gap instead
of grilles, and no fixings visible from any normal angle.
Designed in Fusion (project **Inkplate Env Monitor Enclosure**, design **Env Monitor Enclosure**);
`enclosure.py` regenerates every part, every board placement and the wiring layer from the numbers in this file.

| | |
|---|---|
| `stl/` | The four printed parts, in print orientation, mm. |
| `step/` | The same parts, upright in their own frames (head parts in the head frame, base parts in the base frame). |
| `3mf/` | The same four parts again as 3MF, in print orientation, for slicers that prefer it. |
| `enclosure.py` | Fusion script: downloads the Inkplate / Adafruit STEP models, builds the Soldered and AMS1117 block-outs, places every board, builds the four parts and the two wiring layers, applies the tilt. Run it from Fusion's script editor in an empty design. |

On the desk: **150.7 wide × 87.3 deep × 89.8 tall mm**. Base 30.5 mm tall at the front (flat over the cradle to
D 25), sloping to 25 mm at the rear — the front height is set by the Dupont housings standing on the PMSA003I's
header, see Wiring.

## Shape

It is meant to sit on a desk without announcing itself, which drove the architecture:

- **The sensors live in the base, not behind the display.** That keeps the centre of mass low (below) and lets the
  head be only 14 mm thick.
- **The base is a chassis inside a shell.** The shell is one uninterrupted skin; all four of its screws come up
  from underneath through the chassis, so nothing breaks the top or the sides.
- **The front is one continuous 20° slab.** The head's bezel and the base's front face lie in the same plane with
  only a parting line between them. At the sides the base's walls frame the head, 1.3 mm outside it at the top.
- **Nothing is square.** 10 mm plan radii on the base and 5 mm on the head, a 1.5 mm chamfer round the top edge and
  a 1.2 mm round on the bezel, and 4.3° of draft on the side and rear walls so the base reads as a foot, not a box.
- **The vents are hidden.** A 1.5 mm shadow gap under the whole shell replaces every grille; the only visible
  openings are the PMSA003I's, sunk in a recessed strip on the left wall.

## Stability

Mass is ≈ 280 g (92 g Inkplate, 52 g head shells, 145 g base and boards, PLA+ or PETG at ~1.24 g/cm³ printed near
solid). The centre of mass sits **≈ 27 mm above the desk and 32 mm back** (worked out on the 27 mm base; the extra
3.5 mm of shell moves it by a fraction of a millimetre), and only the chassis touches the desk
(X −7.1…132.4, D 3.5…82.5), so tipping needs ≈ 46° forward, 62° backward or 68° sideways. Keeping the sensors in
the base rather than behind the panel is what buys that margin — carried in the head they would sit 40 mm higher.

## Parts

| Part | Print orientation | Fixings |
|---|---|---|
| **Head tray** | face down | Bezel (2.4 mm lip) and four walls, 14.1 mm deep, 5 mm plan radii, 1.2 mm round on the bezel edge. Left wall 7.3 mm thick, carrying the USB-C, power-button and microSD pockets; right wall 2 mm with the wake-button hole. Relief in the bezel lip for the expander header's solder tails. No vents. |
| **Head back cover** | flat, outside down | 2 mm plate resting on the Inkplate's four 7.2 mm SMT standoffs and screwed to them: 4 × M3 through clearance holes, counterbored 0.7 mm so the heads sit near flush in a 2 mm plate. Nothing screws into the tray — there is nothing in the tray to screw into, see below. One grille band over the ESP32 (8 capsule slots, X 74–94, Y 14–40) — the head's only opening, facing up and back. |
| **Base chassis** | upright (desk face down) | Floor, the solid 20° cradle block with the head pocket, and every bay feature: board bosses, the SCD41 compartment, the SHTC3 baffle, the AMS1117 pocket. It also carries the pogo plinth standing in the trench. Nothing fastens the head: the connector's two Ø5 magnets hold it down and the cradle pocket locates it. |
| **Base shell** | upside down (top skin on the bed) | The visible skin: rounded, drafted walls, the sloped top and a 2 mm front wall under the head, in one piece with no top-side fixings. 4 × M3×8 countersunk up from underneath into heat-set inserts in its internal pillars (×10 bottoms out — the insert ends at 7.7 mm). A Ø4 post holds the AMS1117 module down, and the PMSA003I's seal rib is part of this wall. |

0.4 mm nozzle, 2 mm walls and skin, 2.2 mm slots on a 3.4 mm pitch where slots remain. The shell prints upside
down so its whole outer surface is either on the bed or a drafted wall — no supports; the STL is rotated 5.15° past
the flip so the sloped skin lies flat. Everything is printed in **PLA+**: the only heat in the base
is the AMS1117's few hundred milliwatts, so PETG is the fallback if its pocket or the shell post over it ever
softens (Unverified 10).

**Nothing stands inside the head's cavity, and nothing may.** The Inkplate is 130.59 × 75.23 in a 134.6 × 77.2
opening — 2 mm a side in X, because SW2 and the wake switch stand 0.85 mm past the board's left and right edges,
and 1 mm top and bottom — and it goes in from the back, which means its own footprint sweeps the whole cavity on
the way to its seat. A boss is in the way however far behind
the seated board it finally sits. So the cover screws to the Inkplate's own
standoffs, and the head is held by magnets.

## Fasteners

Four brass heat-set inserts carry the one screwed joint that gets opened: the shell on the chassis. The back cover
screws into the Inkplate's own standoffs, the pogo connector's two magnets hold the head down, and everything else
threads straight into printed plastic.

| Fastener | Qty | Where | Hole |
|---|---|---|---|
| M3 heat-set insert (≈ 5.7 long, 4.6 OD) | 4 | Base shell, internal pillars | Ø 4.0 × 6.0 deep |
| M3 × 8 countersunk, 90° | 4 | Shell → chassis, up from underneath | Ø 3.4 clearance, Ø 6.2 × 1.4 cone |
| M3 × 6 machine screw | 4 | Head back cover → the Inkplate's four SMT standoffs | Ø 3.4 clearance, Ø 6.2 × 0.7 counterbore |
| M2 × 4 self-tapping, pan head | 8 | PMSA003I and SCD41, 4 each | Ø 2.1 pilot, 3 mm deep |
| M2.5 × 4 self-tapping | 8 | BME688 and SHTC3, 4 each | Ø 2.6 pilot, 3 mm deep |

- Board pilots are blind, in 2 mm bosses on the chassis floor: 3 mm of engagement with 1 mm of floor left under
  them, so no screw breaks the desk face. Two screws per sensor board carry a few grams comfortably; all four holes
  are there if wanted.
- **Board screws are one nominal size under their pilot** *(measured on a PLA+ print)*, for two separate
  reasons. The PMSA003I's board holes are 2.5 mm, so an M2.5 screw cannot pass through one — M2 is the only option
  there, and the SCD41 takes the same screw for consistency though its 3.0 mm holes would also accept M2.5. The
  Soldered boards' 3.2 mm holes would pass M3 happily; what rules M3 out is the printed pilot, since Ø 2.6 nominal
  finishes nearer 2.4 on an FDM print and a thread-former that tight in PLA+ splits the boss. Do not re-cut the
  pilots to suit the smaller screws: they are sized for how the hole prints, not for how it reads in CAD.
- Every self-tapper is sized to stop **short of the blind end of its pilot**, not to fill the material: a tapered
  tip driven into the last millimetre wedges the boss open. A 1.57 mm board plus 3 mm of pilot leaves 4.6 mm,
  hence 4 mm screws and 2.4 mm of engagement — short of the usual 2 × diameter, but these are five-gram boards.
- The shell screw stops at 8 mm: its insert ends at 7.7, so an M3 × 10 bottoms out.
- The cover's counterbore leaves 1.3 mm of plate under each screw head, so an M3 × 6 puts about 4.7 mm of thread
  into the 7.2 mm standoff.
- Self-tapping into PLA or PETG holds fine for a one-time build. If boards will come in and out repeatedly, those
  pilots strip after a handful of cycles and want inserts instead — which means taller, wider bosses.

## Frames

**Head frame**: X left → right seen from the front (the Inkplate PCB spans 0…130.59), Y up (PCB 0…75.23), Z
toward the viewer with Z = 0 at the panel's front face. In Fusion, X_f = X, Y_f = −Z, Z_f = Y. Z levels: bezel
front +2.4 · panel 0 · PCB back −2.45 · standoff tops / cover inner −9.67 · cover outer −11.67.

**Base frame**: X as the head, D = depth from the front-bottom edge (0…86 nominal, 87.9 including the draft),
H = height above the desk. This is Fusion's world frame; the `Base` component is untilted and the `Head`
component carries the 20° tilt. Bay interior X −8.6…133.9, D 25…84, H 2 up to the skin's underside (28.5 at D 25,
sloping to 23 at the rear). Board component faces at H 5.6 (Adafruit / Soldered) and 6.0 (AMS1117, raised so the
regulator on its underside hangs in free air).

The head's front-bottom edge lands at D 4.91 / H 13.5, chosen so the **bezel plane passes through (D 0, H 0)** —
that is what makes the base's front face and the bezel one plane. Change `HEAD_FRONT_H` and the front slab
follows automatically.

## Surfacing rules

- **Plan corners** are built into the solid, not filleted: the shell's outer prism is four truncated cones
  (r 10 mm at the top, growing with the draft) plus two tilted-plane slabs. The cavity uses r 8 and the chassis
  r 6.5 about *the same centres*, so the wall stays 2 mm and the chassis-to-shell gap stays 1.5 mm all the way
  round the corner.
- **Draft** 4.3° on the sides and rear, referenced to the top of the walls: 2.0 mm wider at the desk than at the
  top, where the shell stands 1.3 mm outside the head's sides. The front (bezel) plane and the cavity are not
  drafted. Flush with the head, the draft would carry the side walls out past its vertical sides to a knife edge;
  1.3 mm out, the wall beside the head is 0.8 mm at the top of the walls and thickens down the draft.
- **The top chamfer is also solid geometry.** A 2 mm skin cannot carry a fillet larger than 1.17 mm — the arc
  breaks through into the cavity at the corner — whereas a 45° chamfer of leg *c* only eats (4 − c)/√2, so 1.5 mm
  is comfortable. It is made by intersecting the shell with a 45°-drafted prism whose reference plane is rotated
  onto the sloped top, which also wraps it around the rounded corners. Fusion's own chamfer feature fails here
  (`ASM_BL_UNFIN_SHEET`) because the chain runs out onto the head opening's curved wall.
- Only two rounds are real features: the bezel's outer edge (1.2 mm, limited the same way by the 2 mm wall and
  2.4 mm lip) and the shell's bottom rim (0.8 mm chamfer). Both are picked geometrically, so the script re-runs.

## Ventilation

There are no grilles on the top, the right side, the rear or the head.

- **Shadow gap.** The shell's bottom rim floats 1.5 mm above the desk and the chassis is inset 1.5 mm from the
  shell's inner wall, so the gap is not decorative: room air passes under the rim, up the slot between chassis
  and shell, and into the bay. Open area ≈ 390 mm² along the bay's sides and rear.
- **PMSA003I.** The fan needs its own path and cannot use the gap: its inlet and outlet are both on the face
  against the left wall, 8 mm above the gap and up to 40 mm away. So that wall keeps two real slot groups
  (D 41.4–54.5 for the outlet, D 58.4–78 for the inlet), sunk in a 1 mm recessed strip so they read as one
  detail rather than a grille. A 4.6 mm rib on the shell's inner wall (D 54.8–58.1, H 1.5–19) crosses the 4.8 mm
  gap between that wall and the module's face, between the two slot groups, so exhaust cannot run along it into
  the inlet. It is on the shell, not the chassis: the chassis is inset 1.5 mm from this wall and could only reach
  it as a detached island. The 3.1 mm of rib that reaches over the chassis floor starts 0.2 mm above it, so the
  shell still drops on freely.
- **SCD41** breathes through its compartment's open front (≈ 500 mm² facing the bay) rather than a lid grille.
  If its response turns out sluggish, the fix is a slot row low in the compartment's left wall — see Unverified.
- **Head.** Sealed except for one grille band in the back cover: 8 stadium slots, 2.2 × 20 mm on the usual 3.4 mm
  pitch, X 74–94 and Y 14–40, ≈ 344 mm². They sit over the **ESP32-WROVER** (X 75–93, Y −0.2–31.8), which at
  80–150 mA with Wi-Fi up is the only real heat source in the head and sits directly behind the panel. The slots run
  **along X**: everything else about this object is horizontal — the shadow gap, the PM's vent strip — and vertical
  ticks cut across all of it. One band spanning low to high also vents better than two discrete ones, since the 20°
  tilt makes the bottom rows the intake and the top rows the exhaust. Y 14 is the lower limit: the head's five wires
  cross the board at Y 3–11 and would otherwise show through.

## Bay layout

Each board's place follows the placement rules in its section of [HARDWARE.md](../../../docs/HARDWARE.md)
(§2–§5):

- **SHTC3**: at a corner or edge, in the incoming airflow, slit-isolated from any mounting plate, nowhere near the
  Inkplate's LDO, PMIC or ESP32 or the PM fan's exhaust. It sets the reading everyone sees.
- **PMSA003I**: inlet and outlet against an enclosure wall or separated by a baffle; enclosure vent no smaller than
  the inlet; ≥ 20 cm off the floor; its exhaust pointed away from the SHTC3 and SCD41.
- **SCD41**: its own compartment with a large opening, small dead volume, out of the direct airflow, lowest point
  of the device, away from the fan and the Inkplate's warm parts. Membrane untouched.
- **BME688**: anywhere with air access; its heater is a heat source for the others, so not adjacent to the SHTC3.
- **Inkplate**: the ESP32, LDO and panel PMIC are the warmest parts; the sensors go on the opposite side or in a
  ventilated bay.
- Vent the sensor bay on two sides so air moves through rather than pooling.

| Board | X × D (mm) | Placement |
|---|---|---|
| PMSA003I | −3.8…31.8 × 27…77.8 | Left end, module face 4.8 mm from the left wall and its vents. X −3.8 puts the board edge and its two left bosses 3.3 mm inside the edge of the chassis floor (which is inset 1.5 mm from the wall). Header row along its **front** edge, so the tall Dupont housings stand behind the head where the base is deepest. D 27 (not 30) keeps its rear corner clear of the cavity's 10 mm rounded corner. |
| SCD41 | 49.9…72.8 × 35…60.4, sockets facing front and rear | Middle, in its own compartment (walls X 47.3–48.8 and 74.3–75.8 from D 30, rear wall D 72–73.5, all to the skin). Both sockets in use. A 5-pin straight header on its right-hand edge (X 70.8; VIN · 3Vo · GND · SCL · SDA along D 42.6–52.8) carries one standing Dupont housing, on GND, for the second ground return. |
| SHTC3 | 82.8…120.8 × 26.5…48.5 | Front-right: coolest corner, against the solid cradle block, farthest from the fan and the LDO, behind a full-height baffle at D 50–51.5. End of the chain, only its right socket used. |
| BME688 | 82.8…120.8 × 53.5…75.5 | Rear-right, behind the baffle. Both sockets in use. |
| AMS1117-3.3 | 35.3…43.8 × 61…73.5, **pins toward the head** | Centred in the strip between the PM board (X 31.8) and the SCD41 compartment wall (47.3). No mounting holes: it sits in a pocket 0.5 mm clear of the board on every side (9.5 × 13.5 in plan; 0.3 mm a side would give a 9.1 mm slot, too tight to trust an FDM print with), front and rear walls 1 mm thick to H 8, the sides only 2.5 mm corner tabs so the underside is open to the strip. The board rests on a pad under its two solder domes at the front (top H 4.8; the domes stand 1.2 mm proud) and on two solid corners at the rear either side of the SOT-223 (to H 6.0, the PCB's underside), so the regulator hangs in a 2.3 mm air passage open at both sides — no floor slots, nothing to bridge. A Ø4 shell post at (39.55, 66), on the board's centreline between the two supports, holds it down with 0.15 mm of preload (until the shell is on, the module is loose); a 3 mm cone at the post's root keeps it printable upside down. Dupont housings on its three pins run **forward**, D 47.3–61. |

The four shell pillars sit at (68, 30), (125, 30), (50, 77.5) and (125, 76) — plan positions clear of every board,
plug, ribbon and wire lane, **and far enough in from the chassis edge for the countersink on the underside to keep
a full wall outside it**. The corner is the trap: the chassis corner is r 6.5, so out there the edge curves away
on two sides at once and the *further into the corner the hole goes, the worse it gets*. The useful position is
near the corner arc's centre (125.9, 76), not near the corner itself. Each hole keeps **≥ 1.7 mm** of wall, and
each is limited by the thing it sits beside: 0.7 mm of drop-on clearance to the SHTC3, 0.5 mm to the SCD41
compartment's rear wall, 0.7 mm to the BME688. The countersink is Ø6.2 × 1.4 deep at 90°: an ISO 7046 M3 head is
5.5 across (5.6 max), so a Ø6.6 cone would give away 0.4 mm of wall for nothing, and the smaller cone leaves
0.6 mm rather than 0.4 of floor above it.

The left third of the shell has no pillar (the PM board leaves 6 mm at the rear and 2 mm at the front, and a
pillar needs 9); it is held by the skin and located by the cradle block.

## Wiring and headers

Follows the wiring table in [HARDWARE.md §8](../../../docs/HARDWARE.md#8-wiring). Two Fusion components hold every header,
plug, Dupont housing and wire as separate coloured bodies — **Head wiring (toggle)** and **Base wiring
(toggle)**; switch their light bulbs off to hide the lot. Wires are drawn schematically, right-angle bends only,
each in a dedicated channel, so the model documents where cables are meant to run rather than how they sag.
Colours: red 3V3 / VIN, black GND, blue SDA, yellow SCL, white SET. Qwiic cables are 4 mm ribbons in the standard
black / red / blue / yellow order with white plugs; the boards' JST-SH sockets are beige. A mated plug is drawn
standing 2 mm proud of its socket, which is what the real ones do — the housing disappears inside the socket —
so the space to leave at a socket is whatever the cable needs to turn — about 6 mm is comfortable
*(measured)* — not the length of a loose plug. Everything nominally
black is drawn as a mid grey instead — Dupont housings #696969, header shrouds #585858, the GND wire #646464:
these appearances copy Fusion's matte-black plastic, whose shader darkens the base colour so far that a true
black housing or wire loses every edge and reads as one solid blob against the boards. The Adafruit boards' bare
PCBs reuse the Inkplate STEP model's own IC appearance
(`Opaque(64,64,64)`, #404040) rather than pure black, so every board reads as one family under the same light.
That grey carries every IC in the model: the Soldered boards' sensor and regulator block-outs take it too, and so
does the PMSA003I's fan cover, so the only colours left are the ones that mean something — purple and grey PCBs,
beige JST-SH sockets, and the Plantower module's blue shell.

**Head.** The back cover sits on the Inkplate's own 7.2 mm standoffs, so the space behind the board is 7.2 mm
and a straight header will not fit. Two **right-angle headers** with pins pointing down the board and flat Dupont
housings: a 5-pin on the expander row (P1_3 · P1_2 · P1_1 · 3V3 · GND, along the **top** edge at X 90.7–100.9 once
the board is rotated) with housings on P1_3 (SET) and GND (the AMS1117's reference), and a 2-pin on the ESP32
group's GND · 3V3 at X 45–47.5 with a housing on GND — the second ground return, to the SCD41. Both 5.5 mm tall,
1.7 mm clear of the cover. All the header pads are 0.8 mm drills, so use round machined-pin headers or solder the
wires straight to the pads. Cable 1 plugs into easyC K3 with its red conductor cut; its black, blue and yellow run
on as three wires. With VIN from its pad that is **seven conductors** leaving the head, in two lanes behind the
board (Z −7.4 for SET, expander GND and ESP32 GND; Z −8.7 for VIN, cable 1's GND, SCL and SDA — clear of the
ESP32), running along the bottom edge at Y 3–12.5. They do not leave the head as wires: they end on the solder
tails of the pogo male, let into the bottom wall at X 62.65. Each run first gets clear of the **AVX bulk
capacitor** — it stands 7.89 mm off the board at X 62.5–67, deeper than either lane and directly over the
connector — dropping to Y 2.05 or 2.70 at X 70 coming from the right, X 56 from the left, and making the last hop
underneath it, where nothing else in that corner reaches past Z −2.6. The connector's stadium hole is the only
thing that pierces the head.

**The junction.** Head and base meet on an **8-pin magnetic pogo pair**, centred on the device at X 62.65.
Both halves are panel-mount parts fixed by their lips, each fitted from inside its own shell. The male's nose
fills the head's 2 mm bottom wall and stands 0.30 mm proud of the underside; its lip is glued to the cavity floor
between two locating ribs, and its back band and tails are in open cavity. The female drops into a plinth standing
in the base's trench, its lip landing on a ledge with a glue relief inside the rim, and only its 1 mm boss stands
above the plinth's rim. That boss enters the male's pocket, so the halves nest: the mated bodies come to 9.3 mm,
not 10.3. The key is the contact block's own outline — a rounded rectangle with one semicircle cut into the middle
of its S-end wall — so a half turned end for end fouls it and will not close. The plinth is open at the front
above the ledge; the shell's front wall closes it, 0.9 mm off the lip.

The seven conductors use seven of its eight pins. The connector is rated 1 A and its listing gives no per-pin
figure, so each pin is taken as good for 1 A. The two heavy pins are VIN (220 mA typical, 475 mA peak) and cable
1's GND, the return for all four sensors (215 mA typical, 470 mA peak, less whatever the SCD41's second return
takes); the other five carry a few milliamps or less. Nor does the listing give a contact resistance:
[HARDWARE.md §8](../../../docs/HARDWARE.md#8-wiring) carries it into the voltage-drop estimate as an assumption.

Assembly order matters. **Fit the Inkplate before the connector**: the male's back band sits at the board's bottom
edge, and with the connector already in, the board cannot pass it. Solder all seven wires to each half on the
bench, then fit.

**Base.** The wires pick up on the female's tails, in a chamber under it that breaks out through the plinth's back
into the trench (X 42–84, D 9.5–26, floor at H 3 — a well around the plinth with about 4 mm of working room each
side, open at the top once the head is off). Each drops to H 3.9 only for the few millimetres it takes to get out
from under the connector, runs back to D 19, climbs to **H 7**, and crosses the bay up there rather than along the
floor. From D 25.8 — behind the plinth, which ends about D 20, and behind the head's back cover, which leans to
about D 24.2 at the top lane's height — they go three ways:

- **To the PM header** (cable 1's GND, SCL and SDA, and the expander's SET): across at H 7 to the pin's X, up
  there to the **H 25.2 lane** just under the skin, then back to the header row and down into the top of a
  standing housing. The PM's **straight** 7-pin header is on its front edge at D 29.5 with five housings on it
  (VIN, GND, SCL, SDA, SET; tops at H 22.1). A housing is 14 mm tall and the wire needs ~3.7 mm above it to turn
  without strain — **17.7 mm clear above the header block** *(measured on the real parts)* — which is
  what makes the base 30.5 mm tall at the front; the skin's underside there is at 28.5, 2.7 mm above the wire
  crowns.
- **To the AMS1117** (VIN and the expander GND): stay at H 7, cross to the pin's X, run back to D 31 and D 29, and
  rise to H 11.6 into the open ends of the IN / GND housings at D 47.3. AMS **OUT** leaves its housing the same
  way, forward to D 42, up to the H 25.2 lane, across and forward into the PM's VIN housing. There is no AMS GND →
  PM GND wire: the PM's ground comes down cable 1, so the regulator's GND pin carries one crimp (star
  grounding, [HARDWARE.md §8](../../../docs/HARDWARE.md#8-wiring)).
- **To the SCD41** (the ESP32-group GND): crosses at H 7 to X 73 — clear of the shell pillar at (68, 30) — rises
  there to the H 25.2 lane, runs back along the compartment's right wall to D 47.7, and drops into a housing
  standing on a **5-pin straight header on the SCD41's right-hand edge** (X 70.8, GND the middle pin; housing top
  at H 22.1, 4.3 mm under the skin there). Which edge of the Adafruit board actually carries the
  row is unverified — see below.

The AMS1117 module is **rotated 180° from the obvious orientation so its pins face the head**. With the pins at the
rear the head's two power wires would travel to D 78.9 and the regulator's outputs all the way forward again to
D 29.5 — about 100 mm of round trip, plus two long lanes up the strip and a jog around the pocket. Pins at X 37.0 (IN), 39.55 (OUT) and 42.1 (GND), housings running forward D 47.3–61. The board sits as far
back as it does — rear edge flush with the SCD41 compartment's rear wall — because the housings project 14 mm
forward of it. Any further forward and they foul the PM → SCD41 ribbon, which crosses the strip at D 25.5–37.9 on
its way to the compartment.

**Qwiic chain**: PM (socket B) → SCD41 front → SCD41 rear → BME688 left → BME688 right → SHTC3 right —
i.e. PM, SCD41, BME688, SHTC3, the order in the wiring table. The PM's socket A faces the left wall 5.2 mm away,
where no plug fits, so the bus reaches that board on its header instead. All three are stock cables: 45 mm
PM → SCD41, 30 mm SCD41 → BME688, 40–45 mm BME688 → SHTC3. Ribbons stay at board height (H 7.1): the PM ribbon
runs down the lane at X 45.05 and along the bay's front into the compartment; the SCD41 → BME688 ribbon leaves
through a notch in the compartment's right wall (D 60.1–68.9); the BME688 → SHTC3 ribbon runs up the right-hand
lane at X 126 through a notch in the baffle (X 119.7–128.5).

Both notches are **8.8 × 6 mm — a JST-SH plug is 6.8 × 2.7, and it has to be threaded through them**, so each one
is the plug plus a millimetre a side. Size them from the plug, not the ribbon. The right-hand lane sits at X 126
rather than hard against the chassis edge, with a **guide rib at X 128.5–132.4, 7 mm tall, from D 35 to 67**: at
129.1 the ribbon would overhang the edge of the chassis with only the shell's inner wall to hold it in, so it
would have to be stuffed in as the lid came down and would spring out every time the lid came off. The rib is that
wall, and the shell drops on without touching the cable. Thread the loose plug down the lane at X 123–125, inboard of
the rib, then let the ribbon settle against it.

## Display window

The ED052TC4 STEP model carries the active area as a 0.04 mm recess on its front face: 114.56 × 64.44 mm, in the
rotated frame at X 5.35–119.91, Y 5.39–69.84. The window is that plus 0.8 mm, with a 1 × 1 mm step outside. The
Inkplate is mounted rotated 180° from the STEP model's own orientation so USB-C, the power button and microSD exit
the **left** wall; the thick wall is on that side, keeping the visible bezel symmetric (13.9 mm each side, 7.6 mm
top and bottom).

## Sensor board models

`enclosure.py` downloads three vendor models:

| Model | Source |
|---|---|
| Inkplate 5 Gen2 board | [Soldered's hardware repo](https://github.com/SolderedElectronics/Soldered-Inkplate-5-Gen2-hardware-design), `OUTPUTS/V1.1.0/Soldered Inkplate 5 Gen2 3D.step` (31 MB). In the export the panel model sits at the origin; move it after a manual import. |
| Adafruit PMSA003I (4632), with the Plantower module | [Adafruit_CAD_Parts, `4632 PMSA003I`](https://github.com/adafruit/Adafruit_CAD_Parts/tree/main/4632%20PMSA003I) |
| Adafruit SCD41 (5190) | [Adafruit_CAD_Parts, `5187 SCD-40 C02 Sensor`](https://github.com/adafruit/Adafruit_CAD_Parts/tree/main/5187%20SCD-40%20C02%20Sensor). The 5187 and 5190 share one PCB. |

Soldered publishes no model for its two boards, so the SHTC3 (333032) and BME688 (333203) are built from the
docs.soldered.com pinout drawings and checked with calipers: 38.0 × 22.0 mm, 2 mm corner
radius, four Ø3.2 holes inset 3.05 mm (32 × 16 mm pitch), JST-SH sockets 0.5–5.5 mm in from each short edge and
centred on it, a 4-pin 2.54 mm header 1.6 mm from one long edge, 1.6 mm PCB, 3.0 mm sockets, 1.1 mm regulator.
The AMS1117-3.3 module is from caliper measurements: PCB 12.5 × 8.5 × 1.4 mm, no mounting holes, SOT-223 on the
underside 1.7 mm tall, a 3-pin right-angle header on the other face with a 6.9 mm overall stack and pins reaching
7 mm past the short edge.

## Printing check

Every part is one connected solid — verified in Fusion (`lumps == 1`) and again from the exported STLs. This is
worth re-checking after any edit to `enclosure.py`: because the parts are built by unioning primitives, a boss or
rib whose position drifts clear of the body it should touch silently becomes a second lump in the same body, and
the slicer will just plate it as a loose part with no indication of where it goes.

The head has a second check for the same reason. `enclosure.py` sweeps the Inkplate's footprint from the cavity
mouth to its seated position, intersects that with the tray, and reports the result as
`inkplate_insertion_blocked_mm3`. It must be **0**.

## Unverified

1. **Everything about how it looks and feels** is unverified until it is printed — the shape is a judgement no render settles. Print the shell first: it is the only part whose surface is on show.
2. Active-area offset — from the panel's STEP; with the board rotated the narrow border should be on the left (USB-C) side. Check on the real panel before printing the head tray.
3. The shadow gap doubles as a dust path. If it collects, a 1 mm tongue on the chassis edge inside the gap would baffle it without closing the air path.
4. SCD41 response time: it vents into the bay, not through a lid grille of its own.
5. Dupont housings are modelled as 2.54 × 2.54 × 14 mm single-position shells (14 mm measured, plus 3.7 mm for the wire to turn — the base height follows from that); right-angle headers with the pin axis 4.2 mm off the board. Check the 1.7 mm margin to the head's back cover with the real housings before soldering the Inkplate headers.
6. The Inkplate's expander pads are 0.8 mm drills (from the KiCad board): confirm the chosen header's pins fit, otherwise solder the two wires straight to the pads.
7. The head sits 8 mm deep in the cradle pocket with 0.5 mm side clearance, located by the pocket and the block's rear lip and held down by the pogo connector's two Ø5 magnets — nothing is screwed. A ≈145 g head on a 20° lean is the thing to watch; if it creeps or lifts too easily the cure is a catch on the rear lip, not screws back through the cavity.
8. The shell's left end is unsupported over ≈ 50 mm. If it lifts, the cure is a printed clip on the chassis edge rather than a fifth screw — there is no room for one past the PM board.
9. The SCD41's header is modelled on the board's right-hand edge (X 70.8) as it sits in its compartment. Confirm which edge of the Adafruit 5190 carries the five pads before soldering; on the left-hand edge the ESP32-GND wire would come straight down the compartment's front instead of round its right wall, and the compartment has the room either way.
10. PLA+ through a winter. The two places heat could tell are the AMS1117's pocket walls and the shell post over it; check them after the first warm spell, and go to PETG for the base if they have moved.

## Decision Log

Dated findings and decisions behind the text above, oldest first.

- **2026-09-12**: on a PLA+ print, the board screws held one size under their pilots: M2 in the 2.1 mm pilots of
  the Adafruit boards, M2.5 in the 2.6 mm pilots of the Soldered ones. A mated JST-SH plug stands about 2 mm proud
  of its socket, and about 6 mm is comfortable for the cable to turn.
- **2026-09-13**, after the first print:
  - Three shell pillars sat at (126, 30), (50, 78.5) and (126, 79), which left 0.8, 0.7 and −0.6 mm of material
    outside the countersink; the last one broke clean out through the rounded corner. They moved in to keep
    ≥ 1.7 mm, and the countersink went from the Ø6.6 first drawn to Ø6.2.
  - The ESP32 grille moved from X 104–124 to X 74–94. At 104–124 it sat on the CR2032 holder (X 106–122), left over
    from rotating the Inkplate 180°, and vented the one part of the board that makes no heat.
  - The AMS1117 pocket went from 0.3 mm a side, a 9.1 mm slot, to 0.5 mm.
  - The PMSA003I board moved from X −5.3, where its two left bosses overhung the chassis floor, to X −3.8.
  - The right-hand ribbon lane moved in from X 129.1 to X 126, behind a guide rib. At 129.1 the ribbon overhung the
    chassis, had to be stuffed in as the shell came down, and sprang out every time it came off.
  - The lumps check caught two strays: the PM seal rib, built at X −6.1…−5.3 after the chassis had been trimmed to
    X ≥ −4.8, and the four head-cover bosses, floating 0.5 mm clear of the cavity wall through several revisions
    of the head.
  - A standing Dupont housing and its wire were measured at 17.7 mm above the header, which set the base at
    30.5 mm tall at the front. Everything is printed in PLA+ from here.
- **2026-09-14**: the first printed head could not be assembled. Four cover-boss towers and two base-screw blocks
  stood in the cavity that the Inkplate sweeps on its way in. All six went: the cover screws to the Inkplate's
  standoffs, and an 8-pin magnetic pogo connector holds the head down and carries the head-to-base wiring.
  `enclosure.py` reports the swept volume as `inkplate_insertion_blocked_mm3`; it would have read several hundred
  on the printed head.
- **2026-09-15**:
  - Fitting the Inkplate into the printed head broke off SW2 (power) and the wake switch. Both stand 0.85 mm past
    the board's edges, and the cavity was 1 mm clear of the board: 0.15 mm for the switches, less whatever the print
    took. The cavity went to 2 mm a side in X, and the head 1 mm wider each side with it.
  - The printed shell was tight as well. The base went 1 mm wider each side to stay flush with the head, the chassis
    with it, and the clearance round the head in the cradle pocket and the shell's opening went from 0.3 to 0.5 mm.
  - The switches stay pin-operated. SW2 and the wake switch sit 1.15 mm behind the wall's inner face, behind an
    8 × 4.7 mm hole in the left wall's inner skin and an 8 × 4.2 mm hole through the right wall, and a finger did not
    reach them on the print even at 0.15 mm. Kept in reserve: a printed plunger in each hole, with a flange inside
    the wall to keep it and a head to press, fitted before the Inkplate goes in. On the current board SW2 is
    bypassed (R34 bridged), so the wake switch would get one first.
  - The shell had no front wall above H 5.5. The two cuts meant to leave it 2 mm thick had the offset in X, which a
    plane tilted about X ignores, so the front was a 1 mm wedge that bent easily, with the cradle block showing above
    it. The wall is now 2 mm from the rim to the head, and the cradle block stands CH_FRONT (0.3 mm) behind it. The
    pogo plinth opens to the front above its ledge, since its front wall would have been 0.4 mm.
  - The side walls ended beside the head in a 4.3° knife edge: flush with the head at the top of the walls, the
    draft carried them out past its vertical sides. The base is now 1.3 mm wider each side than the head, so the
    walls frame it with 0.8 mm at the top, more below. Kept in reserve: stop the side walls behind the head, with a
    2 mm shoulder round its bottom corners; or drop the side draft, so the head is flush with the base's sides the
    full height and the base looks boxier.
  - The two front shell pillars stood 0.55 mm into the clearance behind the head and left a 0.23 mm sliver at their
    tops: the head opening was cut before they were added. It is cut after them now.
