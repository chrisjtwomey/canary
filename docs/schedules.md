# Schedules

When the page changes, when the dock takes a reading, and when the display syncs. The server holds all three, in
`config.yaml`.

## The page schedule

"Every five minutes" as a list of wall-clock times would be 288 entries. So epd's `display` block has `pools` of
images, and a `schedule` of `type: times` or `type: timeranges`. CANARY uses `timeranges`, and refuses `times`.
[pages.md](pages.md) explains the pools.

- **`week`** puts each day of the week in one group. Each group has up to 8 time ranges, which cover the whole day.
- **A range** runs from its start until the next range starts. The last range runs past midnight to the first.
- **Each range has an interval.** An interval of 0 turns the range off, and the display then shows the splash
  screen. A page left up overnight would show its readings as if they were current. So where a range that is on
  gives way to one that is off, the server names the splash for a wake. It also answers any page fetched while off
  with the splash, such as the first after a restart (`server/off_hours.py`). The display wakes again at the next
  range that is on.
- **A day stands alone.** Before its first start, its own last range runs, not the range of the day before. So a
  group's dial shows all that happens on its days.
- **By default** the page changes every 300 s all day, every day, on :00, :05 ... on the wall clock.
- **A slot** is a local time in a range that is on, a whole number of the range's intervals from its start. So a
  range has a slot at its start: from 08:30 every 20 minutes gives 08:30, 08:50, 09:10. A range that starts on the
  hour, with an interval that divides the hour, keeps to :00, :05 ... on the wall clock.
- epd's `TimeRanges` finds the slot by stepping through the minutes, and asking for each minute which range it is in.
  This is because some clocks change at 01:00: in spring that hour does not happen, and in autumn it happens twice.
- The page's turn through the pools is counted over the week, from the slots of the days before. So it continues
  from one day into the next, whatever each day holds.

The Display tab of `/web/config` edits the week beside a dial of the day:

- A chip for each group selects the group that the dial shows.
- The day toggles move a day into the group, or out of it into a group of its own with a copy of its ranges. So each
  day always has a group.
- A new range halves the range that starts latest, which runs on past midnight to the earliest start.
- A range that you remove gives its hours to the range before it.

## The dock's schedule

`dock.sync.week` has the same shape. At each slot, the dock takes a reading and posts its queue.

- **By default**, every day: every 1800 s from 01:00, and every 300 s from 07:00. So readings come on :00, :05 ...
  by day, and on the hour and half hour at night. 07:00 is a slot in both.
- **The PM fan** runs for about 35 s before each reading. So the default week costs about 810 fan hours and 83,000
  starts a year. A reading every minute would cost about 5,100 hours and 526,000 starts.
- **Each response** tells the dock how long until its next slot, in `Canary-Next-Sensor-Poll-Seconds`, rounded up
  to a whole second. With no answer, the dock keeps the last gap that the server gave between two slots.
- **A post up to 5 s before a slot counts as that slot's**, and the answer names the slot after it. The dock's clock
  runs fast in light sleep ([dock.md](dock.md#the-clock)), so after 30 minutes its post can arrive a second early.
  An answer of "1 s" would make it read again at once, and the SCD41 has no new CO₂ for 5 s. Each answer sets the
  dock's timer again, so the error never adds up from one slot to the next.
- A week in which no range syncs is refused, because the dock would take no readings. A day with none is allowed.
- The Dock tab edits it as the Display tab edits the page schedule.

## The display's sync

- `display.sync.every` sets how often the display syncs all day: every 1800 s by default. 0 means only beside each
  page that it fetches. The Display tab sets it in minutes.
- Each board gets its own next slot in `Canary-Next-Sensor-Poll-Seconds`, by the name it gives in `Canary-Device`,
  with the same 5 s rule as the dock.
- The display posts its state at each wake. It also wakes for a sync that comes before its next page.
- The display holds none of the `display` and `image` settings: the server picks each page, and the time to the
  next wake, from them. So the display runs a saved change from the answer to its next sync.
- The server keeps the version for it: a hash of those two blocks, taken at the server's start. It puts the
  version on each report from the display as `settings_version`. The Display tab compares the newest report's with
  the one the server runs: "Synchronized", or "Not synchronized" with the time of the next sync. A save that leaves
  both blocks alone leaves the display synchronized, where a test of the restart alone would mark it out of step
  after every save.
