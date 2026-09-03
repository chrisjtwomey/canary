# Contributing to Inkplate 5 Environment Monitor

This project is at the design stage. The plan, and the status of the work
that makes it possible, is in [docs/EXTRACTION-PLAN.md](docs/EXTRACTION-PLAN.md).

## What it will be

A thin consumer of [epd](https://github.com/chrisjtwomey/epd), in the same
shape as [inkplate10-weather-cal](https://github.com/chrisjtwomey/inkplate10-weather-cal):

```
platformio.ini            -DARDUINO_INKPLATE5V2; lib_deps symlink://../epd/firmware
src/main.cpp              which IBoard to use
src/defaults.example.cpp  copy to defaults.cpp: WiFi, server URL, MQTT logging
server/
  server.py               config keys, a DataSource, a page list, DisplayServer(...).run()
  sources/                where the readings come from
  pages/                  the views
  static/                 CSS, icons, fonts
  config.example.yaml
```

Everything generic — the client firmware, HTTP, scheduling, rendering — is
epd. If a change is not about this device's sensors or pages, it goes there,
with its tests.

## Setup

epd must be checked out beside this repo. Then, once the server exists:

```sh
python3 -m venv server/.venv && source server/.venv/bin/activate
pip install -r server/requirements-dev.txt
pip install -e ../epd/server        # develop against the local kit
```

## Making Changes

- Please fork the repository and create a new branch for your changes.
- Add a test for every behaviour you add or change.
- Comments describe the present, not the change. Git holds the history.
- Follow the policy in the [AI-Assisted Code](#ai-assisted-code) section when AI tools are used.

## AI-Assisted Code

If your change was written by an AI tool (such as GitHub Copilot, Claude, or similar), add a `Co-Authored-By` trailer to the commit message naming the tool.

Example commit message:

```
Add new feature X

Co-Authored-By: Claude <noreply@anthropic.com>
```

## Submitting Pull Requests

- Ensure your changes build and pass tests.
- Open a pull request with a clear description of your changes.
- Reference any related issues.
