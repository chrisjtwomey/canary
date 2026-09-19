// The dock's loop.
//
// A TinyS3 with the four sensors on their own regulator. Mains powered, so
// nothing sleeps: it connects once, then samples every 5 s and posts a
// readings document once a minute to the server's /readings, with its own
// status beside it. Readings the server will not take wait in PSRAM and go
// out with the next one it takes. The head fetches the pages the server
// renders from them and knows nothing about any of this.
#include <Arduino.h>
#include <WiFi.h>
#include <Wire.h>
#include <ezTime.h>

#include "log_utils.h"
#include "network_utils.h"
#include "settings.h"
#include "time_utils.h"
#include "user_agent.h"
#include "version.h"

#include "net/Backlog.h"
#include "net/Calibration.h"
#include "net/ClientStatus.h"
#include "net/Url.h"
#include "sensors/II2cBus.h"
#include "sensors/IClock.h"
#include "sensors/Readings.h"
#include "sensors/SensorSuite.h"

// The settings this image was built with, from src/defaults.cpp.
ClientConfig builtInSettings();

// hardware/README.md, "Wires at the TinyS3": the bus on J4 pins 5 and 6, the
// PM module's SET line on pin 7, the status LED on pin 8.
static const uint8_t kSdaPin = 8;
static const uint8_t kSclPin = 9;
static const uint8_t kPmSetPin = 7;

static ArduinoClock wallClock;

// UTC seconds at boot, once NTP has answered; 0 until then. The dock has no
// clock of its own, so until then a reading carries no timestamp and the BSEC
// task saves none.
static volatile uint32_t bootEpoch = 0;
static uint32_t syncedEpoch() { return bootEpoch ? bootEpoch + millis() / 1000 : 0; }

static char calibrationURL[310];   // the server's /calibration; empty when there is no server

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
static void startI2c() {}
static void logSensorBanner() { log(LOG_INFO, "mock sensors up; PM fan warming up for 30 s"); }
static const bool kMockSensors = true;
// The mock models BSEC's output itself, and has no state to keep.
static void startBsec() {}
static void fillBsecStatus(ClientStatus&) {}
static size_t calibrationBlock(char*, size_t) { return 0; }
static void restoreFromServer() {}

#else
#include <Preferences.h>

#include "sensors/Bme688Driver.h"
#include "sensors/BsecLibrary.h"
#include "sensors/BsecRunner.h"
#include "sensors/Pmsa003iDriver.h"
#include "sensors/Scd41Driver.h"
#include "sensors/Shtc3Driver.h"

static void setPmFanLine(bool high) { digitalWrite(kPmSetPin, high ? HIGH : LOW); }

static ArduinoI2cBus  i2cBus;
static Shtc3Driver    shtc3Impl(i2cBus, wallClock);
static Scd41Driver    scd41Impl(i2cBus, wallClock);
static Bme688Driver   bmeDriver(i2cBus, wallClock);
static Pmsa003iDriver pmImpl(i2cBus, wallClock, setPmFanLine);

static void startI2c() {
    pinMode(kPmSetPin, OUTPUT);
    digitalWrite(kPmSetPin, LOW);        // the fan stays off until the suite starts it
    Wire.begin(kSdaPin, kSclPin);
    Wire.setClock(100000);               // docs/HARDWARE.md 6: 100 kHz, and nothing cut
    // A sensor that drops off the bus would otherwise slow every sample.
    Wire.setTimeOut(ArduinoI2cBus::kTimeoutMs);
}

// BSEC's state in NVS, which keeps it across power cuts, OTA updates and USB
// uploads.
static const char kBsecNamespace[] = "bsec";
class NvsBsecStore : public IBsecStateStore {
public:
    bool load(BsecState& out) override {
        Preferences prefs;
        if (!prefs.begin(kBsecNamespace, true)) return false;
        out = BsecState();
        out.len = prefs.getBytes("state", out.blob, sizeof(out.blob));
        out.accuracy = prefs.getUChar("accuracy", 0);
        out.savedEpoch = prefs.getULong("saved", 0);
        prefs.end();
        return out.len > 0;
    }
    bool save(const BsecState& state) override {
        Preferences prefs;
        if (!prefs.begin(kBsecNamespace, false)) return false;
        const bool ok = prefs.putBytes("state", state.blob, state.len) == state.len;
        prefs.putUChar("accuracy", state.accuracy);
        prefs.putULong("saved", state.savedEpoch);
        prefs.end();
        return ok;
    }
};

