# The dock

How the dock's firmware works: its loop, its clock, the readings queue, and the sensor code. To run it on a board,
read [boards.md](boards.md).

## The loop

`src/dock/main.cpp`:

```
setup:  80 MHz; light sleep on; wifi; the settings from NVS; I2C; BSEC; sensors.begin(); the first reading in 35 s
loop:   once a second, light-sleeping between passes
        until known   GET /about           every 30 s, for the server's time
        before a slot GET /board-settings  the settings, applied (dock-settings.md); a recalibration; a stopped sensor started again
        each slot     queue a reading      the SCD41 and BME688 means, a fresh SHTC3 and PM sample, the dock's own status, into PSRAM
        every pass    the SCD41            its measurement, when one is ready, for the next reading's mean
                      POST /sensor-readings       the oldest 100 in the queue as one batch, once the time is known
                      POST /calibration    BSEC's state, after a batch, when BSEC has saved a new copy
        continuous    the PM fan and the status LED
BSEC:   a FreeRTOS task of its own; its state goes to NVS when accuracy first reaches 3, and every six hours after
LED:    a FreeRTOS task of its own, so the booting pattern runs while setup() blocks
```

- **80 MHz, not 240.** Wi-Fi needs 80 MHz. Below it, the APB clock follows the processor, which would move the
  serial baud rate. So 80 MHz is both the floor and the choice.
- **Light sleep.** Power management holds the clock at 80 MHz, and light-sleeps the chip whenever every task waits.
  Between passes of the loop, the Wi-Fi driver wakes it for the access point's beacons, the BSEC task for its
  samples, and the LED task for each step of the pattern ([led.md](led.md)). The LED's PWM runs through the sleep on
  the RC_FAST clock. The chip stays awake while its USB port is connected to a computer.
- **The PM fan.** It runs for the 35 s before each reading, and stops after it: 12% of the time at 5-minute slots,
  and 2% overnight. It is the dock's largest load: about 95 mA of the sensors' 110 mA *(measured)*. The 35 s is Plantower's
  30 s warm-up and a margin, counted back from the next slot. Each reading records in `pm_warmup_s` how long the fan
  ran, so the stored readings can show whether 30 s is enough. `SensorSuite` counts no missed frame while the fan is
  off, so a stopped fan does not make the module look dead. The settings can lengthen the time, or keep the fan on.

## The clock

The dock has no clock, and does not ask NTP.

- Every response from the server carries its time and its time zone ([versions.md](versions.md)). The dock holds
  the time as an offset from its uptime, so the readings it stamps and the slots the server counts always agree.
