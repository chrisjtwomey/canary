# Readings — the JSON the firmware posts

One document per sample set, `POST /sensor-readings`, `Content-Type: application/json`.
The firmware encodes it (`readingsToJson` in `src/sensors/ReadingsJson.cpp`),
the server stores it as-is, and the pages read it. The Python mock source
produces the same keys, so pages developed against the mock render the real
thing unchanged.

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

  "gas_ohm": 132000,
  "iaq": 63,
  "iaq_accuracy": 2,
  "pressure_hpa": 1011.2,

  "scd41":  { "temp_c": 25.2, "rh_pct": 36.0 },
  "bme688": { "temp_c": 22.8, "rh_pct": 40.2 },

  "valid": { "temp_humidity": true, "co2": true, "particulates": true, "pressure": true, "gas": true }
}
```

| Key | Source | Unit | Notes |
|---|---|---|---|
| `ts` | the server's clock | epoch seconds | when the set was taken; the dock keeps the server's time |
| `temp_c`, `rh_pct` | **SHTC3** | °C, % | the reference temperature and humidity |
| `co2_ppm` | SCD41 | ppm | pressure-compensated from the BME688 |
| `pm1_0`, `pm2_5`, `pm10` | PMSA003I | µg/m³ | "atmospheric environment" values, not CF=1 |
| `pc_*` | PMSA003I | count per 0.1 L | particles larger than 0.3 … 10 µm |
| `pm_warmup_s` | the dock | s | how long the PM fan had run when the particle reading was taken; with the particles only |
| `gas_ohm` | BME688 | Ω | raw heater-plate resistance; lower = more VOC |
| `iaq`, `iaq_accuracy` | BME688 via BSEC | 0–500, 0–3 | absent until BSEC has produced an index; the mock emits them |
| `pressure_hpa` | BME688 | hPa | present whenever the chip answered, even on a cold plate |
| `scd41.*`, `bme688.*` | those sensors | °C, % | their own T/RH, which run warm; kept for offset tuning, not for display |
| `client` | firmware | object | the board's own state, see below |
| `valid.*` | firmware | bool | false when that measurement was not trustworthy this cycle |

Integers are integers; floats carry one decimal (temperatures, humidity,
pressure). Keys never change meaning; new sensors add keys.

## Absent keys

**A measurement the firmware does not trust is left out, never sent as
`null`.** Read a value with `doc.get("co2_ppm")` and absence arrives as
`None` on its own.

`valid` says the same thing in one place, so a page can report *why* a
figure is missing rather than just showing a dash. Its flags are per
**measurement**, not per sensor, because one chip can be right about one
thing and wrong about another: the BME688's gas plate heats to 300 °C, and
until `heat_stab` says it arrived, the resistance and the IAQ derived from
it are meaningless — while the pressure from the same cycle is fine. So the
first sample of every boot looks like this:

```json
{ "ts": 1756900000, "pressure_hpa": 1011.2,
  "valid": { "temp_humidity": true, "co2": false, "particulates": false,
             "pressure": true, "gas": false } }
```

no `gas_ohm`, no `iaq`, `pressure_hpa` present. `co2` is false because the
SCD41's first five-second conversion has not landed, `particulates` because
the PM fan needs thirty seconds before its counts mean anything.

## The `client` object

Beside the measurements, every posted document carries what the board
knows about itself. None of it is a measurement of the room; the
Diagnostics page shows it. Network, memory and version are common to both
boards; each board's own fields sit in a block named for it, `head` or
`dock`, and a board sends only its own.

```json
"client": {
  "board": "Inkplate5V2", "version": "v0.1.0-dev", "ip": "192.168.1.43", "rssi": -70,
  "uptime_s": 400, "reset": "power_on", "chip_temp_c": 53,
  "heap_free": 100000, "heap_size": 327680, "psram_free": 4000000, "psram_size": 4194304,
  "head": {
    "panel_temp_c": 27, "width": 1280, "height": 720, "rotation": 0,
    "fetch": { "next_url": "http://h:8080/day.png", "next_in_s": 120, "backoff_step": 0,
               "ok": 12, "failed": 1 }
  }
}