static BsecLibrary  bsecLibrary;
static NvsBsecStore bsecStore;
static BsecRunner   bsecRunner(bsecLibrary, bmeDriver, wallClock, bsecStore, syncedEpoch);
static BsecBme688   bmeImpl(bsecRunner);

// Above the loop's priority, so a post cannot make a sample late. Wire locks
// each transaction, so the task and the loop share the bus without a lock of
// their own.
static const uint32_t    kBsecStackBytes = 8192;
static const UBaseType_t kBsecPriority = 2;

static void bsecTask(void*) {
    for (;;) {
        const uint32_t waitMs = bsecRunner.step();
        vTaskDelay(pdMS_TO_TICKS(waitMs ? waitMs : 1));
    }
}

// The state NVS gave BSEC at boot, to weigh against the server's copy.
static BsecState nvsState;

static void startBsec() {
    const bool running = bsecRunner.begin(&nvsState);
    const BsecRunner::Status bsec = bsecRunner.status();
    if (!bsec.started) {
        log(LOG_WARNING, "[bsec] start: failed; retry in 3 s");
    } else {
        if (bsec.restored) {
            logf(LOG_INFO, "[bsec] start: NVS state (accuracy %u)", (unsigned)nvsState.accuracy);
        } else {
            log(LOG_INFO, "[bsec] start: no saved state");
        }
        if (!running) log(LOG_WARNING, "[bsec] BME688: not answering; retry in 3 s");
    }
    xTaskCreatePinnedToCore(bsecTask, "bsec", kBsecStackBytes, nullptr, kBsecPriority, nullptr, 1);
}

static void fillBsecStatus(ClientStatus& s) {
    const BsecRunner::Status bsec = bsecRunner.status();
    s.bsecRunning = bsec.running;
    s.bsecRestored = bsec.restored;
    s.iaqAccuracy = bsec.accuracy;
    s.bsecLateCalls = bsec.lateCalls;
    s.bsecSavedEpoch = bsec.savedEpoch;
}

// The state as of BSEC's last copy, for the calibration block of the POST.
static size_t calibrationBlock(char* buf, size_t len) {
    BsecState state;
    if (!bsecRunner.current(state)) return 0;
    return calibrationJson(state.blob, state.len, state.accuracy, state.savedEpoch, buf, len);
}

// Asked once a boot, after the server has taken a readings POST, so a failed
// request means the server holds no copy, not that it is down.
static bool askedServerForState = false;

static void restoreFromServer() {
    if (askedServerForState || !bootEpoch || !calibrationURL[0]) return;
    askedServerForState = true;

    char url[360];
    snprintf(url, sizeof(url), "%s?device=%s&before=%lu", calibrationURL, CLIENT_NAME,
             (unsigned long)bootEpoch);
    int32_t size = 1024;
    uint8_t* answer = downloadFile(url, clientUserAgent(CLIENT_NAME), &size, nullptr);
    const SavedCopy ours = {nvsState.len > 0, nvsState.accuracy, nvsState.savedEpoch};
    char why[80];
    if (!answer) {
        const SavedCopy none = {};
        if (describeChoice(ours, none, chooseCopy(ours, none), why, sizeof(why))) {
            logf(LOG_INFO, "[bsec] state: %s", why);
        }
        return;
    }
    char text[1024];
    const size_t n = size > 0 && (size_t)size < sizeof(text) ? (size_t)size : sizeof(text) - 1;
    memcpy(text, answer, n);
    text[n] = '\0';
    free(answer);

    BsecState theirs = {};
    if (!parseBme688Calibration(text, theirs.blob, sizeof(theirs.blob), theirs.len,
                                theirs.accuracy, theirs.savedEpoch)) {
        logf(LOG_WARNING, "[bsec] state: %s selected (server state unreadable)",
             ours.present ? "NVS" : "none");
        return;
    }
    const SavedCopy server = {true, theirs.accuracy, theirs.savedEpoch};
    const CopyChoice choice = chooseCopy(ours, server);
    if (describeChoice(ours, server, choice, why, sizeof(why))) {
        logf(choice.takeServer ? LOG_NOTICE : LOG_INFO, "[bsec] state: %s", why);
    }
    if (choice.takeServer) bsecRunner.restartWith(theirs);
}

