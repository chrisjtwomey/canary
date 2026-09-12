// The awake loop.
//
// Mains powered, so nothing sleeps. The board connects once, then fetches
// the page the server names, draws it, and waits the seconds the server
// sends before fetching again. Between fetches it samples the sensors
// every 5 s and once a minute posts a readings document, with the board's
// own status beside it, to the server's /readings. A failed fetch leaves
// the last image on the panel and backs off before the next try.
#include <Arduino.h>
#include <WiFi.h>
#include <ezTime.h>

#include "epd.h"
#include "InkplateBoard.h"
#include "backoff.h"
#include "image.h"
#include "log_utils.h"
#include "network_utils.h"
#include "ota.h"
#include "sd_config.h"
#include "settings.h"
#include "wake.h"
#include "time_utils.h"
#include "user_agent.h"
#include "version.h"

#include "net/ClientStatus.h"
#include "net/RefreshTimer.h"
#include "net/Url.h"
#include "sensors/IClock.h"
#include "sensors/Readings.h"
#include "sensors/SensorSuite.h"

// The settings this image was built with, from src/defaults.cpp. epd declares
// no settings symbols of its own, so this one is the project's.
ClientConfig builtInSettings();

static InkplateBoard inkplateBoard;
static ArduinoClock  wallClock;

// ─── The only part that knows which sensor implementation is in use ───────

#if defined(USE_MOCK_SENSORS)
#include "sensors/mock/EnvModel.h"
#include "sensors/mock/MockBme688.h"
#include "sensors/mock/MockPmsa003i.h"
#include "sensors/mock/MockScd41.h"
#include "sensors/mock/MockShtc3.h"

static EnvModel     room(7);
static MockShtc3    shtc3Impl(room);
static MockScd41    scd41Impl(room);
static MockPmsa003i pmImpl(room);
static MockBme688   bmeImpl(room);

// The simulated room only moves when it is told to. The first call settles
// it over the three hours before now; walking from epoch 0 would take minutes.
static void advanceSimulation(uint32_t epoch) {
    static bool started = false;
    if (!started) {
        room.reset(epoch - 3 * 3600);
        started = true;
    }
    room.advanceTo(epoch);
}
static void logSensorBanner() {
    log(LOG_INFO, "mock sensors up; PM fan warming up for 30 s");
}
static const bool kMockSensors = true;

#else
#include "sensors/Bme688Driver.h"
#include "sensors/II2cBus.h"
#include "sensors/Pmsa003iDriver.h"
#include "sensors/Scd41Driver.h"
#include "sensors/Shtc3Driver.h"

// docs/HARDWARE.md 8: the PM module's SET line goes to expander P1_3. The
// Inkplate library drives that pin low at boot, which stops the fan, so the
// driver is given the pin. With no wire on it the write does nothing.
static const uint8_t kPmSetPin = 11;
static void setPmFanLine(bool high) { epdBoard().writeExpanderPin(kPmSetPin, high); }

static ArduinoI2cBus  i2cBus;          // Wire, which Inkplate::begin() started
static Shtc3Driver    shtc3Impl(i2cBus, wallClock);
static Scd41Driver    scd41Impl(i2cBus, wallClock);
static Bme688Driver   bmeImpl(i2cBus, wallClock);
static Pmsa003iDriver pmImpl(i2cBus, wallClock, setPmFanLine);

// The readings come from the room itself, so there is nothing to advance.
static void advanceSimulation(uint32_t) {}
static void logSensorBanner() {
    log(LOG_INFO, "sensors up; PM fan SET line driven high on expander P1_3");
}
static const bool kMockSensors = false;
#endif

// ─── Everything below is implementation-agnostic ──────────────────────────

static const uint8_t  kRotation = 0;             // landscape; 2 turns it round
static const uint32_t kSampleIntervalMs = 5000;
static const uint32_t kReportIntervalMs = 60000;
// Buffer size when the server sends no Content-Length. An eight-grey
// 1280x720 PNG is under 200 KB.
static const int32_t  kDownloadFallbackBytes = 512 * 1024;

