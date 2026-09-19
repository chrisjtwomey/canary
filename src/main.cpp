// The head's loop.
//
// The Inkplate and nothing else: it fetches the page the server names,
// draws it, and waits the seconds the server sends before fetching again.
// Mains powered through the dock, so nothing sleeps. Once a minute it posts
// its own state — network, memory, panel, fetch counts — to the server's
// /readings, where the dock's readings also go; the head carries no
// sensors, so its document holds the client object and nothing else. A
// failed fetch leaves the last image on the panel and backs off before the
// next try.
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

#include "net/Backlog.h"        // postResult: what an HTTP status means for the sender
#include "net/ClientStatus.h"
#include "net/RefreshTimer.h"
#include "net/Url.h"

// The settings this image was built with, from src/defaults.cpp. epd declares
// no settings symbols of its own, so this one is the project's.
ClientConfig builtInSettings();

static InkplateBoard inkplateBoard;

static const uint8_t  kRotation = 0;             // landscape, as the board comes: the USB-C port on the right
static const uint32_t kReportIntervalMs = 60000;
// Buffer size when the server sends no Content-Length. An eight-grey
// 1280x720 PNG is under 200 KB.
static const int32_t  kDownloadFallbackBytes = 512 * 1024;

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
static uint32_t lastReportMs = 0;
static uint32_t fetchOk = 0;
static uint32_t fetchFailed = 0;
// Room for a next URL of up to 256 characters.
static char     clientJson[768];
static char     body[768 + 96];
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
    s.nextUrl = nextURL[0] ? nextURL : config.serverURL;
    s.nextInS = refresh.secondsUntilDue(nowMs);
    s.backoffStep = refresh.step();
    s.fetchOk = fetchOk;
    s.fetchFailed = fetchFailed;
    s.backlogStore = "";
    return s;
}

// The head's own state, with no readings round it. Nothing is held for a
// retry: the next minute's report says the same things, fresher.
static void postStatus(uint32_t nowMs) {
    char doc[64];
    snprintf(doc, sizeof(doc), "{\"ts\":%lu,\"device\":\"%s\"}", (unsigned long)epochNow(), CLIENT_NAME);
    if (!clientStatusJson(clientStatus(nowMs), clientJson, sizeof(clientJson)) ||
        !withClientStatus(doc, clientJson, body, sizeof(body))) {
        log(LOG_WARNING, "status document too large to post");
        return;
    }
    log(LOG_DEBUG, body);
    if (!readingsURL[0]) return;
    int code = postJson(readingsURL, clientUserAgent(epdBoard().deviceName()), body);
    switch (postResult(code)) {
        case POSTED:    logf(LOG_INFO, "posted status (%d)", code); break;
        case REFUSED:   logf(LOG_ERROR, "the server refused the status (%d)", code); break;
        case TRY_LATER: logf(LOG_ERROR, "posting status failed (%d)", code); break;
    }
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
        logf(LOG_INFO, "posting status to %s", readingsURL);
    } else {
        log(LOG_WARNING, "the server URL has no host; status stays on the serial log");
    }
}

void loop() {
    events();   // ezTime: periodic NTP re-sync
    keepMQTTConnected();
    uint32_t nowMs = millis();

    if (refresh.due(nowMs)) fetchAndDraw();

    if (nowMs - lastReportMs >= kReportIntervalMs) {
        lastReportMs = nowMs;
        postStatus(nowMs);
    }
    delay(10);
}
