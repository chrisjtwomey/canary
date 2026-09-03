# Extraction plan: `inkplate10-weather-cal` → reusable core + thin projects

Analysis of `chrisjtwomey/inkplate10-weather-cal` (client firmware + server), and a
plan to split it into a **shared core** plus **thin per-project repos**.

---

## 1. What the project actually is

Two programs joined by one small HTTP contract.

| Part | Language | Role |
|---|---|---|
| Client | C++ / PlatformIO / ESP32 | Wake → fetch a PNG over HTTP → draw it → deep sleep |
| Server | Python / Flask | Fetch data → render HTML → screenshot to PNG → serve on a schedule |

**The wire contract** (the only coupling between the two):

```
GET /<page>.png
  200 image/png
  X-Next-Refresh-Seconds: 7200     ← client sleeps this many seconds
  X-Next-URL: http://host/hourly.png ← client fetches this next
```

This contract is domain-agnostic. Nothing in it knows about weather.

---

## 2. Key finding: the client is already generic

The firmware never mentions weather. It downloads *an image* from *a URL* and
draws it. `IBoard` already abstracts the hardware. The extraction is close to
free — it is mostly a file move plus four leak fixes.

**Client code that is 100% reusable as-is:**

| File | What it does |
|---|---|
| `include/IBoard.h` | Hardware abstraction (lifecycle, GFX, battery, RTC, SD) |
| `include/MockBoard.h` | Test double for `IBoard` |
| `src/app.cpp` | The whole boot → config → wifi → fetch → draw → sleep state machine |
| `src/network_utils.cpp` | WiFi connect, HTTP download, `X-Next-*` header parsing |
| `src/sleep_utils.cpp` | Deep sleep, RTC alarm scheduling |
| `src/time_utils.cpp` | NTP sync |
| `src/log_utils.cpp` | Levelled logging, serial + MQTT with offline queue |
| `src/battery.cpp` | LiPo voltage → capacity lookup |
| `src/backoff.cpp` | Exponential back-off (pure, tested) |
| `src/refresh_header.cpp` | Header parsing (pure, tested) |
| `src/file_utils.cpp` | SD write |
| `src/display_utils.cpp` | PNG draw, battery overlay, error banner, SPIFFS cache |
| `src/InkplateBoard.cpp` | Inkplate driver wrapper — **model-agnostic already** |
| `test/` | Native tests: backoff, battery, refresh_header, mock board, integration |

**Client code that stays per-project:**

| File | Why |
|---|---|
| `src/defaults.cpp` | Credentials, server URL, MQTT client ID |
| `src/main.cpp` | 13 lines: picks the `IBoard` implementation |
| `platformio.ini` | Board flags (`-DARDUINO_INKPLATE10` vs `-DARDUINO_INKPLATE5V2`) |
| `include/version.h` | Per-project version string |
| `include/font/`, `include/icon/` | Branding assets (could go core as defaults) |

### 2.1 Leaks to fix before extraction — **DONE**

These are real defects, not just tidiness. All five are now fixed in
`inkplate10-weather-cal`; 64 native tests and both ESP32 builds are green.

1. **`src/time_utils.cpp` bypasses `IBoard` and is type-unsafe.**
   It declares `extern Inkplate board;` while `src/main.cpp` defines
   `IBoard& board`. Global variables are not name-mangled, so this links, but
   `board.rtc.setEpoch(nowTime)` reinterprets a reference (a pointer) as an
   `Inkplate` object. Undefined behaviour.
   **Fix:** add `rtcSetEpoch(time_t)` to `IBoard` and call through it.

2. **`src/sleep_utils.cpp` hardcodes `GPIO_NUM_39`** as the RTC wake pin.
   That is the Inkplate 10 pin. Other boards differ.
   **Fix:** move to `IBoard::enableWakeOnRtcAlarm()` — the board owns its pin
   and wake source.

3. **`include/display_utils.h` leaks `E_INK_WIDTH` / `E_INK_HEIGHT`** into a
   header that is supposed to be hardware-neutral (in the now-unused
   `DEFAULT_BUFFER_SIZE` macro).
   **Fix:** delete the macro; `app.cpp` already sizes from `board.getWidth()`.

