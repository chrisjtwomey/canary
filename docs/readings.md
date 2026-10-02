# Readings

The JSON that the boards post to `POST /sensor-readings` (`Content-Type: application/json`), and the routes that
give it back.

- The firmware encodes a reading in `readingsToJson` (`src/sensors/ReadingsJson.cpp`).
- The server stores it as it is, and the pages read it.
- The Python mock source makes the same keys, so a page made against the mock shows real readings with no change.

## A reading

The dock posts one document for each reading:

```json
{
  "ts": 1756900000,
  "device": "canary-dock",

  "temp_c": 21.3,
  "rh_pct": 44.1,

  "co2_ppm": 812,

  "pm1_0": 4,
  "pm2_5": 6,
  "pm10": 8,
  "pc_0_3": 900, "pc_0_5": 250, "pc_1_0": 40, "pc_2_5": 4, "pc_5_0": 1, "pc_10": 0,
  "pm_warmup_s": 35,

  "gas_ohm": 132000,
  "iaq": 63,
  "iaq_accuracy": 2,
  "static_iaq": 58,
  "static_iaq_accuracy": 2,
  "pressure_hpa": 1011.2,

  "scd41":  { "temp_c": 25.2, "rh_pct": 36.0 },
  "bme688": { "temp_c": 22.8, "rh_pct": 40.2 },

  "samples": { "scd41": 60, "bme688": 100, "iaq": 92, "static_iaq": 92 },

  "valid": { "temp_humidity": true, "co2": true, "particulates": true, "pressure": true, "gas": true }
}
```

