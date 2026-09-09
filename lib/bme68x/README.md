# bme68x

Bosch Sensortec's BME68x Sensor API, v4.4.8, taken from
[BME68x_SensorAPI](https://github.com/boschsensortec/BME68x_SensorAPI) at
commit `80ea120` (2023-05-17). Only `bme68x.c`, `bme68x.h` and
`bme68x_defs.h` are here; the upstream `examples/` define their own `main()`
and would collide with the test binaries.

It carries the temperature, pressure, humidity and gas-resistance
compensation, and the heater-resistance calculation. Those are twenty
calibration coefficients and a page of arithmetic whose failure mode is a
plausible wrong number, so the vendor's version is the one to run.

`Bme688Driver` is the only thing that includes it. The API reaches the bus
through function pointers, so the driver hands it `II2cBus` and the host
tests drive it with a fake register file.

Licence: BSD-3-Clause, see `LICENSE`.
