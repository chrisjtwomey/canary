# Contributing to Inkplate 5 Environment Monitor

This project is at the design stage. The plan, and the status of the work
that makes it possible, is in [docs/EXTRACTION-PLAN.md](docs/EXTRACTION-PLAN.md).

## What it will be

A thin consumer of [epd](https://github.com/chrisjtwomey/epd), in the same
shape as [inkplate10-weather-cal](https://github.com/chrisjtwomey/inkplate10-weather-cal):

```
platformio.ini            -DARDUINO_INKPLATE5V2; lib_deps symlink://../epd/firmware
src/main.cpp              which IBoard to use
src/defaults.example.cpp  copy to defaults.cpp: WiFi, server URL, MQTT logging
server/
  server.py               config keys, a DataSource, a page list, DisplayServer(...).run()
  sources/                where the readings come from
  pages/                  the views, one class each
  static/                 CSS, fonts, charts.js; the rendered HTML lands here too
  config.example.yaml
```

Everything generic — the client firmware, HTTP, scheduling, rendering — is
epd. If a change is not about this device's sensors or pages, it goes there,
with its tests.

## Running it

No sensors and no board are needed to see the client work. Three ways, fastest
feedback first.

### 1. On your machine

`pio run -e sim` builds the client's sensor loop as a host binary: the same
`EnvModel`, the same mocks, the same `SensorSuite` the firmware runs —
everything but `Arduino.h`.

```sh
pio run -e sim
.pio/build/sim/program --help

.pio/build/sim/program                            # a day, five-minute samples, instantly
.pio/build/sim/program --start 17:00 --hours 4 --interval 600   # the evening: cooking spike, CO2 climb
.pio/build/sim/program --start 08:00 --hours 0.02 --interval 5  # the PM fan's 30 s warm-up
.pio/build/sim/program --speed 60                 # watch it unfold, a minute a second
.pio/build/sim/program --json --hours 0.01        # the JSON the device POSTs
```

The `sensors` column shows which parts reported: `T` temp/humidity, `C` CO₂,
`P` particulates, `G` gas. A dot means no reading — expected while the PM fan
warms up and between the SCD41's five-second conversions.

### 2. Host tests

```sh
pio test -e native            # room model, sensor mocks, SensorSuite protocol
```

### 3. The pages

The server renders the pages from the simulated room. It needs Chrome; on
macOS point Selenium at it:

```sh
export CHROME_BIN="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
cd server && source .venv/bin/activate && cp config.example.yaml config.yaml
python3 server.py --once                                   # every page -> server/*.png
python3 server.py --only comfort.png --at 2026-09-03T21:45  # one page, clock pinned
python3 server.py                                          # serve, follow the schedule
```

`epd_server` lives in `server/.venv` (see Setup), so activate it first or
run `.venv/bin/python server.py`.

`--at` pins the clock the room and the pages see, so a render is the same
every time and you can pick an interesting hour: the evening CO₂ climb
starts at 18:30, cooking spikes the particulates at 19:00, a window opens
at 22:00. (The room keeps UTC hours; local time is one hour later in
summer.)

The HTML is written to `server/static/<page>.html` beside its CSS, so open
it in a browser to iterate on layout without a render. The PNG is what the
panel shows: 1280×720, eight greys, dithered.

Selenium needs a chromedriver that matches Chrome. If a stale one is on
your PATH (Homebrew's, say) it is used and fails; `brew upgrade
chromedriver`, or take it off the PATH and Selenium fetches the right one.

#### Adding a page

Subclass `EnvPage` in `server/pages/`, set `title`, `stylesheet`,
`css_class` and `requires`, build the DOM in `body()`, and return chart
specs from `charts()`. Add it to `make_pages()` in `server.py`, give it a
stylesheet in `static/` keyed on `.page-<css_class>`, and a slot in
`display_schedule`. Layout units are `cqw`/`cqh`: 1% of the panel's width
and height.

Charts are drawn by `static/charts.js` with rough.js. A spec names its
`canvas` and `kind` (`sparkline`, `comfort`, `ribbon`, `axis`, `dotcloud`,
`scale`, `dial`, `meter`, `bars`) and carries plain data; the page computes
everything time-zone or unit related in Python, where it is tested.
`metrics.py` holds the derived values and the wording.

The pages: Breathe (CO₂), Comfort (temperature and humidity), Day (24 h
ribbons), Dust (particulates), Air (the VOC index), Barometer (pressure and
its tendency) and Diagnostics (the board's own report). The first six read
the simulated room; Diagnostics reads the `status` dataset, which is the
last document the board posted.

### 4. On the Inkplate, end to end

The board fetches the pages from the server and draws them; the mocks stand
in for the sensors. Three things to set up.

1. **Credentials.** Copy `src/defaults.example.cpp` to `src/defaults.cpp`
   (gitignored) and fill in the WiFi SSID and password. Point `serverURL`
   at the machine that runs the server, for example
   `http://192.168.1.20:8080/breathe.png`. On a Mac, `ipconfig getifaddr en0`
   prints its address.
2. **The server**, on the same network:

   ```sh
   cd server && source .venv/bin/activate && python3 server.py
   ```

   It renders every page at start, then one page a minute before each
   five-minute slot. macOS asks once whether Python may accept incoming
   connections; allow it.
3. **Flash and watch:**

   ```sh
   pio run -e esp32 -t upload
   pio device monitor -b 115200
   ```

The log shows the boot banner and User-Agent, WiFi and NTP, then
`downloading file at URL ...`, `drawing image from buffer` and
`next refresh in N s`. The panel shows the seven pages in turn, five
minutes apart on the wall clock (:00, :05, ...). Once a minute the board
posts a readings document to the server's `/readings`, with a `client`
object beside the measurements (`posted readings (204)`); the Diagnostics
page is drawn from the last one. A fetch that fails leaves the last image
on the panel and backs off (`back-off step N`).

`kRotation` in `src/main.cpp` is 0. If the image is upside down for the way
the board sits, set it to 2.

Swapping in real hardware means writing four drivers against the `IShtc3` /
`IScd41` / `IPmsa003i` / `IBme688` interfaces and clearing
`-DUSE_MOCK_SENSORS`; building without that flag is an `#error` naming them.

## Setup

epd must be checked out beside this repo. Then:

```sh
python3 -m venv server/.venv && source server/.venv/bin/activate
pip install -e ../epd/server        # the local kit, not the pushed branch
pip install -r server/requirements-dev.txt
```

Install the local `epd` checkout **editable**, and first. `requirements.txt`
pulls `epd-server` from GitHub at `@main`, which is right for a deployment
and wrong while developing both repos at once.

`pyrightconfig.json` at the repo root points the editor at that virtualenv
and adds `server/` and `../epd/server` to the import path, so Pylance
resolves `epd_server` and `sources.*`. Without it both show as unresolved
even though the tests pass, because Pylance does not read `pytest.ini`.

## Making Changes

- Please fork the repository and create a new branch for your changes.
- Add a test for every behaviour you add or change.
- Comments describe the present, not the change. Git holds the history.
- Follow the policy in the [AI-Assisted Code](#ai-assisted-code) section when AI tools are used.

## AI-Assisted Code

If your change was written by an AI tool (such as GitHub Copilot, Claude, or similar), add a `Co-Authored-By` trailer to the commit message naming the tool.

Example commit message:

```
Add new feature X

Co-Authored-By: Claude <noreply@anthropic.com>
```

## Submitting Pull Requests

- Ensure your changes build and pass tests.
- Open a pull request with a clear description of your changes.
- Reference any related issues.
