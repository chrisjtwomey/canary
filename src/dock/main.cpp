// The dock's loop.
//
// A TinyS3 with the four sensors on their own regulator. Mains powered, so
// nothing sleeps: it connects once, samples every minute to notice a sensor
// that stops, and on each of the server's slots takes a reading and queues
// it, with its own status beside it. The server names the slots, every five
// minutes and every half hour overnight, and the time: the dock has no clock
// and asks for none elsewhere. The queue is in PSRAM, and each pass of the
// loop posts the oldest hundred of it to the server's /readings as one
// batch. BSEC's state goes to /calibration whenever BSEC saves a new copy.
// The server offers the image its own version calls for on any answer, and
// the dock takes it once its queue is empty, then keeps it only if it posts.
// The head fetches the pages the server renders from the readings and knows
// nothing about any of this. The status LED under the head's right end
// pulses slowly while the dock works, and gives three flashes and a steady
// glow while anything is wrong. The PM module's fan, the dock's largest
// load, runs only for the window before each post.
#include <Arduino.h>
#include <WiFi.h>
#include <Wire.h>
#include <ezTime.h>

#include "log_utils.h"
#include "network_utils.h"
#include "ota.h"
#include "ota_offer.h"
#include "settings.h"
#include "time_utils.h"
#include "user_agent.h"
#include "version.h"

#include "dock/FanWindow.h"
#include "dock/PostTimer.h"
#include "dock/StatusLed.h"
#include "net/Backlog.h"
#include "net/Calibration.h"
#include "net/ClientStatus.h"
#include "net/ServerClock.h"
#include "net/Stamp.h"
#include "net/Url.h"
#include "sensors/II2cBus.h"
#include "sensors/IClock.h"
#include "sensors/Readings.h"
#include "sensors/SensorSuite.h"

// The settings this image was built with, from src/defaults.cpp.
ClientConfig builtInSettings();

// hardware/README.md, "Wires at the TinyS3", which names the same lines by
// their header pin: SCL on J4.5, SDA on J4.6, SET on J4.7, the LED on J4.8.
static const uint8_t kSdaPin = 8;
static const uint8_t kSclPin = 9;
static const uint8_t kPmSetPin = 7;
// Through a 1 kOhm resistor to the LED's anode, so a duty of 0 is dark.
static const uint8_t kLedPin = 6;

static ArduinoClock wallClock;

// The server's time, from the last response that carried it. Until the
// first, a reading is queued with its uptime and stamped later, and the BSEC
// task saves no time with its state. The BSEC task reads it too, so every
// use takes the lock.
static ServerClock serverClock;
static portMUX_TYPE clockLock = portMUX_INITIALIZER_UNLOCKED;
// UTC seconds at boot, from the first response; 0 until then.
static uint32_t bootEpoch = 0;

static uint32_t epochAt(uint32_t ms) {
    portENTER_CRITICAL(&clockLock);
    const uint32_t epoch = serverClock.epochAt(ms);
    portEXIT_CRITICAL(&clockLock);
    return epoch;
}
static uint32_t syncedEpoch() { return epochAt(millis()); }

