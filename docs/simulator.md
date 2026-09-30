# The simulated room

Run CANARY with no sensors and no board. First do the [setup](../CONTRIBUTING.md#setup).

`EnvModel` is a simulated room. People come and go, and CO₂ follows them: it rises with the people and decays with
ventilation (τ ≈ 60–90 minutes). Windows open twice a day, cooking and cleaning make particulates and VOCs, and the
temperature and humidity follow a daily curve with the heating on. The C++ and the Python versions use the same
pseudo-random sequence, so the firmware and the pages see the same room. Each mock sensor copies the timing and the
faults of its datasheet, not its registers ([The mock sensors](#the-mock-sensors)).

The server uses the room when `source.kind` is `mock`, which is the default. [pages.md](pages.md) draws the pages
from it.

`pio run -e sim` builds the dock's sensor loop for your computer: the same room, mocks and `SensorSuite` as the
firmware, with no Arduino.

```sh
pio run -e sim
.pio/build/sim/program --help
.pio/build/sim/program                            # one day, a sample every 5 minutes, at once
.pio/build/sim/program --start 17:00 --hours 4 --interval 600   # the evening: cooking, CO2 climbs
.pio/build/sim/program --start 08:00 --hours 0.02 --interval 5  # the PM fan's 30 s warm-up
.pio/build/sim/program --speed 60                 # one minute a second, as it happens
.pio/build/sim/program --json --hours 0.01        # the JSON the dock posts
```

The `sensors` column shows which sensors gave a reading: `T` temperature and humidity, `C` CO₂, `P` particulates,
`G` gas. A dot means no reading. That is normal while the PM fan warms up, and between the SCD41's 5 s
measurements.

For a TinyS3 with no sensors, the `dock-mock` environment reads the room in place of the sensors
([boards.md](boards.md)).

## The mock sensors

The value is in the **timing and the faults**, not in a copy of the registers. Each mock has its part's interface
(`IShtc3`, `IScd41`, `IPmsa003i`, `IBme688`), and does what the datasheet says the real part does:

| Mock | What it does as the part does |
|---|---|
| `MockScd41` | A 5 s measurement interval, with `data_ready` false between. Missed intervals are dropped, not queued. The first shot after power-up is discarded. ±10 ppm repeatability noise. Commands are refused while it measures, and for 500 ms after a stop. `set_ambient_pressure` changes the answer. |
| `MockPmsa003i` | 3 s to boot, then 30 s of fan spin-up with the counts rising from zero. A frame every 2.3 s, with old bytes between. A checksum failure now and then. SET low silences it, and starts the warm-up again. |
| `MockBme688` | Forced-mode timing (TPH and heater). `heat_stab` is false on the first cycle, and when the profile is too short or too hot. The gas resistance falls with VOC and with humidity. The pressure follows the model. |
| `MockShtc3` | A 12 ms measurement, 0.8 ms in low-power mode. Sleep and wake, with NACKs while asleep. ±0.1 °C and ±0.1 % RH repeatability, ±0.4 in low-power mode. |

### Response time and self-heating

Each reading lags what it measures, and two of the parts heat themselves. `LaggedValue` is the shared first-order
lag, and each mock uses the τ63 that its datasheet gives:

| | τ63 |
|---|---|
| SHTC3 temperature / humidity | 15 s (datasheet: 5–30 s, depends on the design) / 8 s |
| SCD41 CO₂ / humidity / temperature | 60 s / 90 s / 120 s |
| BME688 gas / humidity | 92 s (ULP duty cycle) / 8 s |
| PMSA003I concentration | 4 s, from "total response time ≤ 10 s" |

- Self-heating rises from zero after power-on, with a time constant of 300 s. That is not a datasheet figure. It
  puts the part within 5% at 15 minutes, which is the time Sensirion's design-in guide asks you to wait before you
  judge the temperature offset.
- The real SCD41 also reads high for about 2 minutes after each start of its measurements
  ([the sensor code](dock.md#the-sensor-code)). That is a different effect from the cold start below, and the mock
  does not make that error. The dock's rule still applies: the JSON has no `scd41` object during the warm-up, the
  first 3 minutes of a run by default.
- This is why the SHTC3 is the display's reference for temperature:

  ```
    time    SHTC3   SCD41   BME688
    14:00    18.4       -    18.4
    14:04    18.3    16.7    19.3
    14:12    18.4    18.3    19.8
    14:20    18.4    18.4    19.9
  ```

- The SCD41 reads about 4 °C **low** after a cold start, because its default offset takes off self-heating that
  the part has not made yet. The SHTC3 has no real self-heating (16 µW) and no electrical warm-up: 240 µs to idle,
  and its first reading is valid. So it is steady from the first sample.
- The Python mock source always runs settled, because it replays the three hours before the window it returns. So
  the pages never show the warm-up, which is correct while you design them.
