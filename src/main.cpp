// The display's program.
//
// The Inkplate and nothing else: it fetches the page the server names, draws
// it, and deep-sleeps until the server says to come back. E-paper keeps its
// image without power, so the display wakes only for the next page, or for its
// next sync when that comes first. Every wake posts the display's own state —
// network, memory, panel, fetch counts — to the server's /sensor-readings,
// where the dock's readings also go; the display carries no sensors, so its
// document holds the client object and nothing else. A failed fetch leaves
// the last image on the panel and backs off before the next try.
//
// A freshly written image stays awake until a page proves it, since the
// bootloader takes back an image that is not confirmed.
//
// Two things replace the page with a notice the firmware draws itself: a
// server whose version this display cannot work with, and a server that has
// not answered three fetches in a row. The firmware also draws the splash
// screen: from the start until the first page, and while it writes an update,
// with a progress bar.
#include <Arduino.h>
#include <WiFi.h>

#include "epd.h"
#include "InkplateBoard.h"
#include "backoff.h"
#include "image.h"
#include "log_utils.h"
#include "network_utils.h"
#include "ota.h"
#include "sd_config.h"
#include "settings.h"
#include "sleep_utils.h"
#include "wake.h"
#include "time_utils.h"
#include "user_agent.h"
#include "version.h"

#include "version_compat.h"

#include "display/AfterFetch.h"
#include "display/Notice.h"
#include "display/Splash.h"
#include "display/WakePlan.h"
#include "net/Backlog.h"        // postResult: what an HTTP status means for the sender
#include "net/ClientStatus.h"
#include "net/ResetReason.h"
#include "net/Url.h"

// The settings this image was built with, from src/defaults.cpp. epd declares
// no settings symbols of its own, so this one is the project's.
ClientConfig builtInSettings();

static InkplateBoard inkplateBoard;

static const uint8_t  kRotation = 0;             // landscape, as the board comes: the USB-C port on the right
// Buffer size when the server sends no Content-Length. An eight-grey
// 1280x720 PNG is under 200 KB.
static const int32_t  kDownloadFallbackBytes = 512 * 1024;
// A shorter wait is spent awake: a wake costs a boot and Wi-Fi.
static const uint32_t kShortestSleepS = 10;
static const uint32_t kWifiRetryS = 30;

static ClientConfig config;          // this board's own server URL and wifi
// True until this boot proves a freshly written image works.
static bool     onTrial = false;
static int      trialFailures = 0;

// Three failures in a row is enough to call a new image broken.
static const int kTrialFailureLimit = 3;

// Fetches the server has not answered, in a row. The back-off makes three of
// them about 26 minutes, long enough that a blip never replaces the page.
static const int kUnreachableAfter = 3;

// What outlasts deep sleep. A real start clears it, so the display then
// fetches a page at once and counts from zero.
static RTC_DATA_ATTR WakePlan plan;
static RTC_DATA_ATTR char     nextURL[256];      // from Canary-Next-URL; empty means the server URL
static RTC_DATA_ATTR int      unanswered;
static RTC_DATA_ATTR char     lastPageAt[32];    // when the last page arrived, in RFC 3339, for the unreachable notice
static RTC_DATA_ATTR uint32_t fetchOk;
static RTC_DATA_ATTR uint32_t fetchFailed;
// The last real start, which a wake from deep sleep is not: when, in UTC
// seconds by the server's clock (0 until it has answered), and why.
static RTC_DATA_ATTR uint32_t startedAt;
static RTC_DATA_ATTR int      startReason;

static const char kReadingsPath[] = "/sensor-readings";
static char     readingsURL[300];    // the server's /sensor-readings; empty disables posting
// Room for a next URL of up to 256 characters.
static char     clientJson[768];
static char     body[768 + 96];
static char     ipText[16];

// UTC seconds: the server's clock once it has answered, the RTC's until then.
static uint32_t epochNow() { return (uint32_t)time(nullptr); }

// Deep sleep until `at`, in UTC seconds, which the RTC holds. The ESP32's
// own timer stands behind the RTC's alarm, a little later, so a missed alarm
// costs a late page rather than a display that never wakes.
static void sleepUntil(uint32_t at) {
    const uint32_t seconds = secondsUntil(at, epochNow());
    enableWakeOnTimer(seconds + seconds / 20 + 60);
    logf(LOG_INFO, "sleeping %u s", seconds);
    sleep((time_t)at);
}