static SensorSuite sensors(wallClock, shtc3Impl, scd41Impl, pmImpl, bmeImpl);
// The fallback interval is a compiled-in constant, so it can be read before
// setup() resolves the rest of the config against the board's own store.
static RefreshTimer refresh(builtInSettings().defaultRefreshSeconds);

static ClientConfig config;          // this board's own server URL and wifi
static char     nextURL[256];        // from X-Next-URL; empty means the server URL
// True until this boot proves a freshly written image works.
static bool     onTrial = false;
static int      trialFailures = 0;

// Three failures in a row is enough to call a new image broken.
static const int kTrialFailureLimit = 3;
static char     readingsURL[300];    // the server's /readings; empty disables posting
static uint32_t lastSampleMs = 0;
static uint32_t lastReportMs = 0;
static uint32_t fetchOk = 0;
static uint32_t fetchFailed = 0;
static char     json[640];
static char     clientJson[512];
static char     body[1200];
static char     ipText[16];

// UTC seconds: network time once NTP has answered, the RTC until then.
static uint32_t epochNow() {
    if (timeStatus() != timeNotSet) return (uint32_t)now();
    return (uint32_t)epdBoard().rtcGetEpoch();
}

// Mains power and no schedule to keep, so there is nothing to do but wait
// for the network to come back.
static void connectNetworkForever() {
    while (connectNetwork(config) != ESP_OK) {
        log(LOG_ERROR, "wifi connect timeout; trying again in 30 s");
        delay(30000);
    }
}

// A new image that cannot complete a cycle is not worth keeping. Mains
// power means a failure here is the image's fault, not a flat battery.
static void abandonTrialAfterRepeatedFailures(const char* why) {
    if (!onTrial) return;
    if (++trialFailures < kTrialFailureLimit) return;
    otaRollback(why);   // reboots into the previous image
}

// Count the failure, arm the next try, and give up on an image on trial.
static void failedFetch(const char* why) {
    ++fetchFailed;
    uint32_t wait = refresh.failed(millis(), computeBackoffSeconds);
    logf(LOG_ERROR, "%s (back-off step %d): next try in %u s", why, refresh.step(), wait);
    abandonTrialAfterRepeatedFailures(why);
}

static void fetchAndDraw() {
    if (WiFi.status() != WL_CONNECTED) {
        log(LOG_WARNING, "wifi down; reconnecting");
        configureWiFi(config.wifiSSID, config.wifiPass, config.wifiRetries);
    }

    // One try each time round: the loop comes back on its own, and there is
    // no sleep to get right.
    const char* errMsg = nullptr;
    PageFetch page = {};
    page.length = kDownloadFallbackBytes;
    const char* url = nextURL[0] ? nextURL : config.serverURL;

    if (!fetchPage(url, clientUserAgent(epdBoard().deviceName()), 0, &page, &errMsg)) {
        failedFetch(errMsg);
        return;
    }
    if (page.response.nextURL[0])
        snprintf(nextURL, sizeof(nextURL), "%s", page.response.nextURL);

    // Nothing over the page: this board has no battery to report.
    bool drawn = drawPage(page, nullptr, 0, nullptr, &errMsg);
    free(page.data);
    if (!drawn) {
        failedFetch(errMsg);
        return;
    }

    ++fetchOk;
    trialFailures = 0;
    refresh.succeeded(millis(), page.response.nextRefreshSeconds);
    logf(LOG_INFO, "next refresh in %u s",
         page.response.nextRefreshSeconds ? page.response.nextRefreshSeconds
                                          : config.defaultRefreshSeconds);

    // A page is on the panel, so a freshly written image has proved itself.
    // Confirming it also frees the idle slot for the next update.
    if (onTrial) {
        otaConfirm();
        onTrial = false;
    }

    // Mains power, so no battery to wait for.
    takeOfferedUpdate(page.response, clientUserAgent(epdBoard().deviceName()), 100, 0);
}

