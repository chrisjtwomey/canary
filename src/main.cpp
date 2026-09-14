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

#include "net/Backlog.h"
#include "net/Calibration.h"
#include "net/ClientStatus.h"
#include "net/RefreshTimer.h"
#include "net/Url.h"
#include "sensors/II2cBus.h"
#include "sensors/IClock.h"
#include "sensors/Readings.h"
#include "sensors/SensorSuite.h"

// The settings this image was built with, from src/defaults.cpp. epd declares
// no settings symbols of its own, so this one is the project's.
ClientConfig builtInSettings();

static InkplateBoard inkplateBoard;
static ArduinoClock  wallClock;

// UTC seconds at boot, once NTP has answered; 0 until then. The loop sets it
// once, and the BSEC task reads it to stamp the state it saves.
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
static void logSensorBanner() {
    log(LOG_INFO, "mock sensors up; PM fan warming up for 30 s");
}
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
static Bme688Driver   bmeDriver(i2cBus, wallClock);
static Pmsa003iDriver pmImpl(i2cBus, wallClock, setPmFanLine);

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

// Above the loop's priority, so a page download or a draw cannot make a
// sample late. Wire locks each transaction, so the task and the loop share
// the bus without a lock of their own.
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
    uint8_t* answer = downloadFile(url, clientUserAgent(epdBoard().deviceName()), &size, nullptr);
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
        logf(LOG_WARNING, "[bsec] state: %s selected (server state unreadable)", ours.present ? "NVS" : "none");
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
    log(LOG_INFO, "sensors up; PM fan SET line driven high on expander P1_3");
}
static const bool kMockSensors = false;
#endif

// ─── Everything below is implementation-agnostic ──────────────────────────

static const uint8_t  kRotation = 2;             // landscape, turned 180° so the USB-C port is on the left
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
static char     json[FileBacklog::kMaxDoc];
// Room for a next URL of up to 256 characters.
static char     clientJson[768];
// BSEC's state as base64 is about 380 bytes of calibration block.
static char     calibration[400];
static char     withCalibration[FileBacklog::kMaxDoc + 400];
static char     body[FileBacklog::kMaxDoc + 400 + 768 + 32];
static char     ipText[16];

// Readings the server did not take, sent again once it answers.
static IBacklog* backlog = nullptr;
// PSRAM for them when there is no card: about 2,400 readings, 40 hours.
static const size_t   kBacklogBytes = 1024 * 1024;
// Sent after each live reading, so a long backlog does not hold up the page.
static const uint32_t kBacklogPerPass = 5;
static char heldJson[FileBacklog::kMaxDoc];

class ReadingsPoster : public IPoster {
public:
    int post(const char* doc) override {
        return postJson(readingsURL, clientUserAgent(epdBoard().deviceName()), doc);
    }
};
static ReadingsPoster readingsPoster;

#if defined(USE_SDCARD)
// The board's SD card, a whole file at a time.
class BoardFiles : public IFileStore {
public:
    bool write(const char* path, const uint8_t* data, size_t len) override {
        return epdBoard().sdWriteFile(path, data, len);
    }
    size_t read(const char* path, uint8_t* buf, size_t maxLen) override {
        return epdBoard().sdReadFile(path, buf, maxLen);
    }
};
#endif

// The card when there is one, so held readings survive a restart; PSRAM when
// there is not, where a power cut while the server is down loses them.
static void openBacklog() {
#if defined(USE_SDCARD)
    static BoardFiles card;
    char* work = epdBoard().sdCardInit() ? (char*)ps_malloc(FileBacklog::kWorkBytes) : nullptr;
    if (work) {
        static FileBacklog onCard(card, work, FileBacklog::kWorkBytes);
        onCard.load();
        backlog = &onCard;
    }
#endif
    if (!backlog) {
        uint8_t* mem = (uint8_t*)ps_malloc(kBacklogBytes);
        if (mem) {
            static RingBacklog inPsram(mem, kBacklogBytes, "psram");
            backlog = &inPsram;
        }
    }
    if (backlog) {
        logf(LOG_INFO, "readings the server misses wait in %s; %u held", backlog->where(),
             (unsigned)backlog->count());
    } else {
        log(LOG_WARNING, "no room to hold readings the server misses; they are lost");
    }
}

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
    int code = postJson(readingsURL, clientUserAgent(epdBoard().deviceName()), body);
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
            // The held copy leaves out the client object: the board's state
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
    epdBegin(inkplateBoard);
    startBoard(kRotation);
    // A sensor that drops off the bus would otherwise slow every sample.
    Wire.setTimeOut(ArduinoI2cBus::kTimeoutMs);

    logf(LOG_NOTICE, "##### %s boot #####", epdBoard().deviceName());
    logf(LOG_NOTICE, "Client version: %s", CLIENT_VERSION);
    logf(LOG_INFO, "User-Agent: %s", clientUserAgent(epdBoard().deviceName()));

    onTrial = otaTrialPending();
    if (onTrial) logf(LOG_NOTICE, "trial boot of %s", CLIENT_VERSION);
    config = loadConfig(builtInSettings());
    applySdConfig(&config);

    connectNetworkForever();
    if (urlOrigin(config.serverURL, readingsURL, sizeof(readingsURL) - 10)) {
        snprintf(calibrationURL, sizeof(calibrationURL), "%s/calibration", readingsURL);
        strcat(readingsURL, "/readings");
        logf(LOG_INFO, "posting readings to %s", readingsURL);
    } else {
        log(LOG_WARNING, "the server URL has no host; readings stay on the serial log");
    }
    openBacklog();

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
    uint32_t nowMs = millis();
    if (!bootEpoch && timeStatus() != timeNotSet) bootEpoch = (uint32_t)now() - nowMs / 1000;

    if (refresh.due(nowMs)) fetchAndDraw();

    if (nowMs - lastSampleMs >= kSampleIntervalMs) {
        lastSampleMs = nowMs;
        sampleSensors(nowMs);
    }
    delay(10);
}
