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
| `enclosure.py` | Fusion script: downloads the Inkplate / Adafruit STEP models, builds the Soldered and AMS1117 block-outs, places every board, builds the four parts and the two wiring layers, applies the tilt. Run it from Fusion's script editor in an empty design. |

On the desk: **145.7 wide × 87.4 deep × 88.3 tall mm**. Base 27 mm tall at the front, 21.5 mm at the rear.

## Shape

It is meant to sit on a desk without announcing itself, which drove the architecture:

- **The sensors live in the base, not behind the display.** That keeps the centre of mass low (below) and lets the
  head be only 14 mm thick.
- **The base is a chassis inside a shell.** The shell is one uninterrupted skin; all four of its screws come up
  from underneath through the chassis, so nothing breaks the top or the sides.
- **The front is one continuous 20° slab.** The head's bezel and the base's front face lie in the same plane with
  only a parting line between them, rather than the head standing in a visible pocket.
- **Nothing is square.** 10 mm plan radii on the base and 5 mm on the head, a 1.5 mm chamfer round the top edge and
  a 1.2 mm round on the bezel, and 4.3° of draft on the side and rear walls so the base reads as a foot, not a box.
- **The vents are hidden.** A 1.5 mm shadow gap under the whole shell replaces every grille; the only visible
  openings are the PMSA003I's, sunk in a recessed strip on the left wall.

## Stability

Mass is ≈ 280 g (92 g Inkplate, 52 g head shells, 145 g base and boards, PETG at 1.24 g/cm³ printed near solid).
The centre of mass sits **27 mm above the desk and 32 mm back**, and only the chassis touches the desk
(X −4.8…130.1, D 3.5…82.5), so tipping needs ≈ 46° forward, 62° backward or 68° sideways. Keeping the sensors in
the base rather than behind the panel is what buys that margin — carried in the head they would sit 40 mm higher.

## Parts

| Part | Print orientation | Fixings |
|---|---|---|
| **Head tray** | face down | Bezel (2.4 mm lip) and four walls, 14.1 mm deep, 5 mm plan radii, 1.2 mm round on the bezel edge. Left wall 7.3 mm thick, carrying the USB-C, power-button and microSD pockets; right wall 2 mm with the wake-button hole. Relief in the bezel lip for the expander header's solder tails. No vents. |
| **Head back cover** | flat, outside down | 2 mm plate resting on the Inkplate's four 7.2 mm SMT standoffs (4 × M3 clearance holes over them, screws optional), held by 4 × M2.5 self-tapping into tray bosses. Those bosses reach in from the top and bottom walls and sit behind the PCB (Z −4…−9.67), which is the only place in a 2 mm-walled tray where a boss can both clear the board and stay attached to something. Two grille bands over the ESP32 — the head's only opening, facing up and back. |
| **Base chassis** | upright (desk face down) | Floor, the solid 20° cradle block with the head pocket, and every bay feature: board bosses, the SCD41 compartment, the SHTC3 baffle, the AMS1117 pocket. Two M3×12 from below (counterbored) into heat-set inserts in the head's bottom wall hold the head. |
| **Base shell** | upside down (top skin on the bed) | The visible skin: rounded, drafted walls and the sloped top, in one piece with no top-side fixings. 4 × M3×10 up from underneath into heat-set inserts in its internal pillars. One post holds the AMS1117 module down, and the PMSA003I's seal rib is part of this wall. |

Sensor boards: M2.5 self-tapping into 2.1 mm pilots (Adafruit), M3 self-tapping into 2.6 mm pilots (Soldered),
all on 2 mm bosses on the chassis floor. Heat-set inserts: 2 × M3 in the head's bottom wall, 4 × M3 in the shell.
0.4 mm nozzle, 2 mm walls and skin, 2.2 mm slots on a 3.4 mm pitch where slots remain. The shell prints upside
down so its whole outer surface is either on the bed or a drafted wall — no supports. PETG for the base (the LDO
and the fan live there), anything for the head.

## Frames

**Head frame**: X left → right seen from the front (the Inkplate PCB spans 0…130.59), Y up (PCB 0…75.23), Z
toward the viewer with Z = 0 at the panel's front face. In Fusion, X_f = X, Y_f = −Z, Z_f = Y. Z levels: bezel
front +2.4 · panel 0 · PCB back −2.45 · standoff tops / cover inner −9.67 · cover outer −11.67.

**Base frame**: X as the head, D = depth from the front-bottom edge (0…86 nominal, 87.9 including the draft),
H = height above the desk. This is Fusion's world frame; the `Base` component is untilted and the `Head`
component carries the 20° tilt. Bay interior X −6.3…131.6, D 25…84, H 2…25. Board component faces at H 5.6
(Adafruit / Soldered) and 5.4 (AMS1117).

