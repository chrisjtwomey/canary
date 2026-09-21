# CANARY

**Read [CONTRIBUTING.md](CONTRIBUTING.md) first.** It covers the repository layout, how to run the tests, and how to build and run things locally.

## This repo

- A thin consumer of [epd](https://github.com/chrisjtwomey/epd): the firmware (`src/`, `include/`) builds with `-DARDUINO_INKPLATE5V2` against epd's two libraries, and the server (`server/`) is its data sources, a page list and `DisplayServer(...).run()`. [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) has the layout.
- epd must be checked out beside this repo.

## Docs

Each doc covers one area:

- [README.md](README.md): what CANARY is.
- [CONTRIBUTING.md](CONTRIBUTING.md): layout, tests, local builds.
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): firmware and server design, wire headers, LED, version gate, notices. Has a decision log.
- [docs/READINGS.md](docs/READINGS.md): the JSON the dock posts.
- [hardware/README.md](hardware/README.md): the front door to the hardware, and what is in that folder.
- [hardware/bom.md](hardware/bom.md): every part, what to buy, alternatives, cost, and the datasheet facts each one brings.
- [hardware/assembly.md](hardware/assembly.md): how to build one, with the circuit and every connection.
- [hardware/enclosure.md](hardware/enclosure.md): the printed parts, fit, fasteners and the model's rules.

The hardware docs carry no decision log and no open questions of their own: both are below, so those docs
inform a reader and this file holds what is still being decided.

Before each commit:

1. For each staged file, name the doc that covers it.
2. Search that doc for each name, number and behaviour the change touches. Fix stale lines.
3. Record a design choice in that doc's decision log.
4. In the review, list the docs you checked and the docs you changed. If no doc changed, say so.

## General rules when working in this codebase

### 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them — don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

### 2. Goal-Driven Execution

**Define success criteria. Loop until verified. If tests exist, they must pass. If you weren't asked for tests, verify the code builds.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

## Code comments and documentation

### 1. Describe the present, not the change

Comments state how the code behaves now. They are not a changelog.

- No "changed to…", "now returns…", "previously…", "fixed so that…".
- No ticket or PR numbers standing in for an explanation.
- If a comment only makes sense to someone who saw the diff, cut it.

Git already holds the history, and a comment that narrates a change is stale the moment the next one lands.

### 2. Let the code carry the meaning

- Start a doc comment with a one-line summary of what the thing does.
- Inside a function body, reach for a better name, an extracted function, or a simpler conditional before reaching for a comment.
- If a body still seems to need one — a subtle contract, a load-bearing ordering, a trap the next reader will "tidy up" — ask before adding it.

Ask yourself: "Could I delete this comment by naming something better?" If yes, do that instead.

### 3. Say it once, and stop

- A sentence or two. A comment is not a design document.
- State what it does and what it hands back. Nothing more.
- Don't paraphrase the signature — the reader can see the parameters.
- Don't restate a system-wide idea in a low-level helper. Repeat an architectural rule everywhere and a reader starts hunting for the places it doesn't hold.

### 4. Assume competence

**Assume the reader has reasonable competence in the programming languages, principles, and practice.**

- Spend the words on what the code can't say: why this ordering, why this field is trusted without a guard, why this parse is a gate rather than a convenience.

The test: a comment that would read the same in any codebase isn't earning its place.

### 5. Plain language, not metaphor

**Name the thing itself — the function, the caller, the package, the type.**

- Borrowed imagery reads as precision but charges the reader a translation step.
- Tree and graph terms are the usual offenders: "low-level helper", not "leaf function"; "the packages that import it", not "its parents".
- Worse when the word is already taken — here "page" is a rendered image and "display" is the panel.

Ask yourself: "Does the metaphor explain this better than plain words would?" If you have to weigh it up, it doesn't.

## Open hardware questions

Unsettled, and each one names what would settle it.

