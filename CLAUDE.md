# CANARY

## This repo

- A thin consumer of [epd](https://github.com/chrisjtwomey/epd). The display builds against EpdClient and EpdBoardInkplate (`-DARDUINO_INKPLATE5V2`), and the dock against EpdClient alone. The server (`server/`) is its data sources, a page list and `DisplayServer(...).run()`. [docs/architecture.md](docs/architecture.md) has the layout.
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
| Uses or changes the simulated room, the mock sensors or `pio run -e sim` | [docs/simulator.md](docs/simulator.md) |
| Changes a page, the web UI, the config page or the pools | [docs/pages.md](docs/pages.md) |
| Runs the firmware on a board, reads a board's log, or checks the wiring | [docs/boards.md](docs/boards.md) |
| Changes or tests the updates over the air | [docs/firmware-updates.md](docs/firmware-updates.md) |
| Changes the release workflow, the images or the firmware builder | [docs/releases.md](docs/releases.md) |
| Needs the overview of the firmware and the server, or the repo tree | [docs/architecture.md](docs/architecture.md) |
| Changes the dock's loop, its clock, the readings queue or the sensor code | [docs/dock.md](docs/dock.md) |
| Changes the display's wakes, its notices or its splash screen | [docs/display.md](docs/display.md) |
| Changes the page schedule, the dock's schedule or the display's sync | [docs/schedules.md](docs/schedules.md) |
| Changes the status LED | [docs/led.md](docs/led.md) |
| Changes a header, `/about`, the version rule or the updates over the air | [docs/versions.md](docs/versions.md) |
| Changes a dock setting or the recalibration | [docs/dock-settings.md](docs/dock-settings.md) |
| Changes the JSON that the boards post | [docs/readings.md](docs/readings.md) |
| Looks for a file in `hardware/` | [hardware/README.md](hardware/README.md) |
| Changes what to buy, or an alternative part | [hardware/bom.md](hardware/bom.md) |
| Touches a datasheet fact, the power budget or the I²C bus | [hardware/parts.md](hardware/parts.md) |
| Changes a build step, the circuit or a connection | [hardware/assembly.md](hardware/assembly.md) |
| Changes the wiring drawings | [hardware/wiring/README.md](hardware/wiring/README.md) |
| Changes the printed parts, the fit, the fasteners or the model's rules | [hardware/enclosure.md](hardware/enclosure.md) |

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

## UX writing

Use UX writing (microcopy) when you write words into an interface.

People learn the words of an interface from the other apps they use. A familiar word lets them act without reading
further. A word from the code makes them stop and guess. So the interface uses the common word, even where the code
has a more exact one:

- "Delete", not "Purge".
- "Download", not "Export the store".
- "4 records already exist", not "4 keys collide in the store".
- "Try again", not "Re-send the POST".

Ask yourself: "Would a person who has never seen the code understand this at a glance?" If not, use the words that other apps use for the same thing, and keep the code's words in the code.