The head's front-bottom edge lands at D 2.3 / H 12, chosen so the **bezel plane passes through (D 0, H 0)** —
that is what makes the base's front face and the bezel one plane. Change `HEAD_FRONT_H` and the front slab
follows automatically.

## Surfacing rules

- **Plan corners** are built into the solid, not filleted: the shell's outer prism is four truncated cones
  (r 10 mm at the top, growing with the draft) plus two tilted-plane slabs. The cavity uses r 8 and the chassis
  r 6.5 about *the same centres*, so the wall stays 2 mm and the chassis-to-shell gap stays 1.5 mm all the way
  round the corner.
- **Draft** 4.3° on the sides and rear, referenced to the top of the walls: 2.0 mm wider at the desk than at the
  top, where the shell matches the head's width exactly. The front (bezel) plane and the cavity are not drafted.
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
  detail rather than a grille. A 2.3 mm rib on the shell's inner wall (D 54.8–58.1, H 1.5–19) crosses the 2.5 mm
  gap between that wall and the module's face, between the two slot groups, so exhaust cannot run along it into
  the inlet. It is on the shell, not the chassis: the chassis is inset 1.5 mm from this wall and could only reach
  it as a detached island. The 0.8 mm of rib that reaches over the chassis floor starts 0.2 mm above it, so the
  shell still drops on freely.
- **SCD41** breathes through its compartment's open front (≈ 500 mm² facing the bay) rather than a lid grille.
  If its response turns out sluggish, the fix is a slot row low in the compartment's left wall — see Unverified.
- **Head.** Sealed except for the two grille bands in the back cover over the ESP32.

## Bay layout

