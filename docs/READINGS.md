# Readings — the JSON the firmware posts

One document per sample set, `POST /readings`, `Content-Type: application/json`.
The firmware encodes it (`readingsToJson` in `src/sensors/ReadingsJson.cpp`),
the server stores it as-is, and the pages read it. The Python mock source
produces the same keys, so pages developed against the mock render the real
thing unchanged.

```json
{
  "ts": 1756900000,
  "device": "inkplate5-env-monitor",

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
| `ts` | Inkplate RTC | epoch seconds | when the set was assembled |
| `temp_c`, `rh_pct` | **SHTC3** | °C, % | the reference temperature and humidity |
| `co2_ppm` | SCD41 | ppm | pressure-compensated from the BME688 |
| `pm1_0`, `pm2_5`, `pm10` | PMSA003I | µg/m³ | "atmospheric environment" values, not CF=1 |
| `pc_*` | PMSA003I | count per 0.1 L | particles larger than 0.3 … 10 µm |
| `gas_ohm` | BME688 | Ω | raw heater-plate resistance; lower = more VOC |
| `pressure_hpa` | BME688 | hPa | |
| `iaq`, `iaq_accuracy` | BME688 via BSEC | 0–500, 0–3 | absent until BSEC is integrated; the mock emits them |
| `pressure_hpa` | BME688 | hPa | present whenever the chip answered, even on a cold plate |
| `scd41.*`, `bme688.*` | those sensors | °C, % | their own T/RH, which run warm; kept for offset tuning, not for display |
| `client` | firmware | object | object | the board's own state, see below |
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
Diagnostics page shows it.

```json
"client": {
  "board": "Inkplate5V2", "version": "v0.1.0-dev", "ip": "192.168.1.42", "rssi": -61,
  "uptime_s": 8040,
  "heap_free": 120000, "heap_size": 327680, "psram_free": 4000000, "psram_size": 4194304,
  "panel_temp_c": 27, "width": 1280, "height": 720, "rotation": 0,
  "mock_sensors": true,
  "sensors": { "shtc3": true, "scd41": true, "pmsa003i": true, "bme688": true },
  "fetch": { "next_url": "http://h:8080/day.png", "next_in_s": 120, "backoff_step": 0,
             "ok": 12, "failed": 1 }
}
```

`sensors.*` says which parts are running: a flag goes false when its part
stops giving readings, and true again when a restart brings it back.
`valid.*` says which are warm now. `panel_temp_c` is the e-paper power controller's sensor, which
reads the board, not the air. `fetch` is the page loop's state.

The server accepts the document at `POST /readings` and answers 204. It
keeps only the newest until the readings store exists.