4. **`ps_malloc` is assumed everywhere** (`display_utils.cpp`,
   `network_utils.cpp`). Boards without PSRAM will fail.
   **Fix:** `include/mem_utils.h` adds `boardMalloc()`, which tries PSRAM under
   `BOARD_HAS_PSRAM` and falls back to `malloc`.

5. **`downloadFile()` reported a non-200 response as a successful download.**
   Found while fixing #4. On a 404 or 500 it logged the error and then returned
   the freshly allocated — and uninitialised — buffer. The caller's only check
   is `if (!buf)`, so a non-null buffer read as success: the client fed garbage
   to the PNG decoder, leaked the buffer, and left the HTTP connection open.
   The decode then failed, so the fault surfaced as a *draw* error and the
   client backed off for the wrong reason.
   **Fix:** free the buffer, end the connection, restore WiFi sleep, and return
   `nullptr` so the caller's download-retry path runs.

Secondary cleanups: `board.setRotation(1)` is hardcoded in `app.cpp` (make it
config); `CALENDAR_RW_PATH` / `saveCalendarCache` / "Weather Calendar boot"
are naming only — rename to `image` / `IMAGE_RW_PATH` / `deviceName()`.

### 2.3 A sixth leak, found only by doing the split

Under `-DUSE_SDCARD` the client reached **back into the board driver**:
`app.cpp` and `file_utils.cpp` both did

```cpp
SdFat& sd = static_cast<InkplateBoard&>(board).getSdFat();
```

`IBoard.h` documented this as deliberate — `SdFat` is an InkplateLibrary type
and could not be named in the interface. But it makes `EpdClient` depend on
`EpdBoardInkplate`, which already depends on `EpdClient`. The split
failed to compile on exactly this.

**Fix:** two methods on `IBoard`, so storage access never names a concrete type:

```cpp
virtual bool   sdWriteFile(const char* path, const uint8_t* buf, size_t len) = 0;
virtual size_t sdReadFile (const char* path, uint8_t* buf, size_t maxLen)    = 0;
```

`file_utils.cpp` now calls `board.sdWriteFile(...)`, and `app.cpp` reads
`config.yaml` into a 1536-byte buffer and hands that to `deserializeYml`.
`InkplateBoard::getSdFat()` still exists for direct access, but nothing in the
client uses it.

> **Untested:** the host test environments do not define `USE_SDCARD` (YAMLDuino
> does not build natively), so this path is verified by compilation and review
> only. `MockBoard` implements both methods, so a `native_integration_sdcard`
> environment is possible if the YAML dependency is stubbed.

### 2.4 Inkplate 5 Gen2 support is a build flag

`InkplateBoard` wraps whichever `Inkplate` class `InkplateLibrary` compiles for.
Swapping panels is:

```ini
build_flags = -DARDUINO_INKPLATE5V2   ; was -DARDUINO_INKPLATE10
```

Only `deviceName()` hardcodes `"Inkplate10"`. Make it read the compile-time
macro, or pass the name into the constructor.

---

## 3. Server: where the real abstraction work is

The server has three concerns tangled inside `server.py::main()`:

1. **Scheduling + serving** — generic
2. **Rendering HTML → PNG** — generic mechanism, project-specific pages
3. **Fetching data** — entirely project-specific (weather)

### 3.1 Generic (→ core)

| File / symbol | Notes |
|---|---|
| `views/page.py` — `Page` | Airium → HTML → headless Chromium screenshot → palette quantise. **This is the HTML renderer.** |
| `Page.layout_css_variables()` | Inner-canvas letterboxing (`--inner-*` CSS vars). Panel-size independent. |
| `utils.py` | Config accessor with env-var override + type coercion |
| `weather/registry.py` | A **generic plugin registry** — nothing weather-specific. Rename to `providers/registry.py` |
| `weather/cache.py` — `DiskCache` | Generic JSON disk cache with per-key TTL |
| `server.py` — `_next_regen`, `_next_wake`, `get_next_wake` | DST-correct schedule maths |
| `server.py` — `_validate_time_list`, `ServerThread`, `_serve_png` | HTTP serving + `X-Next-*` headers + regen lock |
| `server.py` — `get_client_mqtt_logging` | Subscribes to client log topic |
| `server.py` — signal handling, regen loop, `--once` | The main loop |
| `validate_config` — `server.*`, `image.*`, `mqtt.*`, `display_schedule` | Generic config blocks |
| `Dockerfile`, `entrypoint.sh` | Chromium + driver base image |
| `views/html/styles.css` — `.inner-canvas*` rules | Letterbox scaffolding only |

