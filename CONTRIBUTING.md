# Contributing to CANARY

This guide is for developers. To build a CANARY, read the [README](README.md).

## Where to look

| Task | Read |
|---|---|
| Run CANARY with no sensors and no board | [docs/simulator.md](docs/simulator.md) |
| Draw the pages, use the web UI, or add a page | [docs/pages.md](docs/pages.md) |
| Run the firmware on the boards, read their logs, or check the wiring | [docs/boards.md](docs/boards.md) |
| Test the firmware updates over the air | [docs/firmware-updates.md](docs/firmware-updates.md) |
| Change the wiring diagrams | [hardware/wiring/README.md](hardware/wiring/README.md) |
| Publish the images, or change the firmware builder | [docs/releases.md](docs/releases.md) |
| Learn how the firmware and the server work | [docs/architecture.md](docs/architecture.md) |
| Read or change the data that each board sends | [docs/readings.md](docs/readings.md) |

## Layout

CANARY uses [epd](https://github.com/chrisjtwomey/epd) for everything that is not about its sensors or its pages:
the client firmware, HTTP, the schedules and the rendering. A change to those goes into epd, with its tests.

```
platformio.ini            one environment per board, and a -dev twin of each that builds against an epd checkout
src/main.cpp              the display: fetches and draws the page, and deep-sleeps between wakes
src/dock/                 the dock: the TinyS3 that reads the sensors
src/defaults.example.cpp  copy to defaults.cpp: Wi-Fi, server URL, MQTT logging
server/
  server.py               config keys, a DataSource, a page list, DisplayServer(...).run()
  sources/                where the readings come from
  pages/                  the pages, one class each
  static/                 CSS, fonts, charts.js; the rendered HTML goes here too
  config.example.yaml
```

[docs/architecture.md](docs/architecture.md#the-repo) has the full tree.

Each board is a PlatformIO environment, and `build_src_filter` gives each one only its own files. No build flag
selects what a board runs, so code that the display does not compile cannot get into the display.

## Setup

```sh
python3 -m venv server/.venv && source server/.venv/bin/activate
pip install -r server/requirements-dev.txt   # the tools, and epd-server at its pinned release
```

The firmware takes epd from the PlatformIO registry, and the server takes `epd-server` from PyPI. `platformio.ini`
and `server/requirements.txt` pin both to the same release. So you need an epd checkout only to change epd.

### Working on epd

Put the epd checkout in a folder beside this repo.

- **Firmware.** Build the `-dev` twin of an environment: `esp32-dev`, `dock-dev`, `dock-mock-dev` or
  `dock-validate-dev`. A twin takes every setting from its board's environment, and takes epd from
  `symlink://../epd/firmware`. So nobody edits `platformio.ini` to work on epd.

  ```sh
  pio run -e esp32-dev
  PLATFORMIO_CORE_DIR=~/.platformio-canary-dock pio run -e dock-dev
  ```

  `PLATFORMIO_DEFAULT_ENVS=esp32-dev` in your shell makes a plain `pio run` build the twin.
- **Server.** Install the checkout editable, on top of the pinned release:

  ```sh
  pip install -e ../epd/server
  ```

  **Install the epd checkout last.** Each `pip install -r` puts the pinned release back when the checkout
  declares another version. Install the checkout again after each one. `pip freeze | grep epd` shows which one
  you have: a line that starts with `-e` is the checkout.

**The editor.** `pyrightconfig.json` points the editor at `server/.venv`, and adds `server/` and `../epd/server` to
the import path. It also type-checks `hardware/enclosure.py` against Fusion's API stubs. For the stubs, link
`.fusion-api` at the repo root to the `adsk/defs` folder of your Fusion install. On macOS:

```sh
ln -s "$HOME/Library/Application Support/Autodesk/webdeploy/production/Autodesk Fusion.app/Contents/Api/Python/packages/adsk/defs" .fusion-api
```

Without the link, only the `adsk` imports show as unresolved.

## Tests

```sh
pio test -e native            # the room, the mocks, the drivers, SensorSuite
cd server && pytest           # the server
```

## Building the dock

The dock builds in a PlatformIO folder of its own, `~/.platformio-canary-dock`. Give it in every dock command,
`dock-mock`, `dock-validate` and the `-dev` twins too:

```sh
PLATFORMIO_CORE_DIR=~/.platformio-canary-dock pio run -e dock -t upload
```

- The dock's `custom_sdkconfig` turns on automatic light sleep. The core's precompiled IDF libraries do not have it,
  so pioarduino compiles them again. It writes them into a package that all builds in the PlatformIO folder share,
  and the display then does not build in that folder. `scripts/dock_core.py` stops a dock build in `~/.platformio`
  before that happens.
- A dock project with its own `core_dir` does not work: `PLATFORMIO_CORE_DIR` overrides `core_dir`, and the builder
  image sets it for every build.
- The first build in the folder takes about 6 minutes, and the folder grows to about 7 GB. Later builds take about
  20 seconds.
- The dock does not light-sleep while its USB port is connected to a computer. To measure its current, disconnect
  the port's data lines.

## Making Changes

- Fork the repository, and make a new branch for your changes.
- Add a test for each behaviour that you add or change.
- Comments describe the present, not the change. Git holds the history.
- When you use AI tools, follow the [AI-Assisted Code](#ai-assisted-code) policy.

## AI-Assisted Code

If an AI tool (GitHub Copilot, Claude, or a similar tool) wrote your change, add a `Co-Authored-By` trailer that
names the tool to the commit message.

Example commit message:

```
Add new feature X

Co-Authored-By: Claude <noreply@anthropic.com>
```

## Submitting Pull Requests

- Make sure that your changes build and pass the tests.
- Open a pull request with a clear description of your changes.
- Give the related issues.