1. **PMSA003I input current at 3.3 V** is derived from the charge-pump datasheet, not measured. Measure; it sets the regulator's rating.
2. **TinyS3 awake current** is a typical ESP32-S3 figure. Measure the dock alone on the Power Profiler once it runs.
3. **5 V on the Inkplate's VIN pads**, on the bench, with no battery connected: measure VIN and the battery connector, and check that the charger chip stays cool through a few refreshes. Soldered say the path is harmless ([assembly.md](hardware/assembly.md#9-the-head)); this confirms it on this board.
4. **Pull-ups on the TinyS3's bus.** [bom.md](hardware/bom.md#pull-ups) assumes the board adds none. Measure SDA and SCL to 3.3 V with the sensors unplugged.
5. **What the BME688 board's JP2 joins** ([bom.md](hardware/bom.md#bme688--voc-gas-and-pressure)). Soldered's docs say only that it powers the regulator from 5 V, and no schematic is public. A continuity check across JP2, or the hardware files Soldered sends on request, would settle it.
6. **Pogo contact resistance.** The connector's listing gives none, so [assembly.md](hardware/assembly.md#7-the-pogo-connector) assumes 30–100 mΩ. Measure across a mated pair with ~200 mA flowing.
7. **Flash size** of the Inkplate's ESP32-WROVER-E: 4, 8 or 16 MB by variant, and the module's shield prints no suffix. `esptool.py flash_id` over USB settles it; it resets the board.

---

## Hardware decision log

Dated findings and decisions behind the hardware docs, oldest first.

### The parts and the circuit

- **2026-09-03**: distilled from the datasheets.
- **2026-09-03**: the first wiring plan chained Inkplate → BME688 → SHTC3 → SCD41 → PMSA003I and fed all four from the Inkplate's 3V3 through the chain. Order, connectors, addresses and pull-ups were fine. Power was not: the Inkplate's 500 mA LDO also carries the ESP32, the SCD41 wants a quiet supply, and the two heavy loads sat at the far end, where the drop is worst. Nor was the SHTC3's place: the reference sat between the BME688's heater and the SCD41. The PM fan's SET pin was unused. The circuit now in assembly.md replaced the plan.
- **2026-09-09**: the RTC alarm wakes this board on GPIO39, though Soldered does not guarantee it on the 5 Gen2. `pio run -e esp32-validate` sleeps 10 s on the alarm and wakes on `ESP_SLEEP_WAKEUP_EXT0` every cycle; an ESP32 timer armed at 15 s as a backstop has never had to fire.
- **2026-09-09**: the SCD41 board is the Adafruit 5190. Soldered sells no SCD41; their CO₂ board is the SCD43.
- **2026-09-10**: the Soldered BME688 and SHTC3 boards carry `103` resistors beside their pull-up jumpers, so 10 kΩ, and the 2.0 kΩ bus total in bom.md stands.
- **2026-09-12**: on the bench, BSEC with `bme688_sel_33v_3s_4d` reached accuracy 1 in about 4 minutes and 3 in about 40, and took 1019 hPa as its pressure input without an error.
- **2026-09-12**: with calipers, the Soldered SHTC3 and BME688 boards are both 38.0 × 22.0 mm with four Ø3.2 mm holes on a 32 × 16 mm pitch. For the SHTC3 this overrides Soldered's product page and docs, which give 22 × 22 mm and two holes.
- **2026-09-13**: on the bench, BSEC restarted from the state in NVS was back at accuracy 3 within 3 minutes.
- **2026-09-13**: the wiring became one wire per crimp, with ground starred at the Inkplate and cable 1 landing on the PM header. The draft before it chained ground Inkplate → AMS1117 → PM, which put two wires on the regulator's one GND pin.
- **2026-09-14**: Soldered's pages checked again. Neither Soldered sensor board has a public hardware repo, their docs describe the BME688's JP2 only as feeding the regulator from 5 V, and the Inkplate's BOM names its module only as "ESP32-WROVER", so the PSRAM size stays unverified.
- **2026-09-14**: the head-to-dock pogo connector is rated 1 A, with no per-pin figure and no contact resistance. The build takes 1 A per pin and assumes 30–100 mΩ per contact.
- **2026-09-14**: the module is an ESP32-WROVER-E; its shield prints the name but no variant suffix. The board's Diagnostics report shows 4.0 MB of PSRAM, which rules out the 2 MB variants, so it carries 8 MB. The flash stays 4, 8 or 16 MB.
- **2026-09-15**: the sensors moved off the Inkplate onto a dock of their own, after the full chain jammed the I²C bus on the Inkplate's rail while each board alone was healthy. One bus carried the panel, the expander, the RTC and the chain, and one 500 mA rail carried the ESP32 and the chain; splitting the device gives each half its own bus and its own regulator.
- **2026-09-15**: the TinyS3 runs the sensors, with the AMS1117 for their 3.3 V. Its own NCP167 cannot carry the chain: 198 °C/W in a 1 × 1 mm package is +60 °C at the typical load and +130 °C at the peak, which is thermal shutdown. A ProS3, whose second regulator could be switched off, was the alternative; it would have put the SCD41 back on the processor's rail beside the Wi-Fi bursts, which is the fault this design exists to avoid. A 40 mAh cell in the head was ruled out: the Inkplate charges at ~400 mA (10 C) and draws 2.5–40 C from it.
- **2026-09-15**: no fan in the dock. Under a watt of dissipation does not need one, and moving air would disturb the SHTC3, the SCD41's compartment and the BME688's heater.
- **2026-09-17**: the head takes 5 V at its VIN pads, on Soldered's own advice for this circuit (forum thread 1934). The alternatives were the 0.8 mm VUSB test pad, too small to solder safely, and the battery connector, which is limited to 4.2 V. A Schottky against back-feed was dropped: the dock's side wall covers the head's USB-C socket while it is docked, so nothing can feed it from a computer.
- **2026-09-17**: the chain keeps one ground return, cable 1's GND conductor. A second return existed when seven loose wires crossed the pogo joint; with the sensors in the dock the whole chain returns under 300 mA through 28 AWG, a few millivolts.
- **2026-09-18**: the right-angle pins on the TinyS3's battery pads are not a fit constraint, so nothing in the enclosure accounts for them. They hang in the 2.5 mm between the board's underside and the tops of the female header strips, where the only things that can meet them are wires and resistors. Both flex, so neither stops the board seating. If the pins ever do get in the way, they come off the board.
- **2026-09-20**: the SCD41 stays, and a Soldered SCD43 goes in the spares. The SCD43 is a drop-in for the chip — same SCD4x datasheet, same 0x62 address, same commands, single-shot on both, so the driver needs no change — and it is more accurate: ±(30 ppm + 3%) across 400–5000 ppm, against the SCD41's ±(50 ppm + 2.5%) to 1000, ±(50 ppm + 3%) to 2000 and ±(40 ppm + 5%) above it. In this device that is 16 ppm at 800, 20 ppm at 1500 and 70 ppm at 3000. The pages show bands, and yearly drift is ±(5 ppm + 0.5%), so 20 ppm changes nothing a reader would act on. The board is what costs: Soldered's SCD43 has two mounting holes to the Adafruit 5190's four, and its Qwiic sockets are on the left and right rather than front and rear, so the compartment, its bosses and both ribbon lanes move — a chassis redesign and a reprint. Revisit only if the chassis is reprinted for another reason, and check Soldered's JP1 and their bus pull-ups first.
- **2026-09-21**: the AMS1117 module's pins read GND, OUT, VIN, not IN, OUT, GND. The model, the wiring table and the enclosure notes all had the two ends the wrong way round, and a dock built to them puts 5 V on the regulator's GND pin, which destroys the module. Nothing else is at risk: the output pin can only sit between the two supply rails, so the PM board saw 0 to 5 V, which is inside its rating, and the rest of the chain sits behind the PM board's own regulator. The part has no reverse protection and no marking that survives a drawing, so the fix is procedural as well as numerical — every document now says to read the silkscreen, and that the middle pin is OUT on all of these boards, which is what tells the two ends apart.
- **2026-09-21**: the bench validation image targets the dock alone, as `dock-validate`. The head has no sensors on its easyC socket any more — the dock reads all four — so an Inkplate build of it proved a wiring that no longer exists. `src/validate/` now builds for the TinyS3: SDA on IO8, SCL on IO9, the PM fan's SET on IO7 as a plain output rather than an expander bit, and no RTC, panel or battery to report. It does not sleep between passes: the serial port is the board's own USB, which a deep sleep drops mid-bench, so it waits ten seconds and runs again. The 2026-09-09 entry's `esp32-validate` command is history.