static char calibrationURL[310];   // the server's /calibration; empty when there is no server
static char aboutURL[310];         // the server's /about, asked for the time until it is known

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
// it over the three hours before now; walking from epoch 0 would take
// minutes, so it waits for the server's time.
static void advanceSimulation(uint32_t epoch) {
    static bool started = false;
    if (!epoch) return;
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
static size_t calibrationBlock(char*, size_t, uint32_t&) { return 0; }
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

// The state as of BSEC's last copy, as the calibration block, and when BSEC
// saved it.
static size_t calibrationBlock(char* buf, size_t len, uint32_t& savedEpoch) {
    BsecState state;
    if (!bsecRunner.current(state)) return 0;
    savedEpoch = state.savedEpoch;
    return calibrationJson(state.blob, state.len, state.accuracy, state.savedEpoch, buf, len);
}

// Asked once a boot, after the server has taken a batch of readings, so a failed
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

// Often enough to notice a sensor that stops within a few minutes. The
// reading a post carries is taken fresh at its slot.
static const uint32_t kSampleIntervalMs = 60000;
// Until the server names a slot: five minutes.
static const uint32_t kFirstIntervalMs = 300000;

// Wi-Fi needs 80 MHz, and below it the APB clock follows the processor,
// which would move the LED's PWM frequency and the serial baud rate. So 80
// is both the floor and the choice: the bench board ran warm at 240.
static const uint32_t kCpuMhz = 80;

// The fan settles in 30 s (Pmsa003iDriver::kWarmupMs), Plantower's figure;
// the margin covers a slot the loop reaches a little late. Each reading
// records how long the fan had actually run, so the database can show
// whether 30 s is enough.
static const uint32_t kFanWarmupMs = 30000;
static const uint32_t kFanMarginMs = 5000;
static FanWindow fanWindow(kFanWarmupMs + kFanMarginMs);
static bool fanRunning = true;    // the module's own pull-up holds it on until told otherwise
static uint32_t fanOnSinceMs = 0;

static PostTimer postTimer(kFirstIntervalMs);

static SensorSuite sensors(wallClock, shtc3Impl, scd41Impl, pmImpl, bmeImpl);

// One of the ESP32-S3's eight LEDC channels. Nothing else on this board uses
// one, so the first will do.
static const uint8_t kLedChannel = 0;
static StatusLed statusLed;

// Set once setup() has connected and started the sensors.
static volatile bool running = false;
// Set by a post the server would not take, and by having nowhere to post.
static volatile bool postFailed = false;
// Set while a new image is written, with how much of it, in thousandths.
static volatile bool     updating = false;
static volatile uint16_t updatePermille = 0;

// Trouble is anything that stops a reading reaching the server.
static StatusLed::State ledState() {
    if (updating) return StatusLed::UPDATING;
    if (!running) return StatusLed::STARTING;
    const bool well = WiFi.status() == WL_CONNECTED && !postFailed &&
                      sensors.shtc3Present() && sensors.scd41Present() &&
                      sensors.pmPresent() && sensors.bme688Present();
    return well ? StatusLed::WELL : StatusLed::TROUBLE;
}

// The fast pulse's shortest step lasts about 11 ms, so a 5 ms tick keeps
// every step of every pattern.
static const uint32_t kLedTickMs = 5;
static const uint32_t kLedStackBytes = 2048;

// A task of its own, because setup() blocks for as long as the network takes
// and the starting pattern has to run through it.
static void ledTask(void*) {
    uint16_t written = 0xFFFF;
    for (;;) {
        const uint32_t nowMs = millis();
        statusLed.state(ledState(), nowMs);
        statusLed.progress(updatePermille);
        const uint16_t duty = statusLed.dutyAt(nowMs);
        if (duty != written) {
            written = duty;
            ledcWrite(kLedChannel, duty);
        }
        vTaskDelay(pdMS_TO_TICKS(kLedTickMs));
    }
}

static void startLed() {
    ledcSetup(kLedChannel, StatusLed::kFrequencyHz, StatusLed::kResolutionBits);
    ledcAttachPin(kLedPin, kLedChannel);
    // Core 0: the loop and the BSEC task both run on core 1.
    xTaskCreatePinnedToCore(ledTask, "led", kLedStackBytes, nullptr, 1, nullptr, 0);
}

static ClientConfig config;
static char     readingsURL[300];    // the server's /readings; empty disables posting
static uint32_t lastSampleMs = 0;
static char     json[FileBacklog::kMaxDoc];
static char     clientJson[768];
static char     body[FileBacklog::kMaxDoc + 768 + 32];
static char     ipText[16];

// BSEC's state as base64 is about 380 bytes of calibration block.
static char     calibration[400];
static char     calibrationBody[400 + 64];
// The save time of the copy the server last took; 0 for none this boot.
static uint32_t calibrationSent = 0;

// Every reading waits here until the server takes it. The dock has no card,
// so the queue is in PSRAM: 2 MB, about 1,500 readings, five days at one
// every five minutes. A power cut or a restart empties it.
static IBacklog*      queue = nullptr;
static const size_t   kQueueBytes = 2 * 1024 * 1024;
// One batch per pass of the loop, so a long queue never holds up a sample by
// more than one request.
static const uint32_t kBatchDocs = 100;
static const size_t   kBatchBytes = kBatchDocs * sizeof(body) + 2;
static char*          batch = nullptr;
// Without PSRAM: a queue of a few readings, and one per request.
static uint8_t        fallbackQueue[16 * 1024];
static char           fallbackBatch[sizeof(body) + 2];
static size_t         batchBytes = 0;
// Set when the server could not take a batch; the next reading clears it,
// so the dock asks again once a report period rather than every pass.
static bool           waitForNextReading = false;

// Keeps the headers of the last response that had any, for the clock and
// the schedule.
class ReadingsPoster : public IPoster {
public:
    PageResponse heard = {};
    uint32_t     heardAtMs = 0;

    int post(const char* request) override {
        PageResponse rsp = {};
        const int code = postJson(readingsURL, clientUserAgent(CLIENT_NAME), request, &rsp);
        if (rsp.serverEpoch) {
            heard = rsp;
            heardAtMs = millis();
        }
        return code;
    }
};
static ReadingsPoster readingsPoster;

// One document of the queue at a time, for stamping it.
static char stampIn[sizeof(body)];
static char stampOut[sizeof(body)];

// What a response said about the time, and, for a readings post, about the
// next slot. The first time sets the boot epoch, stamps the readings taken
// before it and sets the clock the log lines show.
static void heardFrom(const PageResponse& rsp, uint32_t atMs, bool schedule) {
    if (!rsp.serverEpoch) return;
    const bool first = !serverClock.known();
    portENTER_CRITICAL(&clockLock);
    serverClock.sync(rsp.serverEpoch, atMs);
    portEXIT_CRITICAL(&clockLock);
    setTime((time_t)rsp.serverEpoch);
    if (schedule && rsp.nextSensorPollSeconds) postTimer.answered(atMs, rsp.nextSensorPollSeconds);
    if (!first) return;
    bootEpoch = epochAt(0);
    const uint32_t stamped = stampQueue(*queue, serverClock, stampIn, sizeof(stampIn), stampOut,
                                        sizeof(stampOut));
    logf(LOG_INFO, "time from the server: %lu; %u readings stamped", (unsigned long)rsp.serverEpoch,
         (unsigned)stamped);
}

// Until the clock is known, GET /about every 30 s. Nothing is posted before:
// a reading must go out with its time.
static const uint32_t kAskForTimeEveryMs = 30000;

static void askForTime(uint32_t nowMs) {
    static bool asked = false;
    static uint32_t askedAtMs = 0;
    if (serverClock.known() || !aboutURL[0]) return;
    if (asked && nowMs - askedAtMs < kAskForTimeEveryMs) return;
    asked = true;
    askedAtMs = nowMs;
    PageResponse rsp = {};
    int32_t size = 2048;
    free(downloadFile(aboutURL, clientUserAgent(CLIENT_NAME), &size, &rsp));
    heardFrom(rsp, millis(), false);
}

static void openQueue() {
    uint8_t* mem = (uint8_t*)ps_malloc(kQueueBytes);
    batch = (char*)ps_malloc(kBatchBytes);
    if (mem && batch) {
        static RingBacklog inPsram(mem, kQueueBytes, "psram");
        queue = &inPsram;
        batchBytes = kBatchBytes;
    } else {
        free(mem);
        free(batch);
        static RingBacklog inRam(fallbackQueue, sizeof(fallbackQueue), "ram");
        queue = &inRam;
        batch = fallbackBatch;
        batchBytes = sizeof(fallbackBatch);
        log(LOG_WARNING, "no PSRAM for the queue; it holds a few readings in RAM");
    }
    logf(LOG_INFO, "readings queue in %s", queue->where());
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
    s.backlogHeld = queue ? queue->count() : 0;
    s.backlogCapacity = queue ? queue->capacity() : 0;
    s.backlogStore = queue ? queue->where() : "";
    fillBsecStatus(s);
    return s;
}

// The document goes into the queue, whatever the network is doing: the
// loop sends it. Before the clock is known it goes in with its uptime.
static void queueReading(Readings& r, uint32_t nowMs) {
    r.pmWarmupS = fanRunning ? (uint16_t)((nowMs - fanOnSinceMs) / 1000) : 0;
    if (!readingsToJson(r, CLIENT_NAME, json, sizeof(json)) ||
        !clientStatusJson(clientStatus(nowMs), clientJson, sizeof(clientJson)) ||
        !withClientStatus(json, clientJson, body, sizeof(body))) {
        log(LOG_WARNING, "readings document too large to queue");
        return;
    }
    log(LOG_DEBUG, body);
    const char* doc = body;
    if (!r.ts) {
        if (!markUnstamped(body, nowMs, stampOut, sizeof(stampOut))) {
            log(LOG_WARNING, "readings document too large to queue");
            return;
        }
        doc = stampOut;
    }
    if (!queue->push(doc, strlen(doc))) log(LOG_WARNING, "readings document not queued");
    waitForNextReading = false;
    if (!readingsURL[0]) postFailed = true;   // nowhere to post is a fault, not a quiet success
}

// Sent only while the server is taking readings, and only when BSEC has saved
// a copy the server does not have. A copy it refuses is not sent again.
static void sendCalibration() {
    if (!calibrationURL[0]) return;
    uint32_t saved = 0;
    if (!calibrationBlock(calibration, sizeof(calibration), saved) || !saved ||
        saved == calibrationSent) {
        return;
    }
    char device[48];
    snprintf(device, sizeof(device), "{\"device\":\"%s\"}", CLIENT_NAME);
    if (!withMember(device, "calibration", calibration, calibrationBody, sizeof(calibrationBody))) {
        return;
    }
    PageResponse rsp = {};
    const int code = postJson(calibrationURL, clientUserAgent(CLIENT_NAME), calibrationBody, &rsp);
    heardFrom(rsp, millis(), false);
    switch (postResult(code)) {
        case POSTED:
            calibrationSent = saved;
            logf(LOG_INFO, "[bsec] state saved at %lu sent (%d)", (unsigned long)saved, code);
            break;
        case REFUSED:
            calibrationSent = saved;
            logf(LOG_ERROR, "[bsec] the server refused the state (%d)", code);
            break;
        case TRY_LATER:
            logf(LOG_WARNING, "[bsec] sending the state failed (%d)", code);
            break;
    }
}

// A freshly written image is on trial until the server takes a batch from
// it. The board is on mains, so failing that three times in a row is the
// image's fault, and the one before it comes back.
static bool     onTrial = false;
static int      trialFailures = 0;
static const int kTrialFailureLimit = 3;

static void trialPosted() {
    trialFailures = 0;
    if (!onTrial) return;
    otaConfirm();   // also frees the idle slot for the next update
    onTrial = false;
}

static void trialFailed(const char* why) {
    if (!onTrial || ++trialFailures < kTrialFailureLimit) return;
    otaRollback(why);   // reboots into the previous image
}

static void updateProgress(int done, int total) {
    if (total > 0) updatePermille = (uint16_t)((int64_t)done * 1000 / total);
}

// The offer a readings response carried, when this board should take it.
// Not while on trial, and not while readings are queued, since a restart
// empties the queue: unless the server is refusing them for this board's
// version, when nothing will drain it and the update is what fixes that.
static void takeOffer(const PageResponse& rsp, bool refusedForVersion) {
    if (onTrial) return;
    if (queue->count() > 0 && !refusedForVersion) return;
    const char* rejected = otaRejectedVersion();
    if (updateRefusedBefore(rsp.firmwareVersion, rejected)) {
        logf(LOG_WARNING, "firmware %s is offered again; this board rolled back from it",
             rsp.firmwareVersion);
        return;
    }
    if (!updateOffered(CLIENT_VERSION, rsp.firmwareVersion, rsp.firmwareURL, rejected)) return;
    if (queue->count() > 0) {
        logf(LOG_WARNING, "taking firmware %s drops %u queued readings the server refuses",
             rsp.firmwareVersion, (unsigned)queue->count());
    }
    updatePermille = 0;
    updating = true;
    applyFirmwareUpdate(rsp.firmwareURL, rsp.firmwareVersion, clientUserAgent(CLIENT_NAME),
                        updateProgress);
    updating = false;   // only reached when nothing was written
}

// One batch of the oldest readings, once the clock is known.
static void sendQueued() {
    if (!readingsURL[0] || waitForNextReading || !serverClock.known() || queue->count() == 0) {
        return;
    }
    const SendResult r = sendBatch(*queue, readingsPoster, kBatchDocs, batch, batchBytes);
    const PageResponse heard = readingsPoster.heard;
    readingsPoster.heard = PageResponse();
    heardFrom(heard, readingsPoster.heardAtMs, true);
    const unsigned left = (unsigned)queue->count();
    if (r.dropped) {
        postFailed = true;
        logf(LOG_ERROR, "the server refused %u readings (%d); %u queued", (unsigned)r.dropped,
             r.status, left);
    }
    if (r.wait) {
        postFailed = true;
        waitForNextReading = true;
        logf(LOG_ERROR, "posting readings failed (%d); %u queued", r.status, left);
        trialFailed("the server took no readings");
        takeOffer(heard, r.status == 409);
        return;
    }
    if (!r.posted) return;
    if (!r.dropped) postFailed = false;
    logf(LOG_INFO, "posted %u reading%s (%d); %u queued", (unsigned)r.posted,
         r.posted == 1 ? "" : "s", r.status, left);
    trialPosted();
    sendCalibration();
    restoreFromServer();
    takeOffer(heard, false);
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

// The suite counts no missed frame while the fan is off, so stopping it does
// not make the module look dead.
static void driveFan(uint32_t nowMs) {
    const bool wanted = fanWindow.shouldRun(postTimer.untilMs(nowMs));
    if (wanted == fanRunning) return;
    fanRunning = wanted;
    if (wanted) fanOnSinceMs = nowMs;
    sensors.setFanEnabled(wanted);
    logf(LOG_INFO, "PM fan %s", wanted ? "on" : "off");
}

static Readings sampleSensors(uint32_t nowMs) {
    lastSampleMs = nowMs;
    const uint32_t epoch = epochAt(nowMs);
    advanceSimulation(epoch);
    sensors.restartFailed();
    Readings r = sensors.sample(epoch);
    logSensorChanges();
    return r;
}

// On a slot, a fresh reading for the queue; between slots, a sample only to
// see that each sensor still answers.
static void sampleWhenDue(uint32_t nowMs) {
    if (postTimer.due(nowMs)) {
        Readings r = sampleSensors(nowMs);
        postTimer.taken(nowMs);
        queueReading(r, nowMs);
    } else if (nowMs - lastSampleMs >= kSampleIntervalMs) {
        sampleSensors(nowMs);
    }
}

void setup() {
    Serial.begin(115200);
    delay(200);
    logf(LOG_NOTICE, "##### %s boot #####", CLIENT_NAME);
    logf(LOG_NOTICE, "Client version: %s", CLIENT_VERSION);
    if (setCpuFrequencyMhz(kCpuMhz)) {
        logf(LOG_INFO, "processor at %u MHz", (unsigned)kCpuMhz);
    } else {
        logf(LOG_WARNING, "processor stays at %u MHz", (unsigned)getCpuFrequencyMhz());
    }

    startLed();
    onTrial = otaTrialPending();
    if (onTrial) logf(LOG_NOTICE, "trial boot of %s", CLIENT_VERSION);
    config = loadConfig(builtInSettings());
    connectNetworkForever();
    setInterval(0);   // ezTime: no NTP; the log's clock is set from the server
    if (config.mqttEnabled && mqttSettingsAreSet(config.mqttBroker)) {
        // The head connects as the config's mqttClientID; a second board with the
        // same id would knock it off the broker, so the dock connects as itself.
        configureMQTT(config.mqttBroker, config.mqttPort, config.mqttTopic, CLIENT_NAME, config.mqttRetries);
    }

    if (urlOrigin(config.serverURL, readingsURL, sizeof(readingsURL) - 10)) {
        snprintf(calibrationURL, sizeof(calibrationURL), "%s/calibration", readingsURL);
        snprintf(aboutURL, sizeof(aboutURL), "%s/about", readingsURL);
        strcat(readingsURL, "/readings");
        logf(LOG_INFO, "posting readings to %s", readingsURL);
    } else {
        log(LOG_WARNING, "the server URL has no host; readings stay on the serial log");
    }
    openQueue();

    startI2c();
    // Before the suite, which asks the BSEC side whether the BME688 is running.
    startBsec();
    if (!sensors.begin()) {
        logf(LOG_WARNING, "sensor start incomplete: shtc3=%d scd41=%d pm=%d bme688=%d",
             sensors.shtc3Present(), sensors.scd41Present(),
             sensors.pmPresent(), sensors.bme688Present());
    }
    logSensorChanges();
    logSensorBanner();
    // The first reading as soon as the fan has warmed up; the server's
    // answer to it puts the dock on the slots.
    postTimer.postAt(millis(), fanWindow.leadMs());
    logf(LOG_INFO, "PM fan runs for %u s before each reading", (unsigned)(fanWindow.leadMs() / 1000));
    running = true;
}

void loop() {
    keepMQTTConnected();
    const uint32_t nowMs = millis();
    askForTime(nowMs);
    driveFan(nowMs);
    sampleWhenDue(nowMs);
    sendQueued();
    delay(10);
}