// The readings come from the room itself, so there is nothing to advance.
static void advanceSimulation(uint32_t) {}
static void logSensorBanner() {
    logf(LOG_INFO, "sensors up; PM fan SET line driven high on IO%u", (unsigned)kPmSetPin);
}
static const bool kMockSensors = false;
#endif

// ─── Everything below is implementation-agnostic ──────────────────────────

static const uint32_t kSampleIntervalMs = 5000;
static const uint32_t kReportIntervalMs = 60000;

static SensorSuite sensors(wallClock, shtc3Impl, scd41Impl, pmImpl, bmeImpl);

static ClientConfig config;
static char     readingsURL[300];    // the server's /readings; empty disables posting
static uint32_t lastSampleMs = 0;
static uint32_t lastReportMs = 0;
static char     json[FileBacklog::kMaxDoc];
static char     clientJson[768];
// BSEC's state as base64 is about 380 bytes of calibration block.
static char     calibration[400];
static char     withCalibration[FileBacklog::kMaxDoc + 400];
static char     body[FileBacklog::kMaxDoc + 400 + 768 + 32];
static char     ipText[16];

// Readings the server did not take, sent again once it answers. The dock has
// no card, so they live in PSRAM: about 2,400 readings, 40 hours. A power cut
// while the server is down loses them.
static IBacklog*      backlog = nullptr;
static const size_t   kBacklogBytes = 1024 * 1024;
// Sent after each live reading, so a long backlog does not hold up a sample.
static const uint32_t kBacklogPerPass = 5;
static char heldJson[FileBacklog::kMaxDoc];

class ReadingsPoster : public IPoster {
public:
    int post(const char* doc) override {
        return postJson(readingsURL, clientUserAgent(CLIENT_NAME), doc);
    }
};
static ReadingsPoster readingsPoster;

static void openBacklog() {
    uint8_t* mem = (uint8_t*)ps_malloc(kBacklogBytes);
    if (mem) {
        static RingBacklog inPsram(mem, kBacklogBytes, "psram");
        backlog = &inPsram;
        logf(LOG_INFO, "readings the server misses wait in %s; %u held", backlog->where(),
             (unsigned)backlog->count());
    } else {
        log(LOG_WARNING, "no room to hold readings the server misses; they are lost");
    }
}

// UTC seconds, or 0 until NTP answers: the dock has no clock of its own.
static uint32_t epochNow() {
    return timeStatus() != timeNotSet ? (uint32_t)now() : 0;
}

// Mains power and no schedule to keep, so there is nothing to do but wait
// for the network to come back.
static void connectNetworkForever() {
    while (configureWiFi(config.wifiSSID, config.wifiPass, config.wifiRetries) != ESP_OK) {
        log(LOG_ERROR, "wifi connect timeout; trying again in 30 s");
        delay(30000);
    }
    logf(LOG_INFO, "wifi: %s, %d dBm", WiFi.localIP().toString().c_str(), (int)WiFi.RSSI());
}

static ClientStatus clientStatus(uint32_t nowMs) {
    strncpy(ipText, WiFi.localIP().toString().c_str(), sizeof(ipText) - 1);
    ClientStatus s = {};
    s.board = CLIENT_NAME;
    s.version = CLIENT_VERSION;
    s.ip = ipText;
    s.rssi = WiFi.RSSI();
    s.uptimeS = nowMs / 1000;
    s.heapFree = ESP.getFreeHeap();
    s.heapSize = ESP.getHeapSize();
    s.psramFree = ESP.getFreePsram();
    s.psramSize = ESP.getPsramSize();
    s.mockSensors = kMockSensors;
    s.shtc3 = sensors.shtc3Present();
    s.scd41 = sensors.scd41Present();
    s.pm = sensors.pmPresent();
    s.bme688 = sensors.bme688Present();
    s.backlogHeld = backlog ? backlog->count() : 0;
    s.backlogStore = backlog ? backlog->where() : "";
    fillBsecStatus(s);
    return s;
}