| Key | From | Unit | Notes |
|---|---|---|---|
| `ts` | The server's clock | Epoch seconds | When the reading was taken. The dock keeps the server's time. |
| `temp_c`, `rh_pct` | **SHTC3** | °C, % | The reference temperature and humidity |
| `co2_ppm` | SCD41 | ppm | Corrected for the BME688's pressure |
| `pm1_0`, `pm2_5`, `pm10` | PMSA003I | µg/m³ | The "atmospheric environment" values, not CF=1 |
| `pc_*` | PMSA003I | Count per 0.1 L | Particles larger than 0.3 … 10 µm |
| `pm_warmup_s` | The dock | s | How long the PM fan had run when the particle reading was taken. Only with the particles. |
| `gas_ohm` | BME688 | Ω | The raw resistance of the heated plate. Lower means more VOC. |
| `iaq`, `iaq_accuracy` | BME688, through BSEC | 0–500, 0–3 | BSEC's index for a device that moves: it stretches its scale to the last few days' air. Not there until BSEC has made an index. Kept to compare with `static_iaq`; no page shows it. The server's mock sends it at accuracy 3. |
| `static_iaq`, `static_iaq_accuracy` | BME688, through BSEC | 0–500, 0–3 | BSEC's index for a device that stays in one place, which Bosch recommends for one (BME688 datasheet, table 20). Not there until BSEC has made an index. The pages show it, and only at accuracy 3 ([pages.md](pages.md)). Both mocks send the same value and accuracy as `iaq`. |
| `pressure_hpa` | BME688 | hPa | There each time the chip answered, even on a cold plate |
| `scd41.*`, `bme688.*` | Those sensors | °C, % | Their own temperature and humidity, which read warm. Kept to tune the offsets, not to show. `scd41` is not there during the SCD41's warm-up after each start, 3 minutes by default ([the sensor code](dock.md#the-sensor-code)). |
| `samples` | The dock | Counts | How many samples each mean holds: `scd41` the SCD41's measurements, `bme688` the BME688's cycles, and of those, `iaq` and `static_iaq` the cycles that each index counted, those at accuracy 3. `bme688` is 0 when no cycle ran since the last reading, as can happen with a BSEC sample every 5 minutes: its values then repeat the newest cycle. Not there when both counts are 0. |
| `client` | The firmware | Object | The board's own state ([below](#the-client-object)) |
| `health` | The dock | Object | How its sensors are ([below](#the-health-object)) |
| `valid.*` | The firmware | Bool | False when that measurement cannot be trusted this time |

- The SCD41's and the BME688's values are the means of their samples over the interval before `ts`: 5 minutes by
  day, 30 at night ([the sensor code](dock.md#the-sensor-code)). The SHTC3 and the PMSA003I measure once a reading.
- Integers are integers. Floats (temperature, humidity, pressure) have one decimal.
- A key never changes its meaning. A new sensor adds new keys.

## Absent keys

**A measurement that the firmware does not trust is left out. It is never sent as `null`.** Read a value with
`doc.get("co2_ppm")`, and a missing value comes back as `None`.

`valid` says the same in one place, so a page can say *why* a value is missing, not only show a dash. Its flags are
for each **measurement**, not each sensor, because one chip can be right about one value and wrong about another.
For example, the BME688's gas plate heats to 300 °C. Until `heat_stab` says that it got there, the resistance and
the IAQ made from it mean nothing, but the pressure from the same cycle is correct. A reading from such a cycle,
with no CO₂ value ready either, looks like this:

```json
{ "ts": 1756900000, "pressure_hpa": 1011.2,
  "valid": { "temp_humidity": true, "co2": false, "particulates": true,
             "pressure": true, "gas": false } }
```

It has no `gas_ohm`, no `iaq` and no `static_iaq`, but it has `pressure_hpa`.

## The `client` object

Each document that a board posts also carries what the board knows about itself. None of it measures the room: the
Diagnostics pages show it.

- Network, memory, version, uptime and reset reason are the same for both boards.
- Each board's own fields are in a block with its name, `display` or `dock`. A board sends only its own block.

```json
"client": {
  "board": "Inkplate5V2", "version": "v0.6.2", "ip": "192.168.1.43", "rssi": -70,
  "uptime_s": 400, "reset": "power_on",
  "heap_free": 100000, "heap_size": 327680, "psram_free": 4000000, "psram_size": 4194304,
  "display": {
    "panel_temp_c": 27, "width": 1280, "height": 720, "rotation": 0,
    "fetch": { "next_url": "http://h:8080/day.png", "next_in_s": 120, "backoff_step": 0,
               "ok": 12, "failed": 1 }
  }
}

"client": {
  "board": "TinyS3", "version": "v0.6.2", "ip": "192.168.1.42", "rssi": -61,
  "uptime_s": 8040, "reset": "software", "chip_temp_c": 41,
  "heap_free": 120000, "heap_size": 327680, "psram_free": 6000000, "psram_size": 8388608,
  "dock": {
    "mock_sensors": false,
    "sensors": { "shtc3": true, "scd41": true, "pmsa003i": true, "bme688": true },
    "fan_warmup_s": 35,
    "backlog": { "held": 0, "capacity": 1480, "store": "psram" },
    "bsec": { "running": true, "restored": true, "accuracy": 2, "late": 0,
              "saved": 1757443200, "sample_s": 300 },
    "settings": { "version": "5bd4ecec", "refused": [] },
    "recalibrated": { "id": 1758650400, "ppm": 420, "ok": true, "correction_ppm": -12 },
    "light": "running"
  }
}
```

**Both boards:**

| Key | What it is |
|---|---|
| `reset` | Why the board last started, as ESP-IDF's `esp_reset_reason()` names it. Expected: `power_on`, `software` (a restart that the firmware asked for, as after an update), `external`, `usb`, `jtag`, `sdio`. Faults: `panic`, `cpu_lockup`, `int_watchdog`, `task_watchdog`, `watchdog`, `brownout`, `power_glitch`, `efuse`. `unknown` is anything else. Diagnostics counts faults apart from the other restarts. |
| `uptime_s`, `reset` on the display | A wake from deep sleep is not a start. So the display sends the values from its last real start. |
| `chip_temp_c` | The chip's own sensor. It reads the chip, not the air. Only the dock sends it, because the display's classic ESP32 always reads 53 °C. Not there when the chip gives no value. |

**`display`:**

| Key | What it is |
|---|---|
| `panel_temp_c` | The e-paper power controller's sensor. It reads the board, not the air. |
| `fetch` | The page loop's state |

**`dock`:**

| Key | What it is |
|---|---|
| `sensors.*` | Which parts run. A flag goes false when its part stops giving readings, and true again when a restart brings it back. `valid.*` says which values are good now. |
| `fan_warmup_s` | How long the PM fan runs before each reading. 0 when it runs all the time. |
| `backlog` | How many readings waited in the queue when this one was taken; about how many the queue holds when full, at the size of the newest (0 before the first); and where they wait: `psram`, or `ram` when the board has no PSRAM to spare. |
| `bsec` | BSEC's own state: whether it runs; whether it took a saved state when it started; the accuracy of `iaq`, not of `static_iaq`; how many of its samples were late; when it last saved its state this boot (0 for not yet); and the seconds between its samples, 3 or 300. |
| `settings` | The version of the settings that the dock runs, and the keys it refused ([dock-settings.md](dock-settings.md)). |
| `recalibrated` | The last recalibration that the dock ran: the id that the server gave it, and the correction that the SCD41 made. An `id` of 0 means none yet. |
| `light` | What the status LED shows: the trigger ([led.md](led.md)), or `updating` or `dark`. |

A reading keeps the `client` object that it was queued with. So a batch that arrives after an outage shows how the
board was through it. The server keeps the report with the highest `ts` as the newest.

## The `health` object

Each dock document also carries how its sensors are, as opposed to what they measure:

```json
"health": {
  "restarts": 2,
  "checksum_failures": { "pmsa003i": 5, "shtc3": 1, "scd41": 0 },
  "bme688": { "gas_valid": true, "heat_stable": true, "heater_c": 300, "heater_ms": 100 },
  "scd41": { "serial": "9a3bc0ffee41", "asc": true, "offset_c": 4.0, "pressure_hpa": 1011 },
  "pmsa003i": { "version": 151, "error": 0 },
  "shtc3": { "id": "0887", "low_power": false }
}
```

| Key | What it is |
|---|---|
| `restarts` | How many times the dock started a sensor again after it stopped answering |
| `checksum_failures` | The answers that arrived damaged: a PMSA003I frame with a bad start, length or checksum, and an SHTC3 or SCD41 word with a bad CRC. A good bus never makes one, so a rising count shows a loose or noisy wire before a sensor goes missing. |
| `bme688` | The last reading: whether the gas conversion took place, whether the heater reached its target, and the heater's target and time. Without both flags, the gas resistance and the index made from it are noise. `valid.gas` only says that one of them failed. Not there when the last sample had no BME688 reading. |
| `scd41` | What the part said at its last start: its serial number, whether its self-calibration is on, and its temperature offset. Also the last pressure that the dock gave it. The part answers these only while idle, so the dock asks before it starts to measure. |
| `pmsa003i` | The version and error bytes of the last frame |
| `shtc3` | The ID that the part gave at its start, and whether it measures in low-power mode |

- The counts start at the dock's start, so they go back to 0 at each restart.
- A value that the dock did not get is left out.
- The server keeps the object with the rest of each report in the status store, not in the readings store. The
  `health-trace` page draws it over the day.

## Posting

- The dock queues each document when it takes the reading. It posts the queue oldest first, up to 100 documents at
  a time, as one JSON array. The display posts its one document as an object.
- The server takes either at `POST /sensor-readings`, writes a batch in one transaction, and answers
  `{"new": 3, "repeated": 0}`.
- A document is stored by its device and `ts`. A second copy of the same pair is ignored, and counted as repeated.
  So to send it again after a lost reply changes nothing.
- A timeout, a 5xx or a 409 keeps the whole batch in the queue. The dock tries again after its next reading.
- Any other 4xx makes the dock send that batch again one document at a time, so a document that the server refuses
  costs only itself.
- Each whole document goes to the Diagnostics pages. With `source.kind: store`, each document also goes into the
  readings store, without its `client` object, and the other pages draw from the store.

## Reading them back

`GET /sensor-readings?from=<epoch>&to=<epoch>&device=<device>` gives the stored documents in that window, oldest
first. By default it gives the last day, and every board unless `device` names one.

```json
{ "from": 1756813600, "to": 1756900000, "count": 288, "left_out": 0,
  "readings": [ { "ts": 1756813654, "device": "canary-dock", "co2_ppm": 640, ... } ] }
```

- They are the documents as the store keeps them: no `client` object, and the pressure as measured, not at sea
  level.
- One answer holds at most 5,000 documents, the newest. `left_out` counts the older ones.

`GET /status` gives the newest report of each board, as the Diagnostics pages read them, or a 404 before the first:

```json
{ "doc": { ... the newest report of any board ... }, "age_s": 12, "count": 40,
  "boards": { "canary-dock": { "doc": { "ts": ..., "client": { ... }, "health": { ... } }, "age_s": 12 },
              "canary-display": { "doc": { ..., "settings_version": "3f2a9c1e" }, "age_s": 48 } } }
```

- The server puts `settings_version` on each report from the display: the version of the display and image
  settings it ran when the report came ([schedules.md](schedules.md#the-displays-sync)). The status store keeps it.

`age_s` is the seconds since the report arrived.

## Calibration

BSEC's learned state is not a reading, so it has a route of its own. BSEC takes a copy of it each minute. After each
batch of readings that the server takes, the dock posts the newest copy to `POST /calibration`:

```json
{ "device": "canary-dock",
  "calibration": {
    "bme688": { "state": "<320 characters of base64>", "accuracy": 3, "saved": 1757443200,
                "sample_s": 300, "history_days": 28 } } }
```

| Key | What it is |
|---|---|
| `state` | BSEC's 238-byte state |
| `accuracy` | The IAQ accuracy when the copy was taken |
| `saved` | When the copy was taken, in UTC seconds. A copy taken before the clock was set is not sent. |
| `sample_s` | The rate at which BSEC learned it. A state is no use to BSEC at the other rate. |
| `history_days` | The days of history in the configuration that BSEC learned it with: 28. A state is no use to BSEC with the other configuration, Bosch's 4-day one. A copy without it is a 4-day copy. |

- The block is keyed by sensor, so that other sensors can join it. Only the BME688 has a learned state that the
  board can back up.
- A copy that the server refuses is not sent again. A copy that the server could not take for now goes after the
  next batch that it takes.
- The calibration store keeps the block for each source kind. It keeps each copy for `calibration.keep_days`.
- `GET /calibration?device=<device>&before=<epoch>&sample_s=<3 or 300>&history_days=<4 or 28>` gives the newest
  copy at that rate and history taken before that time, a copy at accuracy 3 first, or a 404. Copies kept before
  BSEC had a choice of rate count as 3 s. Copies kept, and requests made, without a history count as 4 days.

After a boot, once the server has taken a batch, the dock asks for the server's copy at BSEC's rate and history:
`GET /calibration?device=<device>&before=<boot time>&sample_s=<rate>&history_days=28`.

- It starts BSEC again on that copy when it is better than the copy from NVS: more accurate, or as accurate and more
  than an hour newer.
- A copy from NVS at the other rate, or with the 4-day history, counts as none. BSEC then starts from nothing, and
  the log says so: `[bsec] start: NVS state learned at 3 s with 4 days of history; starting from nothing`.
- When the settings change the rate, BSEC starts again from nothing at the new rate, and the dock asks the server
  once more.
