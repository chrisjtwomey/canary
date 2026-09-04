// The awake loop.
//
// Mains powered, so nothing sleeps. The board connects once, then fetches
// the page the server names, draws it, and waits the seconds the server
// sends before fetching again. Between fetches it samples the sensors
// every 5 s and prints one readings document a minute; POSTing them is
// the next step (docs/ARCHITECTURE.md §7). A failed fetch leaves the last
// image on the panel and backs off before the next try.
#include <Arduino.h>
#include <WiFi.h>
#include <ezTime.h>

#include "IBoard.h"
#include "InkplateBoard.h"
#include "backoff.h"
#include "defaults.h"
#include "display_utils.h"
#include "log_utils.h"
#include "network_utils.h"
#include "time_utils.h"
#include "user_agent.h"
#include "version.h"

#include "net/RefreshTimer.h"
#include "sensors/IClock.h"
#include "sensors/Readings.h"
#include "sensors/SensorSuite.h"

static InkplateBoard inkplateBoard;
IBoard& board = inkplateBoard;   // EpdClient's helpers draw and log through this

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

// The simulated room only moves when it is told to.
static void advanceSimulation(uint32_t epoch) { room.advanceTo(epoch); }
static const char* kBanner = "mock sensors up; PM fan warming up for 30 s";

#else
#error "No real sensor drivers yet. Build with -DUSE_MOCK_SENSORS, or add \
Shtc3Driver / Scd41Driver / Pmsa003iDriver / Bme688Driver implementing the \
IShtc3 / IScd41 / IPmsa003i / IBme688 interfaces and wire them up here."
#endif

// ─── Everything below is implementation-agnostic ──────────────────────────

static const uint8_t  kRotation = 0;             // landscape; 2 turns it round
static const uint32_t kSampleIntervalMs = 5000;
static const uint32_t kReportIntervalMs = 60000;

static ArduinoClock wallClock;
static SensorSuite  sensors(wallClock, shtc3Impl, scd41Impl, pmImpl, bmeImpl);
static RefreshTimer refresh(serverDefaultRefreshSeconds);

static char     nextURL[256];        // from X-Next-URL; empty means serverURL
static uint32_t lastSampleMs = 0;
static uint32_t lastReportMs = 0;
static char     json[640];

// UTC seconds: network time once NTP has answered, the RTC until then.
static uint32_t epochNow() {
    if (timeStatus() != timeNotSet) return (uint32_t)now();
    return (uint32_t)board.rtcGetEpoch();
}

static void connectWiFi() {
    while (configureWiFi(wifiSSID, wifiPass, wifiRetries) != ESP_OK) {
        log(LOG_ERROR, "wifi connect timeout; trying again in 30 s");
        delay(30000);
    }
}

static void fetchAndDraw() {
    if (WiFi.status() != WL_CONNECTED) {
        log(LOG_WARNING, "wifi down; reconnecting");
        configureWiFi(wifiSSID, wifiPass, wifiRetries);
    }

    const char* url = nextURL[0] ? nextURL : serverURL;
    uint32_t waitSeconds = 0;
    int32_t len = board.getWidth() * board.getHeight() * 8 + 100;
    uint8_t* buf = downloadFile(url, clientUserAgent(board.deviceName()),
                                &waitSeconds, &len, nextURL, sizeof(nextURL));
    if (!buf) {
        uint32_t wait = refresh.failed(millis(), computeBackoffSeconds);
        logf(LOG_ERROR, "download failed (back-off step %d): next try in %u s",
             refresh.step(), wait);
        return;
    }

    board.clearDisplay();
    esp_err_t err = loadImage(buf, len);
    free(buf);
    if (err != ESP_OK) {
        uint32_t wait = refresh.failed(millis(), computeBackoffSeconds);
        logf(LOG_ERROR, "image draw failed (back-off step %d): next try in %u s",
             refresh.step(), wait);
        return;
    }
    board.display();

    refresh.succeeded(millis(), waitSeconds);
    logf(LOG_INFO, "next refresh in %u s",
         waitSeconds ? waitSeconds : serverDefaultRefreshSeconds);
}

static void sampleSensors(uint32_t nowMs) {
    uint32_t epoch = epochNow();
    advanceSimulation(epoch);
    Readings r = sensors.sample(epoch);

    if (nowMs - lastReportMs < kReportIntervalMs) return;
    lastReportMs = nowMs;
    if (readingsToJson(r, CLIENT_NAME, json, sizeof(json))) {
        log(LOG_INFO, json);
    } else {
        log(LOG_WARNING, "json buffer too small");
    }
}

void setup() {
    Serial.begin(115200);
    board.begin();
    board.setRotation(kRotation);
    board.rtcGetData();
    setTime(board.rtcGetEpoch());

    logf(LOG_NOTICE, "##### %s boot #####", board.deviceName());
    logf(LOG_NOTICE, "Client version: %s", CLIENT_VERSION);
    logf(LOG_INFO, "User-Agent: %s", clientUserAgent(board.deviceName()));

    connectWiFi();
    if (configureTime(ntpHost, ntpTimezone) != ESP_OK) {
        log(LOG_WARNING, "NTP sync failed; running on the RTC");
    }
    if (mqttLoggerEnabled &&
        configureMQTT(mqttLoggerBroker, mqttLoggerPort, mqttLoggerTopic,
                      mqttLoggerClientID, mqttLoggerRetries) != ESP_OK) {
        log(LOG_WARNING, "remote logging unavailable; serial only");
    }

    advanceSimulation(epochNow());
    if (!sensors.begin()) {
        logf(LOG_WARNING, "sensor start incomplete: shtc3=%d scd41=%d pm=%d bme688=%d",
             sensors.shtc3Present(), sensors.scd41Present(),
             sensors.pmPresent(), sensors.bme688Present());
    }
    log(LOG_INFO, kBanner);
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