Follows [HARDWARE.md §9](../../../docs/HARDWARE.md#9-placement-in-the-enclosure).

| Board | X × D (mm) | Placement |
|---|---|---|
| PMSA003I | −3.8…31.8 × 27…77.8 | Left end, module face 2.5 mm from the left wall and its vents. X −3.8 puts the board edge and its two left bosses 1 mm inside the edge of the chassis floor, which is inset 1.5 mm from the wall. Header row along its **front** edge, so the tall Dupont housings stand behind the head where the base is deepest. D 27 keeps its rear corner clear of the cavity's 10 mm rounded corner. |
| SCD41 | 49.9…72.8 × 35…60.4, sockets facing front and rear | Middle, in its own compartment (walls X 47.3–48.8 and 74.3–75.8 from D 30, rear wall D 72–73.5, all to the skin). Both sockets in use. |
| SHTC3 | 82.8…120.8 × 26.5…48.5 | Front-right: coolest corner, against the solid cradle block, farthest from the fan and the LDO, behind a full-height baffle at D 50–51.5. End of the chain, only its right socket used. |
| BME688 | 82.8…120.8 × 53.5…75.5 | Rear-right, behind the baffle. Both sockets in use. |
| AMS1117-3.3 | 33.3…41.8 × 50.5…63, pins toward the rear | In the strip between the PM board and the SCD41 compartment. The strip, the Qwiic lane and the compartment are placed from the PM board's position: the clearances between them are under 1 mm, so they move as a group. No mounting holes: a floor pad between the underside chip and the solder domes carries it, end stops and side ribs locate it, a shell post holds it down. Dupont housings on its three pins reach D 77. |

The four shell pillars sit at (68, 30), (126, 30), (50, 78.5) and (126, 79) — the only plan positions clear of
every board, plug, ribbon and wire lane. The left third of the shell has no pillar (the PM board leaves 6 mm at
the rear and 2 mm at the front, and a pillar needs 9); it is held by the skin and located by the cradle block.

## Wiring and headers

Follows the wiring table in [HARDWARE.md](../../../docs/HARDWARE.md). Two Fusion components hold every header,
plug, Dupont housing and wire as separate coloured bodies — **Head wiring (toggle)** and **Base wiring
(toggle)**; switch their light bulbs off to hide the lot. Wires are drawn schematically, right-angle bends only,
each in a dedicated channel, so the model documents where cables are meant to run rather than how they sag.
Colours: red 3V3 / VIN, black GND, blue SDA, yellow SCL, white SET. Qwiic cables are 4 mm ribbons in the standard
black / red / blue / yellow order with white plugs; the boards' JST-SH sockets are beige. Everything nominally
black is drawn as a mid grey instead — Dupont housings #696969, header shrouds #585858, the GND wire #646464:
these appearances copy Fusion's matte-black plastic, whose shader darkens the base colour so far that a true
black housing or wire loses every edge and reads as one solid blob against the boards. The Adafruit boards' bare
PCBs reuse the Inkplate STEP model's own IC appearance
(`Opaque(64,64,64)`, #404040) rather than pure black, so every board reads as one family under the same light.
That grey carries every IC in the model: the Soldered boards' sensor and regulator block-outs take it too, and so
does the PMSA003I's fan cover, so the only colours left are the ones that mean something — purple and grey PCBs,
beige JST-SH sockets, and the Plantower module's blue shell.

**Head.** The back cover sits on the Inkplate's own 7.2 mm standoffs, so the space behind the board is 7.2 mm
and a straight header will not fit: the expander row (P1_3 · P1_2 · P1_1 · 3V3 · GND, along the **top** edge at
X 90.7–100.9 once the board is rotated) takes a **right-angle header** with pins pointing down the board and flat
Dupont housings on P1_3 and GND — 5.5 mm tall, 1.7 mm clear of the cover. The expander pads are 0.8 mm drills, so
use round machined-pin headers or solder the two wires straight to the pads. The easyC cable is cut down to
SDA / SCL. VIN comes off the VIN pad, a 4 × 4 mm surface pad with no hole, and unplugs at the AMS1117 end. All five wires run in two lanes behind the board (Z −7.4 and −8.7, clear of the ESP32) to a single
**common slot** in the bottom wall at X 31–45, Z −3.5…−9.2. Nothing else pierces the head.

**Base.** The slot opens into a trench in the cradle block (X −2.7…51.3, D 9.5–26, floor at H 3) leading under
the head into the bay. Every wire drops to H 5 in the trench, runs back to D 24–27, then rises behind the head's
back face:

- SET, SDA, SCL rise at D 26.7 / 25.5 / 24.3 to H 22.7 just under the skin, cross to their pin's X and drop into
  the tops of the PM's Dupont housings. The PM gets a **straight** 7-pin header on its front edge with the
  housings standing up (tops at H 22.1 — the base is 27 mm tall at the front for exactly this).
- VIN and GND rise to H 16.2 / 18.8, run back up the strip at X 40.1 / 33.1 and drop into the AMS1117 IN / GND
  housings from the rear (D 78.9).
- AMS OUT and GND leave the same housings, rise to H 18.5 then H 22.7 and run forward into the PM VIN / GND
  housing tops.

**Qwiic chain**: PM (front socket) → SCD41 front → SCD41 rear → BME688 left → BME688 right → SHTC3 right —
i.e. PM, SCD41, BME688, SHTC3, the order in the wiring table. Ribbons stay at board height (H 7.1): the PM ribbon
runs down the lane at X 44.9 and along the bay's front into the compartment; the SCD41 → BME688 ribbon leaves
through a notch in the compartment's right wall; the BME688 → SHTC3 ribbon runs along the right wall at X 129.1
through a notch in the baffle.

## Display window

The ED052TC4 STEP model carries the active area as a 0.04 mm recess on its front face: 114.56 × 64.44 mm, in the
rotated frame at X 5.35–119.91, Y 5.39–69.84. The window is that plus 0.8 mm, with a 1 × 1 mm step outside. The
Inkplate is mounted rotated 180° from the STEP model's own orientation so USB-C, the power button and microSD exit
the **left** wall; the thick wall is on that side, keeping the visible bezel symmetric (12.9 mm each side, 7.6 mm
top and bottom).

## Sensor board models

The Adafruit PMSA003I and SCD41 are Adafruit's own STEP models. The Soldered SHTC3 (333032) and BME688 (333203)
are built from the docs.soldered.com pinout drawings and checked with calipers: 38.0 × 22.0 mm, 2 mm corner
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

## Unverified

1. **Everything about how it looks and feels** is unverified until it is printed — the shape is a judgement no render settles. Print the shell first: it is the only part whose surface is on show.
2. Active-area offset — from the panel's STEP; with the board rotated, the narrow border should be on the left (USB-C) side. Check on the real panel before printing the head tray.
3. The shadow gap doubles as a dust path. If it collects, a 1 mm tongue on the chassis edge inside the gap would baffle it without closing the air path.
4. SCD41 response time: it vents into the bay, not through a grille in its own lid.
5. Dupont housings are modelled as 2.54 × 2.54 × 14 mm single-position shells; right-angle headers with the pin axis 4.2 mm off the board. Check the 1.7 mm margin to the head's back cover with the real housings before soldering the Inkplate header.
6. The Inkplate's expander pads are 0.8 mm drills (from the KiCad board): confirm the chosen header's pins fit, otherwise solder the two wires straight to the pads.
7. The head sits 8 mm deep in the cradle pocket with 0.3 mm side clearance, held by its two screws and the block's rear lip. If the printed pocket is loose, foam tape in the pocket floor takes up the play.
8. The shell's left end is unsupported over ≈ 50 mm. If it lifts, the cure is a printed clip on the chassis edge rather than a fifth screw — there is no room for one past the PM board.