### 3.2 Project-specific (stays in `inkplate10-weather-cal`)

- `weather/service.py` (the `WeatherService` data contract) and all five
  providers: accuweather, openweathermap, meteireann, openmeteo, mock
- `views/simplified.py`, `detailed.py`, `today.py`, `tomorrow.py`,
  `current.py`, `hourly.py`, `daily.py`
- All page CSS, HTML, weather icons, fonts
- `google/api.py` (static maps) — reusable, but publish as an **optional
  extra**, not core
- `validate_config` — `weather.*`, `google.*`, `location` blocks

### 3.3 The inversion that makes it pluggable

Today `main()` hardcodes five page objects, and `regenerate()` hardcodes which
weather call feeds which page. Core must not know that. Three new abstractions:

**a) `DataSource` — replaces `WeatherService` as the core contract**

```python
class DataSource(ABC):
    """Supplies named datasets to pages. The project defines the names."""

    @abstractmethod
    def datasets(self) -> dict[str, Callable[[], Any]]:
        """Map dataset name → zero-arg lazy fetcher."""

    def invalidate(self) -> None:
        """Drop caches so the next fetch hits the network."""
```

`WeatherService` becomes a project-level subclass exposing
`{"daily_summary": ..., "current_conditions": ..., "hourly_forecast": ...}`.
An env-monitor project exposes `{"sensor_readings": ..., "history_24h": ...}`.

**b) `Page.requires` — pages declare their data needs**

```python
class Page:
    name: str = ""
    requires: tuple[str, ...] = ()      # dataset names this page needs

    def render(self, **datasets) -> None: ...   # build self.airium
    def save(self) -> None: ...                 # core: screenshot + quantise
```

**c) `PageRegistry` — maps served URL path → page**

Then core's regeneration loop is fully generic:

```python
def regenerate(self, url_path=None, force_refresh=False):
    pages = [self.pages[url_path]] if url_path else self.pages.values()
    if force_refresh:
        self.source.invalidate()
    needed = {k for p in pages for k in p.requires}
    fetchers = self.source.datasets()
    data = {k: fetchers[k]() for k in needed}      # fetched once, shared
    with self.regen_lock:
        for p in pages:
            p.render(**{k: data[k] for k in p.requires})
            p.save()
```

This removes every `if regen_today: ...` branch from `server.py`.

### 3.4 Make the renderer itself pluggable

`Page.save()` currently hardcodes two things:

- **Screenshot backend:** Selenium + Chromium. Extract as a `Renderer`
  protocol (`render(html_path, width, height) -> PIL.Image`) so Playwright,
  `wkhtmltoimage`, or a pure-PIL renderer can be swapped in.
- **Quantisation:** hardcoded 4-level greyscale, Floyd–Steinberg. Different
  panels need different palettes (1-bit mono, 3-bit grey, 7-colour ACeP).
  Make it a `Quantiser` with a per-panel palette from config.

```python
class Renderer(Protocol):
    def render(self, html_path: str, width: int, height: int) -> Image.Image: ...

class Quantiser(Protocol):
    def apply(self, img: Image.Image) -> Image.Image: ...
```

Core ships `ChromiumRenderer` + `GreyscaleQuantiser(levels=4)` as defaults.

---

### 3.5 Step 3 outcome

`epd/server/` is a pip package, `epd-server`, importable as `epd_server`:

