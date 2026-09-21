# The enclosure

Desk enclosure for the Inkplate 5 Gen2 and the four sensor boards: a thin display head tilted 20° back, standing
in a low sensor dock that extends behind it. Rounded plan corners, drafted walls, a continuous shadow gap instead
of grilles, and no fixings visible from any normal angle.
Designed in Fusion (project **CANARY**, design **CANARY**); `enclosure.py` regenerates every part, every board
placement and the wiring layers from the numbers in this file. [assembly.md](assembly.md) builds it, and
[bom.md](bom.md) lists what goes in it.

The four enclosure parts print in **PLA+ with a 0.4 mm nozzle**; `logo` and `logo-stencil` need the **0.2 mm
nozzle** and go on their own plate, the logo in white.

On the desk: **150.7 wide × 87.3 deep × 89.8 tall mm**. The dock's top is one plane, 33.9 mm tall at the front
edge and 25 mm at the rear, 5.15°. The rear is set by the TinyS3's USB-C under the skin; over the PMSA003I's
header the Dupont housings and the wires arcing over them have 1.4 mm to spare, see
[assembly.md](assembly.md#8-wire-the-dock).

## Working on the model

`enclosure.py` is the design. The Fusion document is not in this repository: the script builds the whole thing in
an empty design, and downloads the Inkplate, Adafruit and pogo STEP models it places. Fusion's own copy holds the
saved milestones.

- Run it from **Fusion's script editor**: Utilities → Scripts and Add-Ins → the green **+** beside "My Scripts",
  pick the file, then Run. A full run takes a few minutes and needs a network connection the first time, for the
  STEP downloads.
- It is **re-runnable**. Every part is rebuilt from scratch each time, and components are reused by name, so
  nothing is duplicated. Edges rounded by Fusion features are found geometrically, not by index.
- The report it prints at the end is the check: `lumps_must_all_be_1` (each printed part is one solid),
  `inkplate_insertion_blocked_mm3` (the board can still go in), `cover_pullout_blocked_mm3` (the cover cannot
  drop out of the tray), `interference`, `printability` and `wiring`. The pull-out figure must be more than 0.
  All the others must be empty or 0: a part that touches another lands on it, it does not overlap it.
- **Exports** are made in a second step, never in the same run as the build: the transformed bodies first, the
  export calls after, or Fusion writes empty files.

## Shape

It is meant to sit on a desk without announcing itself, which drove the architecture:

- **The sensors live in the dock, not behind the display.** That keeps the centre of mass low (below) and lets the
  head be only 14 mm thick.
- **The dock is a chassis inside a shell.** The shell is one uninterrupted skin; all four of its screws come up
  from underneath through the chassis, so nothing breaks the top or the sides.
- **The front is one continuous 20° slab.** The head's bezel and the dock's front face lie in the same plane with
  only a parting line between them. At the sides the dock's walls frame the head, 1.3 mm outside it at the top.
- **Nothing is square.** 10 mm plan radii on the dock and 5 mm on the head, a 1.5 mm chamfer round the top edge and
  a 1.2 mm round on the bezel, and 4.3° of draft on the side and rear walls so the dock reads as a foot, not a box.
- **The vents are hidden.** A 1.5 mm shadow gap under the whole shell replaces every grille; the only visible
  openings are the PMSA003I's, sunk in a recessed strip on the left wall.

## Stability

Mass is ≈ 280 g (92 g Inkplate, 52 g head shells, 145 g dock and boards, PLA+ or PETG at ~1.24 g/cm³ printed near
solid). The centre of mass sits **≈ 27 mm above the desk and 32 mm back** (worked out on the 27 mm dock; the extra
3.5 mm of shell moves it by a fraction of a millimetre), and only the chassis touches the desk
(X −7.1…132.4, D 3.5…82.5), so tipping needs ≈ 46° forward, 62° backward or 68° sideways. Keeping the sensors in
the dock rather than behind the panel is what buys that margin — carried in the head they would sit 40 mm higher.

## Parts

| Part | Print orientation | Fixings |
|---|---|---|
| **Head tray** | face down | Bezel (2.4 mm lip) and four walls, 14.1 mm deep, 5 mm plan radii, 1.2 mm round on the bezel edge. Right wall 7.3 mm thick, carrying the USB-C, power-button and microSD pockets; left wall 2 mm with the wake-button hole. The rear edge of the walls carries what holds the cover: a 1 mm step all round as its seat, two tongue slots in the thin wall, and two ear pockets with heat-set inserts in the thick wall's corners. No vents. |
| **Head back cover** | flat, outside down | 2 mm plate resting on the Inkplate's four 7.2 mm SMT standoffs and screwed to them: 4 × M3 through clearance holes, counterbored 0.7 mm so the heads sit near flush in a 2 mm plate. It holds the tray with two 12 mm tongues on one side edge and two ears on the other, each ear screwed to an insert in the thick wall. It goes on tilted, tongues first, and swings down. One grille band over the ESP32 (8 capsule slots, X 74–94, Y 14–40) — the head's only opening, facing up and back. |
| **Dock chassis** | upright (desk face down) | Floor, the solid 20° cradle block with the head pocket, and every bay feature: board bosses, the SCD41 compartment, the SHTC3 baffle, the AMS1117 pocket. It also carries the pogo plinth standing in the trench. Nothing fastens the head: the connector's two Ø5 magnets hold it down and the cradle pocket locates it. It also carries the TinyS3's cradle, whose channel is the dock's wiring duct, the USB-C socket's holder by the rear wall, and the status LED's access pit. |
| **Dock shell** | upside down (top skin on the bed) | The visible skin: rounded, drafted walls, the sloped top and a 2 mm front wall under the head, in one piece with no top-side fixings. 4 × M3×8 countersunk up from underneath into heat-set inserts in its internal pillars, which stand on 1 mm bosses on the chassis floor (×10 bottoms out — the insert ends at 8.7 mm). A Ø4 post holds the AMS1117 module down, and the PMSA003I's seal rib is part of this wall. |

0.4 mm nozzle, 2 mm walls and skin, 2.2 mm slots on a 3.4 mm pitch where slots remain. The shell prints upside
down so its whole outer surface is either on the bed or a drafted wall — no supports; the STL is rotated 5.15° past
the flip so the whole skin lies flat on the bed. Everything is printed in **PLA+**: the only heat in the dock
is the AMS1117's few hundred milliwatts, so PETG is the fallback if its pocket or the shell post over it ever
softens.

**Nothing stands inside the head's cavity, and nothing may.** The Inkplate is 130.59 × 75.23 in a 134.6 × 77.2
opening — 2 mm a side in X, because SW2 and the wake switch stand 0.85 mm past the board's left and right edges,
and 1 mm top and bottom — and it goes in from the back, which means its own footprint sweeps the whole cavity on
the way to its seat. A boss is in the way however far behind
the seated board it finally sits. So the cover screws to the Inkplate's own
standoffs, and the head is held by magnets.

The cover goes in from the back in a straight line, so only something that engages after it is in can keep it
there. Two tongues on its thin-wall edge enter slots in that wall, and two ears at the other end sit in pockets in
the thick wall and screw into inserts. All of it is cut into the walls, so the board still passes. Hold the head
with the panel facing up and the tongues and the two ear screws carry the Inkplate; `enclosure.py` reports what
blocks the cover from dropping straight out as `cover_pullout_blocked_mm3`, which must be **more than 0**.

The bezel lip stands 0.15 mm clear of the panel, and the tongues have the same play in their slots. A wall that
prints that much short therefore cannot make the ear screws press the lip on to the glass.

## Fasteners

Six brass heat-set inserts carry the screwed joints between printed parts: four for the shell on the chassis, two
for the back cover's ears on the tray. The back cover also
screws into the Inkplate's own standoffs, the pogo connector's two magnets hold the head down, and everything else
threads straight into printed plastic.

| Fastener | Qty | Where | Hole |
|---|---|---|---|
| M3 heat-set insert (≈ 5.7 long, 4.6 OD) | 6 | Dock shell, internal pillars (4); head tray, thick wall corners (2) | Ø 4.0 × 6.0 deep |
| M3 × 8 countersunk, 90° | 4 | Shell → chassis, up from underneath | Ø 3.4 clearance, Ø 6.2 × 1.4 cone |
| M3 × 6 machine screw | 6 | Head back cover → the Inkplate's four SMT standoffs (4) and the tray's two inserts (2) | Ø 3.4 clearance; Ø 6.2 × 0.7 counterbore over the standoffs only |
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
- The shell screw stops at 8 mm: it passes 3 mm of floor and boss and holds 5 mm of the insert, which ends at 8.7, so an M3 × 10 bottoms out.
- The cover's counterbore leaves 1.3 mm of plate under each screw head, so an M3 × 6 puts about 4.7 mm of thread
  into the 7.2 mm standoff.
- Self-tapping into PLA or PETG holds fine for a one-time build. If boards will come in and out repeatedly, those
  pilots strip after a handful of cycles and want inserts instead — which means taller, wider bosses.

## Frames

**Head frame**: X left → right seen from the front (the Inkplate PCB spans 0…130.59), Y up (PCB 0…75.23), Z
toward the viewer with Z = 0 at the panel's front face. In Fusion, X_f = X, Y_f = −Z, Z_f = Y. Z levels: bezel
front +2.4 · panel 0 · PCB back −2.45 · standoff tops / cover inner −9.67 · cover outer −11.67.

**Dock frame**: X as the head, D = depth from the front-bottom edge (0…86 nominal, 87.9 including the draft),
H = height above the desk. This is Fusion's world frame; the `Dock` component is untilted and the `Head`
component carries the 20° tilt. Bay interior X −8.6…133.9, D 25…84, H 2 up to the skin's underside (28.5 at D 25,
sloping to 23 at the rear). Board component faces at H 5.6 (Adafruit / Soldered) and 6.0 (AMS1117, raised so the
regulator on its underside hangs in free air).

