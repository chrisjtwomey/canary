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
  "pressure_hpa": 1011.2,
  "iaq": 63,
  "iaq_accuracy": 2,

  "scd41":  { "temp_c": 25.2, "rh_pct": 36.0 },
  "bme688": { "temp_c": 22.8, "rh_pct": 40.2 },

  "valid": { "trh": true, "co2": true, "pm": true, "gas": true }
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
| `scd41.*`, `bme688.*` | those sensors | °C, % | their own T/RH, which run warm; kept for offset tuning, not for display |
| `valid.*` | firmware | bool | false when that sensor gave no good reading this cycle; its keys are then omitted or stale |

Integers are integers; floats carry one decimal (temperatures, humidity,
pressure). Keys never change meaning; new sensors add keys.
