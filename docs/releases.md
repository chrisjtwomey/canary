# Releases

How the images are published, and how the firmware builder works. To deploy them, follow
[README, Run the server](../README.md#1-run-the-server).

Each push to `main` runs CI, `.github/workflows/build.yaml`: the firmware builds, the host tests and the server
tests. When all of them pass, `.github/workflows/release.yaml` builds two images, both tagged `latest` and stamped
with what `git describe` gives for the commit that CI tested:

| Folder | Image |
|---|---|
| `server/` | `ghcr.io/chrisjtwomey/canary-server` |
| `firmware-builder/` | `ghcr.io/chrisjtwomey/canary-firmware-builder` |

- A push that fails CI publishes no image, so a server on `latest` never takes firmware that does not build or a
  server that fails its tests. The images come when CI ends, about 8 minutes after the push.
- A tag publishes nothing. It marks a point tested on `latest`, and names the commits after it in `git describe`:
  `v0.6.6-1-g03c1761`. `latest` keeps the version of the push that built it, so a tag pushed later does not change
  what a server on `latest` reports.
- A published GitHub release builds the images of its tag's commit, as `0.3.0`, `0.3` and `latest` for `v0.3.0`. On
  that commit `git describe` gives the tag alone. The run fails if CI has not passed on that commit, as a push waits
  for it, or if `git describe` gives another tag on the same commit.
- Releases are few. Each is a version with enough changes to be worth upgrading to, or a fix to one. A breaking change
  alone is no reason for a release. The work in between is tested on `latest` and tags.
- No image holds firmware. The firmware links Bosch's BSEC binary, and this project does not give it out. The
  builder image holds the firmware's sources at its commit, and builds them where it runs. Each build downloads
  epd from the PlatformIO registry, at the version that `platformio.ini` pins.
- At start, the builder builds the display's and the dock's firmware of its own version into the server's firmware
  folder, as `canary-display/<version>.bin` and `canary-dock/<version>.bin`. Then it waits. Its container log shows
  each build.
- Beside each image, the builder keeps `<version>.merged.bin`: the same firmware with its bootloader and partition
  table, which the install page writes over USB. It copies the merged image first, so the install page always has
  the version that the boards are offered. When a version's merged image is missing, the builder builds that
  version again.
- The builder keeps the older images in the folder. A server offers the image that its version calls for, and that
  can be an older one.
- Run the builder beside a server of the same tag. A pair on `latest` moves the boards with every push, because a
  server past a tag offers development builds. A pair on `0.3.1` keeps them on that release.
- Without a mounted `config.yaml`, the server image runs the example config: the simulated room.
