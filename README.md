# CANARY

CANARY shows the air in a room on a 5.2" e-paper display. It measures CO₂, particulates, gas (VOC),
temperature, humidity and pressure.

![CANARY on a desk](hardware/images/device.png)

It has two halves and a server:

- The **dock** holds the sensors. It takes a reading every 5 minutes, and every 30 minutes from 01:00 to 07:00,
  and sends it to the server.
- The **display** stands on the dock. Every 5 minutes it shows the next page that the server draws from the
  readings.
- The **server** runs on a computer of yours. It keeps the readings, draws the pages, and can update the firmware
  on both boards. Its config sets the times above.

One USB-C cable powers the dock and the display.

| What | Part |
|---|---|
| CO₂ | Sensirion SCD41 (Adafruit breakout) |
| Particulates: PM1.0, PM2.5, PM10 | Plantower PMSA003I (Adafruit breakout) |
| Gas (VOC) and pressure | Bosch BME688 (Soldered breakout) |
| Temperature and humidity | Sensirion SHTC3 (Soldered breakout) |
| Display | Soldered Inkplate 5 Gen2 |
| Dock controller | Unexpected Maker TinyS3 |

## Build one

**You build the firmware yourself.** The dock uses Bosch's BSEC2 library to calculate the air quality index.
BSEC2 is closed source, and Bosch's licence does not let this project give out firmware that contains it. The
build downloads BSEC2 from Bosch, and Bosch's terms then apply to you. Read them first: the
[library's LICENSE.md](https://github.com/boschsensortec/Bosch-BSEC2-Library) links to them.

You need:

- The parts in [hardware/bom.md](hardware/bom.md). They cost about €220.
- A 3D printer with a 0.4 mm and a 0.2 mm nozzle, and a soldering iron.
- A computer that is always on, with Docker, on the same network as the device.
- A computer with a USB port and Chrome, Edge, Opera or Firefox, for the first install on each board.

### 1. Run the server

On the computer that is always on:

```sh
git clone https://github.com/chrisjtwomey/canary.git
cd canary
./setup.sh
```

- `setup.sh` writes `server/config.yaml` for a real install: the pages show your readings, the boards take new
  firmware from the server, and the time zone and the server's address are this computer's. It asks nothing, and
  it keeps a config that exists, so you can run it again at any time. Then it starts the containers.
- The second container builds the firmware for both boards. Its first build takes some minutes.
  To build again, restart the server with `docker compose restart`. `docker compose logs -f firmware-builder`
  shows the build.
- `http://<server>:8080/web/` shows the pages, and `/web/config` is the Settings page. Set your altitude there, in
  the Server tab, so that the pages show the pressure at sea level. **It has no login: anyone on your network can
  change the settings.**
- The readings, board reports, board logs, calibration copies and the HTTPS certificate go in the `canary-data`
  volume. They stay when Docker recreates the container.
- The images follow this repo's `main` branch. Your boards take each new version.

### 2. Install each board's firmware

The first install puts the firmware and your network settings on a board, over USB. After that, each board takes
its firmware from the server.

Install both boards before you build the device. The dock's USB-C socket carries power only. To install the dock
later, you must open it and lift the TinyS3 off its strips.

1. On a computer with a USB port, open `https://<server>:8443/web/install` in Chrome, Edge, Opera or Firefox.
   `setup.sh` prints the address. Your browser warns about the certificate first: select Advanced, then continue.
2. Enter your Wi-Fi name and password. Each saves when you leave its field. Change the server address if the
   boards reach the server by another name.
3. Connect a board with a USB cable, then select Install beside it. After the install the page checks that the
   board joins your Wi-Fi and reaches the server.

- A board's Install button appears once the server has built its firmware.
- Firefox asks to install an add-on for the site first, and it cannot install from an IP address: open the page by
  the server's name.
- Safari cannot install firmware. From a terminal on macOS or Linux, the same install is
  `curl -O http://<server>:8080/install-firmware.sh`, then `sh install-firmware.sh dock` or
  `sh install-firmware.sh display`.
- Behind a reverse proxy that has its own certificate, set the HTTPS port to 0 in Settings and open the page
  through the proxy.

To build and flash the boards with PlatformIO instead, as for development, see [docs/boards.md](docs/boards.md).

### 3. Build it

[hardware/assembly.md](hardware/assembly.md) builds the device in 12 steps, with a picture for each. Set aside a
day. The last step is the first power-up.

## Documentation

| Doc | What it tells you |
|---|---|
| [hardware/](hardware/README.md) | What is in the hardware folder. |
| [hardware/bom.md](hardware/bom.md) | The parts to buy, and what else would do. |
| [hardware/assembly.md](hardware/assembly.md) | How to build the device, step by step. |
| [hardware/enclosure.md](hardware/enclosure.md) | The design of the printed parts, for changes to the model. |
| [docs/architecture.md](docs/architecture.md) | How the firmware and the server work. |
| [docs/readings.md](docs/readings.md) | The data that each board sends. |
| [CONTRIBUTING.md](CONTRIBUTING.md) | For developers: the setup, the tests, and where the other developer docs are. |
