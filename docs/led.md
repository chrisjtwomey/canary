# The status LED

The dock drives a yellow LED on IO6, behind a clear tile in the front of the shell. It says what the dock needs.

## Triggers

The LED shows the first trigger in this table that holds and has a look in the server's `dock.led.looks`. A look is
a pattern, and the length of one cycle of it. A trigger that the list leaves out passes the light to the next
trigger that holds. With no trigger, the LED is dark.

| Trigger | When | Look by default |
|---|---|---|
| Updating | The dock writes a new image. | It pulses faster and brighter as the image is written: from 60 a minute at a quarter of the light, to 240 a minute at full light. The server cannot set it. |
| Booting | `setup()` connects, or starts the sensors. | Pulse every 0.5 s |
| Error | Anything is wrong: off the network, a post that the server did not get or did not take, readings that wait in the queue, a sensor that does not answer, or a setting that the dock refused. The Boards page says which. | Flash every 1 s |
| Alert | The latest reading has CO₂, PM2.5 or, once BSEC is calibrated, `iaq` at or over its limit. Each limit is a setting in its sensor's section of the Dock tab: by default 1500 ppm, 37.5 µg/m³ and 150, the pages' bands for stuffy, dusty and polluted air. | Double flash every 2 s |
| Calibrating | The accuracy of `iaq` is below 2, which Bosch calls unreliable, or a recalibration waits for the SCD41 to measure for 3 minutes. | Swell every 4 s |
| Running | The dock has booted. | Pulse every 1 s |

- While `setup()` runs, only Booting holds, because the other states are not known yet. After boot, Running always
  holds, last.
- **The slow pulse is the heartbeat.** A dock that has stopped goes dark. A solid light would hide that.
- **Temperature and humidity raise no trigger.** What is comfortable depends on the home, and a humid climate would
  keep the light on.

## Patterns

| Pattern | Shape |
|---|---|
| Flash | 150 ms of full light at the start of each cycle |
| Blip | 50 ms of full light at the start of each cycle |
| Pulse | Rises and falls along a sine |
| Swell | Rises over the first third of its length, holds, and falls over the last third |
| Ramp | Rises over its length, and goes dark at once |
| Double, triple | Two or three quick pulses or flashes of 300 ms each, then dark for the rest of the length |

- The length of a double or a triple is at least one step longer than the group, so the gap always shows.
- A fade moves in equal steps of perceived light. `dock.led.smoothness` selects 4, 8, 16, 32 or 64 steps, or steps
  too small to see. The default is 16. At a low brightness, the dimmest steps can have the same duty.
- Brightness is perceived brightness, mapped through gamma 2.2 onto a 14-bit channel at 1 kHz.
- `dock.led.schedule` sets the hours that the LED is on ([dock-settings.md](dock-settings.md)).

## The code

- `StatusLed` turns the time into an LEDC duty, and holds no hardware. So the host tests cover the patterns. They
  also cover `LightTriggers`, which judges the air and calibration triggers from a reading.
- A task of its own drives the pin, because `setup()` blocks for as long as the network takes, and the booting
  pulse must run through it. The task waits until the pattern's next step, and at most 250 ms, so that a new state
  shows soon. It does not look every 5 ms, which would keep the chip out of light sleep.
- The Dock tab plays a look on a dot, with the same timings and steps (`sheet.js`), so you can see it before you
  save it. The dot shows what the light showed at the dock's last sync, which the dock reports as `light`
  ([readings.md](readings.md)), until you change or click a row. The dot's area follows the brightness. At 0, it
  stays dark.
