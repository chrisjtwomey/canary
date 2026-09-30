# The dock's settings

The server holds the dock's settings: the `dock` block of `config.yaml`, which the Dock tab of `/web/config` edits.

## What they set

- The warm-ups: how long the PM fan runs before each reading, and how long after each start the SCD41's temperature
  and humidity are left out.
- The SCD41's temperature offset and self-calibration.
- The SHTC3's low-power mode.
- BSEC's sample rate.
- The limits of poor air for CO₂, fine dust and IAQ.
- The LED's brightness, smoothness, schedule and looks ([led.md](led.md)).
- The dock's log level.

## How the dock takes them

- The dock asks `GET /board-settings` at the pre-warm before each slot, and applies what has changed. It keeps the
  answer in NVS, so it starts on the same settings after a power cut.
- The answer carries a version, which is a hash of the settings. The dock reports the version it runs, and any key
  it refused, in its `client` object. The Dock tab says whether the dock has taken the saved settings. The
  Display tab says the same of the display ([schedules.md](schedules.md#the-displays-sync)).
- The dock holds each value to limits of its own. So a value out of range from the server changes nothing.
- A board that has missed two of its syncs (two slots of its own schedule) is offline. The Boards page marks it.
  The Dock tab greys out its settings and its recalibration until the dock syncs again, because nothing sent then
  would reach it. The saved values do not change. A range that is off makes the silence the dock may keep longer,
  because it has no slots to miss.

## When a change takes effect

Each setting takes effect as soon as it can.

- **The SCD41's offset and self-calibration.** The SCD41 takes them only while idle, and forgets them at a power
  cycle. So the dock sets them at each start of the part. A change stops its measurements for half a second at the
  pre-warm, which leaves time for five seconds of conversions before the slot. The reading at that slot has the
  CO₂, but not the SCD41's own temperature and humidity ([the sensor code](dock.md#the-sensor-code)). Neither
  setting is written to the part's EEPROM.
- **The SCD41's warm-up** takes effect at the next reading. It does not stop the part.
- **BSEC's sample rate:** every 3 s, or every 5 minutes, which is the default. Bosch gives a configuration for each
  rate, and the state that BSEC learns at one rate is no use at the other. So each saved copy says its rate, the
  dock restores only a copy at its own rate, and a change of rate starts BSEC again from nothing. At 5 minutes, Bosch
  counts the BME688's self-heating as negligible, and a reading has the newest cycle, which can be up to 5 minutes
  old.
- **The LED's schedule** (`dock.led.schedule`), the hours that it is on. The answer says whether the next slot is
  outside those hours. So the LED goes dark at the pre-warm before the first slot past the end, and comes back at the
  pre-warm before the first slot in the hours again. With no schedule, the LED is on all day. It is a window of its
  own, not a range of the sync schedule, so that the light can stay dark while the dock syncs slowly.

## Recalibration

A recalibration is not a setting.

- The Dock tab asks for one, with a reference in ppm. The server keeps the request, with the time it was asked as its
  id. The answer carries it for an hour, or until the dock reports that id as done.
- The dock runs it at the pre-warm, once the SCD41 has measured for the 3 minutes that the datasheet asks. It stops
  the part for about a second, and reports the correction, or the failure, in its `client` object.
- The SCD41 writes each recalibration to its own EEPROM. So a recalibration is for a person with the dock in known
  air, not for a schedule.