"client": {
  "board": "canary-dock", "version": "v0.1.0-dev", "ip": "192.168.1.42", "rssi": -61,
  "uptime_s": 8040, "reset": "software", "chip_temp_c": 41,
  "heap_free": 120000, "heap_size": 327680, "psram_free": 4000000, "psram_size": 4194304,
  "dock": {
    "mock_sensors": true,
    "sensors": { "shtc3": true, "scd41": true, "pmsa003i": true, "bme688": true },
    "fan_warmup_s": 35,
    "backlog": { "held": 0, "capacity": 1480, "store": "psram" },
    "bsec": { "running": true, "restored": true, "accuracy": 2, "late": 0,
              "saved": 1757443200, "sample_s": 300 },
    "settings": { "version": "5bd4ecec", "refused": [] },
    "recalibrated": { "id": 1758650400, "ppm": 420, "ok": true, "correction_ppm": -12 }
  }
}
```

`chip_temp_c` is the chip's own sensor: it reads the chip, not the air, and
is left out when the chip gives none. `reset` is why the board last
started, as ESP-IDF's `esp_reset_reason()` names it: `power_on`, `software`
(a restart the firmware asked for, as after an update), `deep_sleep` (a
wake), `external`, `usb`, `jtag` or `sdio` are expected; `panic`,
`cpu_lockup`, `int_watchdog`, `task_watchdog`, `watchdog`, `brownout`,
`power_glitch` and `efuse` are faults; `unknown` is anything else.
Diagnostics counts a fault apart from the other restarts, and a wake from
deep sleep as no restart.

In `head`, `panel_temp_c` is the e-paper power controller's sensor, which
reads the board, not the air, and `fetch` is the page loop's state.

In `dock`, `sensors.*` says which parts are running: a flag goes false when
its part stops giving readings, and true again when a restart brings it
back; `valid.*` says which are warm now. `fan_warmup_s` is how long the PM
fan runs before each reading, 0 when it runs all the time. `backlog` is how
many readings waited in the queue when this one was taken, about how many
it holds when full, at the size of the newest (0 before the first), and
where they wait: `psram`, or `ram` when the board has no PSRAM to spare. A
reading keeps the `client` object it was queued with, so a batch that
arrives after an outage fills in how the board fared through it; the server
keeps the report with the highest `ts` as the newest. `bsec` is BSEC's own
state: whether it runs, whether it took a saved state when it started, the
accuracy of its index, how many of its samples were late, when it last
saved its state this boot (0 for not yet), and the seconds between its
samples, 3 or 300. `settings` and `recalibrated` (ARCHITECTURE §3.8) are
the version of the settings it runs and the keys of them it refused, and
the last recalibration it ran, with the id the server gave it and the
correction the SCD41 made; an `id` of 0 is none yet.

The dock queues every document when it takes the reading, and posts the
queue oldest first, up to 100 documents at a time as one JSON array. The
head posts its single document as an object. The server takes either at
`POST /sensor-readings`, writes a batch in one transaction, and answers
`{"new": 3, "repeated": 0}`. A document is stored by its own device and
`ts`, and a second copy of the same pair is ignored and counted as
repeated, so sending one again after a lost reply changes nothing.

A timeout, a 5xx or a 409 leaves the whole batch in the queue, and the dock
tries again once the next reading is queued. Any other 4xx makes it send
that batch again one document at a time, so a document the server refuses
costs only itself.

Every document, whole, feeds the Diagnostics pages. With `source.kind:
store` in `config.yaml`, every document also goes into the readings store,
without its `client` object, and the other pages draw from the store.

## Reading them back

`GET /sensor-readings?from=<epoch>&to=<epoch>&device=<device>` answers with the
stored documents in that window, oldest first: the last day by default, and
every board unless `device` names one.

```json
{ "from": 1756813600, "to": 1756900000, "count": 288, "left_out": 0,
  "readings": [ { "ts": 1756813654, "device": "canary-dock", "co2_ppm": 640, ... } ] }
