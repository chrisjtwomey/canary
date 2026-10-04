# Running it on the boards

How to run the firmware on the display and the dock from your own computer, read their logs, and check the
wiring. First do the [setup](../CONTRIBUTING.md#setup).

## Start

1. Copy `src/defaults.example.cpp` to `src/defaults.cpp` (gitignored). Set the Wi-Fi name and password. Set
   `serverURL` to your computer, for example `http://192.168.1.20:8080/breathe.png`. On a Mac,
   `ipconfig getifaddr en0` gives the address.
2. Start the server:

   ```sh
   cd server && source .venv/bin/activate && python3 server.py
   ```

   It draws every page at start, then each page 60 s before its slot. macOS asks once if Python can accept
   incoming connections: allow it.
3. Flash each board, and watch its log. Lift the display off the dock first: the dock's side wall covers its USB-C
   socket. The dock builds in a PlatformIO folder of its own
   ([Building the dock](../CONTRIBUTING.md#building-the-dock)).

   ```sh
   pio run -e esp32 -t upload && pio device monitor -b 115200
   PLATFORMIO_CORE_DIR=~/.platformio-canary-dock pio run -e dock -t upload && pio device monitor -b 115200
   ```

   For a TinyS3 with no sensors, use `dock-mock` in place of `dock`: it reads the [simulated room](simulator.md).

## The display

- The log shows the boot banner, the User-Agent and the Wi-Fi join. Then it shows `downloading file at URL ...`,
  `drawing image from buffer` and `next refresh in N s`.
- By default it shows a new page every 5 minutes on the clock (:00, :05 ...) ([schedules.md](schedules.md)).
- When a fetch fails, the last page stays on the panel, and each new try waits longer (`back-off step N`).
- `kRotation` in `src/main.cpp` is 0: the board as it comes, with the USB-C port on the right. For a board turned
  180°, set it to 2.

## The dock

- The first reading comes 35 s after boot, when the PM fan has warmed up. After that, a reading comes at each of the
  server's slots (`dock.sync.week`).
- Each reading goes into a queue, with a `client` object beside the measurements. The loop posts the queue to
  `/sensor-readings`: `posted 1 reading (200); 0 queued`.
- While the server is down, the queue grows: `posting readings failed (-1); 12 queued`. When the server answers, the
  dock sends up to 100 readings a request until the queue is empty.
- The queue is 2 MB of PSRAM, about 1,500 readings. A restart empties it. The Diagnostics page shows the count under
  Memory, for example `queue 12 of ~1,500, in psram`.
- A sensor that gives no reading gives no value. The dock does not make one up.

### Which sensors answered

- `sensor start incomplete: shtc3=1 scd41=0 pm=1 bme688=1` names each sensor that did not start (0). The
  Diagnostics page shows the same. A 0 means that the sensor is not on the bus, that another part has its address,
  or that a different part answered. The SHTC3 and the BME688 check what they talk to.
- A sensor that did not start gets another try after 30 s. Each later try waits double the last wait, up to
  10 minutes. So a sensor that you connect starts with no restart.
- A running sensor that gives no reading at a slot has stopped: it is disconnected, or it lost its settings in a
  power cut. The first 15 s after its start do not count. The dock starts it again in the same way. The log shows
  `sensor scd41 stopped; starting it again`, then `sensor scd41 running; it was idle` or `…; it was still
  measuring`. The SCD41 refuses the stop that each start sends when it is idle, and idle is where a reset of
  the part or a power cut leaves it.
- A reading without CO₂ logs why: `[scd41] no CO2 in this reading: no answer`, `bad checksum` or `no data
  ready`. The dock polls the SCD41 every second, and a run of failed polls logs two lines at info level:
  `[scd41] poll: no answer` or `bad checksum` at its first poll, and `[scd41] polls answered again after 3 failed`
  at the poll that ends it. A poll with no data ready is an answer, not a failure. The next poll reads what a
  failed one missed, so a short run costs no reading; the times show whether failures come with the readings,
  when Wi-Fi sends and the PM fan runs, or at any time.
- A damaged particle frame logs each read of that sample, such as `[pmsa003i] read 1: bad checksum;
  read 2: good`: at info level when the second read was good, as a warning when it was not. Each damaged frame
  then logs its 32 bytes, 16 to a line, so that a line queued while the broker is away keeps them whole:
  `[pmsa003i] read 1 0-15: 424d001c …`. A frame torn by the module's own update holds parts of two frames and
  keeps its start; a noisy wire changes single bits anywhere. The usual kind is a third: the module stops
  sending partway through the read, so the frame keeps its start and reads `FF` from that byte on.

### BSEC

- `static_iaq` and `iaq`, each with its accuracy, come from BSEC, Bosch's closed-source library. It runs in its
  own task, and takes a sample every `dock.bsec.sample_s`: 300 s by default, or 3 s.
- BSEC scales the index to the clean and the dirty air in its recent history. The dock uses Bosch's 28-day
  configuration, at either rate. With the 4-day one, the dock was at accuracy 1 for 53-66 % of the readings on most
  days from 28 September to 2 October 2026, in a room with steady air. A copy that BSEC learned with one
  configuration is no use with the other ([readings.md](readings.md#calibration)).
- The accuracy starts at 0. With a sample every 3 s and the 4-day configuration, it got to 3 in about 40 minutes on
  the bench.
- BSEC saves what it has learned to NVS when the accuracy first gets to 3, and every 6 hours after that. It also
  takes a copy each minute, and the dock sends the newest copy to the server after each batch of readings. After a
  restart, the dock uses the more accurate copy, or the newer one: `[bsec] state: server selected (more accurate: 3
  vs 1)`. So the server's copy is never more than one batch old. A restart for an update costs about a minute of
  learning, since the dock sends the copy just before it takes the update. A power cut costs up to the gap between
  two batches. NVS alone could lose up to 6 hours.
- Each BSEC line in the log starts with `[bsec]`. The Diagnostics page shows the accuracy and the count of late
  samples.
- `gas_ohm` is the raw gas resistance. It does not need BSEC.

#### Calibrate BSEC

BSEC stays at accuracy 1 while the air is steady, because it cannot set its references. To bring it to 3, give it
dirty air and then clean air:

1. Wait until the accuracy is 1 or more. At 0 the gas sensor is still settling after a start.
2. Hold a cloth with isopropyl alcohol 5-10 cm from the dock's air holes for 1 minute.
3. Open a window near the dock for 10-15 minutes.
4. Read the accuracy on the Diagnostics page. It goes to 2, then to 3, in about 10 minutes.

- Keep the dock plugged in. A restart sets the accuracy to 0 for about 20 minutes.
- Do not spray anything at the dock. Droplets get into the PM sensor.
- **Keep silicone away from the dock, for example sealant or some hair products. Its vapour can damage the gas
  sensor permanently.**

### The sensor drivers

- `src/dock/main.cpp` names the sensor types in one `#if` block, and nowhere else.
- The drivers take an `II2cBus` and an `IClock`. The tests in `test/test_drivers` run them against fake parts that
  answer as their datasheets say.
- The BME688's compensation is Bosch's own C API, in `lib/bme68x`.

## Validating the wiring

`dock-validate` is an image that runs a bench check in place of the dock's loop. Use it when the hardware is new or
you changed the wiring, and to measure the current. It uses no network and no server, so the log shows only the
sensors.

```sh
PLATFORMIO_CORE_DIR=~/.platformio-canary-dock pio run -e dock-validate -t upload
pio device monitor -b 115200
```

Each pass scans the bus, checks that each sensor runs and goes into its low-power state, takes one set of readings,
and puts the sensors to sleep. The next pass starts 10 s later. The phase markers give milliseconds, so that a PPK2
trace lines up with them.

```
##### canary-dock hardware validation #####
i2c timeout 50 ms; SDA IO8, SCL IO9, PM fan SET IO7
i2c scan: 0x12 0x62 0x70 0x76 (4 devices)
[validate]       0 ms  phase 1: probing the bus
[validate] shtc3 present
...
[validate] summary: 0 failures, 0 warnings in 42000 ms
```

When a pass fails:

- **A sensor is missing.** Its address is not in the scan, and it counts as a failure. The rest of the pass runs.
  The scan must show the PM module at 0x12, the SCD41 at 0x62, the SHTC3 at 0x70 and the BME688 at 0x76.
- **`PM still answers with SET low; SET wire not connected`** is a warning, not a failure. The dock cannot stop the
  fan, but each PM reading is valid. SET is the TinyS3's pin 7 ([assembly.md](../hardware/assembly.md)).
- **The board does not sleep.** A sleep would drop the USB serial port. The first pass waits up to 3 s for the port
  to open. If the start of the log is missing, start the monitor before you connect the board.
