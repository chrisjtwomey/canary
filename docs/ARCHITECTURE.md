# Architecture — where CANARY departs from the kit, and how

How this device differs from the weather calendar that [epd](https://github.com/chrisjtwomey/epd)
came out of, and what it builds on the kit. [the hardware docs](../hardware/README.md) have the numbers; the
[Decision Log](#decision-log) has the history.

## 1. What the kit assumes

`epd` was extracted from a weather calendar, and its client model is that
device's: **wake, fetch a PNG, draw it, deep-sleep until the server says.**
The client is dumb and battery-powered. All data lives server-side. The
server decides *when* (`Canary-Next-Display-Refresh-Seconds`) and *what*
(`Canary-Next-URL`) from a daily list of wall-clock times.

## 2. What is different here

| | Weather calendar | Env monitor |
|---|---|---|
| Power | LiPo, years | **USB mains** ([hardware/bom.md](../hardware/bom.md)) |
| Data origin | server fetches from APIs | **the device holds the sensors**, in a dock the panel stands in |
| Cadence | 7 wakes a day | readings every few seconds, display every few minutes |
| Client between refreshes | deep sleep | **awake**: sensors need it (SCD41 periodic mode with ASC, BSEC calibration state, PM fan warm-up) |
| Panel | Inkplate 10, 4 greys used | Inkplate 5 Gen2, **8 greys** |

Three of those change the design. The panel is one config line.

## 3. Four differences in the design

### 3.1 Each board runs its own program, not `run_app()`

`run_app()` is epd's deep-sleep state machine for a board that only draws
pages. Each board here does more, so each has its own program: the dock stays
online and light-sleeps between passes of its loop, and the display
deep-sleeps on a plan of its own.

The dock, `src/dock/main.cpp`, is the one the sensors need:

```
setup:  80 MHz; light sleep on; wifi; the settings from NVS; I2C; BSEC; sensors.begin(); the first reading 35 s on
loop:   once a second, light-sleeping between passes
        until known   GET /about           every 30 s, for the server's time
        before a slot GET /board-settings  the settings, applied (§3.8); a recalibration; a stopped sensor started again
        each slot     queue a reading      a fresh sample, PM included, with the dock's own status, into PSRAM
        every pass    POST /sensor-readings       the oldest 100 in the queue as one batch, once the time is known
                      POST /calibration    BSEC's state, after a batch, when BSEC has saved a new copy
        continuous    the PM fan and the status LED
BSEC:   a FreeRTOS task of its own; its state goes to NVS when accuracy first reaches 3 and every six hours after
LED:    a FreeRTOS task of its own, so the starting pattern runs while setup() blocks
```

The dock runs at 80 MHz rather than 240. Wi-Fi needs 80, and below it the
APB clock follows the processor, which would move the serial baud rate. So
80 is both the floor and the choice. Power management holds it there, and
light-sleeps the chip whenever every task waits: between passes of the loop,
the Wi-Fi driver wakes it for the access point's beacons, the BSEC task for
its samples and the LED task for each step of the pattern (§3.5). The LED's
PWM runs through the sleep on the RC_FAST clock. The chip stays awake while
its USB port is connected to a host.

The PM module's fan runs for the 35 seconds before each reading and stops
after it: 12% of the time at five-minute slots, 2% overnight. It is the
dock's largest load, about 200 mA of the sensors' 215. The window is
Plantower's 30 second warm-up and a margin, counted back from the next slot,
and each reading records in `pm_warmup_s` how long the fan had actually run,
so the stored readings can show whether 30 seconds is enough. `SensorSuite`
counts no missed frame while the fan is off, so stopping it does not make the
module look dead. The settings can lengthen the window, or keep the fan on
(§3.8).

The dock has no clock and does not ask NTP. Every response from the server
carries its time and time zone, and the dock holds the time as an offset from
its uptime, so the
readings it stamps and the slots the server counts agree by construction.
Until the first response it queues readings with their uptime and stamps them
when the time arrives, so a dock that boots while the server is down keeps
what it measured, correctly timed.

The display, `src/main.cpp`, deep-sleeps between wakes. E-paper keeps its image
without power, so a display awake between pages would only make heat:

```
each wake:  board.begin(); wifi
            page due     GET the named page → draw; a failed fetch keeps the old image and backs off
            every wake   POST /sensor-readings   the display's own status, which is its sync; the answer names the next
            then         deep sleep until the next page or the next sync, whichever is first
```

Every answer from the server sets the display's clock, time zone and RTC, so
it asks no NTP, and it reads no SD card: its settings are in its own store.
The RTC's alarm wakes it, and the ESP32's timer stands behind the alarm a
little later, so a missed alarm makes a late page rather than a display that
never wakes. What must outlast the sleep, the wake plan, the next URL and the
counts, is in RTC memory, which a real start clears. Two things keep the display
awake: a wait under 10 seconds, which costs less than a wake, and a freshly
written image, which the bootloader takes back unless a page proves it. The
display reports its uptime and reset reason from its last real start, so a wake
is not a restart on the Diagnostics page.

Both programs compose epd's WiFi, time, download, `postJson` and back-off
helpers and the logger; the display adds the image helpers and `IBoard`, the
dock needs no board at all. The kit stays a library, not a framework: it
does not need to know what a sensor is.

### 3.2 Readings travel client → server by HTTP POST

The dock queues one document a minute in PSRAM, in the layout of
[READINGS.md](READINGS.md), and each pass of its loop posts the oldest 100
to `/sensor-readings` as one batch. A reading is kept before anything is sent, so
one path covers the post that works and the outage that does not, and a
queue that built up while the server was down drains a batch per pass
without making a sample late by more than one request. The queue holds
2 MB, about five days of readings; a restart empties it.

epd's `DisplayServer(ingest=...)` hands a batch to `ReadingsIngest`, which
keeps each document for the Diagnostics pages and, with `source.kind:
store`, appends it to epd's `ReadingsStore` (SQLite) in one transaction. The
store's key, the device and `ts`, is what makes the route safe to repeat:
the same document posted twice is stored once, however the two requests
were batched.
`IngestSource` serves the store to the pages as the datasets `latest`,
`history_24h` and `history_72h`, and `SeaLevelSource` reduces the pressure on
the way. With `source.kind: mock`, `MockReadingsSource` serves the simulated
room under the same names. The Diagnostics page reads `status`.

The reading schema is the project's (`co2_ppm`, `pm2_5`, `iaq`, `temp_c`, …);
the kit stores a timestamped JSON document and does not interpret it. BSEC's
learned state goes to `POST /calibration` whenever BSEC saves a new copy;
`CalibrationStore` keeps it and `GET /calibration` hands it back after the
board restarts.

### 3.3 The schedules are ranges round the clock

"Every five minutes" as a list of wall-clock times would be 288 entries. epd's `display` block has
`pools` of images and a `schedule` of `type: times` or `type: timeranges`. This device uses
`timeranges`, and refuses `times`: its `week` puts each day of the week in one group, and each group
has ranges that cover the whole day, up to 8, each from its start until the next range's, the last
running past midnight to the first; each has an interval, and 0 turns its range off, so the page can
stay as it is overnight. A day stands alone: before its first start its own last range runs, not the
day before's, so a group's dial shows all that happens on its days. By default the page changes every
300 seconds all day, every day, on :00, :05, … on the wall clock; the weather calendar keeps `times`.
[CONTRIBUTING.md](../CONTRIBUTING.md) explains the pools. A slot is a local time in a range that is on,
whose seconds past midnight are a multiple of that range's interval. epd's `TimeRanges` finds the slot
by stepping through the minutes and asking of each which range it is in, because some clocks change at
01:00: in spring that hour never happens, and in autumn it happens twice. The page's turn through the
pools is counted over the week, from the slots of the days before, so it runs on from one day into
the next whatever each holds. The Display tab edits the week beside a dial of the day: a chip for
each group chooses the one shown, and its day toggles move a day into it, or out of it into a group of
its own with a copy of its ranges, so each day always has a group. In a group a new time range halves
the one that starts latest, which runs on past midnight to the earliest start, and a range removed
gives its hours to the one before.

The dock syncs on a week of the same shape, `dock.sync.week` in `config.yaml`: it takes a reading at each
sync and posts its queue. By default, every day, it is every 1800 seconds from 01:00 and every 300 from 07:00, so
readings land on :00, :05, … by day and on the hour and half hour by night, and 07:00 is a slot in
both. Every response tells the dock how long until the next, in `Canary-Next-Sensor-Poll-Seconds`,
rounded up so it is never early. Without an answer the dock keeps the last gap the server gave between
two slots. A week in which no range syncs is refused, since the dock would take no readings; a day
with none is allowed. The Dock tab edits it as the Display tab edits the page schedule.

The display syncs every so often all day, `display.sync.every`, every half hour by default and 0 for only
beside each page it fetches; the Display tab sets it in minutes. Each board is sent its own next slot
in `Canary-Next-Sensor-Poll-Seconds`, by the name it states in `Canary-Device`. The display posts its
state at every wake, and wakes for a sync that comes before its next page.

### 3.4 The device is a display and a dock

The panel and the sensors are two boards, in two halves of one enclosure:

- **Display**: the Inkplate 5 Gen2 and nothing else. Its I²C bus carries only its own expander, RTC and panel PMIC,
  and its regulator carries only itself.
- **Dock**: an ESP32-S3 (TinyS3), the four sensors on a regulator of their own, and the USB-C socket that powers
  both halves. A magnetic pogo connector carries 5 V and ground up to the display, which sits in the dock's cradle.

Three things forced it, all in [hardware/bom.md](../hardware/bom.md):

- **The bus.** With the chain on the Inkplate's bus, a jammed sensor also stopped panel refreshes and the panel
  temperature read, because the expander, the RTC and the PMIC share that bus.
- **The rail.** The Inkplate's regulator is 500 mA and also carries its ESP32 and panel PMIC. The sensors peak at
  ~470 mA on their own.
- **Heat and quiet.** The SCD41 wants a supply free of Wi-Fi bursts, and the dock's own regulator would reach
  thermal shutdown carrying the chain.

Nothing else leaves the display: its only connections are the two wires soldered to its power pads, which meet the
dock at the pogo connector.

### 3.5 One LED says what the dock needs

The dock drives a yellow LED on IO6, behind a clear tile in the shell's front face. It shows the first of these
triggers that holds and has a look in the server's `dock.led.looks`: a pattern, and the length of one cycle of it
before it repeats. A trigger the list leaves out passes the light to the next one that holds, and with none the
LED is dark. While `setup()` runs only Booting holds, since the others are not known yet; once it has booted,
Running always holds, last.

| Trigger | When | Look by default |
|---|---|---|
| Updating | Writing a new image. | Pulsing faster and brighter as it is written: from 60 a minute at a quarter of the light to 240 at full light. Not set by the server. |
| Booting | `setup()` is connecting, or starting the sensors. | Pulse every 0.5 s. |
| Error | Anything wrong: off the network, a post the server did not get or would not take, readings waiting in the queue, a sensor that does not answer, or a setting the dock refused. The Boards page says which. | Flash every 1 s. |
| Poor air quality | The latest reading has CO₂, PM2.5 or, once BSEC is calibrated, IAQ at or over its limit. Each limit is a setting in its sensor's section of the Dock tab: 1500 ppm, 37.5 µg/m³ and 150 by default, the pages' bands for stuffy, dusty and polluted air. | Double flash every 2 s. |
| Calibrating | BSEC's IAQ accuracy is below 2, which Bosch calls unreliable, or a recalibration waits for the SCD41 to have measured for 3 minutes. | Swell every 4 s. |
| Running | Booted. | Pulse every 1 s. |

The slow pulse is the heartbeat: a dock that has died goes dark, which a solid running light would hide.
Temperature and humidity raise no trigger: what is comfortable depends on the home, and a humid climate would keep
the light on. A flash is 150 ms of full light at the start of each cycle, and a blip 50 ms. A pulse rises and
falls along a sine; a swell rises over the first third of its length, holds, and falls over the last; a ramp
rises over its length and goes dark at once. A double or a triple is two or three quick pulses or flashes of
300 ms each, then dark for the rest of the length, which is at least one of those steps longer than the group, so
the gap always shows. A fade moves in equal steps of perceived light: `dock.led.smoothness` picks 4, 8, 16, 32 or
64 of them, or none to see, and 16 is the default. At a low brightness the dimmest steps can share a duty.

`StatusLed` turns the time into an LEDC duty and holds no hardware, so the pattern is tested on the host, and so
is `LightTriggers`, which judges the air and calibration triggers from a reading. The Dock tab plays a look on a dot,
with the same timings and steps in `sheet.js`, so it can be seen before it is saved: what the light showed at the
dock's last sync, which the dock reports as `light` (READINGS.md), until a row is changed or clicked. The dot's
area follows the brightness, and at 0 it stays dark. Brightness is perceived
brightness, mapped through gamma 2.2 onto a 14-bit channel at 1 kHz. A task of its own drives the pin, because
`setup()` blocks for as long as the network takes and the booting pulse runs through it. It waits until the
pattern's next step, and at most 250 ms so a new state shows soon, rather than looking every 5 ms, which would
keep the chip out of light sleep.

### 3.6 The headers carry canary's name, not the library's

Every header on the wire starts with `Canary-`, because the server's responses are canary's interface and a reader
of the traffic should not have to know which library built it. The kit builds the names from a prefix each product
sets: the server takes `header_prefix="Canary"`, the firmware takes `-DEPD_HEADER_PREFIX='"Canary"'`, and a
mismatch is silent, so both come from this repository.

| Direction | Header | Carries |
|---|---|---|
| Board to server | `Canary-Device`, `Canary-Device-Version` | which board, and what it runs |
| Server to board | `Canary-Server-Version`, `Canary-Server-Epoch-Seconds` | on every response |
| Server to display | `Canary-Next-Display-Refresh-Seconds`, `Canary-Next-URL` | when to fetch, and what |
| Server to dock | `Canary-Next-Sensor-Poll-Seconds` | on every response: when to take the next reading |
| Server to board | `Canary-Server-Firmware-Version`, `Canary-Server-Firmware-URL` | only when an update applies |

`GET /about` answers with the same version and clock, plus the firmware on offer and the library version. A board
asks at boot, after a post the server would not take, and once an hour.

The server's version is canary's own, from `git describe` when the image is built. It is not the `epd-server`
package's version: that package is a library this server is built with, and the two move independently.

### 3.7 When the two ends cannot work together

A board and the server work together when their major versions match, or, while the major is 0, their major and
minor. Both ends apply the rule, the server through `epd_server.compat` and the boards through `version_compat.h`,
so they reach the same answer about each other. A version that cannot be read, such as `dev`, is never judged:
refusing it would silently stop every development build.

The server's own version is the one the boards follow. It holds each board's images in a folder of its own,
`firmware/canary-display/` and `firmware/canary-dock/`, keeps every one, and offers each board the newest image of its
product that can work with the server's version, newer or older than what the board runs; among builds past one
tag, the one furthest past it. So a mismatch clears itself once the board takes the offer. The offer goes on any
response to the board, a refusal included. The firmware-builder beside the server builds the firmware of its own
commit into that folder when it starts, so a redeploy moves the server and the boards together. A server past a
tag offers development builds; a tagged server offers only to boards on a tagged build. The server logs each offer
of an older image, and the Diagnostics page shows each board's last change of version, marked when it was a
downgrade, and the posts the server refused from it, even from a board it has never taken a report from.

- **The dock** gets 409 from `/sensor-readings` and leaves the batch in its queue rather than dropping it, since the
  readings are sound and only the pairing is wrong. The refused post puts the LED into its trouble pattern, and the
  same response offers the image that fixes it.
- **The display** still gets its pages, since the server never refuses a fetch. It draws a notice in place of the page
  and then takes any update on offer exactly as it would after a page. The order is fixed in
  `include/display/AfterFetch.h` and tested: the update is what clears the notice, and the dock's wall covers the
  display's USB-C socket. When the server offers no image the display will take, the notice says so and asks for one:
  firmware for the server's version, or a server of the display's.

The dock takes an offer from the answer to a batch of readings, and only once its queue is empty, since the restart
empties it. The exception is a 409: the server will not drain that queue until the dock runs another version, so
the dock takes the image and loses the readings. While the image is written the LED pulses faster and brighter with
the bytes written, from the working pulse at a quarter of the light to four pulses a second at full light. The new
image boots on trial, as the display's does: the first batch the server takes confirms it, and three failures in a row
roll it back, after which the dock refuses that version.

The display draws another notice when three fetches in a row go unanswered, about 26 minutes with the back-off, so a
blip never replaces the page. It says when the last page arrived. The notices come from the firmware, not the
server, so they work when the server is what is wrong, and each is drawn once rather than on every retry, since
every draw is a full refresh of the panel.

They are pages. `server/pages/notice.py` sets each one like the others, a spaced-capitals label, an italic verdict
and a line of detail, and `scripts/notices.py` renders them through the same pipeline, browser and quantiser as
every page the server serves. The display holds the three PNGs in its firmware and draws them with the call that draws a
fetched page, so a notice is pixel for pixel what the server would have rendered. They are rendered again only when
their wording or design changes, so the firmware build needs no browser.

The layout leaves its bottom free for the two facts the display only knows at run time: when the last page arrived, or
the server's version, and then the board's own name, version and address. The display writes those in the pages' face
at the size of their detail text, from a one-bit font `scripts/gfxfont.py` makes out of the server's font file.

The display holds one more screen, the splash screen: the logo alone, from `hardware/canary-logo-screen.svg`, rendered
by `scripts/notices.py` like the notices, but in black and white. The display draws it at every start but a wake from
deep sleep, before it joins the network, with its firmware version under the logo, and it stays until the first
page or notice replaces it. While the display
writes an update, it draws the logo again with a progress bar under it, and under that "Installing firmware" and the
version, in the pages' italic from a second one-bit font. The bar fills in ten steps, each a partial update of the
panel, which works only in black and white; the Inkplate library makes every eleventh partial update a full refresh
(`include/display/ProgressBar.h`).

### 3.8 The server holds the dock's settings

The `dock` block of `config.yaml`, the Dock tab on `/web/config`, sets what the dock does between readings: the
fan's warm-up, the SCD41's temperature offset and self-calibration, the SHTC3's low-power mode, BSEC's sample
rate, the limits of poor air for the CO₂, fine dust and air-quality sensors, the LED's brightness, smoothness,
schedule and looks, and the dock's log level. The dock asks `GET /board-settings` at the
pre-warm before each slot, applies what has changed, and keeps the answer in NVS, so it starts on the same settings
after a power cut. The answer carries a version, a hash of the settings, and the dock reports the version it runs,
and any key it refused, in its `client` object; the Dock tab says whether the dock has taken the saved settings.
The dock holds each value to limits of its own, so a server that sends one out of range changes nothing. A board that has
missed two of its syncs, two slots of its own schedule, is offline: the Boards page marks it,
and the Dock tab greys out its settings and its recalibration until the dock syncs again, since nothing sent then
would reach it. The saved values stay as they are. A range that is off lengthens the silence the dock may keep, since
it has no slots to miss.

Each setting takes effect where it can without a wait. The SCD41 takes its offset and self-calibration only while
idle and forgets them at a power cycle, so the dock sets them at each start of the part, and a change stops its
measuring for half a second at the pre-warm, which leaves five seconds' conversions to spare before the slot.
Neither is written to the part's EEPROM.

BSEC samples the BME688 every 3 s or every 5 minutes, 5 by default. Bosch ships a configuration for each rate, and
the state BSEC learns at one is no use at the other, so each saved copy says its rate, the dock restores only a copy
at its own, and a change of rate starts BSEC again from nothing. At 5 minutes Bosch counts the BME688's self-heating
as negligible, and a reading carries the newest cycle, up to 5 minutes old.

The LED's schedule, `dock.led.schedule`, the hours it is on, is the server's: the answer says whether the next slot
falls outside it, so the LED goes dark at the pre-warm before the first slot past its end and comes back at the one
before the first slot in it again. Without a schedule the LED is on all day. It is a window of its own rather than
a range of the sync schedule, so the light can stay dark while the dock syncs slowly.

A recalibration is not a setting. The Dock tab asks for one with a reference in ppm, the server keeps the request
with the time it was asked as its id, and the answer carries it for an hour or until the dock reports that id as
run. The dock runs it at the pre-warm, once the SCD41 has measured for the three minutes the datasheet asks, stops
the part for about a second, and reports the correction, or the failure, in its `client` object. Each one is
written to the SCD41's EEPROM by the part itself, so it is for a person with the dock in known air, not for a
schedule.

## 4. What stays as the kit has it

- The wire contract: `GET /<page>.png` with the refresh and next-URL headers. The awake client honours the header by waiting instead of sleeping.
- `DisplayServer`, `Page`, `regenerate()`, `DataSource`, the config loader, the MQTT log relay.
- `IBoard` and `EpdBoardInkplate`. Inkplate 5 Gen2 is `-DARDUINO_INKPLATE5V2`; GPIO39 RTC wake matches the schematic, though this device does not sleep.
- Rendering: `GreyscaleQuantiser` at eight levels for the panel's eight greys, one argument.

## 5. Shape of the repo

```
platformio.ini                 envs: esp32 (the display), dock (the TinyS3), dock-mock (-DUSE_MOCK_SENSORS), dock-validate, native, sim
partitions.csv
src/main.cpp                   the display: fetch, draw, post its own state
src/dock/main.cpp              the dock: the loop from §3.1
src/defaults.example.cpp       copy to defaults.cpp: WiFi, server URL, MQTT logging
include/sensors/  src/sensors/
  Readings.h  ReadingsJson.cpp                  what the sensors return, and the wire format in READINGS.md
  IShtc3.h  IScd41.h  IPmsa003i.h  IBme688.h    one interface per part, shaped by its datasheet
  IClock.h  II2cBus.h                           the clock and bus seams
  SensorSuite  SensorHealth                     the four sensors as one begin() and one sample(), and how they fare
  Shtc3Driver  Scd41Driver  Pmsa003iDriver  Bme688Driver  SensirionI2c  Pmsa003iFrame
  IBsec.h  BsecRunner  BsecLibrary              BSEC, in a task of its own
  SensorValidation                              the bench routine's checks
  mock/                                         EnvModel, LaggedValue and the four mocks
include/net/  src/net/         Backlog, BoardSettings, Calibration, ClientStatus, ServerClock, Stamp, Url
include/dock/                  StatusLed (§3.5), FanWindow and PostTimer: when the fan runs and the next reading falls
include/display/               when the display wakes (§3.1), what it does after a fetch, and the notices it draws (§3.7)
src/notice.cpp                 the notices, with the facts only the display knows at run time (§3.7)
src/splash.cpp                 the splash screen, and the update's progress bar under it (§3.7)
include/display/notices/       the notices, rendered by scripts/notices.py from server/pages/notice.py
include/display/splash.png     the splash screen, rendered by scripts/notices.py from server/pages/splash.py
include/display/fonts/         the pages' face as one-bit fonts, from scripts/gfxfont.py, for the lines the display writes
src/sim/main.cpp               the sensor loop as a host binary
src/validate/main.cpp          the bench routine
lib/bme68x/                    Bosch's BME68x API
scripts/                       bsec.py, dock_core.py, gfxfont.py, notices.py, version.py
test/                          host tests, native env
server/
  server.py                    config, sources, pages, DisplayServer(...).run()
  about.py  version.py         GET /about, and what this server calls itself
  web.py                       /web/: the pages in a browser, the explorer, and GET /history
  config_page.py               /web/config: config.yaml as a form in tabs and as text, checked, saved, and restarted on
  config_form.py               the form's fields, and how a filled-in form edits config.yaml
  transfer.py                  a store out to a file and back in, and what it holds, for the Storage tab
  schedule.py                  the dock's reading slots, slower overnight (§3.3)
  dock_settings.py             the dock block and GET /board-settings (§3.8)
  sources/                     the mock room, readings ingest, calibration store, device status, sea-level pressure
  pages/                       Breathe, Comfort, Dust, Air, Day, the Diagnostics pages, and the trace and delta pages
  metrics.py                   derived values and wording
  static/                      CSS, fonts, charts.js; web.css, browse.js, explore.js and config.js for /web/
  config.example.yaml
hardware/                      the boards, the desk enclosure and how to build it: README, bom, assembly, enclosure, enclosure.py, images/
docs/                          ARCHITECTURE and READINGS
```

## 5.1 The sensor seam

`src/dock/main.cpp` names a concrete sensor type in exactly one place, a
`#if defined(USE_MOCK_SENSORS)` block that constructs either the mocks or the
real drivers and binds them to `IShtc3&`, `IScd41&`, `IPmsa003i&`, `IBme688&`.
Everything else — including the whole sampling protocol — is written against
those interfaces in `SensorSuite`, so the mocks exercise the code that will
run on the device rather than a parallel copy of it.

`SensorSuite::sample()` runs the datasheet sequence: wake the SHTC3, measure,
wait 13 ms, read, put it back to sleep; one BME688 forced cycle, then feed its
pressure to the SCD41 so the CO₂ conversion is right; take whatever the
SCD41's periodic mode has ready; read a PM frame, retrying once on a bad
checksum, and only after the fan's 30 s warm-up.

The waits are real, so the clock is injected (`IClock`): `ArduinoClock` on the
device, a fake the tests drive. `ArduinoClock` waits until the millisecond
clock has moved on, not for one `::delay()`: while the chip light-sleeps a
delay can return up to 51 ms early, and a read before a conversion ends
fails. A sample costs ~150 ms of wall clock, nearly
all of it the BME688 heater, once a minute, and `::delay()` yields on
ESP32, so WiFi keeps running. If that ever becomes a problem the interfaces
already return false-when-not-ready, so `sample()` can become a state machine
without touching the drivers.

`-DUSE_MOCK_SENSORS` picks the mocks; without it the drivers talk to the
parts. The `dock` and `dock-mock` environments are that one flag apart.

The drivers reach the bus through `II2cBus`, for the reason `IClock` exists:
the command sequences, the CRCs and the conversions are what a driver gets
wrong, and a host test cannot drive `Wire`. `ArduinoI2cBus` wraps the `Wire`
instance `Inkplate::begin()` has already started; `test/test_drivers` drives
the same code against parts that answer the bus the way their datasheets
describe.

The BME688 is the exception to writing the registers here. Its compensation
reads twenty calibration coefficients out of the part and the failure mode
is a plausible wrong number, so Bosch's own C API does that arithmetic
(`lib/bme68x`, v4.4.8, BSD-3-Clause). It reaches the bus through function
pointers, so it sits behind `II2cBus` like everything else, and it has no
Arduino dependency, so it builds for the host tests too. IAQ comes from
BSEC, which drives the part through the same driver from a task of its
own; `BsecBme688` hands `SensorSuite` the newest cycle BSEC ran, so the
suite's sequence is the same with BSEC as without it.

## 6. Mocks — what "as close as possible" means

The value is in the **timing and the quirks**, not in emulating registers.
Each mock implements its part's interface (`IShtc3`, `IScd41`, `IPmsa003i`,
`IBme688`) and reproduces what the datasheet says the real part does:

| Mock | Reproduces |
|---|---|
| `MockScd41` | 5 s measurement interval; `data_ready` false in between; missed intervals dropped, not queued; first shot after power-up discarded; ±10 ppm repeatability noise; commands refused while measuring and for 500 ms after stop; `set_ambient_pressure` changes the answer |
| `MockPmsa003i` | 3 s boot then 30 s fan spin-up with counts ramping from zero; 2.3 s frame cadence with stale bytes in between; occasional checksum failure; SET-low silences it and restarts the warm-up |
| `MockBme688` | forced-mode timing (TPH + heater); `heat_stab` false on the first cycle and whenever the profile is too short or too hot; gas resistance falls with VOC and with humidity; pressure tracks the model |
| `MockShtc3` | 12 ms measurement, 0.8 ms low-power; sleep/wake with NACKs when asleep; ±0.1 °C / ±0.1 % RH repeatability, ±0.4 in low-power mode |

### Warm-up and response time

Every reading trails what it measures, and two of the parts warm themselves.
`LaggedValue` is the shared first-order lag; each mock applies the τ63 its
datasheet quotes:

| | τ63 |
|---|---|
| SHTC3 temperature / humidity | 15 s (quoted 5–30 s, design-dependent) / 8 s |
| SCD41 CO₂ / humidity / temperature | 60 s / 90 s / 120 s |
| BME688 gas / humidity | 92 s (ULP duty cycle) / 8 s |
| PMSA003I concentration | 4 s, from "total response time ≤10 s" |

Self-heating rises from nothing after power-on rather than appearing at
once, with a 300 s time constant — not a datasheet figure, but it puts the
part within 5% at the fifteen minutes Sensirion's design-in guide asks you
to wait before judging the temperature offset.

The visible consequence, and the reason the SHTC3 is the display reference:

```
  time    SHTC3   SCD41   BME688
  14:00    18.4       -    18.4
  14:04    18.3    16.7    19.3
  14:12    18.4    18.3    19.8
  14:20    18.4    18.4    19.9
```

The SCD41 reads about 4 °C **low** at a cold boot, because its default
offset subtracts self-heating the part has not produced yet. The SHTC3 has
no meaningful self-heating (16 µW) and no electrical warm-up at all — 240 µs
to idle, first reading valid — so it is steady from the first sample.

The Python mock source always runs settled, since it replays three hours
before the window it returns. Pages therefore never see the warm-up, which
is what you want while designing them.

`EnvModel` is the room: CO₂ rises with occupancy and decays with ventilation
(τ ≈ 60–90 min), PM has cooking/cleaning spikes, VOC has a baseline and
events, T/RH follow a diurnal curve with the heating on. The same model,
ported to Python, feeds `MockReadingsSource` so the pages are developed
against the same shapes the firmware will send.

---

## Decision Log

Dated decisions and status behind the text above, oldest first.

- **2026-09-03**: proposed: an awake loop, readings posted to the server, and an interval schedule, with the kit additions they need (`postJson`, a `refresh_cycle()` helper, an interval schedule, `ReadingsStore` and `IngestSource`, `POST /readings`). Four questions were open: HTTP or MQTT for the readings; the PM fan always on or duty-cycled; which SCD41 breakout; firmware in `firmware/` or at the repo root.
- **2026-09-03**: the firmware scaffold at the repo root, `EnvModel`, the four mocks and their host tests; the server with `MockReadingsSource`, the first pages and `config.example.yaml`.
- **2026-09-03**: the first draft planned one `ISensor` (`begin()` / `poll(now)` / `read(out)` / `sleep()`) with one `Reading` struct for all four parts. It was never built. The sensors could not share an interface because they do not share the same sampling sequence. The code has one interface for each part, and `SensorSuite` runs each part's sequence in turn. It also gives the SCD41 the BME688's pressure, and it drives the PM module's fan.
- **2026-09-04**: epd's `display` block landed: `pools` of images and a `schedule` of type `times` or `interval`, round-robin over pools and within them, with random starts reshuffled every few hours. `postJson` and `DisplayServer(ingest=...)` landed. `refresh_cycle()` was not needed: the awake loop composes the kit's WiFi, download, draw and back-off helpers directly. The awake loop ran end to end against the mocks, drawing on the server's cadence and posting one readings document a minute with the board's `client` status. Until the store existed, the server kept only the newest document, for the Diagnostics page.
- **2026-09-04**: the build settled three of the four questions. Readings go by HTTP POST: one route in `DisplayServer`, testable with Flask's test client, and an MQTT republish can follow on the server when Home Assistant enters the picture, with no change to the firmware. The firmware sits at the repo root, like the weather calendar's. The PM fan runs all the time.
- **2026-09-09**: the four drivers landed behind `II2cBus`, with host tests. The SCD41 board is the Adafruit 5190. The mocks were not corrected against logs of the real parts; that needs a log of each part.
- **2026-09-12**: `ReadingsStore` and `IngestSource` are in epd from 0.5.0, and `source.kind: store` serves them to the pages. BSEC runs for the BME688's IAQ index.
- **2026-09-15**: the device became a display and a dock (§3.4). One bus and one 500 mA rail could not carry both the panel and the sensor chain; each half now has its own.
- **2026-09-19**: every reading goes into the dock's queue when it is taken, and the loop posts the queue in batches of 100 (§3.2). This replaced a live post with a held copy on failure, which sent at most five held readings after each live one and stripped their `client` object. Held readings keep it: the server has stored every report since the trace pages, so a held one fills the outage in on them. The calibration block moved to its own route, because it is current state rather than part of a reading. Repeats are handled by the store's device-and-`ts` key, not by an idempotency key on the request: the one-at-a-time fallback resends documents in a differently shaped request, which a request key would store twice.
- **2026-09-19**: the dock takes its readings on the server's slots, every five minutes and every half hour from 01:00 to 07:00 (§3.3), and its time from the server rather than NTP (§3.1). Overnight, fine readings are rarely needed. The server sends the seconds to the next slot rather than an interval, so a restart at 03:07 rejoins at 03:30 and readings land on tidy times. The time is a custom header rather than HTTP's `Date` because plain epoch seconds cost the TinyS3 no parsing. The fan now follows the next slot instead of the last post, and the reading is sampled fresh at the slot: at 228 readings a day that is about 809 fan hours and 83,000 starts a year, against 5,110 hours and 526,000 starts for the 60 s cadence before it. Plantower's 30 s warm-up stands, and `pm_warmup_s` lets the stored readings judge it.
- **2026-09-19**: the dock's queue moved from the Sensors card to the Memory card, as a count against its capacity with a meter, since it is memory. The diagnostics trace page draws one chart per measure with both boards on it, the dock dark and the display light on one scale: free memory tallest, the queue, then the signal, which barely moves once the dock is placed. A page of changes since the last report was considered in its place and dropped. The queue's axis fits the day's highest, no lower than 10, because it is empty almost always and then climbs through an outage.
- **2026-09-19**: the dock updates over the air like the display, and every board is offered the newest image of its product that works with the server's version, rather than the newest file (§3.7). The boards follow the server rather than work out which end is newer, so the server's version is the one dial. That needs the older images, so neither `build-firmware.sh` nor the server removes any. An accidental server downgrade therefore downgrades the boards within a request each: each update restarts the dock and empties its queue, BSEC may refuse state an older library did not write, and later features go until it is fixed. The Diagnostics page shows each downgrade and each refused post so such a day is visible. The dock takes an update only with its queue empty, except under a 409, when the queue cannot drain until it does.
- **2026-09-23**: the firmware-builder image carries the firmware's sources at its commit and builds them where it runs, instead of polling GitHub for releases and building their tags (§3.7). Every push to `main` publishes both images as `latest`, so a server and its builder on `latest` move the boards with every push, and a pair pinned to a release keeps them there. Whether a server offers development builds follows its own version rather than a setting: a server past a tag is itself a development deployment. `scripts/build-firmware.sh` and the builder's release watcher went with this, and with them the check that a tag was signed: an image now comes from CI building a pushed commit.
- **2026-09-19**: each dock document carries a `health` object beside `client` (READINGS.md): sensor restarts, the checksum failures the drivers used to drop without counting, the BME688's gas and heater flags, and the SCD41's serial, self-calibration and offset from its start. The bus jam of 2026-09-15 showed as missing sensors only once it was bad; damaged answers come first, so they are counted. Nothing here costs extra bus traffic but two SCD41 reads at each of its starts. The server keeps the object with the rest of each report, and a `health-trace` page draws the day: restarts and damaged answers as running totals, since the dock's own counts begin again at each of its restarts, and the heater as a flag, all in steps; the SCD41's settings and its few damaged answers go on one line above them.
- **2026-09-22**: the server shows its pages in a browser at `/web/`, and an explorer at `/web/explore` draws one measurement over any window from `GET /history`. A page is built from the readings when it is asked for, on a copy of the page object, so the PNGs and the browser never share a document. The explorer reuses the trace chart and its Python, so a window in the browser is drawn as the panel draws three days. There is no login: the view shows what the PNGs show, on the same port. `GET /readings` and `GET /status` answer with the stored readings and the boards' reports as JSON (READINGS.md), so a board can be diagnosed without reading a page.
- **2026-09-22**: `/web/config` edits `config.yaml` in the browser. An edit is checked by `load_settings`, the code the server runs at start, and any error it meets refuses the edit, so a saved config always starts the server. Save restarts the process in place with `os.execv`; the container stays up. The page has no login yet.
- **2026-09-22**: `/web/config` is a form in tabs, one for each block of the file, each about one screen, and the file as text in a last tab for the keys the form does not show. The form edits the file with ruamel.yaml, a new dependency, because PyYAML cannot write it back with its comments. The server still reads it with PyYAML, and the two read some plain scalars differently, so each edit is read back with PyYAML and refused if a value reads differently or a key the form did not change has changed. An empty field takes its key out, so the server uses the default that the field shows. A field that an environment variable sets is locked, since the variable wins. The firmware token is never sent to the form. A save first lists each change, old and new; Restore puts `config.yaml.bak` back.
- **2026-09-22**: the boards post to `/sensor-readings`, and the default store is `sensor-readings.db`, so the route and the file say what they hold. There is no `/readings` for older firmware: before 1.0 a minor release may break the contract with no transition, and a dock on older firmware is flashed by USB.
- **2026-09-22**: the Storage tab downloads each store as a file and takes one back. The file is one JSON document a line, in the shape the board posted, and not the SQLite file: a store keeps a document under its board and its time and ignores a second with that key, so a file goes into another store of the same kind and adds only what is missing. An import writes the whole file or none of it, so a corrupt line leaves nothing behind, and when the store already holds some of them it writes nothing until the person says to put the file over them. The size beside Download is taken from the first lines and how many documents are held, so drawing the page costs the same whatever the store holds. An upload weighs at most 64 MB.
- **2026-09-22**: the menu gives each group a row of its own, with the headings in a column beside the pages. Three days and Changes name the same five measurements, so they share one row and the heading is a switch between them; a hidden radio holds the choice, which keeps the switch working without JavaScript. On the browse page, `browse.js` moves the shown page to the same measurement over the other span, and flips the switch when a page from the other span is opened.
- **2026-09-23**: the dock takes its settings from the server (§3.8) rather than from constants in its firmware, so changing how it runs needs no build. It asks at each pre-warm rather than reading them off the answer to a batch, because the pre-warm is when a setting can take effect before the slot, and a failed request costs nothing: the dock keeps what it runs. The pre-warm is a moment of its own, the fan's lead before each slot, since a fan kept on never starts. BSEC's sample rate is a setting too, 5 minutes by default: the dock's first run, which looked like a start from nothing, reached accuracy 3 about 5.5 hours in at 3 s, so a change costs hours of learning rather than days. A recalibration is a request with an id rather than a setting, so saving the config again never repeats one.
- **2026-09-25**: the dock's `posts` schedule became `dock.sync`, ranges round the clock (§3.3). A sync is an exchange both ways, the dock's readings up and its settings and any update down, which "post" undersold. A schedule always covers the day: it starts as one range, a range is made by splitting one, and there are at most 8, so there is never a gap or an overlap to explain. A range may run past midnight, and an interval of 0 is off. The display gets a sync schedule of the same shape next, and its refreshes after that, so the Dock and Display tabs edit all three with one editor. A board is offline after two missed syncs, fixed in the code, since what is abnormal is the product's call and not the user's. The LED's dark hours moved from the old quiet window to `dock.led.dark` as a stopgap until the status light is redone.
- **2026-09-25**: the LED's looks became a list, `dock.led.looks`, a row on the Dock tab for each trigger, with its pattern and interval (§3.5). A trigger without a row passes the light to the next state that holds rather than going dark: taking a row out says that state is not worth showing, not that the problems behind it are not. Only the dock knows which states hold at once, so the dock does the passing on. The order stays the triggers' own and a row's place means nothing, so the tab keeps the rows in that order.
- **2026-09-25**: the LED's dark hours became its schedule, `dock.led.schedule`, the hours it is on, so each schedule on the tabs says when something happens rather than when it does not. Without one the light is on all day.
- **2026-09-26**: the page schedule became ranges round the clock and the display's sync a plain interval, the other way round from before. What changes through the day is when the page should change, with none at night, while a sync only has to happen often enough. epd's `display.schedule` gained `type: timeranges`, which replaced `interval`, since one range all day does what `interval` did, and the ranges moved into epd as `TimeRanges`, since the page schedule is epd's; canary imports it for the dock's sync. A slot is a whole minute, so the page cannot change faster than once a minute.
- **2026-09-26**: the looks gained a double and a triple of both the flash and the pulse, as named patterns rather than a count and a pause on every row, so a row stays three fields and each name says what it looks like. A new one needs the dock's firmware and the server both. The row's interval became its length, one cycle of the pattern, which reads the same for all of them: for a triple it is the group and the dark after it.
- **2026-09-26**: the Storage tab is a spec sheet like the Dock tab. Each store shows its records, its file's size on disk and the date of its oldest record, and the tab opens with a drawing of the server's disk, used and free, with the files' part drawn larger below it, since at a few MB it would not show on a bar hundreds of GB long. The size is the file's on disk rather than an estimate of the download, so the drawing and the line agree and one number stands for each file. The disk is the one the first store's file is on: in a container, the one its folder is mounted from.
- **2026-09-26**: the Server, Firmware and MQTT tabs became spec sheets too, so every form tab is one: each group under a heading that says what it is for, and each setting a line. A setting that matters only while a switch is on, such as the MQTT broker or the firmware folder, shows only then.
- **2026-09-26**: the page schedule and the dock's sync became weeks: groups of days, each with its own time ranges, so a weekend or a single day can differ from the rest. Groups rather than a list for each day, since most weeks have two or three shapes and one group of all seven is the old schedule. A day stands alone rather than running on from the day before's last range, so each group's dial shows its days exactly; a night that spans midnight is set on both days. The display's sync stays a plain interval, which is one group of every day inside the server, so every board's schedule is the same kind and `/about` gives each as a week. The boards need no change: the server gives each its next slot.
- **2026-09-26**: the menu's Three days and Changes became History and Trend: where a measurement has been and where it is going. The names say what each page shows rather than its span, and History matches Board history in the Boards row.
- **2026-09-26**: the light's triggers became what the dock needs from you: Booting, Error, Poor air quality, Calibrating and Running. Error takes in every fault, from the network to a refused setting, because any of them needs attention and the Boards page says which. Poor air quality judges CO₂, PM2.5 and IAQ against limits in each sensor's section, not temperature or humidity, whose comfort depends on the home. Running holds whenever the dock has booted, so a trigger without a look passes the light on rather than leaving it dark. The patterns gained a blip, a swell and a ramp, and fades a smoothness of 4 to 64 steps or none, a slider in stops; 16 steps is what the light always had.
- **2026-09-27**: the display deep-sleeps between wakes instead of staying awake (§3.1). E-paper holds its image without power, so the awake display made heat and drew power for nothing. It wakes for the next page, and for its next sync when that comes first, and posts its state at every wake, so a sync beside a page needs no wake of its own. The RTC's alarm wakes it because its crystal keeps the page slots; the ESP32's timer, a little later, is there only so that a missed alarm cannot leave the display asleep for good. A freshly written image stays awake until a page confirms it: a wake from deep sleep passes through the bootloader, which takes back an image not yet confirmed. On the live display a wake costs about 7 seconds, 12 with a page, so about 55 minutes awake a day at five-minute pages; the SD card check, NTP and the one-second Wi-Fi poll are most of what could still go.
- **2026-09-27**: the head became the display, in the product and in the code: the board name `canary-display`, its firmware folder, its block in the client object, and its sync as `display.sync`, beside the page schedule it goes with. A user knows what a display is; "head" was the enclosure's word. epd's `display` block refuses keys it does not know, so canary takes `sync` out before epd reads the block rather than widen epd for one project's key. A board on the old name is offered no firmware under the new one, so the display is flashed once over USB, and the reports and logs under `canary-head` stay until they expire.
- **2026-09-27**: the dock builds in a PlatformIO folder of its own: `~/.platformio-canary-dock` locally and in CI, `/platformio/dock` in the builder. Automatic light sleep needs power management and tickless idle, which the core's precompiled IDF libraries leave out, so pioarduino compiles them again for the dock. It writes them into a package that every build in the folder shares, and the display then fails to build there. `scripts/dock_core.py` stops a dock build in `~/.platformio`. A separate dock project with its own `core_dir` was not taken: `PLATFORMIO_CORE_DIR` overrides `core_dir`, and the builder image sets it for every build.
- **2026-09-27**: the dock light-sleeps between passes of its loop (§3.1), with Wi-Fi kept: automatic light sleep at 80 MHz, the loop once a second rather than every 10 ms, and the LED task waiting for the pattern's next step rather than looking every 5 ms. On mains power the reasons are heat and power: awake, the dock drew about 71 mA at 5 V between readings, with the BME688 1.3 mm from the TinyS3. It stays online rather than deep-sleeping, which would lose the PSRAM queue and BSEC's settling. Its LED runs on the IDF's LEDC driver, because Arduino's leaves the channel no output in light sleep.
- **2026-09-28**: the boards take their time and time zone from the server instead of NTP and a time-zone lookup, which cost the display about a second at every wake, seven when NTP timed out. The zone comes as a POSIX TZ string from `server.timezone`, sent on every response, and the C library reads it. ezTime, which did the lookup, is gone: it misreads the string the zone database writes for Europe/Dublin, whose winter is a negative daylight shift, and would show summer time all year. The Wi-Fi join is checked every 100 ms rather than every second.
- **2026-09-28**: the display reads no SD card. Looking for one cost two seconds at every wake, the time the SD library waits for a card that is not there, and the display's settings are in its own store, so a card would only repeat them.