- Its uptime runs fast while the chip light-sleeps: about +350 ppm against the server, 0.6 s in 30 minutes. Before
  light sleep it was +25 ppm. Each response sets the time again, so only the timer to the next slot sees it
  ([schedules.md](schedules.md#the-docks-schedule)).
- Until the first response, the dock asks `GET /about` every 30 s. It queues its readings with their uptime, and
  stamps them when the time arrives. So a dock that starts while the server is down keeps what it measured, with
  the correct times.

## The readings queue

- Each slot puts one reading into the queue, in the layout of [readings.md](readings.md). The reading is kept before
  anything is sent, so one path covers a post that works and an outage.
- Each pass of the loop posts the oldest 100 readings to `/sensor-readings` as one batch. A queue that built up
  while the server was down empties one batch a pass, and no new reading waits for more than one request.
- The queue is 2 MB of PSRAM: about 1,500 readings, or five days at a reading every five minutes. A restart empties
  it.

On the server:

- epd's `DisplayServer(ingest=...)` gives each batch to `ReadingsIngest`. It keeps each document for the
  Diagnostics pages. With `source.kind: store`, it also adds the batch to epd's `ReadingsStore` (SQLite), in one
  transaction.
- The store's key is the device and `ts`. So the same document posted twice is stored once, however the requests
  were batched, and the route is safe to repeat.
- `IngestSource` gives the store to the pages as the datasets `latest`, `history_24h` and `history_72h`, and
  `CorrectedSource` reduces the pressure to sea level and holds back an IAQ below accuracy 3 ([pages.md](pages.md)).
  With `source.kind: mock`, `MockReadingsSource` gives the simulated room under the same names. The Diagnostics
  pages read `status`.
- The fields (`co2_ppm`, `pm2_5`, `iaq`, `temp_c` ...) are CANARY's own. The kit stores a timestamped JSON
  document, and does not read it.
- BSEC's learned state goes to `POST /calibration` each time BSEC saves a new copy. `CalibrationStore` keeps it, and
  `GET /calibration` gives it back after the dock restarts. The dock then uses the more accurate copy, or the newer
  one ([boards.md](boards.md#bsec)).

## The sensor code

- **One place names the parts.** `src/dock/main.cpp` names a concrete sensor type only in one
  `#if defined(USE_MOCK_SENSORS)` block. That block makes either the mocks or the real drivers, and binds them to
  `IShtc3&`, `IScd41&`, `IPmsa003i&` and `IBme688&`. All other code, the whole sampling sequence included, is written
  against those interfaces in `SensorSuite`. So the mocks run the code that runs on the device, not a copy of it.
  The `dock` and `dock-mock` environments differ only in `-DUSE_MOCK_SENSORS`.
- **`SensorSuite::sample()`** follows the datasheets:
  1. Wake the SHTC3, measure, wait 13 ms, read, and put it back to sleep.
  2. Take the mean of the BME688's cycles since the last reading, then give its pressure to the SCD41, so that the
     CO₂ conversion is correct. With BSEC the cycles are BSEC's own; without it the suite runs one forced cycle.
  3. Take the SCD41's measurement if one is ready, and the mean of those `poll()` took since the last reading. The
     part makes one every 5 s and keeps only the last, so the dock calls `poll()` every second, and the part is never
     asked twice for the same measurement.
  4. Read a PM frame, only after the fan's 30 s warm-up. Read once more after a read that fails or is damaged.
  The suite keeps why the SCD41 gave no CO₂, and what each PM read met with its 32 bytes, and the dock logs them
  ([boards.md](boards.md)).
- **A reading holds the means of the SCD41's and the BME688's samples since the last reading**, so that a value covers
  the whole 5 or 30 minutes, not one moment of them. Each value counts only its good samples: the SCD41's
  temperature and humidity after its warm-up, the gas resistance from a heater at its target, each index at accuracy
  3 (`Bme688Mean`). A value with no good sample is the newest one. `samples` in the reading gives the counts
  ([readings.md](readings.md)). The status light judges the newest samples (`SensorSuite::newest()`), so an alert
  does not wait for a mean.
- **A reading has no `scd41` temperature and humidity during the SCD41's warm-up after each start.** The warm-up is
  `dock.scd41.warmup_s`, 3 minutes by default; 0 keeps every value. A start is a dock start, a change to the part's
  settings, or a recalibration. After a start the part's temperature reads high by about half its offset, and its
  humidity reads low to match: 2.6 °C at 40 s with an offset of 4.5, 0.6 °C at 110 s, and nothing at 260 s. These
  figures come from the dock's stored readings, not from the datasheet. The first reading after a dock start comes
  inside the first minute, and a change to the settings restarts the part 35 s before a slot, so each start would
  store one wrong value. The CO₂ stays in the reading: at a start it was within 15 ppm of the readings on each
  side, which is inside the part's accuracy.
- **The clock is injected** (`IClock`), because the waits are real: `ArduinoClock` on the device, a fake in the
  tests. `ArduinoClock` waits until the millisecond clock has moved on, not for one `::delay()`. While the chip
  light-sleeps, a delay can return up to 51 ms early, and a read before a conversion ends fails.
- **A sample takes about 150 ms** without BSEC, nearly all of it the BME688's heater, once a slot. With BSEC the
  suite runs no cycle of its own, and `poll()` adds one short I²C read a second. `::delay()` yields on the ESP32, so
  Wi-Fi keeps running. The interfaces already return false when a part is not ready, so `sample()` can
  become a state machine without a change to the drivers.
- **The bus is injected too** (`II2cBus`). The command sequences, the CRCs and the conversions are where a driver
  goes wrong, and a host test cannot drive `Wire`. `ArduinoI2cBus` wraps the `Wire` instance that the dock starts on
  SDA IO8 and SCL IO9 at 100 kHz. `test/test_drivers` runs the same drivers against fake parts that answer as their
  datasheets say.
- **The BME688 uses Bosch's own code.** Its compensation reads twenty calibration values from the part, and a
  mistake gives a number that looks correct. So Bosch's C API does that arithmetic (`lib/bme68x`, v4.4.8,
  BSD-3-Clause). It reaches the bus through function pointers, so it sits behind `II2cBus` too, and it builds for
  the host tests.
- **BSEC** gives the two indexes, static and not. It drives the BME688 through the same driver, from a task of its
  own. `BsecBme688` gives `SensorSuite` the mean of the cycles that BSEC ran since the last reading, so the sampling
  sequence is the same with BSEC as without it.