Inside `Dock`, only the chassis and the shell sit at the top level. Every board, the pogo female and **Dock wiring
(toggle)** sit in **Dock electronics (toggle)**; switch its light bulb off to see the bare printed parts.

The head's front-bottom edge lands at D 4.91 / H 13.5, chosen so the **bezel plane passes through (D 0, H 0)** —
that is what makes the dock's front face and the bezel one plane. Change `HEAD_FRONT_H` and the front slab
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
  If its response turns out sluggish, the fix is a slot row low in the compartment's left wall.
- **Head.** Sealed except for one grille band in the back cover: 8 stadium slots, 2.2 × 20 mm on the usual 3.4 mm
  pitch, X 74–94 and Y 14–40, ≈ 344 mm². They sit over the **ESP32-WROVER** (X 75–93, Y −0.2–31.8), which at
  80–150 mA with Wi-Fi up is the only real heat source in the head and sits directly behind the panel. The slots run
  **along X**: everything else about this object is horizontal — the shadow gap, the PM's vent strip — and vertical
  ticks cut across all of it. One band spanning low to high also vents better than two discrete ones, since the 20°
  tilt makes the bottom rows the intake and the top rows the exhaust. Y 14 is the lower limit: the head's five wires
  cross the board at Y 3–11 and would otherwise show through.

