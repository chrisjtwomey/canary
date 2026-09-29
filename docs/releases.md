# Releases

How the images are published, and how the firmware builder works. To deploy them, follow
[README, Run the server](../README.md#1-run-the-server).

Each push to `main` runs `.github/workflows/release.yaml`. It builds two images, both tagged `latest` and stamped
with what `git describe` gives:

| Folder | Image |
|---|---|
| `server/` | `ghcr.io/chrisjtwomey/canary-server` |
| `firmware-builder/` | `ghcr.io/chrisjtwomey/canary-firmware-builder` |

- A published GitHub release adds its version tags: `0.3.0` and `0.3` for `v0.3.0`.
- No image holds firmware. The firmware links Bosch's BSEC binary, and this project does not give it out. The
  builder image holds the firmware's sources at its commit, and builds them where it runs.
- At start, the builder builds the display's and the dock's firmware of its own version into the server's firmware
  folder, as `canary-display/<version>.bin` and `canary-dock/<version>.bin`. Then it waits. Its container log shows
  each build.
- The builder keeps the older images in the folder. A server offers the image that its version calls for, and that
  can be an older one.
- Run the builder beside a server of the same tag. A pair on `latest` moves the boards with every push, because a
  server past a tag offers development builds. A pair on `0.3.1` keeps them on that release.
- Without a mounted `config.yaml`, the server image runs the example config: the simulated room.
