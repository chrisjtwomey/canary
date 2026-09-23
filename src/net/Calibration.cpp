#include "net/Calibration.h"

#include <cstdio>
#include <cstdlib>
#include <cstring>

namespace {

const char kAlphabet[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

int sextet(char c) {
    if (c >= 'A' && c <= 'Z') return c - 'A';
    if (c >= 'a' && c <= 'z') return c - 'a' + 26;
    if (c >= '0' && c <= '9') return c - '0' + 52;
    if (c == '+') return 62;
    if (c == '/') return 63;
    return -1;
}

// The text after `"key":` in `json`, or null.
const char* valueOf(const char* json, const char* key) {
    char needle[32];
    snprintf(needle, sizeof(needle), "\"%s\"", key);
    const char* at = strstr(json, needle);
    if (!at) return nullptr;
    at += strlen(needle);
    while (*at == ' ') ++at;
    if (*at != ':') return nullptr;
    ++at;
    while (*at == ' ') ++at;
    return at;
}

bool unsignedOf(const char* json, const char* key, unsigned long max, unsigned long& out) {
    const char* at = valueOf(json, key);
    if (!at || *at < '0' || *at > '9') return false;
    char* end = nullptr;
    out = strtoul(at, &end, 10);
    return end != at && out <= max;
}

}  // namespace

size_t base64Encode(const uint8_t* in, size_t len, char* out, size_t outLen) {
    const size_t need = (len + 2) / 3 * 4;
    if (need + 1 > outLen) {
        if (outLen) out[0] = '\0';
        return 0;
    }
    size_t o = 0;
    for (size_t i = 0; i < len; i += 3) {
        const uint32_t b = (uint32_t)in[i] << 16 | (i + 1 < len ? (uint32_t)in[i + 1] << 8 : 0) |
                           (i + 2 < len ? in[i + 2] : 0);
        out[o++] = kAlphabet[b >> 18 & 0x3F];
        out[o++] = kAlphabet[b >> 12 & 0x3F];
        out[o++] = i + 1 < len ? kAlphabet[b >> 6 & 0x3F] : '=';
        out[o++] = i + 2 < len ? kAlphabet[b & 0x3F] : '=';
    }
    out[o] = '\0';
    return o;
}

size_t base64Decode(const char* in, size_t inLen, uint8_t* out, size_t outLen) {
    if (inLen % 4 != 0) return 0;
    size_t o = 0;
    for (size_t i = 0; i < inLen; i += 4) {
        const bool last = i + 4 == inLen;
        const int pad = last ? (in[i + 3] == '=') + (in[i + 2] == '=') : 0;
        int s[4];
        for (int k = 0; k < 4; ++k) {
            s[k] = (k >= 4 - pad) ? 0 : sextet(in[i + k]);
            if (s[k] < 0) return 0;
        }
        const uint32_t b = (uint32_t)s[0] << 18 | (uint32_t)s[1] << 12 | (uint32_t)s[2] << 6 | s[3];
        const int bytes = 3 - pad;
        if (o + bytes > outLen) return 0;
        out[o++] = (uint8_t)(b >> 16);
        if (bytes > 1) out[o++] = (uint8_t)(b >> 8);
        if (bytes > 2) out[o++] = (uint8_t)b;
    }
    return o;
}

size_t calibrationJson(const uint8_t* state, uint32_t len, uint8_t accuracy, uint32_t savedEpoch,
                       uint16_t sampleS, char* buf, size_t bufLen) {
    static const char kHead[] = "{\"bme688\":{\"state\":\"";
    const size_t head = sizeof(kHead) - 1;
    if (bufLen <= head) {
        if (bufLen) buf[0] = '\0';
        return 0;
    }
    memcpy(buf, kHead, head);
    const size_t encoded = base64Encode(state, len, buf + head, bufLen - head);
    if (encoded == 0 && len > 0) {
        buf[0] = '\0';
        return 0;
    }
    const size_t pos = head + encoded;
    const int n = snprintf(buf + pos, bufLen - pos,
                           "\",\"accuracy\":%u,\"saved\":%lu,\"sample_s\":%u}}",
                           (unsigned)accuracy, (unsigned long)savedEpoch, (unsigned)sampleS);
    if (n < 0 || (size_t)n >= bufLen - pos) {
        buf[0] = '\0';
        return 0;
    }
    return pos + (size_t)n;
}

size_t withMember(const char* doc, const char* key, const char* obj, char* out, size_t len) {
    if (len) out[0] = '\0';
    const size_t dn = strlen(doc);
    if (dn < 2 || doc[0] != '{' || doc[dn - 1] != '}') return 0;
    if (!obj || obj[0] != '{') return 0;
    const int n = snprintf(out, len, "%.*s,\"%s\":%s}", (int)(dn - 1), doc, key, obj);
    if (n < 0 || (size_t)n >= len) {
        if (len) out[0] = '\0';
        return 0;
    }
    return (size_t)n;
}

bool parseBme688Calibration(const char* json, uint8_t* state, uint32_t max, uint32_t& len,
                            uint8_t& accuracy, uint32_t& savedEpoch, uint16_t& sampleS) {
    const char* entry = valueOf(json, "bme688");
    if (!entry || *entry != '{') return false;
    const char* text = valueOf(entry, "state");
    if (!text || *text != '"') return false;
    ++text;
    const char* end = strchr(text, '"');
    if (!end || end == text) return false;
    const size_t decoded = base64Decode(text, (size_t)(end - text), state, max);
    unsigned long acc = 0, saved = 0, rate = 0;
    if (decoded == 0 || !unsignedOf(entry, "accuracy", 3, acc) ||
        !unsignedOf(entry, "saved", 0xFFFFFFFFul, saved) ||
        !unsignedOf(entry, "sample_s", 0xFFFF, rate)) {
        return false;
    }
    len = (uint32_t)decoded;
    accuracy = (uint8_t)acc;
    savedEpoch = (uint32_t)saved;
    sampleS = (uint16_t)rate;
    return true;
}

CopyChoice chooseCopy(const SavedCopy& nvs, const SavedCopy& server) {
    if (!server.present) return {false, CopyReason::NoServerCopy};
    if (!nvs.present) return {true, CopyReason::NoNvsCopy};
    if (server.accuracy != nvs.accuracy) {
        return server.accuracy > nvs.accuracy ? CopyChoice{true, CopyReason::MoreAccurate}
                                              : CopyChoice{false, CopyReason::LessAccurate};
    }
    if (server.savedEpoch == 0) return {false, CopyReason::ServerHasNoTime};
    if (nvs.savedEpoch == 0) return {true, CopyReason::NvsHasNoTime};
    if (server.savedEpoch > nvs.savedEpoch && server.savedEpoch - nvs.savedEpoch > kNewerByS) {
        return {true, CopyReason::Newer};
    }
    return {false, CopyReason::NotNewEnough};
}

size_t describeChoice(const SavedCopy& nvs, const SavedCopy& server, const CopyChoice& choice,
                      char* buf, size_t len) {
    const char* picked = choice.takeServer ? "server" : nvs.present ? "NVS" : "none";
    const unsigned long newerS =
        server.savedEpoch > nvs.savedEpoch ? (unsigned long)(server.savedEpoch - nvs.savedEpoch) : 0;
    const unsigned ours = nvs.accuracy, theirs = server.accuracy;
    int n = 0;
    switch (choice.reason) {
    case CopyReason::NoServerCopy:
        n = snprintf(buf, len, "%s selected (server state not found)", picked);
        break;
    case CopyReason::NoNvsCopy:
        n = snprintf(buf, len, "%s selected (no NVS state)", picked);
        break;
    case CopyReason::MoreAccurate:
        n = snprintf(buf, len, "%s selected (more accurate: %u vs %u)", picked, theirs, ours);
        break;
    case CopyReason::LessAccurate:
        n = snprintf(buf, len, "%s selected (server less accurate: %u vs %u)", picked, theirs, ours);
        break;
    case CopyReason::ServerHasNoTime:
        n = snprintf(buf, len, "%s selected (server state has no time)", picked);
        break;
    case CopyReason::NvsHasNoTime:
        n = snprintf(buf, len, "%s selected (NVS state has no time)", picked);
        break;
    case CopyReason::Newer:
        n = snprintf(buf, len, "%s selected (same accuracy, %lu h newer)", picked, newerS / 3600);
        break;
    case CopyReason::NotNewEnough:
        n = newerS ? snprintf(buf, len, "%s selected (same accuracy, only %lu min newer)", picked, newerS / 60)
                   : snprintf(buf, len, "%s selected (same accuracy, not newer)", picked);
        break;
    }
    return n > 0 && (size_t)n < len ? (size_t)n : 0;
}
