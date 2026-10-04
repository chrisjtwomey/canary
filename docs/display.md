# The display

How the display's firmware works: its wakes, its notices and its splash screen. To run it on a board, read
[boards.md](boards.md).

## The wakes

`src/main.cpp` deep-sleeps between wakes. E-paper keeps its image with no power, so a display that stays awake
between pages would only make heat.

```
each wake:  board.begin(); wifi
            page due     GET the named page → draw; a failed fetch keeps the old image and backs off
            every wake   POST /sensor-readings   the display's own status, which is its sync; the answer names the next
            then         deep sleep until the next page or the next sync, whichever is first
```

- **Time.** Each answer from the server sets the display's clock, time zone and RTC, so it does not ask NTP.
- **Settings.** The display reads no SD card: its settings are in its own store. The server applies the display
  and image settings for it, so the display reports no settings version
  ([schedules.md](schedules.md#the-displays-sync)).
- **Wake-up.** The RTC's alarm wakes it, on GPIO39 as the schematic shows. The ESP32's timer is set a little later
  as a backup, so a missed alarm makes a late page, not a display that never wakes.
- **RTC memory** holds what must outlast the sleep: the wake plan, the next URL and the counts. A real start clears
  it.
- **Two things keep the display awake:** a wait under 10 s, which costs less than a wake, and a newly written image,
  which the bootloader takes back unless a page proves it. Three failures in a row, to join Wi-Fi or to fetch a
  page, roll it back.
- **Its report.** The display reports its uptime and its reset reason from its last real start. So the Diagnostics
  page does not count a wake as a restart.

## Notices

The display draws a notice in place of a page in two cases:

| Case | What the display does |
|---|---|
| Its version does not work with the server's ([versions.md](versions.md)) | The server never refuses a fetch, so the display still gets its page. It draws a notice in its place, then takes any update on offer. The update is what clears the notice, because the dock's wall covers the display's USB-C socket. `include/display/AfterFetch.h` fixes this order, and the tests cover it. When the server offers no image that the display can take, the notice says so, and asks for firmware for the server's version or a server of the display's version. |
| The server does not answer 3 fetches in a row | About 26 minutes with the back-off (2, 6 and 18 minutes), so a short outage never replaces the page. The notice says when the last page arrived. |

- The notices come from the firmware, not from the server, so they work when the server is the problem.
- The display draws each notice once, not at every retry, because each draw is a full refresh of the panel.
- **They are pages.** `server/pages/notice.py` sets each one as the others are set: a spaced-capitals label, an
  italic verdict and a line of detail. `scripts/notices.py` renders them through the same pipeline, browser and
  quantiser as each page the server serves. The display holds the three PNGs in its firmware, and draws them with
  the call that draws a fetched page. So a notice is the same, pixel for pixel, as the server's render.
- They are rendered again only when their words or design change, so the firmware build needs no browser.
- The bottom of each notice is free for the facts that the display knows only at run time: when the last page
  arrived or the server's version, then the board's own name, version and address. The display writes them in the
  pages' face at the size of their detail text, from a one-bit font that `scripts/gfxfont.py` makes from the
  server's font file.

## The splash screen

- The logo alone, from `server/pages/canary-logo-screen.svg`, rendered by `scripts/notices.py` as the notices are,
  but in black and white. The SVG is in the server's folder because the server's image holds only that folder.
- The server also serves it as `splash.png` while the page schedule is off ([schedules.md](schedules.md#the-page-schedule)).
  The display draws it as any page, with no version under the logo.
- The display draws it at each start except a wake from deep sleep, before it joins the network, with its firmware
  version under the logo. It stays until the first page or notice replaces it.
- While the display writes an update, it draws the logo again with a progress bar under it, and under that
  "Installing firmware" and the version, in the pages' italic from a second one-bit font.
- The bar fills in ten steps. Each step is a partial update of the panel, which works only in black and white. The
  Inkplate library makes each eleventh partial update a full refresh (`include/display/ProgressBar.h`).