| Module | From | Change |
|---|---|---|
| `config.py` | `utils.py` | Dropped the unused `dehumanized` parameter. `even_select` stayed in weather-cal (only AccuWeather uses it). |
| `registry.py` | `weather/registry.py` | Now a `Registry` **class**, one instance per plugin kind, so data sources and pages can be registered independently. `create(name, **kwargs)` keeps the declared-kwargs filtering. |
| `cache.py` | `weather/cache.py` | Verbatim. |
| `page.py` | `views/page.py` | `Page` takes `html_dir` and `png_dir`; it no longer writes next to its own source file, which would be site-packages. |
| `scheduling.py` | `server.py` | `next_wake`, `next_regen`, plus `seconds_until` and `validate_time_list`. The latter **raises** `ValueError`; the daemon decides to exit. |
| `mqtt.py` | `server.py` | `client_log_subscriber`. |

weather-cal keeps thin shims at the old import paths, so its providers, views
and tests are unchanged. Tests moved with the code: 44 out of weather-cal,
26 new in the kit (registry, cache, page paths, `validate_time_list`,
`seconds_until`). Kit: 70 pass. weather-cal: 116 pass + the pre-existing
Met Éireann date-rot failure.

Consumers install with a VCS URL. pip honours `#subdirectory=` only for VCS
URLs (verified: the archive form fails to find `pyproject.toml`), so the
weather-cal Dockerfile now installs `git`:

```
epd-server @ git+https://github.com/chrisjtwomey/epd.git@main#subdirectory=server
```

### 3.6 Step 4 outcome

`Page.save()` is now three lines: render, quantise, write. Both steps are
protocols with defaults that reproduce the previous output exactly.

| Module | Provides |
|---|---|
| `render.py` | `Renderer` protocol. `ChromiumRenderer` (Selenium, headless) is the default; starts and quits a browser per render, now inside `try/finally` so a failed render cannot leak a Chromium process. Sets `binary_location` only when the path exists, so Selenium Manager can find a browser outside Docker. |
| `quantise.py` | `Quantiser` protocol. `GreyscaleQuantiser(levels=4)` default; `levels=2` mono, `levels=8` for 3-bit Inkplates. `PaletteQuantiser(colors)` for 3-colour and 7-colour panels. `IdentityQuantiser` for none. |

**Golden equivalence:** `test_quantise.py` carries the old inline algorithm
verbatim and asserts `GreyscaleQuantiser(levels=4)` produces byte-identical
output on seeded noisy gradients. `Page.save()` is tested end to end with a
fake `Renderer`, so no test needs Chromium.

Kit: 103 tests pass. weather-cal: 116 + the pre-existing Met Éireann
date-rot failure; its `views/page.py` shim forwards `renderer=` /
`quantiser=` so the calendar can switch to eight greys with one argument.

### 3.7 Step 5 outcome — the inversion

`server.py`'s `regenerate()` is now four lines: lock, call the pipeline,
log. Every `if regen_today:` branch is gone.

| Where | What |
|---|---|
| `epd_server/source.py` | `DataSource` — `datasets()` returns name → zero-arg fetcher, so nothing is fetched until a page needs it. `StaticSource(**consts)`. `CompositeSource(*sources)` merges and rejects colliding names. |
| `epd_server/page.py` | `Page.requires` — dataset names `template()` takes as kwargs. `SkipPage` — raise from `template()` to keep the old PNG. `png_filename`. |
| `epd_server/pipeline.py` | `regenerate(pages, source, only=, force_refresh=)` — select by name or filename, fetch each needed dataset **once**, render, save. Unknown page or unprovided dataset is an error raised before any fetch. |
| weather-cal `weather/service.py` | `WeatherService(DataSource)`; `datasets()` maps the four `get_*` methods. |
| weather-cal `views/*.py` | `requires` on all five. `TomorrowPage` picks tomorrow from `daily_forecasts` itself and raises `SkipPage` when absent — the special case left `server.py`. |
| weather-cal `server.py` | `source = CompositeSource(StaticSource(map_url=…), weather_svc)`; `regenerate()` delegates. |

New integration test drives the real views through the pipeline with the
mock weather service and a fake renderer. Kit: 122 tests. weather-cal: 122 +
the pre-existing date-rot failure.

**What this buys the env-monitor:** its `main.py` will be a page list, a
`DataSource`, and one call. No server-loop code to write.

### 3.8 Step 6 outcome — config

The "hook" is plain composition, not a callback: a project calls
`load_core_config(raw, default_schedule=…)` for the generic blocks and reads
its own keys with the same env-overridable `get_prop_by_keys`. One
`try/except (ConfigError, KeyError)` around both decides how to report.

