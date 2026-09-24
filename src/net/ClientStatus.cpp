#include "net/ClientStatus.h"

#include <cstdarg>
#include <cstdio>
#include <cstring>

#include "net/BoardSettings.h"

static const char* b(bool v) { return v ? "true" : "false"; }

// Appends to buf, which holds n characters. Returns the new length, or -1
// once anything has not fit.
static int append(char* buf, size_t len, int n, const char* fmt, ...) {
    if (n < 0 || (size_t)n >= len) return -1;
    va_list args;
    va_start(args, fmt);
    const int m = vsnprintf(buf + n, len - (size_t)n, fmt, args);
    va_end(args);
    return m < 0 || (size_t)(n + m) >= len ? -1 : n + m;
}

static int headJson(const ClientStatus& s, char* buf, size_t len, int n) {
    return append(buf, len, n,
        ",\"head\":{\"panel_temp_c\":%d,\"width\":%d,\"height\":%d,\"rotation\":%u"
        ",\"fetch\":{\"next_url\":\"%s\",\"next_in_s\":%lu,\"backoff_step\":%d,\"ok\":%lu,\"failed\":%lu}}",
        s.panelTempC, (int)s.width, (int)s.height, (unsigned)s.rotation,
        s.nextUrl ? s.nextUrl : "", (unsigned long)s.nextInS, s.backoffStep,
        (unsigned long)s.fetchOk, (unsigned long)s.fetchFailed);
}

static int dockJson(const ClientStatus& s, char* buf, size_t len, int n) {
    char refused[kRefusedJsonBytes];
    if (!refusedJson(s.settingsRefused, refused, sizeof(refused))) return -1;
    return append(buf, len, n,
        ",\"dock\":{\"mock_sensors\":%s"
        ",\"sensors\":{\"shtc3\":%s,\"scd41\":%s,\"pmsa003i\":%s,\"bme688\":%s}"
        ",\"backlog\":{\"held\":%lu,\"capacity\":%lu,\"store\":\"%s\"}"
        ",\"bsec\":{\"running\":%s,\"restored\":%s,\"accuracy\":%u,\"late\":%lu,\"saved\":%lu"
        ",\"sample_s\":%u}"
        ",\"settings\":{\"version\":\"%s\",\"refused\":%s}"
        ",\"recalibrated\":{\"id\":%lu,\"ppm\":%u,\"ok\":%s,\"correction_ppm\":%d}}",
        b(s.mockSensors), b(s.shtc3), b(s.scd41), b(s.pm), b(s.bme688),
        (unsigned long)s.backlogHeld, (unsigned long)s.backlogCapacity,
        s.backlogStore ? s.backlogStore : "",
        b(s.bsecRunning), b(s.bsecRestored), (unsigned)s.iaqAccuracy,
        (unsigned long)s.bsecLateCalls, (unsigned long)s.bsecSavedEpoch, (unsigned)s.bsecSampleS,
        s.settingsVersion ? s.settingsVersion : "", refused,
        (unsigned long)s.recalibratedId, (unsigned)s.recalibratedPpm, b(s.recalibratedOk),
        (int)s.recalibratedCorrection);
}

size_t clientStatusJson(const ClientStatus& s, char* buf, size_t len) {
    int n = append(buf, len, 0,
        "{\"board\":\"%s\",\"version\":\"%s\",\"ip\":\"%s\",\"rssi\":%d,\"uptime_s\":%lu"
        ",\"heap_free\":%lu,\"heap_size\":%lu,\"psram_free\":%lu,\"psram_size\":%lu",
        s.board ? s.board : "", s.version ? s.version : "", s.ip ? s.ip : "", s.rssi,
        (unsigned long)s.uptimeS,
        (unsigned long)s.heapFree, (unsigned long)s.heapSize,
        (unsigned long)s.psramFree, (unsigned long)s.psramSize);
    n = s.role == ClientStatus::DOCK ? dockJson(s, buf, len, n) : headJson(s, buf, len, n);
    n = append(buf, len, n, "}");
    if (n < 0) {
        if (len) buf[0] = '\0';
        return 0;
    }
    return (size_t)n;
}

size_t withClientStatus(const char* readingsJson, const char* clientJson, char* out, size_t len) {
    if (len) out[0] = '\0';
    size_t rn = strlen(readingsJson);
    if (rn < 2 || readingsJson[0] != '{' || readingsJson[rn - 1] != '}') return 0;
    if (!clientJson || clientJson[0] != '{') return 0;
    int n = snprintf(out, len, "%.*s,\"client\":%s}", (int)(rn - 1), readingsJson, clientJson);
    if (n < 0 || (size_t)n >= len) {
        if (len) out[0] = '\0';
        return 0;
    }
    return (size_t)n;
}
