# Inkplate 5 Gen2 Environment Monitor

An indoor air-quality display: CO₂, particulates, VOC and temperature on a
5.2" e-paper panel, rendered server-side.

**Status: scaffold.** The sensors have not arrived. What runs today is the
simulated room and its four sensor mocks, on the host and on the device.

| | |
|---|---|
| CO₂ | Sensirion SCD41 |
| PM1.0 / PM2.5 / PM10 | Plantower PMSA003I (Adafruit breakout) |
| VOC, gas, pressure | Bosch BME688 (Soldered breakout) |
| Temperature, humidity | Sensirion SHTC3 (Soldered breakout) — the reference |
| Display / controller | Soldered Inkplate 5 Gen2 (ESP32-WROVER-E) |

All four sensors hang off one I²C bus over Qwiic/easyC. Mains powered: the
particulate sensor's fan and the CO₂ sensor's 175 mA peaks rule out useful
battery life. See [docs/HARDWARE.md](docs/HARDWARE.md) §7.

## Documentation

| | |
|---|---|
| [docs/HARDWARE.md](docs/HARDWARE.md) | Every datasheet distilled: wiring, commands, timing, currents, gotchas, 3D files. The reference to reach for instead of searching. |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | How this departs from the weather calendar's model, what [epd](https://github.com/chrisjtwomey/epd) must gain, and the order of work. |
| [docs/READINGS.md](docs/READINGS.md) | The JSON the firmware posts. |

## Build and test

epd must be checked out beside this repo.

```sh
pio test -e native     # room model and sensor mocks, on the host
pio run -e esp32       # firmware; mocks selected by -DUSE_MOCK_SENSORS
```

```sh
cd server
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pip install -e ../../epd/server     # develop against a local kit checkout
pytest
```

`pio run -e esp32 -t upload` then `pio device monitor` prints one readings
document every five seconds, driven by the simulated room.

## The mocks

`EnvModel` is a simulated room: CO₂ rises with occupancy and decays with
ventilation, windows open twice a day, cooking spikes particulates and VOCs,
the heating follows a schedule. It exists in C++ and in Python, pinned to the
same pseudo-random sequence, so the firmware and the page rendering see the
same shapes.

Each mock reproduces its datasheet's timing and quirks rather than its
registers: the SCD41's 5 s cadence and untrustworthy first reading, the
PMSA003I's 30 s fan warm-up and occasional bad checksum, the BME688's
unstable first heater cycle, the SHTC3's 13 ms measurement and sleep. They
are corrected against the real parts when those arrive.