| Kit (`epd_server/config.py`) | |
|---|---|
| `load_core_config(raw, **defaults) -> CoreConfig` | `server`, `image`, `mqtt`, `display_schedule`, `debug` → frozen dataclasses `ServerSettings`, `ImageSettings`, `MqttSettings`. Every default is a keyword argument. |
| `ConfigError(ValueError)` | Message is user-facing. Messages are unchanged from the original. |
| `load_yaml(path)` | Empty file → `{}`; non-mapping → error. |
| `ImageSettings.page_kwargs()` | Straight into `Page(**…)`. |

New checks over the original: `server.port` and `mqtt.port` must be valid
TCP ports. One behaviour fix in weather-cal: a missing required key used to
escape as a raw `KeyError` traceback; it now reports like every other config
error and exits.

Kit: 175 tests. weather-cal: 128 + the pre-existing date-rot failure.

### 3.9 Step 7 outcome — `DisplayServer`

`epd_server/app.py` owns what used to be module-level state and free
functions in `server.py`:

| | |
|---|---|
| Routes | `/<page>.png` for every page in the list, served from `page.png_path`; plus `/` returning pages, schedule and next wake as JSON. |
| Headers | `X-Next-Refresh-Seconds`, `X-Next-URL` from the schedule via `next_wake()`. |
| `regenerate(only=, force_refresh=)` | The pipeline under the lock that stops a client reading a half-written PNG. |
| `run(once=)` | Regenerate all; HTTP thread; MQTT log relay if enabled; sleep until `regen_lead_seconds` before each wake, then regenerate that page with a fresh fetch. `SIGTERM`/`SIGINT` stop it cleanly. |
| `align_process_timezone(tz)` | Sets `TZ` so logging timestamps match the configured zone. |

The schedule is checked against the pages at construction: a filename no
page produces is a `ValueError` at startup. Before, it silently regenerated
nothing every cycle (the no-op flagged in §3.7).

weather-cal's `server.py` went from 434 to 245 lines and is now only: its
config keys, its weather service, its five pages, one `run()`. I kept the
filename `server.py`; renaming to `main.py` would have churned the
Dockerfile, entrypoint and README for no functional gain.

