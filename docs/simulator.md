# The simulated room

Run CANARY with no sensors and no board. First do the [setup](../CONTRIBUTING.md#setup).

`EnvModel` is a simulated room. People come and go, and CO₂ follows them. Windows open twice a day, cooking makes
particulates and VOCs, and the heating follows a schedule. The C++ and the Python versions use the same
pseudo-random sequence, so the firmware and the pages see the same room. Each mock sensor copies the timing and the
faults of its datasheet, not its registers ([ARCHITECTURE §6](architecture.md#6-mocks--what-as-close-as-possible-means)).

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
