# Contributing to CANARY

## Layout

A thin consumer of [epd](https://github.com/chrisjtwomey/epd), in the same
shape as [inkplate10-weather-cal](https://github.com/chrisjtwomey/inkplate10-weather-cal):

```
platformio.ini            one environment per board; lib_deps symlink://../epd/firmware
src/main.cpp              the head: the awake loop over sensors, readings and the page loop
src/dock/                 the dock: the TinyS3 that reads the sensors
src/defaults.example.cpp  copy to defaults.cpp: WiFi, server URL, MQTT logging
server/
  server.py               config keys, a DataSource, a page list, DisplayServer(...).run()
  sources/                where the readings come from
  pages/                  the views, one class each
  static/                 CSS, fonts, charts.js; the rendered HTML lands here too
  config.example.yaml
```

[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) §5 has the whole tree.

Each board is a PlatformIO environment, and each compiles its own files
through `build_src_filter`: `esp32` takes everything but `src/dock/`, `dock`
takes `src/dock/`. No build flag decides what a board runs, so code the head
does not compile cannot reach the head.

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
pio test -e native            # room model, sensor mocks, drivers, SensorSuite protocol
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

While the server runs, `http://localhost:8080/web/` shows every page in a
browser, built from the readings when it is asked for, and reloads it every
minute; the arrow keys step through them. `/web/explore` draws one
measurement over any window: pick a window, drag the chart to move through
time, scroll or pinch to zoom. It asks `GET /history` for each window, which
answers with the chart spec `charts.js` draws.

`/web/config` shows `config.yaml` as a form in tabs, and as text in the YAML
tab for the keys the form does not show. The form keeps the file's comments
and layout. Check tests an edit as the server tests the file when it starts;
Save and restart lists the changes, keeps the old file as `config.yaml.bak`,
writes the new one, and restarts the server on it. Restore puts the `.bak`
back. With the file mounted into a container on its own, the `.bak` stays
inside the container and goes when the container is recreated. The page has
no login yet, so anyone who can reach the server can change its config.

The Storage tab downloads each store as a file, one JSON document a line,
and takes such a file back. A store keeps a document under its board and its
time, so an import adds what is missing and asks before it puts anything
over what is held.

Selenium needs a chromedriver that matches Chrome. If a stale one is on
your PATH (Homebrew's, say) it is used and fails; `brew upgrade
chromedriver`, or take it off the PATH and Selenium fetches the right one.

#### Adding a page

Subclass `EnvPage` in `server/pages/`, set `title`, `stylesheet`,
`css_class` and `requires`, build the DOM in `body()`, and return chart
specs from `charts()`. Add it to `make_pages()` in `server.py`, give it a
stylesheet in `static/` keyed on `.page-<css_class>`, and a slot in
`display.pools`. Layout units are `cqw`/`cqh`: 1% of the panel's width
and height.

Charts are drawn by `static/charts.js` with rough.js. A spec names its
`canvas` and `kind` (`sparkline`, `comfort`, `ribbon`, `axis`, `dotcloud`,
`scale`, `dial`, `meter`, `bars`) and carries plain data; the page computes
everything time-zone or unit related in Python, where it is tested.
`metrics.py` holds the derived values and the wording.

The pages: Breathe (CO₂), Comfort (temperature and humidity), Dust
(particulates), Air (the VOC index), a trace and a delta page for each of
those and for pressure, Day (24 h ribbons), and three Diagnostics pages
(each board's own report now, both boards over the day, and the dock's
sensor health over the day). All but Diagnostics read the measurements: the
simulated room by default, or what the board has posted with `source.kind:
store` in `config.yaml`, which keeps them in `server/sensor-readings.db`. Before
the first reading, every one of those pages says "No readings yet."
Diagnostics reads the `status` dataset, the last document each board
posted, and the reports of the day behind it.

A metric's *pool* is its main page plus two pages of the same two shapes,
both in `pages/pool.py` and driven by a `Metric` spec: `TracePage`, the
value now with three days behind it and the thresholds as dashed lines;
and `DeltaPage`, the change over a short window, a column showing where
the value stood, and a sentence on what such a change usually means.

The `display` block in `config.yaml` has two parts. `pools` is what can
show: named lists of images, each read in turn on its own count from a
random start that moves every `reshuffle_hours`, so a pass is never all of
one shape. `schedule` is when: `type: interval` visits the pools in `order`
every `every` seconds. The randomness is seeded from the clock, so a
restart changes nothing. Day rides along as a pool of one, and Diagnostics
as a pool of its three pages; leave a pool out of `order` to keep it off the
panel. The weather calendar uses the same block with `type: times` and one
image per pool.

To review pages on the panel quickly, set `every: 20` in `config.yaml`
and restart the server; the board follows whatever it is told.

`site.altitude_m` in `config.yaml` reduces the pressure to sea level, as
forecasts quote it. The reading as measured stays under
`pressure_station_hpa`.

#### Firmware updates on the bench

Both boards flash themselves from the server. Each is offered the newest
image of its own product that can work with the server's version: the same
major and minor while the major is 0. A server run from a checkout reports
what `git describe` says, `v0.3.1-51-gab12cd4` say, so it offers development
builds, and an image in the v0.3 line is offered and one in v0.4 is not. To
watch it happen:

```sh
mkdir -p server/firmware/canary-head server/firmware/canary-dock
```

```yaml
client:
  firmware:
    enabled: true
```

Flash each board once over USB, so it stores its WiFi and server URL. Then
commit a change, and put each board's build of it in the folder, named by
its version:

```sh
pio run -e esp32 -t upload && pio run -e dock -t upload
v=$(git describe --tags --match 'v*' --dirty)
pio run -e esp32 && cp .pio/build/esp32/firmware.bin server/firmware/canary-head/$v.bin
pio run -e dock && cp .pio/build/dock/firmware.bin server/firmware/canary-dock/$v.bin
```

The file's name must be the `CLIENT_VERSION` the build prints, and the
server offers the build furthest past the tag. Commit before each build: a
tree with uncommitted changes builds `...-dirty`, two builds of one commit
share one version, and a board already on a version is not offered it
again.

The head takes the image after its next page, the dock after the next batch
of readings the server takes with its queue empty; its LED pulses brighter
and faster as the image is written. The serial log shows the offer, the
progress, the restart, `trial boot of v0.3.1-52-gcd34ef5`, and `firmware
v0.3.1-52-gcd34ef5 confirmed` once the head has drawn a page or the server
has taken the dock's readings.

To watch a bad image roll back, give the trial image a server it cannot
reach: set `serverURL` in `src/defaults.cpp` to
`http://192.0.2.1:8080/breathe.png` before building it. That address is
reserved for documentation and never answers. The board takes the image,
fails three times, and boots the previous one again.

It then refuses that version for good, so the next offer logs `firmware
v0.3.1-52-gcd34ef5 is offered again; this board rolled back from it` rather
than looping. To try the same version again, erase the board with
`pio run -e esp32 -t erase` (or `-e dock`), or commit again for a new one.

To watch a board go back to the server's line, build an image under a tag
the server's line is behind, flash it over USB, and leave the older image in
the folder: the server offers it, logs that it is offering an older image,
and logs that the board went back to it.

A server past a tag moves every board to the newest image in the folder: a
board flashed over USB with a build the folder does not hold is offered the
folder's newest at its next request, even an older one. A tagged server
offers only to boards on a tagged build, and leaves the others alone.

### 4. On the Inkplate, end to end

Two boards: the head (`esp32`) fetches the pages from the server and draws
them; the dock (`dock`) reads the four sensors over I2C and posts them.
Three things to set up. See [hardware/assembly.md](hardware/assembly.md) for the
wiring; `pio run -e dock-mock -t upload` builds the dock's firmware with the
simulated room in place of the sensors, for a board with nothing attached.

1. **Credentials.** Copy `src/defaults.example.cpp` to `src/defaults.cpp`
   (gitignored) and fill in the WiFi SSID and password. Point `serverURL`
   at the machine that runs the server, for example
   `http://192.168.1.20:8080/breathe.png`. On a Mac, `ipconfig getifaddr en0`
   prints its address.

   An SD card can carry the same settings instead. Copy
   [docs/config.yaml](docs/config.yaml) to the root of the card. The board
   reads it after the built-in settings and its own store, so the card wins.
   One image then serves boards on different networks.
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
`next refresh in N s`. The panel works through the pools in turn, one page
every five minutes on the wall clock (:00, :05, ...). A fetch that fails
leaves the last image on the panel and backs off (`back-off step N`).

The dock takes a reading 35 s after boot, once the PM fan has warmed up,
and then on each of the server's slots (`posts` in `config.yaml`). It
queues a readings document, with a `client` object beside the
measurements, and the loop posts the queue to the server's
`/sensor-readings` (`posted 1 reading (200); 0 queued`); the Diagnostics page is
drawn from the newest. While the server is down the queue grows
(`posting readings failed (-1); 12 queued`), and once it answers the dock
sends up to 100 a request until the queue is empty. The queue is 2 MB of
PSRAM, about five days of readings, and a restart empties it. The
Diagnostics page shows the count against the queue's capacity under Memory
(`queue 12 of ~1,500, in psram`), and its trace page draws it over the day.

`kRotation` in `src/main.cpp` is 0: the enclosure holds the board as it
comes, with the USB-C port on the right. A board mounted turned 180° needs
2.

#### Which sensors answered

`sensor start incomplete: shtc3=1 scd41=0 pm=1 bme688=1` names the parts
that did not start, and the Diagnostics page carries the same flags. A zero
is one of three things: the part is not on the bus, its address is taken, or
it answered something that is not that part — the SHTC3 and the BME688 both
check what they are talking to before saying yes.

A part that did not start is tried again 30 s later, then after twice the
last wait each time, up to ten minutes, so plugging it in brings it up
without a restart. A part that misses three samples in a row, over at least
15 s, has stopped — unplugged, or back from a power cut without its
settings — and is started again the same way. The log says `sensor scd41
stopped; starting it again`, then `sensor scd41 running`, and the
Diagnostics page follows.

Readings are dropped, not invented, so the first minute after a boot looks
sparse on purpose: the SCD41's first five-second conversion has not landed,
and the PM counts mean nothing until the fan has run for thirty seconds. The
board drives the fan's SET line high when it starts the sensors, and the
thirty seconds count from then. Without a wire on SET the fan has run since
power-on, so the wait is longer than it needs to be, never shorter.

`iaq` and `iaq_accuracy` come from BSEC, Bosch's closed-source library,
which runs in a task of its own and takes a sample every 3 s. Its accuracy
starts at 0 and reaches 3 in about 40 minutes on the bench. What it has
learned is saved to NVS when the accuracy first reaches 3 and every six
hours after, so a restart resumes from there (`[bsec] start: NVS state
(accuracy 3)`). Every BSEC line in the log starts with `[bsec]`. The
Diagnostics page shows the accuracy and the count of late samples;
`gas_ohm` is the raw plate resistance either way.

#### Swapping the mocks for the sensors, in code

`src/main.cpp` names a concrete sensor type in one `#if` block and nowhere
else. The drivers take an `II2cBus` and an `IClock`, so they are host-tested
in `test/test_drivers` against parts that answer the bus the way their
datasheets describe. The BME688's compensation is Bosch's own C API, in
`lib/bme68x`.

### 5. Validating the wiring

A separate image that runs the bench routine instead of the dock's awake loop.
Use it when the hardware is new or has been re-wired, and to take a current
capture: it has no network and no server, so what the log shows is the
sensors and nothing else.

```sh
pio run -e dock-validate -t upload
pio device monitor -b 115200
```

Every pass it scans the bus, checks each sensor running and in its low-power
state, takes one reading set and puts everything back to sleep; ten seconds
later it does it again, so a capture can bracket the same sequence as often
as you like. A pass looks like this:

```
##### canary-dock hardware validation #####
Client version: 0.6.0
i2c timeout 50 ms; SDA IO8, SCL IO9, PM fan SET IO7
i2c scan: 0x12 0x62 0x70 0x76 (4 devices)
[validate]       0 ms  phase 1: probing the bus
[validate] shtc3 present
...
[validate] summary: 0 failures, 0 warnings in 42000 ms
```

The phase markers carry milliseconds so a PPK2 trace lines up with the phase
it was taken in. Three things worth knowing when it does not pass:

- **A sensor is absent.** Its address is missing from the scan and it counts
  as a failure. The rest of the pass still runs. The four the dock should
  show are the PM module at 0x12, the SCD41 at 0x62, the SHTC3 at 0x70 and
  the BME688 at 0x76.
- **The PM fan's SET line.** `PM still answers with SET low; SET wire not
  connected` is a warning, not a failure — the fan is simply not
  controllable, and every PM reading is still valid. It is the TinyS3's pin
  7 (hardware/assembly.md).
- **Nothing sleeps.** The serial port is on the board's own USB, which a deep
  sleep would drop mid-bench, so the board stays up between passes. The first
  pass waits up to three seconds for the host to open the port; if the head
  of the log is still missing, start the monitor before plugging the board in.

## Setup

epd must be checked out beside this repo. Then, in this order:

```sh
python3 -m venv server/.venv && source server/.venv/bin/activate
pip install -r server/requirements-dev.txt   # the tools, and epd-server at its pinned tag
pip install -e ../epd/server                 # then the local kit, editable, on top
```

`requirements.txt` pins `epd-server` to a release tag on GitHub, which is
right for a deployment and for the server image, and wrong while developing
both repos at once. The order matters: pip treats that pin as a direct
reference, so any `pip install -r` replaces an editable epd with the tagged
release, whatever the two versions are. Install the checkout last, and again
after any later `pip install -r`. `pip freeze | grep epd` shows which one is
in: a line starting `-e` is the checkout.

`pyrightconfig.json` at the repo root points the editor at that virtualenv
and adds `server/` and `../epd/server` to the import path, so Pylance
resolves `epd_server` and `sources.*`. Without it both show as unresolved
even though the tests pass, because Pylance does not read `pytest.ini`.

It also type-checks `hardware/enclosure.py` against Fusion's API stubs, read
from `.fusion-api` at the repo root. Link that name to the `adsk/defs` folder
of your Fusion install; on macOS:

```sh
ln -s "$HOME/Library/Application Support/Autodesk/webdeploy/production/Autodesk Fusion.app/Contents/Api/Python/packages/adsk/defs" .fusion-api
```

Without the link, only the `adsk` imports show as unresolved.

## The wiring diagrams

The circuit drawings in `hardware/images/` are generated, not painted.
[hardware/wiring/](hardware/wiring/) holds it as one YAML file per run of
wire, which [WireViz](https://github.com/wireviz/WireViz) turns into a harness
drawing. Edit the YAML, never the PNG.

```sh
pip install wireviz          # and graphviz: brew install graphviz
hardware/wiring/render.sh    # rewrites the drawings in hardware/images/
```

`render.sh` takes WireViz's Graphviz source, turns the layout top to bottom
and runs `dot` itself. WireViz's own left-to-right layout gives a strip too
wide and too short to read on a page.

**Keep each drawing near 1200 px.** That is what stays legible at page width.
One run of wire per file does it; the whole circuit in one file does not, and
neither does a chain of four identical cables — say that in a sentence
instead.

**Every wire gets a colour, and never `WH`.** White draws as a white line on
a white page, which reads as no wire at all. Red is a supply, black is ground,
blue and yellow are SDA and SCL; anything else picks a colour that stands out.

The same joints are listed in `hardware/assembly.md`, under "Appendix:
every joint". Change one and change the other.

## Releases

Every push to `main` runs `.github/workflows/release.yaml`. It builds
`server/` into `ghcr.io/chrisjtwomey/canary-server` and `firmware-builder/`
into `ghcr.io/chrisjtwomey/canary-firmware-builder`, both tagged `latest`
and stamped with what `git describe` says. Publishing a GitHub release adds
the release's version tags (`0.3.0` and `0.3` for `v0.3.0`).

No image carries firmware: the firmware links Bosch's BSEC binary, which
this project does not hand out. The firmware-builder image carries the
firmware's sources instead, at its commit, and builds them where it runs.
When it starts, it builds the head's and the dock's firmware of its own
version into the folder the server offers images from, as
`canary-head/<version>.bin` and `canary-dock/<version>.bin`, and then waits.
Images already in the folder stay: a server offers the one its version calls
for, which may be an older one.

Run the builder beside a server of the same tag. A pair on `latest` moves
the boards with every push, because a server past a tag offers development
builds; a pair on `0.3.1` keeps them on that release. The one USB flash a
board needs, with your own `src/defaults.cpp`, is `pio run -e dock -t upload`
(`-e esp32` for the head) from a checkout of the version the server runs.

The server image runs `python server.py` with the example config on port
8080. Mount your own `config.yaml` at `/app/config.yaml`, and volumes at
`/app/data` and `/app/firmware` to keep the stores and the OTA images; point
`source.path`, `calibration.path`, `status.path` and `logs.path` into
`data/`, or those stores are lost with the container. `docker-compose.yml`,
at the repo root, runs both images this way, with `server/config.yaml` as
the config and `server/firmware/` as the firmware directory.

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