### The enclosure

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
  - A standing Dupont housing and its wire were measured at 17.7 mm above the header, which set the dock at
    30.5 mm tall at the front. Everything is printed in PLA+ from here.
- **2026-09-14**: the first printed head could not be assembled. Four cover-boss towers and two dock-screw blocks
  stood in the cavity that the Inkplate sweeps on its way in. All six went: the cover screws to the Inkplate's
  standoffs, and an 8-pin magnetic pogo connector holds the head down and carries the head-to-dock wiring.
  `enclosure.py` reports the swept volume as `inkplate_insertion_blocked_mm3`; it would have read several hundred
  on the printed head.
- **2026-09-15**:
  - Fitting the Inkplate into the printed head broke off SW2 (power) and the wake switch. Both stand 0.85 mm past
    the board's edges, and the cavity was 1 mm clear of the board: 0.15 mm for the switches, less whatever the print
    took. The cavity went to 2 mm a side in X, and the head 1 mm wider each side with it.
  - The printed shell was tight as well. The dock went 1 mm wider each side to stay flush with the head, the chassis
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
    draft carried them out past its vertical sides. The dock is now 1.3 mm wider each side than the head, so the
    walls frame it with 0.8 mm at the top, more below. Kept in reserve: stop the side walls behind the head, with a
    2 mm shoulder round its bottom corners; or drop the side draft, so the head is flush with the dock's sides the
    full height and the dock looks boxier.
  - The two front shell pillars stood 0.55 mm into the clearance behind the head and left a 0.23 mm sliver at their
    tops: the head opening was cut before they were added. It is cut after them now.
  - The pogo plinth's rim sloped down onto the tails chamber's ceiling at 20°, so the plinth's back wall over the
    chamber was a wedge under 0.8 mm. It printed, but thin. The chamber's roof now drops to H 5.5 under that wall,
    which makes it 2 mm thick, and the wires climb to their H 7 lane at D 21, behind the plinth, not inside it.
  - The AMS1117 pocket's two rear supports stopped at the board's rear edge, 0.5 mm short of the pocket's rear wall:
    a slot that would half fuse in print. They run to the wall now.
  - The header-tail reliefs in the bezel lip went 0.1 mm past the window step's floor, which left a 0.36 × 0.1 mm
    strip between the two cuts, under one nozzle width. They stop at the step's floor now: the skin over them is
    1.0 mm, and the tails have 2.25 mm past the board's front face, not 2.35.
  - The tails chamber stopped 0.01 mm short of the bay, which left a 0.01 mm film over the bottom 0.5 mm of its
    way out. It runs 1 mm into the bay now.
  - These fixes came from a scan run by hand. The rebuild report runs it every time now, as `printability`: see
    Printing check.
  - The two `(ref)` pogo components beside the device were made by hand, and they had drifted: the female's pads
    were an older revision. `run()` builds them now, from the same code as the fitted pair, with all eight ways and
    the male's plungers standing free in its pocket. It builds them hidden.