static ClientStatus clientStatus(uint32_t nowMs) {
    strncpy(ipText, WiFi.localIP().toString().c_str(), sizeof(ipText) - 1);
    ClientStatus s = {};
    s.board = epdBoard().deviceName();
    s.version = CLIENT_VERSION;
    s.ip = ipText;
    s.rssi = WiFi.RSSI();
    s.uptimeS = nowMs / 1000;
    s.heapFree = ESP.getFreeHeap();
    s.heapSize = ESP.getHeapSize();
    s.psramFree = ESP.getFreePsram();
    s.psramSize = ESP.getPsramSize();
    s.panelTempC = epdBoard().readPanelTemperature();
    s.width = epdBoard().getWidth();
    s.height = epdBoard().getHeight();
    s.rotation = kRotation;
    s.mockSensors = kMockSensors;
    s.shtc3 = sensors.shtc3Present();
    s.scd41 = sensors.scd41Present();
    s.pm = sensors.pmPresent();
    s.bme688 = sensors.bme688Present();
    s.nextUrl = nextURL[0] ? nextURL : config.serverURL;
    s.nextInS = refresh.secondsUntilDue(nowMs);
    s.backoffStep = refresh.step();
    s.fetchOk = fetchOk;
    s.fetchFailed = fetchFailed;
    return s;
}

static void postReadings(const Readings& r, uint32_t nowMs) {
    if (!readingsToJson(r, CLIENT_NAME, json, sizeof(json)) ||
        !clientStatusJson(clientStatus(nowMs), clientJson, sizeof(clientJson)) ||
        !withClientStatus(json, clientJson, body, sizeof(body))) {
        log(LOG_WARNING, "readings document too large to post");
        return;
    }
    log(LOG_DEBUG, body);
    if (!readingsURL[0]) return;
    int code = postJson(readingsURL, clientUserAgent(epdBoard().deviceName()), body);
    if (code == 204 || code == 200) {
        logf(LOG_INFO, "posted readings (%d)", code);
    } else {
        logf(LOG_ERROR, "posting readings failed (%d)", code);
    }
}

static void sampleSensors(uint32_t nowMs) {
    uint32_t epoch = epochNow();
    advanceSimulation(epoch);
    Readings r = sensors.sample(epoch);

    if (nowMs - lastReportMs < kReportIntervalMs) return;
    lastReportMs = nowMs;
    postReadings(r, nowMs);
}

void setup() {
    epdBegin(inkplateBoard);
    startBoard(kRotation);

    logf(LOG_NOTICE, "##### %s boot #####", epdBoard().deviceName());
    logf(LOG_NOTICE, "Client version: %s", CLIENT_VERSION);
    logf(LOG_INFO, "User-Agent: %s", clientUserAgent(epdBoard().deviceName()));

    onTrial = otaTrialPending();
    if (onTrial) logf(LOG_NOTICE, "trial boot of %s", CLIENT_VERSION);
    config = loadConfig(builtInSettings());
    applySdConfig(&config);

    connectNetworkForever();
    if (urlOrigin(config.serverURL, readingsURL, sizeof(readingsURL) - 10)) {
        strcat(readingsURL, "/readings");
        logf(LOG_INFO, "posting readings to %s", readingsURL);
    } else {
        log(LOG_WARNING, "the server URL has no host; readings stay on the serial log");
    }

    advanceSimulation(epochNow());
    if (!sensors.begin()) {
        logf(LOG_WARNING, "sensor start incomplete: shtc3=%d scd41=%d pm=%d bme688=%d",
             sensors.shtc3Present(), sensors.scd41Present(),
             sensors.pmPresent(), sensors.bme688Present());
    }
    logSensorBanner();
}

void loop() {
    events();   // ezTime: periodic NTP re-sync
    uint32_t nowMs = millis();

    if (refresh.due(nowMs)) fetchAndDraw();

    if (nowMs - lastSampleMs >= kSampleIntervalMs) {
        lastSampleMs = nowMs;
        sampleSensors(nowMs);
    }
    delay(10);
}