Kit: 192 tests, none need a network or a browser (`DisplayServer` is tested
with Flask's test client and a stand-in shutdown event). weather-cal: 121 +
the pre-existing date-rot failure; the route and `get_next_wake` tests moved
to the kit, and a new smoke test runs `main() --once` end to end with the
mock weather service, a stubbed Google API and a fake renderer.

## 4. Repo layout — firmware done

**One core repo**, because client and server share the HTTP contract and must
version together. The firmware half now exists at
`../epd`:

```
epd/
├── firmware/                       ← library: EpdClient
│   ├── library.json
│   ├── platformio.ini              host-only test project (excluded from package)
│   ├── include/                    IBoard, MockBoard, app, *_utils, mem_utils, fonts, icons
│   ├── src/                        app.cpp + the util implementations
│   ├── boards/inkplate/            ← library: EpdBoardInkplate
│   └── test/                       64 host tests, 3 environments
├── docs/custom-board.md
└── .github/workflows/build.yaml
```

Two libraries, not one: a project on other hardware never pulls in
InkplateLibrary. A `lib_deps` git URL can only address a repository root, so
consumers use `symlink://` locally and published packages for releases.

```
epd/                          ← NEW shared repo
├── firmware/                        ← PlatformIO library
│   ├── library.json
│   ├── src/     IBoard.h  MockBoard.h  app.cpp  network_utils.cpp
│   │            sleep_utils.cpp  time_utils.cpp  log_utils.cpp
│   │            display_utils.cpp  battery.cpp  backoff.cpp
│   │            refresh_header.cpp  file_utils.cpp  error_utils.h
│   ├── boards/  InkplateBoard.{h,cpp}
│   └── assets/  default fonts + battery icons
├── server/                          ← pip package `epd_server`
│   ├── pyproject.toml
│   └── epd_server/
│       ├── app.py          DisplayServer: schedule, serve, regen loop
│       ├── config.py       generic config blocks + env override (from utils.py)
│       ├── scheduling.py   _next_wake / _next_regen
│       ├── page.py         Page base + layout_css_variables
│       ├── render.py       Renderer protocol + ChromiumRenderer
│       ├── quantise.py     Quantiser protocol + greyscale/mono palettes
│       ├── registry.py     generic plugin registry (from weather/registry.py)
│       ├── cache.py        DiskCache
│       ├── source.py       DataSource ABC
│       ├── mqtt.py         client log subscriber
│       └── static/         inner-canvas CSS scaffolding
├── docker/                          Chromium base image
└── docs/                            wire contract, custom-board, custom-source
```

**Consumers become thin:**

```
inkplate10-weather-cal/              ← after extraction
├── platformio.ini                   lib_deps: epd/firmware
├── src/main.cpp  src/defaults.cpp
└── server/
    ├── sources/weather/             5 providers + WeatherService(DataSource)
    ├── pages/                       today, current, tomorrow, hourly, daily
    ├── static/                      weather CSS, icons, fonts
    ├── config.yaml
    └── main.py                      ~30 lines: register + DisplayServer().run()

inkplate5-env-monitor/            ← this repo
├── platformio.ini                   -DARDUINO_INKPLATE5V2, lib_deps: epd
├── src/main.cpp  src/defaults.cpp
└── server/
    ├── sources/                     sensor / MQTT / InfluxDB DataSource
    ├── pages/                       env pages
    ├── static/
    ├── config.yaml
    └── main.py
```

A project's `main.py` reduces to roughly:

```python
from epd_server import DisplayServer, load_config
from sources.sensors import SensorSource
from pages.now import NowPage
from pages.history import HistoryPage

cfg = load_config("config.yaml", extra_schema=MY_SCHEMA)
DisplayServer(
    config=cfg,
    source=SensorSource(**cfg.source),
    pages=[NowPage(cfg.image), HistoryPage(cfg.image)],
).run()
```

---

## 5. Migration order

Each step leaves `inkplate10-weather-cal` green.

| # | Step | Risk |
|---|---|---|
| 1 | ~~Fix the `IBoard` leaks in §2.1 in-place; add `rtcSetEpoch` + `enableWakeOnRtcAlarm` to `IBoard`; keep tests green~~ **DONE** | Low — caught a live UB bug and a download-error bug |
| 2 | ~~Create `epd`; move firmware files; add `library.json`; point `inkplate10-weather-cal` at it via `lib_deps`~~ **DONE** | Turned out not to be a pure move — see §2.3 |
| 3 | ~~Move the generic server modules (`utils.py`, `registry.py`, `cache.py`, `page.py`, scheduling helpers) into `epd_server`; leave shims~~ **DONE 2026-09-02** | Two small API changes, see §3.5 |
| 4 | ~~Introduce `Renderer` + `Quantiser`; make `Page.save()` delegate~~ **DONE 2026-09-02** | Default output proven byte-identical to the old algorithm, see §3.6 |
| 5 | ~~Introduce `DataSource` + `Page.requires`; rewrite `regenerate()` generically; make `WeatherService` a `DataSource`~~ **DONE 2026-09-02** | See §3.7 |
| 6 | ~~Split `validate_config` into core blocks + project schema hook~~ **DONE 2026-09-02** | See §3.8 |
| 7 | ~~Extract `DisplayServer`; reduce `server.py` to a thin `main.py`~~ **DONE 2026-09-03** | See §3.9. Kept the filename `server.py`. |
| 8 | Stand up `inkplate5-env-monitor` against `epd` | — |

Steps 1–3 are safe mechanical wins. Steps 4–7 are the design work.

---

## 6. Open decisions

1. **One core repo or two** (firmware and server split)? One is recommended —
   the `X-Next-*` contract must not skew.
2. ~~**Core repo name.**~~ Decided 2026-09-02: `epd`. Libraries are `EpdClient` and `EpdBoardInkplate`; the Python package will be `epd_server`.
3. **Python distribution.** Git-tag pip install, or publish to PyPI?
4. **Keep `google/api.py` in core** as an optional extra, or leave it in the
   weather project?
5. **Fonts and battery icons:** core defaults, or per-project assets?
