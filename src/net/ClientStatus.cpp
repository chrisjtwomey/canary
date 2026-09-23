#include "net/ClientStatus.h"

#include <cstdio>
#include <cstring>

#include "net/BoardSettings.h"

static const char* b(bool v) { return v ? "true" : "false"; }

// The dock's settings and its last recalibration, for a board that has
// settings: the head leaves settingsVersion null and sends neither.
static int settingsJson(const ClientStatus& s, char* buf, size_t len) {
    if (!s.settingsVersion) return snprintf(buf, len, "}");
    char refused[kRefusedJsonBytes];
    if (!refusedJson(s.settingsRefused, refused, sizeof(refused))) return -1;
    return snprintf(buf, len,
        ",\"settings\":{\"version\":\"%s\",\"refused\":%s}"
        ",\"recalibrated\":{\"id\":%lu,\"ppm\":%u,\"ok\":%s,\"correction_ppm\":%d}}",
        s.settingsVersion, refused,
        (unsigned long)s.recalibratedId, (unsigned)s.recalibratedPpm, b(s.recalibratedOk),
        (int)s.recalibratedCorrection);
}

size_t clientStatusJson(const ClientStatus& s, char* buf, size_t len) {
    int n = snprintf(buf, len,
        "{\"board\":\"%s\",\"version\":\"%s\",\"ip\":\"%s\",\"rssi\":%d,\"uptime_s\":%lu"
        ",\"heap_free\":%lu,\"heap_size\":%lu,\"psram_free\":%lu,\"psram_size\":%lu"
        ",\"panel_temp_c\":%d,\"width\":%d,\"height\":%d,\"rotation\":%u,\"mock_sensors\":%s"
        ",\"sensors\":{\"shtc3\":%s,\"scd41\":%s,\"pmsa003i\":%s,\"bme688\":%s}"
        ",\"fetch\":{\"next_url\":\"%s\",\"next_in_s\":%lu,\"backoff_step\":%d,\"ok\":%lu,\"failed\":%lu}"
        ",\"backlog\":{\"held\":%lu,\"capacity\":%lu,\"store\":\"%s\"}"
        ",\"bsec\":{\"running\":%s,\"restored\":%s,\"accuracy\":%u,\"late\":%lu,\"saved\":%lu"
        ",\"sample_s\":%u}",
        s.board ? s.board : "", s.version ? s.version : "", s.ip ? s.ip : "", s.rssi,
        (unsigned long)s.uptimeS,
        (unsigned long)s.heapFree, (unsigned long)s.heapSize,
        (unsigned long)s.psramFree, (unsigned long)s.psramSize,
        s.panelTempC, (int)s.width, (int)s.height, (unsigned)s.rotation, b(s.mockSensors),
        b(s.shtc3), b(s.scd41), b(s.pm), b(s.bme688),
        s.nextUrl ? s.nextUrl : "", (unsigned long)s.nextInS, s.backoffStep,
        (unsigned long)s.fetchOk, (unsigned long)s.fetchFailed,
        (unsigned long)s.backlogHeld, (unsigned long)s.backlogCapacity,
        s.backlogStore ? s.backlogStore : "",
        b(s.bsecRunning), b(s.bsecRestored), (unsigned)s.iaqAccuracy,
        (unsigned long)s.bsecLateCalls, (unsigned long)s.bsecSavedEpoch, (unsigned)s.bsecSampleS);
    if (n >= 0 && (size_t)n < len) {
        const int m = settingsJson(s, buf + n, len - (size_t)n);
        n = m < 0 ? -1 : n + m;
    }
    if (n < 0 || (size_t)n >= len) {
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