// A freshly written image waits awake for the network, since proving itself
// is all it may do. Any other wake sleeps between tries.
static void connectNetworkOrSleep() {
    while (connectNetwork(config) != ESP_OK) {
        logf(LOG_ERROR, "wifi connect timeout; trying again in %u s", kWifiRetryS);
        if (!onTrial) sleepUntil(epochNow() + kWifiRetryS);
        delay(kWifiRetryS * 1000);
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
    uint32_t wait = pageFailed(plan, epochNow(), computeBackoffSeconds);
    logf(LOG_ERROR, "%s (back-off step %d): next try in %u s", why, plan.step, wait);
    abandonTrialAfterRepeatedFailures(why);
}

// The fetch afterFetch() is working on. Its steps are plain functions, so
// they find the page here.
static PageFetch*  fetched = nullptr;
static const char* drawError = nullptr;

// The image is freed as soon as it is drawn, or skipped, so the memory is
// there for an update's download.
static void releaseImage() {
    free(fetched->data);
    fetched->data = nullptr;
}

static bool drawFetchedPage() {
    // Nothing over the page: this board has no battery to report.
    const bool drawn = drawPage(*fetched, nullptr, 0, nullptr, &drawError);
    releaseImage();
    if (drawn) noticeReplaced();
    return drawn;
}

static bool drawVersionNotice() {
    releaseImage();
    const PageResponse& rsp = fetched->response;
    const bool offered = updateOffered(CLIENT_VERSION, rsp.firmwareVersion, rsp.firmwareURL,
                                       otaRejectedVersion());
    return showVersionNotice(CLIENT_VERSION, rsp.serverVersion, offered);
}

static void fetchSucceeded() {
    ++fetchOk;
    trialFailures = 0;
    unanswered = 0;
    pageFetched(plan, epochNow(), fetched->response.nextRefreshSeconds,
                config.defaultRefreshSeconds);
    logf(LOG_INFO, "next refresh in %u s",
         fetched->response.nextRefreshSeconds ? fetched->response.nextRefreshSeconds
                                              : config.defaultRefreshSeconds);
    strlcpy(lastPageAt, nowTzFmt().c_str(), sizeof(lastPageAt));

    // Something is on the panel, so a freshly written image has proved itself.
    // Confirming it also frees the idle slot for the next update.
    if (onTrial) {
        otaConfirm();
        onTrial = false;
    }
}

static void takeOffer(const PageResponse& rsp) {
    beginUpdateProgress(rsp.firmwareVersion);
    // Mains power, so no battery to wait for.
    takeOfferedUpdate(rsp, clientUserAgent(epdBoard().deviceName()), 100, 0, showUpdateProgress);
    endUpdateProgress();
}

static void takeFetchedOffer() { takeOffer(fetched->response); }

static const AfterFetchSteps kAfterFetch = {drawFetchedPage, drawVersionNotice,
                                            fetchSucceeded, takeFetchedOffer};

static void fetchAndDraw() {
    if (WiFi.status() != WL_CONNECTED) {
        log(LOG_WARNING, "wifi down; reconnecting");
        configureWiFi(config.wifiSSID, config.wifiPass, config.wifiRetries);
    }

    // One try each wake: a failure backs off to a later one.
    const char* errMsg = nullptr;
    PageFetch page = {};
    page.length = kDownloadFallbackBytes;
    const char* url = nextURL[0] ? nextURL : config.serverURL;

    if (!fetchPage(url, clientUserAgent(epdBoard().deviceName()), 0, &page, &errMsg)) {
        if (++unanswered >= kUnreachableAfter) showUnreachableNotice(lastPageAt);
        failedFetch(errMsg);
        return;
    }
    if (page.response.nextURL[0])
        snprintf(nextURL, sizeof(nextURL), "%s", page.response.nextURL);

    // A server whose version cannot be read is not judged: that is every
    // development build.
    const bool compatible =
        versionsMatch(CLIENT_VERSION, page.response.serverVersion) != VERSIONS_DIFFER;
    if (!compatible)
        logf(LOG_WARNING, "server runs %s; this display runs %s", page.response.serverVersion,
             CLIENT_VERSION);

    fetched = &page;
    drawError = nullptr;
    const bool drawn = afterFetch(compatible, kAfterFetch);
    free(page.data);   // null unless the draw never ran
    fetched = nullptr;
    if (!drawn) failedFetch(drawError);
}

static ClientStatus clientStatus() {
    const uint32_t now = epochNow();
    strncpy(ipText, WiFi.localIP().toString().c_str(), sizeof(ipText) - 1);
    ClientStatus s = {};
    s.role = ClientStatus::Role::Display;
    s.board = epdBoard().deviceName();
    s.version = CLIENT_VERSION;
    s.ip = ipText;
    s.rssi = WiFi.RSSI();
    s.uptimeS = startedAt ? now - startedAt : millis() / 1000;
    s.reset = resetReasonName(startReason);
    s.heapFree = ESP.getFreeHeap();
    s.heapSize = ESP.getHeapSize();
    s.psramFree = ESP.getFreePsram();
    s.psramSize = ESP.getPsramSize();
    s.panelTempC = epdBoard().readPanelTemperature();
    s.width = epdBoard().getWidth();
    s.height = epdBoard().getHeight();
    s.rotation = kRotation;
    s.nextUrl = nextURL[0] ? nextURL : config.serverURL;
    s.nextInS = secondsUntil(plan.pageAt, now);
    s.backoffStep = plan.step;
    s.fetchOk = fetchOk;
    s.fetchFailed = fetchFailed;
    return s;
}

// The display's own state, with no readings round it, and what the server
// answers: the next sync, and any update on offer. Nothing is held for a
// retry: the next wake's report says the same things, fresher.
static PageResponse postStatus() {
    PageResponse rsp = {};
    char doc[64];
    snprintf(doc, sizeof(doc), "{\"ts\":%lu,\"device\":\"%s\"}", (unsigned long)epochNow(), CLIENT_NAME);
    if (!clientStatusJson(clientStatus(), clientJson, sizeof(clientJson)) ||
        !withClientStatus(doc, clientJson, body, sizeof(body))) {
        log(LOG_WARNING, "status document too large to post");
        return rsp;
    }
    log(LOG_DEBUG, body);
    if (!readingsURL[0]) return rsp;
    int code = postJson(readingsURL, clientUserAgent(epdBoard().deviceName()), body, &rsp);
    switch (postResult(code)) {
        case POSTED:    logf(LOG_INFO, "posted status (%d)", code); break;
        case REFUSED:   logf(LOG_ERROR, "the server refused the status (%d)", code); break;
        case TRY_LATER: logf(LOG_ERROR, "posting status failed (%d)", code); break;
    }
    return rsp;
}

// The page when it is due, then the display's state, which is its sync. A wake
// that fetched a page has dealt with the update on offer already.
static void wake() {
    const bool page = pageDue(plan, epochNow());
    if (page) fetchAndDraw();

    const PageResponse rsp = postStatus();
    keepServerTime(rsp);
    synced(plan, epochNow(), rsp.nextSensorPollSeconds);
    if (!startedAt && rsp.serverEpoch) startedAt = rsp.serverEpoch - millis() / 1000;
    if (!page) takeOffer(rsp);
}

void setup() {
    epdBegin(inkplateBoard);
    startBoard(kRotation);

    const bool woke = esp_reset_reason() == ESP_RST_DEEPSLEEP;
    if (woke) {
        logf(LOG_NOTICE, "##### %s wake #####", epdBoard().deviceName());
    } else {
        startReason = esp_reset_reason();
        logf(LOG_NOTICE, "##### %s boot #####", epdBoard().deviceName());
        logf(LOG_NOTICE, "Client version: %s", CLIENT_VERSION);
        logf(LOG_INFO, "User-Agent: %s", clientUserAgent(epdBoard().deviceName()));
    }
    logWakeReason();   // also clears the RTC alarm, which would wake the next sleep at once

    onTrial = otaTrialPending();
    if (onTrial) logf(LOG_NOTICE, "trial boot of %s", CLIENT_VERSION);
    // A wake from deep sleep keeps the page it went to sleep on.
    if (!woke) showSplash();
    config = loadConfig(builtInSettings());
    applySdConfig(&config);

    connectNetworkOrSleep();
    if (urlOrigin(config.serverURL, readingsURL, sizeof(readingsURL) - sizeof(kReadingsPath))) {
        strcat(readingsURL, kReadingsPath);
        logf(LOG_INFO, "posting status to %s", readingsURL);
    } else {
        log(LOG_WARNING, "the server URL has no host; status stays on the serial log");
    }
}

void loop() {
    const uint32_t now = epochNow();
    if (wakeDue(plan, now)) {
        wake();
        return;
    }
    if (!onTrial && secondsUntil(nextWake(plan), now) >= kShortestSleepS) sleepUntil(nextWake(plan));

    keepMQTTConnected();
    delay(10);
}