static void postReadings(const Readings& r, uint32_t nowMs) {
    if (!readingsToJson(r, CLIENT_NAME, json, sizeof(json))) {
        log(LOG_WARNING, "readings document too large to post");
        return;
    }
    // Only the live POST carries the calibration block: a held reading goes
    // out later, when this state is no longer the current one.
    const char* live = json;
    if (calibrationBlock(calibration, sizeof(calibration)) &&
        withMember(json, "calibration", calibration, withCalibration, sizeof(withCalibration))) {
        live = withCalibration;
    }
    if (!clientStatusJson(clientStatus(nowMs), clientJson, sizeof(clientJson)) ||
        !withClientStatus(live, clientJson, body, sizeof(body))) {
        log(LOG_WARNING, "readings document too large to post");
        return;
    }
    log(LOG_DEBUG, body);
    if (!readingsURL[0]) return;
    int code = postJson(readingsURL, clientUserAgent(CLIENT_NAME), body);
    switch (postResult(code)) {
        case POSTED:
            logf(LOG_INFO, "posted readings (%d)", code);
            if (backlog && backlog->count()) {
                uint32_t sent = drainBacklog(*backlog, readingsPoster, kBacklogPerPass, heldJson,
                                             sizeof(heldJson));
                logf(LOG_INFO, "sent %u held readings; %u still held", (unsigned)sent,
                     (unsigned)backlog->count());
            }
            restoreFromServer();
            break;
        case REFUSED:
            logf(LOG_ERROR, "the server refused the readings (%d)", code);
            break;
        case TRY_LATER:
            // The held copy leaves out the client object: the dock's state
            // then is not news when it finally arrives.
            if (backlog) backlog->push(json, strlen(json));
            logf(LOG_ERROR, "posting readings failed (%d); %u held", code,
                 (unsigned)(backlog ? backlog->count() : 0));
            break;
    }
}

static bool sensorsRunning[4] = {false, false, false, false};

// Logs each sensor that has stopped, or started, since the last call.
static void logSensorChanges() {
    static const char* const names[4] = {"shtc3", "scd41", "pmsa003i", "bme688"};
    const bool running[4] = {sensors.shtc3Present(), sensors.scd41Present(),
                             sensors.pmPresent(), sensors.bme688Present()};
    for (int i = 0; i < 4; ++i) {
        if (running[i] == sensorsRunning[i]) continue;
        sensorsRunning[i] = running[i];
        logf(running[i] ? LOG_NOTICE : LOG_WARNING, "sensor %s %s", names[i],
             running[i] ? "running" : "stopped; starting it again");
    }
}

static void sampleSensors(uint32_t nowMs) {
    uint32_t epoch = epochNow();
    advanceSimulation(epoch);
    sensors.restartFailed();
    Readings r = sensors.sample(epoch);
    logSensorChanges();

    if (nowMs - lastReportMs < kReportIntervalMs) return;
    lastReportMs = nowMs;
    postReadings(r, nowMs);
}

void setup() {
    Serial.begin(115200);
    delay(200);
    logf(LOG_NOTICE, "##### %s boot #####", CLIENT_NAME);
    logf(LOG_NOTICE, "Client version: %s", CLIENT_VERSION);

    config = loadConfig(builtInSettings());
    connectNetworkForever();
    configureTime(config.ntpHost, config.ntpTimezone);
    if (config.mqttEnabled && mqttSettingsAreSet(config.mqttBroker)) {
        configureMQTT(config.mqttBroker, config.mqttPort, config.mqttTopic, config.mqttClientID,
                      config.mqttRetries);
    }

    if (urlOrigin(config.serverURL, readingsURL, sizeof(readingsURL) - 10)) {
        snprintf(calibrationURL, sizeof(calibrationURL), "%s/calibration", readingsURL);
        strcat(readingsURL, "/readings");
        logf(LOG_INFO, "posting readings to %s", readingsURL);
    } else {
        log(LOG_WARNING, "the server URL has no host; readings stay on the serial log");
    }
    openBacklog();

    startI2c();
    advanceSimulation(epochNow());
    // Before the suite, which asks the BSEC side whether the BME688 is running.
    startBsec();
    if (!sensors.begin()) {
        logf(LOG_WARNING, "sensor start incomplete: shtc3=%d scd41=%d pm=%d bme688=%d",
             sensors.shtc3Present(), sensors.scd41Present(),
             sensors.pmPresent(), sensors.bme688Present());
    }
    logSensorChanges();
    logSensorBanner();
}

void loop() {
    events();   // ezTime: periodic NTP re-sync
    keepMQTTConnected();
    uint32_t nowMs = millis();
    if (!bootEpoch && timeStatus() != timeNotSet) bootEpoch = (uint32_t)now() - nowMs / 1000;

    if (nowMs - lastSampleMs >= kSampleIntervalMs) {
        lastSampleMs = nowMs;
        sampleSensors(nowMs);
    }
    delay(10);
}
