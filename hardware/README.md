# Hardware

CANARY has two halves in one desk enclosure:

- The **display** is an Inkplate 5 Gen2: a 5.2" e-paper panel, tilted 20° back. It shows the pages that the server
  draws.
- The **dock** is a TinyS3 with four sensors: CO₂, particulates, temperature and humidity, and gas. It reads the
  room and sends the readings to the server.

The display stands in the dock. An 8-pin magnetic connector carries 5 V up to it, and it is the only connection
between the two halves. One USB-C cable into the dock powers both.

On the desk, it is 150.7 mm wide, 87.3 mm deep and 89.8 mm tall.

![The finished device](images/device.png)

| Doc | What it tells you |
|---|---|
| [bom.md](bom.md) | The parts to buy, what else would do, and the cost. |
| [parts.md](parts.md) | The datasheet facts for each part, and the power and the I²C bus. For developers. |
| [assembly.md](assembly.md) | How to build it, step by step, with a picture for each step. |
| [enclosure.md](enclosure.md) | The design of the printed parts, for a person who changes the model. |

| In this folder | What it holds |
|---|---|
| `stl/`, `3mf/` | The five printed parts, in print orientation. |
| `step/` | The same parts as STEP, each upright in its own frame. |
| `enclosure.py` | The design: a Fusion script that places each board and builds each part from the numbers in `enclosure.md`. |
| `canary-logo.svg` | The logo's outline in millimetres. The script imports it. |
| `canary-logo-screen.svg` | The logo as drawn, with no changes for printing. The display's splash screen uses it. |
| `images/` | Views of the model, and the wiring drawings, for the guides. |
| `wiring/` | The circuit as YAML, one file for each run of wire ([wiring/README.md](wiring/README.md)). |
| `logo/` | The source picture, and the script that traced it. |
