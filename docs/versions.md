# Headers and versions

The headers between the boards and the server, which versions work together, and how the server updates the
boards. To test an update on the bench, read [firmware-updates.md](firmware-updates.md).

## Headers

Each header on the wire starts with `Canary-`. The server's responses are CANARY's interface, and a person who
reads the traffic must not need to know which library built it. The kit makes the names from a prefix that each
product sets: the server takes `header_prefix="Canary"`, and the firmware takes `-DEPD_HEADER_PREFIX='"Canary"'`. A
mismatch gives no error, so both come from this repo.

| Direction | Header | Carries |
|---|---|---|
| Board to server | `Canary-Device`, `Canary-Device-Version` | Which board, and what it runs |
| Server to board | `Canary-Server-Version`, `Canary-Server-Epoch-Seconds` | On every response |
| Server to board | `Canary-Server-Timezone` | On every response, when the server's zone has an IANA name: the zone as a POSIX TZ string |
| Server to display | `Canary-Next-Display-Refresh-Seconds`, `Canary-Next-URL` | When to fetch, and what |
| Server to board | `Canary-Next-Sensor-Poll-Seconds` | On every response: when to sync next ([schedules.md](schedules.md)) |
| Server to board | `Canary-Server-Firmware-Version`, `Canary-Server-Firmware-URL` | Only when an update applies |

- `GET /about` answers with the same version and clock, the firmware on offer, and the library's version. The dock
  asks it every 30 s until it knows the time.
- The server's version is CANARY's own, from `git describe` when the image is built. It is not the version of the
  `epd-server` package: that package is a library that the server is built with, and the two change separately.

## Which versions work together

- A board and the server work together when their major versions are the same. While the major is 0, their major
  and minor versions must be the same.
- Both ends apply the rule, the server through `epd_server.compat` and the boards through `version_compat.h`. So
  both reach the same answer about each other.
- A version that cannot be read, such as `dev`, is never judged. To refuse it would stop each development build,
  with no warning.

## Updates over the air

The boards follow the server's version.

- The server holds each board's images in a folder of its own, `firmware/canary-display/` and
  `firmware/canary-dock/`, and keeps all of them.
- It offers each board the newest image of its product that works with the server's version, newer or older than
  what the board runs. Among builds past one tag, it offers the build furthest past it. So a mismatch clears itself
  when the board takes the offer.
- The offer goes on any response to the board, a refusal included.
- The firmware builder beside the server builds the firmware of its own commit into that folder when it starts. So
  a redeploy moves the server and the boards together ([releases.md](releases.md)).
- A server past a tag offers development builds. A server on a tag offers images only to boards on a tagged build.
- The server logs each offer of an older image. The Diagnostics page shows the posts that the server refused from
  each board, even from a board it has never taken a report from.

**The dock:**

- A post that the server refuses gets 409. The dock keeps the batch in its queue, because the readings are correct
  and only the pair of versions is wrong. The LED shows Error, and the same response offers the image that fixes it.
- The dock takes an offer only from the answer to a batch of readings, and only when its queue is empty, because
  the restart empties the queue. The exception is a 409: the server will not take that queue until the dock runs
  another version, so the dock takes the image and loses the readings.
- While the image is written, the LED shows Updating ([led.md](led.md)).
- The new image starts on trial. The first batch that the server takes confirms it. Three failures in a row roll it
  back, and the dock then refuses that version.

**The display** draws a notice, then takes the update ([display.md](display.md#notices)).
