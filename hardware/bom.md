# Bill of materials

What to buy for one CANARY. The parts cost about €220, and two thirds of that is the panel and the two Adafruit
sensors. The prices are what the makers asked in September 2026, before tax and delivery. Use them to plan, not to
order.

- [enclosure.md](enclosure.md) has the printed parts and the fasteners.
- [assembly.md](assembly.md) builds the device.
- [parts.md](parts.md) has the datasheet facts for each part.

## What to buy

| Part | Qty | Where | Rough cost |
|---|---|---|---|
| Soldered Inkplate 5 Gen2 (333333) | 1 | [soldered.com](https://soldered.com/products/inkplate-5-gen2) | €75 |
| Unexpected Maker TinyS3 (ESP32-S3, 8 MB PSRAM) | 1 | [unexpectedmaker.com](https://unexpectedmaker.com/shop.html), Adafruit 5398, Pimoroni | €20–35 |
| Adafruit PMSA003I (4632) | 1 | [adafruit.com](https://www.adafruit.com/product/4632) | $45 |
| Adafruit SCD-41 (5190) | 1 | [adafruit.com](https://www.adafruit.com/product/5190) | $50 |
| Soldered BME688 (333203) | 1 | [soldered.com](https://soldered.com/products/bme688-environmental-sensor) | €21 |
| Soldered SHTC3 (333032) | 1 | [soldered.com](https://soldered.com/products/temperature-and-humidity-sensor-shtc3-breakout) | €6 |
| AMS1117-3.3 module | 1 | any marketplace, sold in tens | under €1 each |
| USB-C female breakout, 24-pin, 15 × 14.5 mm | 1 | any marketplace, sold in fives or tens | about €1 each |
| 8-pin magnetic pogo pair, 2.3 mm pitch, panel mount | 1 | any marketplace | €3–6 |
| Qwiic / easyC cable: 45 mm, 30 mm, 40–45 mm, plus one to cut up | 4 | Soldered, Adafruit, SparkFun | €1–2 each |
| Single-row female header strip, 20-way, standard height | 2 | any marketplace | pennies |
| Dupont housing, 1-pin, with crimp contact | 8 | any marketplace, sold in kits | pennies |
| 3 mm diffused yellow LED | 1 | any marketplace | pennies |
| Resistor, ¼ W: 1 kΩ ×1, 5.1 kΩ ×2 | 3 | any marketplace | pennies |
| LEGO 1×1 round tile, clear (35380 / 98138) | 1 | BrickLink, or a spare brick | pennies |
| 28 AWG stranded wire, heat-shrink, glue | — | — | — |
| 5 V USB power supply, 2 A, and its cable | 1 | any | €10 |
| M3 brass heat-set insert, about 5.7 mm long, 4.6 mm outside diameter | 6 | any marketplace | pennies |
| M3 × 8 countersunk screw, 90° | 4 | any marketplace | pennies |
| M3 × 6 machine screw | 6 | any marketplace | pennies |
| M2 × 4 self-tapping screw, pan head | 4 (8 fills every hole) | any marketplace | pennies |
| M2.5 × 4 self-tapping screw | 4 (8 fills every hole) | any marketplace | pennies |
| Filament: PLA+, and a little white for the logo | — | — | — |

- **Buy these exact boards.** The printed parts are drawn around them, the pogo pair and the USB-C module. A
  different board needs its pocket, bosses or opening changed in `enclosure.py`. The wire, headers, resistors, LED
  and supply are ordinary stock.
- **Use a 2 A supply.** A computer's USB-A port gives 0.5–0.9 A. At power-on the device takes 1.07 A for 0.06 ms,
  and at boot up to 750 mA.
- **The two 5.1 kΩ resistors** make a USB-C to USB-C cable or a USB-C charger turn on its 5 V. A USB-A to USB-C
  cable does not need them: its plug has the resistor, and a USB-A port always gives 5 V.

## The small parts

- **AMS1117-3.3 module.** It gives the sensors their 3.3 V. The TinyS3's own regulator cannot carry them
  ([parts.md](parts.md#ams1117-33--the-sensors-33-v)).
  - Buy the plain 3-pin module with no mounting holes, 12.5 × 8.5 mm. Its pocket is drawn to that size.
  - Its pins are **GND, OUT, VIN** along the header. OUT is the middle pin on every one of these boards, so the
    silkscreen on the board in your hand tells the two ends apart. Do not trust a drawing.
  - **5 V on the GND pin destroys the part in seconds.** Nothing protects it.
- **USB-C female breakout, 24-pin.** The dock's only power input, and its only opening in the rear wall. The
  dock uses only two pads: V, and the wide end pad as ground. [assembly.md](assembly.md#4-the-usb-c-socket) tells
  you to check the ground pad with a meter.
- **8-pin magnetic pogo pair.** It connects the display to the dock. Four contacts carry power, and four are not
  used. Each 0.5 mm pin carries about 1 A *(measured)*. The magnets hold the display down, and the shape of the
  contact block stops a display that is turned end for end.
- **Status LED.** A 3 mm diffused yellow LED, through a 1 kΩ resistor, behind a clear LEGO 1×1 round tile in the
  front of the shell.
- **Headers, housings and wire.** Two 20-way female strips, cut to 12 and 11 ways, hold the TinyS3 in its cradle.
  Eight 1-pin Dupont housings go on the PM board's 7-pin header and the AMS1117's pins. All other connections are
  28 AWG stranded wire, twisted and soldered into two splices under heat-shrink.

## Alternatives

| Part | What else would do |
|---|---|
| Inkplate 5 Gen2 | No drop-in. A different panel changes the display tray, the window and the frames, and the firmware needs an `IBoard` for it. |
| TinyS3 | An ESP32-S3 board with PSRAM and USB-C. Not the ProS3: its second regulator would put the SCD41 on the processor's rail. A different board changes the cradle and the pin table. |
| SCD41 | A Sensirion SCD4x breakout, or the SCD40, which costs less and is less accurate. Soldered sell an SCD43, which is a drop-in chip and more accurate, but its holes and sockets are in different places, so the chassis must change. |
| PMSA003I | The Plantower PMS5003 is the same sensor with a UART, not I²C, so it needs a serial port and its own driver. The Sensirion SPS30 is a better sensor. |
| BME688 | Adafruit 5046 is the same sensor on a STEMMA QT board. A BME680 fits the sockets and gives the same chip ID, but BSEC's gas index is different, so check the variant byte. |
| SHTC3 | Adafruit 4636, or an SHT4x breakout: a better part, which needs its own driver. |
| AMS1117-3.3 module | A 3.3 V regulator that takes 5 V in and carries 500 mA. A small buck module would not make the 0.37 W of heat that this LDO makes, but it needs its own pocket. |
| Magnetic pogo pair | An 8-pin pair with the same outline and pitch. The tray, the plinth and the key shape are drawn to this one. |
| LEGO tile | A clear 8 mm disc, or a drop of clear resin, sanded on the front. |
