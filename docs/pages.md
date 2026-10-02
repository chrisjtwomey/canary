# The pages

How to draw the pages on your computer, use the web UI, and add a page. First do the
[setup](../CONTRIBUTING.md#setup).

## Draw the pages

The server draws the pages from the [simulated room](simulator.md). It needs Chrome. On macOS, tell Selenium where
it is:

```sh
export CHROME_BIN="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
cd server && source .venv/bin/activate && cp config.example.yaml config.yaml
python3 server.py --once                                   # every page -> server/*.png
python3 server.py --only comfort.png --at 2026-09-03T21:45  # one page, at a set time
python3 server.py                                          # serve, and follow the schedule
```

- `--at` sets the clock for the room and the pages, so a render is the same each time. The room keeps UTC hours:
  CO₂ starts to climb at 18:30, cooking starts at 19:00, and a window opens at 22:00.
- The HTML goes to `server/static/<page>.html`, beside its CSS. Open it in a browser to work on the layout without
  a render.
- The PNG is what the panel shows: 1280 × 720, eight greys, dithered.
- If Selenium fails, look for an old chromedriver on your PATH (Homebrew's, for example). Run
  `brew upgrade chromedriver`, or remove it from the PATH: Selenium then gets the correct one.

## The web UI

While the server runs:

| Address | What it shows |
|---|---|
| `http://localhost:8080/web/` | Every page, built from the readings when you ask. It reloads each minute. The arrow keys move between pages. |
| `/web/explore` | One measurement over a time window. Drag to move in time. Scroll or pinch to zoom. |
| `/web/config` | `config.yaml` as a form, in tabs. |

The Settings page, `/web/config`:

- The form keeps the file's comments and layout. The YAML tab shows the keys that the form does not show.
- The Display tab holds the `display` and `image` blocks: the page schedule, the sync, the page sets (the
  `display.pools` key), the image's size and its page area. They are one tab because they are the settings the
  display takes at its sync.
- A warm-up trades accuracy for time or power, so it has a recommended value: the particle fan's is 35 s, the
  SCD41's is 3 minutes. The group's drawing marks it with a dashed line, "recommended", and a line under the field
  warns while the value is below it. A shorter warm-up is still saved, because it can be the right choice for a
  dock on a battery. `Field.cautions` and `config.js` apply the same rule.
- The Server tab's Comfort group sets the Comfort page's two boxes (the `comfort` block). Its drawing is the Comfort
  page's chart, with the room's last 6 hours from `GET /history`. Each edge drags, temperature in 0.5 °C steps and
  humidity in 1 % steps, and the dot at the inner box's centre moves both boxes. Beside it, the reading now and the
  sentence the Comfort page would give it change as the boxes do, so a person can match the words to how the room
  feels. The fields sit under two tabs, Temperature and Humidity, each a Comfortable and an Acceptable range, with
  one **Reset to defaults**.
- A **Reset** puts a default back without an input event, so `config.js` asks the drawings to redraw. Without that, a
  drawing kept a dragged value.
- **Check** tests an edit, as the server tests the file at start.
- **Save and restart** lists the changes, keeps the old file as `config.yaml.bak`, writes the new file and
  restarts the server. **Restore** puts the `.bak` back.
- The page opens again when `GET /about` names the version of the file it saved ([versions.md](versions.md)). A
  restart can take less time than the page's 2 s between polls, so a poll that fails is no sign of one. After 180 s
  the page says "The server has not come back. Check its log."
- After a save, the save bar names each board that has yet to take the new settings, and when: "Saved. The dock
  takes the new settings at 17:30, the display at 17:45." The Dock and Display tabs each say whether that board
  runs the saved settings ([dock-settings.md](dock-settings.md), [schedules.md](schedules.md#the-displays-sync)).
- When a container has the file mounted alone, the `.bak` stays in the container. It goes when the container is
  recreated.
- The Storage tab downloads each store as a file, one JSON document a line, and takes such a file back. An upload
  adds what is missing, and asks before it replaces a document.
- The page has no login.

## The pages and the pools

| Page | What it shows |
|---|---|
| Breathe | CO₂ |
| Comfort | Temperature and humidity |
| Dust | Particulates |
| Air | The VOC index |
| Trace and delta pages | One of each for the four above, and for pressure |
| Day | 24-hour ribbons |
| Diagnostics, 3 pages | Each board's report now, both boards over the day, and the dock's sensor health over the day |

- All pages except Diagnostics show the measurements: the simulated room by default, or what the dock posts when
  `source.kind` is `store`. Before the first reading, they show "No readings yet."
- Diagnostics shows the `status` data: the last document that each board posted, and the reports of the day.
- A trace page shows the value now, with three days behind it and the thresholds as dashed lines. A delta page shows
  the change over a short window, where the value was, and what such a change usually means. Both are in
  `pages/pool.py` (`TracePage`, `DeltaPage`), and a `Metric` spec drives them.
- The Comfort page's words come from its two boxes, which `comfort` in `config.yaml` sets (`metrics.Comfort`). What
  is comfortable depends on the person, so the boxes are settings. The defaults are 19–24 °C and 35–60 % inside,
  17–26 °C and 30–65 % outside. Each measurement has five bands: Cold, Cool, Comfortable, Warm, Hot, and Very dry,
  Dry, Comfortable, Humid, Very humid. The verdict for a pair of bands is a table, `metrics.VERDICTS`, with words a
  person would use, such as "Muggy." for a comfortable temperature that is humid, "Cold and damp.", "Dank." and
  "Sweltering.". A value is judged as the page shows it, to 0.1 °C and to 1 %, so a number never sits beside the
  word of the next band. The trace pages and `/web/explore` draw the inner box's edges as their guides.
- The pages show the pressure at sea level, as forecasts give it, from `site.altitude_m`. The pressure as measured
  stays under `pressure_station_hpa`.
- The pages show the IAQ only at accuracy 3, BSEC's highest. Below it they say "Calibrating.", and the charts leave
  those readings out. Bosch rates the index at its best only at 3; below it, the index moves with BSEC's
  calibration as much as with the air. The store keeps every reading as the dock posted it. This and the sea-level
  pressure are in `sources/corrections.py`.
- A line chart breaks its line where no reading falls for more than 45 minutes, and shades that stretch light grey,
  as the Day page shades the nights. The shading shows when nothing was measured, or nothing was accurate, without
  drawing a path that no reading supports. The dock reads every 30 minutes at night, so a normal night is no gap; a
  chart thinned to fewer points needs two of its steps. The server marks the gaps (`metrics.gaps`); `charts.js` draws
  them on the sparklines, the trace pages and `/web/explore`.

The `display` block in `config.yaml`:

- `pools` is what the display can show: named lists of pages. Each pool shows its pages in turn, from a random start
  that moves every `reshuffle_hours`. The clock seeds the random start, so a restart changes nothing.
- `schedule` is when. At each slot of its `week`, the display shows the next pool in `order`. Each group of days has
  its own time ranges, and each range has an interval ([schedules.md](schedules.md)). While a range is off, the
  display shows the splash screen, which is in no pool.
- To keep a pool off the panel, leave it out of `order`.
- To check pages on the panel quickly, set the page schedule to one range of `every: 60`, and restart the server.

## Add a page

1. Subclass `EnvPage` in `server/pages/`. Set `title`, `stylesheet`, `css_class` and `requires`. Build the DOM in
   `body()`, and return the chart specs from `charts()`.
2. Add the page to `make_pages()` in `server.py`.
3. Give it a stylesheet in `static/`, keyed on `.page-<css_class>`. The layout units are `cqw` and `cqh`: 1% of the
   panel's width and height.
4. Add it to a pool in `display.pools`.

- `static/charts.js` draws the charts with rough.js. A spec names its `canvas` and its `kind` (a key of `KINDS` in
  `charts.js`), and holds plain data.
- The page calculates all time-zone and unit values in Python, where the tests cover them.
- `metrics.py` holds the derived values and the words.