- **2026-09-16**:
  - The four wires to the PM header ran down and along a 3.3 mm slot, between the cradle block's rear lip and the
    header's housings. Four wires do not lie in that, and nothing holds them. They run at floor level now, in a
    tunnel bored through the block from the trench, and leave through one mouth that opens towards the PMSA. The
    tunnel's far end is rounded into that mouth, so a wire pushed along it turns out instead of jamming on a corner.
    Two traps on the way: cutting the mouth's box and its rounded end as separate cuts leaves a fin that thins to
    nothing where the two faces cross, so the mouth is built as one tool; and the mouth has to stop short of the
    block's top, because the head's pocket leans back into it and the wall in front would feather away to nothing.
  - The wires were schematic: right angles, and several passing through each other. They are drawn at their
    measured size now (jumpers Ø1.3, Qwiic conductors Ø1.0), with an arc of four diameters at every corner where
    the straights allow one, bundled where they travel together, and none passing through another — `run()`
    reports the overlaps (none) and every bend that got less than it wanted. Doing that honestly moved things:
    - The pogo connector's ways are reassigned. Two of the head's tail ways sit under the AVX capacitor with
      1.27 mm above their tips, reachable only along a lane in front of them, one wire from each side; the row
      nearer the cover can only be reached from behind, one wire per line; and in the dock the wires must turn
      out of the chamber in lane order. Between them that fixes which signal takes which way.
    - The tunnel's mouth is 5 mm wider (to X 28.5). A wire cannot turn back over a PM housing from the front —
      the head's back cover leans over the header row, and the hairpin would get 2.5 mm — so the four PM wires
      leave the mouth at its right-hand end, go round the end of the housing row, climb, and drop in from above.
    - The Qwiic lane moved from X 45.05 to 44.3: a ribbon's outer conductor swings wide on a corner, and at
      45.05 it swept into the corner of the compartment wall. The SCD41 → BME688 ribbon runs a longer loop, its
      old route having a 4.5 mm straight between two corners.
    - Places a wire is bent to about 3 mm because nothing more fits: SET's hairpin over its PM housing (3.0,
      twice); the two AMS wires' climbs from the bay floor into their housings (3.8, twice each); the drop into
      the SCD41 housing (3.3) and into the PM's VIN housing (3.2), both under the skin; the bends onto the over-
      lanes 2 mm from SET's hairpin (3.5, twice); and the BME688 → SHTC3 ribbon out of each plug (3.2). Every
      other bend is 4 mm or more, most of them the full four diameters.
    - Fusion's `createTorus` puts the ring at the origin when the axis is one particular direction. The arcs
      are built on the Z axis at the origin and moved into place.