```

They are the documents as the store keeps them: no `client` object, and
pressure as measured, not reduced to sea level. One answer holds at most
5,000, the newest; `left_out` counts the older ones.

`GET /status` answers with the newest report of each board, as the
Diagnostics pages read them, or a 404 before the first:

```json
{ "doc": { ... the newest report of any board ... }, "age_s": 12, "count": 40,
  "boards": { "canary-dock": { "doc": { "ts": ..., "client": { ... }, "health": { ... } }, "age_s": 12 },
              "canary-head": { "doc": { ... }, "age_s": 48 } } }
```

`age_s` is the seconds since the report arrived.

## The `health` object

Beside the `client` object, each dock document carries how its sensors are
faring, as opposed to what they measure:

```json
"health": {
  "restarts": 2,
  "checksum_failures": { "pmsa003i": 5, "shtc3": 1, "scd41": 0 },
  "bme688": { "gas_valid": true, "heat_stable": true },
  "scd41": { "serial": "9a3bc0ffee41", "asc": true, "offset_c": 4.0 }
}
```

`restarts` is how many times the dock started a sensor again after it
stopped answering. `checksum_failures` counts the answers that arrived
damaged: a PMSA003I frame with a bad start, length or checksum, and an
SHTC3 or SCD41 word with a bad CRC. A sound bus never produces one, so a
rising count is a loose or noisy wire before it becomes a missing sensor.
The counts run from the dock's start, so they fall to 0 at each restart.

`bme688` is the state of its last reading: whether the gas conversion took
place and whether the heater reached its target. Without both the gas
resistance, and the index built on it, is noise; `valid.gas` says only that
one of them failed. It is absent when the last sample had no BME688 reading.

`scd41` is what the part said at its last start: its serial number, whether
its automatic self-calibration is on, and its temperature offset. The part
answers these only while idle, so the dock asks before it starts measuring.
A value it did not get is left out.

The server keeps it with the rest of each report in the status store, out
of the readings store, and the `health-trace` page draws it over the day.

## The `calibration` block

BSEC's learned state is not a reading, so it has a route of its own. Each
time BSEC saves a new copy, the dock posts it to `POST /calibration` once
the server is taking its readings:

```json
{ "device": "canary-dock",
  "calibration": {
    "bme688": { "state": "<320 characters of base64>", "accuracy": 3, "saved": 1757443200,
                "sample_s": 300 } } }
```

`state` is BSEC's 238-byte state, `accuracy` the IAQ accuracy when it was
taken, `saved` when it was taken, in UTC seconds, and `sample_s` the rate
BSEC learned it at: a state is no use to BSEC at the other rate. A copy saved before
the clock was set is not sent. The block is keyed by sensor so that other
sensors can join it; only the BME688 has learned state the board can back
up. A copy the server refuses is not sent again; one it could not take for
now is sent after the next batch it takes.

The calibration store keeps the block whatever the source kind. Every copy
is kept for `calibration.keep_days`, and
`GET /calibration?device=<device>&before=<epoch>&sample_s=<3 or 300>` answers
with the newest copy at that rate saved before that time, one at accuracy 3
first, or a 404. Copies kept before BSEC had a choice of rate count as 3 s.

After a boot, once the server has taken a batch, the board asks for the
server's copy at BSEC's rate with
`GET /calibration?device=<device>&before=<boot time>&sample_s=<rate>`, and
restarts BSEC on it when it is better than the copy NVS gave it: more
accurate, or as accurate and more than an hour newer. A copy from NVS at the
other rate counts as none. When the settings change the rate, BSEC starts
again from nothing at the new one, and the board asks the server once more.