### Heat

| Source | Dissipation | Note |
|---|---|---|
| TinyS3, awake with Wi-Fi | ~0.5 W | ~100 mA at 5 V. The dock's largest heater. |
| AMS1117 | 0.37 W at 215 mA, ~0.2 W at 120 mA | 1.7 V dropped. A SOT-223 on the module's copper runs ~70 °C/W, so the tab sits 25–30 °C above the room, about 55 °C. Rated 125 °C. |
| PMSA003I | ≤ 0.5 W | vents straight out through the left wall |
| Sensors | < 0.1 W | |

There is no fan. Under a watt in a vented dock lifts the air near the parts by a degree or two and the far corner
by nothing. A fan would blow over the SHTC3, stir the SCD41's compartment and pull the BME688's heater about, so
both heaters instead sit on the PM side, as far from the SHTC3 as the layout allows.

---

## Bay layout

Each board's place follows the placement rules in its section of [bom.md](bom.md):

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
| PMSA003I | −3.8…31.8 × 27…77.8 | Left end, module face 4.8 mm from the left wall and its vents. X −3.8 puts the board edge and its two left bosses 3.3 mm inside the edge of the chassis floor (which is inset 1.5 mm from the wall). Header row along its **front** edge, so the tall Dupont housings stand behind the head where the dock is deepest. D 27 (not 30) keeps its rear corner clear of the cavity's 10 mm rounded corner. |
| SCD41 | 49.9…72.8 × 35…60.4, sockets facing front and rear | Middle, in its own compartment (walls X 47.3–48.8 and 74.3–75.8 from D 30, rear wall D 72–73.5, all to the skin). Both sockets in use; nothing else is connected to it. |
| SHTC3 | 82.8…120.8 × 26.5…48.5 | Front-right: coolest corner, against the solid cradle block, farthest from the fan and the LDO, behind a full-height baffle at D 50–51.5. End of the chain, only its right socket used. |
| BME688 | 82.8…120.8 × 53.5…75.5 | Rear-right, behind the baffle. Both sockets in use. |
| AMS1117-3.3 | 8…20.5 × 80.5…89, **across the bay, pins to the right** | Behind the PM board, its header end towards the TinyS3's channel. No mounting holes: it sits in a pocket 0.5 mm clear of the board on every side (0.3 mm a side would give a 9.1 mm slot, too tight to trust an FDM print with), with 1 mm locating walls and 2.5 mm corner tabs, so the underside is open. The board rests on a pad under its header's solder domes (they stand 1.2 mm proud) and on two solid corners at the far end either side of the SOT-223 (to H 6.0, the PCB's underside), so the regulator hangs in a 2.3 mm air passage — no floor slots, nothing to bridge. A Ø4 shell post at (15.5, 84.75), on the board's centreline, lands on it and stops it lifting (until the shell is on, the module is loose); a 3 mm cone at the post's root keeps it printable upside down. Dupont housings on its three pins run **right**, to X 35.8. |

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

### Cable lanes

The three Qwiic ribbons stay at board height (H 7.1), lie flat, and bend as a ribbon does, their conductors
1.1 mm apart and concentric round every corner. The PM ribbon runs down the lane at X 44.3 and along the bay's
front into the SCD41 compartment. The SCD41 → BME688 ribbon runs back to D 69.5, across, and slants through a
notch in the compartment's right wall (D 60.1–68.9). The BME688 → SHTC3 ribbon runs up the right-hand lane at
X 126, through a notch in the baffle (X 119.7–128.5); it has 3.2 mm to turn out of each plug, so its bends are
3.2 rather than 4.

Both notches are **8.8 × 6 mm**. A JST-SH plug is 6.8 × 2.7 and has to be threaded through them, so each notch
is the plug plus a millimetre a side. **Size them from the plug, not the ribbon.**

The right-hand lane sits at X 126, not hard against the chassis edge, with a **guide rib at X 128.5–132.4, 7 mm
tall, from D 35 to 67**. At 129.1 the ribbon would overhang the chassis edge with only the shell's inner wall to
hold it in: it would have to be stuffed in as the lid came down, and would spring out every time the lid came
off. The rib is that wall, and the shell drops on without touching the cable.

### Wire routes

The TinyS3's cradle channel is the dock's duct: it runs the length of the cradle, is open at both ends under the
board, and carries every wire that crosses behind the sensors. Wires stack in it by height, so they never cross —
the joints on the 5V row's legs lowest at **H 4.6**, then the pogo pair at **H 8.5**, the AMS1117 pair at **H 11.6**, and
the LED pair just under the board at **H 15.8**. The two splices sit in the channel's middle, X 60–68.

- **The strips.** One 12-way for the 9-8-7-6 row and one 11-way for the 5V row, cut from standard 20-way
  single-row female strips.
  They measure 11.6 mm from leg tip to socket face, 8.4 mm of it plastic, and 2.4 mm wide *(measured,
  calipers)*. The model uses 8.5 mm of plastic, 3 mm legs and 2.5 mm width. The TinyS3's own headers are
  soldered long pins down, and their plastic spacer is 2.5 mm *(measured)*.
- **The cradle.** Each strip sits in a pocket, its outer edge on a ledge along the pocket's outer wall and its
  two ends on end blocks. The ledge stops 0.6 mm from the row's centre and its underside is 1.2 mm below the
  strip, so a joint on the lower half of a leg passes under it. Nothing stands between the two strips, down to
  the floor. A rib inside the shell stands 1 mm above the TinyS3's USB-C, so with the shell on the board cannot
  lift off its strips.
- **The pogo pair.** Each wire meets its tail's tip end-on from below, in a chamber under the plinth, drops to
  the chamber's floor, runs back along it, and leaves under the plinth's back wall at **H 3.9** into the trench.
  In the trench the two become a bundle: left along it, up the strip between the PM board and the SCD41
  compartment — under the Qwiic ribbon, over the PM group — and along the channel to the splices' left ends.
- **The AMS1117 pair.** VBUS and GND leave the splices' left ends straight along the channel into the IN (rear)
  and GND (front) housings at pin height. **AMS OUT → PM VIN** leaves the middle housing over the GND wire, runs
  forward at **H 13.3** over the PM group's lanes, up to a lane under the skin, across the PM module and down
  into its VIN housing.
- **The PM group.** Cable 1's three conductors and SET leave their legs pointing into the channel, turn onto
  their lanes, and run as one bundle left along the channel, up the strip, over the ribbon at **H 10** and left
  along the front of the bay.
- **The LED pair.** Rearward over the SHTC3's right end, left of the shell pillar at (125, 30), onto the ribbon
  lane at X 126, up past the BME688 and across the bay behind it. At X 86 they part: IO6 into the channel's
  right end and down onto the TinyS3's pin 6; GND onto the GND splice's right end.

**Clearance above the PM header.** The PM board's **straight** 7-pin header is on its front edge at D 29.5, with
five housings on it whose tops reach **H 22.1**. A housing is entered from the top, and the head's back cover
leans over the row from the front, so wires must come over the housings from behind: SCL, SDA and GND climb
between the SET housing and the PM's socket B to lanes at **H 26.8**, 1.4 mm under the skin. A housing is 14 mm
tall and a wire needs about 3.7 mm above it to turn without strain, so the design keeps **17.7 mm clear above
the header block** *(measured on the real parts)*.

**In the head**, the back cover sits on the Inkplate's own 7.2 mm standoffs, and each of the two wires takes one
lane in that space.

**The AMS1117's pins** sit at D 87.3 (GND), 84.8 (OUT) and 82.2 (VIN), with their housings running right to
X 35.8 at H 11.6.

**The USB-C holder.** The left ear's seat stops 0.3 mm behind the B5 resistor, to leave room for it.

### The pogo junction

The pair is centred on the device at X 62.65. Both halves are panel-mount parts fixed by their lips, each fitted
from inside its own shell.

- **Male, in the head.** Its nose fills the 2 mm bottom wall and stands 0.30 mm proud of the underside. Its lip
  is glued to the cavity floor between two locating ribs; its back band and tails are in open cavity.
- **Female, in the dock.** It drops into a plinth standing in the trench, its lip landing on a ledge with a glue
  relief inside the rim. Only its 1 mm boss stands above the plinth's rim. The plinth is open at the front above
  the ledge, and the shell's front wall closes it, 0.9 mm off the lip.

The boss enters the male's pocket, so the halves nest: the mated bodies come to 9.3 mm, not 10.3. The key is the
contact block's own outline — a rounded rectangle with one semicircle cut into the middle of its S-end wall — so
a half turned end for end fouls it and will not close.

The trench is X 42–84, D 9.5–26, floor at H 3, open at the top once the head is off.

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

`enclosure.py` also reports `printability` for the four printed parts, for a 0.4 mm nozzle:

- `knives`: edges where two faces meet at less than 30°. It must be empty.
- `fail`: walls or gaps under 0.45 mm, about one extruded line. It must be empty.
- `warn`: walls or gaps from 0.45 to 0.8 mm, under two lines. It is empty on all four parts, so anything there is new.

Each entry is the thinnest point in a 3 mm cell, in the part's own frame (see Frames).

It also reports `wiring`, for the two wiring layers:

- `overlaps`: every pair of wires that pass through each other, with the volume shared. It must be empty.
- `under_floor`: bends under 3 mm that are not at a solder joint. It must be empty.
- `forced`: bends that got at least 3 mm but less than four diameters, because the straights either side had no
  room for more. Each is a place a wire has to be bent harder than it would like.
- `joints`: the bends at the solder tails, which are made tight on purpose.

Positions are in the layer's own frame (see Frames).
