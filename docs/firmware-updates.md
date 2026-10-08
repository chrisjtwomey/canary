# Firmware updates on the bench

How to test the updates over the air with a server on your own computer. First get the boards running
([boards.md](boards.md)).

Each board takes new firmware from the server. The server offers each board the newest image of its product that
works with the server's version: the same major and minor version, while the major is 0. A server that runs from a
checkout reports what `git describe` gives, for example `v0.6.2-5-gab12cd4`, so it offers development builds.

1. Make the folders, and set `client.firmware.enabled: true` in `config.yaml`:

   ```sh
   mkdir -p server/firmware/canary-display server/firmware/canary-dock
   ```

2. Flash each board once over USB, so that it stores your Wi-Fi and the server's address: with PlatformIO and
   `src/defaults.cpp` ([boards.md](boards.md)), or from the server's install page
   ([README.md](../README.md#2-install-each-boards-firmware)).
3. Commit a change. Then build each board, and copy its image into the folder under its version:

   ```sh
   v=$(git describe --tags --match 'v*' --dirty)
   pio run -e esp32 && cp .pio/build/esp32/firmware.bin server/firmware/canary-display/$v.bin
   PLATFORMIO_CORE_DIR=~/.platformio-canary-dock pio run -e dock && cp .pio/build/dock/firmware.bin server/firmware/canary-dock/$v.bin
   ```

- The file name must be the `CLIENT_VERSION` that the build prints.
- The install page offers a version only with its merged image beside it. To install a build from the page, copy
  `.pio/build/<env>/firmware.factory.bin` in as `$v.merged.bin` too, as the firmware builder does.
- Commit before each build. A tree with uncommitted changes builds `...-dirty`. Two builds of one commit have the
  same version, and the server does not offer a board the version that it already has.
- The display takes the image after its next page. The dock takes it after a post that empties its queue, and its
  LED shows the progress.
- The log shows the offer, the progress, the restart and `trial boot of <version>`. Then it shows
  `firmware <version> confirmed`, when the display has drawn a page or the server has taken the dock's readings.

| To see | Do this | What happens |
|---|---|---|
| A rollback | Before the build, set `serverURL` in `src/defaults.cpp` to `http://192.0.2.1:8080/breathe.png`. That address never answers. | The board takes the image, fails 3 times, and starts the previous image again. It then refuses that version: `firmware <version> is offered again; this board rolled back from it`. |
| A rollback when Wi-Fi fails | Before the build, set `wifiPass` in `src/defaults.cpp` to a wrong password. | The board takes the image and fails to join Wi-Fi 3 times, about 1.5 minutes. It starts the previous image again, which stores its own password again, and refuses that version. |
| A board go back to the server's line | Flash an image of a later tag over USB. Leave an older image in the folder. | The server offers the older image, and logs that the board went back to it. |

- To try a refused version again, commit again, or erase the board: `pio run -e esp32 -t erase`, or `-e dock` in
  the dock's folder.
- A server past a tag moves every board to the newest image in the folder, even when that image is older than the
  board's.
- A server on a clean tag offers its image to a board on a tagged build, and to a board on a development build
  older than the image. So a board tested on main moves to the release tagged on that commit, over the air. A
  development build past the release is left alone, so a bench board is not flashed back.