- **2026-09-16**, the dock:
  - The TinyS3 plugs into two glued female header strips, and the wires are soldered to the strips' legs. A wire
    cannot be replaced without a new chassis; that is accepted.
  - The strips' legs hang into an open channel. The first cradle had a deck with a 1.2 mm slot under each strip,
    and a soldered wire (1.3 mm) cannot pass through such a slot as the strip goes in.
  - A 3 mm yellow status LED on the TinyS3's IO6 sits under the display's right end, behind a clear LEGO 1×1 round
    tile pressed flush into the shell, its front sanded. The LED goes in from a pit that opens under the head. The
    top of the dock was not used, because the leaning head hides it from the seat. The centre of the front face was
    not used, because the pogo connector is directly behind it.
  - The Inkplate sits as it comes again: the USB-C, the power button and the microSD are in the right wall, and the
    wake button is in the left wall. The head takes its power from the pogo connector, so no opening has to face
    left. The thick wall is on the right, the head sits 5.3 mm left in its own frame, and the back-cover grille is
    over the ESP32 at the top of the board. The firmware's `kRotation` is 0.
  - With the head docked, the dock's side wall covers most of the head's USB-C opening. This is accepted: to flash
    the Inkplate by cable, lift the head off, and the cable powers it.
- **2026-09-17**, the wiring:
  - The head carries two wires: 5 V to the VIN pad and ground to the GND pad, the 4 × 4 mm pads on the top edge
    above the reset button. Each runs down the board in its own column to a lane along the bottom edge and onto the
    pogo male's cover-side row; each net is on two adjacent contacts joined by a bare bridge. VIN is Soldered's
    recommendation for this circuit ([forum thread 1934](https://community.soldered.com/t/externally-powering-the-inkplate-5v2-with-5v/1934));
    the 0.8 mm test pad TP11, the USB power line itself, was rejected as too small to solder safely.
  - The chain has one ground return, cable 1's GND conductor, and no second wire to the SCD41. The whole chain
    returns under 300 mA at worst (PM fan about 100 mA, SCD41 bursts about 200 mA) through 28 AWG: a few millivolts
    of ground shift, which I2C does not notice.
  - The dock's duct is the TinyS3's cradle channel, in layers: the joints on the 5V row's legs lowest, then the pogo pair,
    the AMS1117 pair, and the LED pair just under the board. Wires that travel together are bundles, so their bends
    are concentric. The AMS1117 moved 20 mm left with its pins pointing right, towards the socket that feeds it.
  - The USB-C module (item 77, measured) has one pad row on each face along its front edge, 1.5 mm tall: ten on
    top, with the single V pad and a wide end pad taken as ground, and nine underneath, whose 2.5 mm G pad lies on
    the holder. Each net therefore has one usable pad, and each pad takes one wire: a stub to a splice in the
    middle of the TinyS3's channel, where the wires are twisted end to end, soldered and heat-shrunk. The branches
    leave the splice from both ends: VBUS to the TinyS3's 5V leg, the AMS1117's IN and the pogo; GND to the
    TinyS3's GND leg, the LED, the AMS1117's GND and the pogo. No joint anywhere takes two wires, because a second
    wire on a joint melts the first. **Check with a meter that the wide end pad on the top face is ground** before
    soldering to it; if it is not, the GND stub moves to the G pad underneath and the holder needs a slot for it.
  - The pogo connector carries GND on the two contacts nearest the head's USB-C end and VBUS on the other two, so
    that in the dock the GND wire runs in front of the VBUS wire, on the side of its splice.
- **2026-09-18**, the top skin: one plane from the front edge to the rear. The first print had the skin flat over
  the cradle and sloping from D 37.7, so printed upside down only one of the two planes could lie on the bed, and
  the change of angle printed badly. Carrying the rear's 5.15° slope to the front edge puts the whole skin on the
  bed; the front rises from 30.5 to 33.9 mm and the wiring over the PM header gains 0.4 mm. Lowering the front
  instead was ruled out: the wire lanes over the header allow 0.5 mm at most.
- **2026-09-19**, the head tray: on the printed head nothing held the Inkplate and the cover in the tray, because
  the cover screws only to the Inkplate; held panel up, they dropped out of the back. The cover now hooks into the
  thin wall with two tongues and screws to the thick wall through two ears. A step for the cover's edge alone was
  tried first and held nothing: it and the bezel lip stop the same direction. Clips were ruled out because PLA+
  ridges wear. The ear screws sit in line with the standoff screws.
