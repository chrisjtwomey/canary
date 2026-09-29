# CANARY

## This repo

- A thin consumer of [epd](https://github.com/chrisjtwomey/epd): the firmware (`src/`, `include/`) builds with `-DARDUINO_INKPLATE5V2` against epd's two libraries, and the server (`server/`) is its data sources, a page list and `DisplayServer(...).run()`. [docs/architecture.md](docs/architecture.md) has the layout.
- epd must be checked out beside this repo.
- The two boards are **the display** (the Inkplate) and **the dock** (the TinyS3), in code, docs and anything a person reads. Never "the head".
- Build the dock only with `PLATFORMIO_CORE_DIR=~/.platformio-canary-dock`, for `dock`, `dock-mock` and `dock-validate`.
- In `server/.venv`, install the editable epd last: `pip install -e ../epd/server` after any `pip install -r`.

## Docs

Each doc covers one area. Read a doc only when the task needs it.

| When the task | Read |
|---|---|
| Sets up the venv, runs the tests, or builds the dock | [CONTRIBUTING.md](CONTRIBUTING.md) |
| Changes how a builder deploys the server or flashes a board | [README.md](README.md) |
| Uses the simulated room or `pio run -e sim` | [docs/simulator.md](docs/simulator.md) |
| Changes a page, the web UI, the config page or the pools | [docs/pages.md](docs/pages.md) |
| Runs the firmware on a board, reads a board's log, or checks the wiring | [docs/boards.md](docs/boards.md) |
| Changes or tests the updates over the air | [docs/firmware-updates.md](docs/firmware-updates.md) |
| Changes the release workflow, the images or the firmware builder | [docs/releases.md](docs/releases.md) |
| Changes the firmware or server design: wire headers, LED, version gate, notices | [docs/architecture.md](docs/architecture.md) |
| Changes the JSON that the boards post | [docs/readings.md](docs/readings.md) |
| Looks for a file in `hardware/` | [hardware/README.md](hardware/README.md) |
| Changes what to buy, or an alternative part | [hardware/bom.md](hardware/bom.md) |
| Touches a datasheet fact, the power budget or the I²C bus | [hardware/parts.md](hardware/parts.md) |
| Changes a build step, the circuit or a connection | [hardware/assembly.md](hardware/assembly.md) |
| Changes the wiring drawings | [hardware/wiring/README.md](hardware/wiring/README.md) |
| Changes the printed parts, the fit, the fasteners or the model's rules | [hardware/enclosure.md](hardware/enclosure.md) |

The hardware docs carry no open questions of their own: they are below, so those docs inform a reader and
this file holds what is still being decided.

Before each commit:

1. For each staged file, name the doc that covers it.
2. Search that doc for each name, number and behaviour the change touches. Fix stale lines.
3. Write a design choice into that doc as how it works now, with the reason for it.
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

## Words in the interface

**A page says what other web interfaces say. Our words are for the code.**

- The code has a store that holds a document under a key. The page says `4 of 4 records already exist`, and the button says `Replace`.
- Use the word the rest of the web uses for the act: Download, Upload, Replace, Delete, Cancel.
- A label, a button and a message are a few words each. Nothing explains the design.

Ask yourself: "Is this the language I would expect from a web interface?" If it is not, it belongs in the code, not on the page.

## Open hardware questions

Unsettled, and each one names what would settle it.

1. **PMSA003I input current at 3.3 V** is derived from the charge-pump datasheet, not measured. Measure; it sets the regulator's rating.
2. **5 V on the Inkplate's VIN pads**, on the bench, with no battery connected: measure VIN and the battery connector, and check that the charger chip stays cool through a few refreshes. Soldered say the path is harmless ([assembly.md](hardware/assembly.md#9-the-display)); this confirms it on this board.
3. **Pull-ups on the TinyS3's bus.** [parts.md](hardware/parts.md#pull-ups) assumes the board adds none. Measure SDA and SCL to 3.3 V with the sensors unplugged.
4. **What the BME688 board's JP2 joins** ([parts.md](hardware/parts.md#bme688--voc-gas-and-pressure)). Soldered's docs say only that it powers the regulator from 5 V, and no schematic is public. A continuity check across JP2, or the hardware files Soldered sends on request, would settle it.
5. **Pogo contact resistance.** The connector's listing gives none, so [assembly.md](hardware/assembly.md#7-the-pogo-connector) assumes 30–100 mΩ. Measure across a mated pair with ~200 mA flowing.
6. **Flash size** of the Inkplate's ESP32-WROVER-E: 4, 8 or 16 MB by variant, and the module's shield prints no suffix. `esptool.py flash_id` over USB settles it; it resets the board.

