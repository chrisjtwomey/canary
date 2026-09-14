# Contributing to Inkplate 5 Environment Monitor

## Layout

A thin consumer of [epd](https://github.com/chrisjtwomey/epd), in the same
shape as [inkplate10-weather-cal](https://github.com/chrisjtwomey/inkplate10-weather-cal):

```
platformio.ini            -DARDUINO_INKPLATE5V2; lib_deps symlink://../epd/firmware
src/main.cpp              the awake loop: sensors, readings, the page loop
src/defaults.example.cpp  copy to defaults.cpp: WiFi, server URL, MQTT logging
server/
  server.py               config keys, a DataSource, a page list, DisplayServer(...).run()
  sources/                where the readings come from
  pages/                  the views, one class each
  static/                 CSS, fonts, charts.js; the rendered HTML lands here too
  config.example.yaml
```

[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) §5 has the whole tree.

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
those and for pressure, Day (24 h ribbons), and Diagnostics (the board's
own report). All but Diagnostics read the measurements: the simulated room
by default, or what the board has posted with `source.kind: store` in
`config.yaml`, which keeps them in `server/readings.db`. Before the first
reading, every one of those pages says "No readings yet." Diagnostics
reads the `status` dataset, the last document the board posted.

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
restart changes nothing. Day and Diagnostics ride along as pools of one;
leave a pool out of `order` to keep it off the panel. The weather calendar
uses the same block with `type: times` and one image per pool.

To review pages on the panel quickly, set `every: 20` in `config.yaml`
and restart the server; the board follows whatever it is told.

`site.altitude_m` in `config.yaml` reduces the pressure to sea level, as
forecasts quote it. The reading as measured stays under
`pressure_station_hpa`.

#### Firmware updates on the bench

The board flashes itself from the server. To watch it happen:

```sh
mkdir -p server/firmware
```

```yaml
client:
  firmware:
    enabled: true
    offer_dev_builds: true  # this project builds v0.1.0-dev, not a tag
```

Flash once over USB so the board stores its WiFi and server URL, then build
an image that claims a different version and drop it in:

```sh
pio run -e esp32 -t upload                       # v0.1.0-dev, the running image
cp src/defaults.cpp /tmp/defaults.real.cpp       # keep your credentials
cp src/defaults.example.cpp src/defaults.cpp     # CI builds have placeholders
sed -i "" 's/v0.1.0-dev/v0.2.0/' platformio.ini
pio run -e esp32
cp .pio/build/esp32/firmware.bin server/firmware/v0.2.0.bin
sed -i "" 's/v0.2.0/v0.1.0-dev/' platformio.ini  # put it all back
cp /tmp/defaults.real.cpp src/defaults.cpp
```

Press RST and watch the serial log: the offer, the progress, the restart,
`trial boot of v0.2.0`, and `firmware v0.2.0 confirmed`. The server log then
shows fetches carrying `v0.2.0`. The image had placeholder credentials, so
a WiFi connection at all proves the board read its own store.

To watch a bad image roll back, give the trial image a server it cannot
reach: set `serverURL` to `http://192.0.2.1:8080/breathe.png` before
building it. That address is reserved for documentation and never answers,
so every fetch fails. The board takes the image, fails three cycles, and
boots the previous one again.

It then refuses that version for good, so the next fetch logs `firmware
v0.3.0 is offered again; this board rolled back from it` rather than
looping. To try the same version number again, erase the board with
`pio run -e esp32 -t erase`, or build under a new one.

Leave `offer_dev_builds: false` anywhere real, or a bench board is flashed
back to the last release at its next fetch.

### 4. On the Inkplate, end to end

The board fetches the pages from the server, draws them, and reads the four
sensors over I2C. Three things to set up. See
[docs/HARDWARE.md](docs/HARDWARE.md) §8 for the wiring; `pio run -e
esp32-mock -t upload` builds the same firmware with the simulated room in
place of the sensors, for a board with nothing attached.

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
every five minutes on the wall clock (:00, :05, ...). Once a minute the board
posts a readings document to the server's `/readings`, with a `client`
object beside the measurements (`posted readings (204)`); the Diagnostics
page is drawn from the last one. A fetch that fails leaves the last image
on the panel and backs off (`back-off step N`).

A reading the server does not take waits on the SD card, or in PSRAM when
there is no card, and goes out again once the server answers: oldest first,
five after each live reading (`posting readings failed (-1); 12 held`, then
`sent 5 held readings; 7 still held`). The card holds two weeks of readings
and keeps them across a restart; PSRAM holds about 40 hours and loses them
to a power cut. The Diagnostics page shows the count as `unsent`.

`kRotation` in `src/main.cpp` is 2: the enclosure holds the board turned
180°, with the USB-C port on the left. A board that sits the other way up
needs 0.

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

A separate image that runs the bench routine instead of the awake loop. Use
it when the hardware is new or has been re-wired, and to take a current
capture: it has no network and no panel, so what the log shows is the
sensors and nothing else.

```sh
pio run -e esp32-validate -t upload
pio device monitor -b 115200
```

Every wake it scans the bus, checks each sensor running and in its low-power
state, takes one reading set, puts everything to sleep and deep-sleeps for
ten seconds. Then it does it again, so a capture can bracket the same
sequence as often as you like. A pass looks like this:

```
wakeup caused by external signal using RTC_IO.
##### Inkplate5V2 hardware validation #####
battery voltage: 4.09v   panel 27 C
i2c scan: 0x12 0x20 0x48 0x51 0x62 0x70 0x76 (7 devices)
[validate]       0 ms  phase 1: probing the bus
[validate] shtc3 present
...
[validate] summary: 0 failures, 0 warnings in 42000 ms
arming deep sleep timer wakeup in 15 seconds
sleeping for 10 seconds (RTC alarm at epoch 1757443210)
```

The phase markers carry milliseconds so a PPK2 trace lines up with the phase
it was taken in. Three things worth knowing when it does not pass:

- **A sensor is absent.** Its address is missing from the scan and it counts
  as a failure. The rest of the pass still runs.
- **The PM fan's SET line.** `PM still answers with SET low; SET wire not
  connected` is a warning, not a failure — the fan is simply not
  controllable, and every PM reading is still valid. docs/HARDWARE.md §8
  puts that wire on expander P1_3.
- **The RTC alarm.** The next boot should say `wakeup caused by external
  signal using RTC_IO` about ten seconds later. `wakeup caused by timer`
  after fifteen means the alarm did not reach GPIO 39, which Soldered does
  not guarantee on this board; the timer is armed as a backstop so the loop
  carries on either way.

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

## Releases

Publishing a GitHub release runs `.github/workflows/release.yaml`. It builds
`server/` into `ghcr.io/chrisjtwomey/inkplate5-env-monitor-server`, tagged
with the release's version (`0.2.0` and `0.2` for `v0.2.0`) and `latest`. No
release carries a firmware image: the firmware links Bosch's BSEC binary,
which this project does not hand out.

The image runs `python server.py` with the example config on port 8080.
Mount your own `config.yaml` at `/app/config.yaml`, and volumes at
`/app/data` and `/app/firmware` to keep the stores and the OTA images; point
`source.path` and `calibration.path` at `data/readings.db` and
`data/calibration.db`.

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
