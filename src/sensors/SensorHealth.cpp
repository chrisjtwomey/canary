#include "sensors/SensorHealth.h"

#include <cstdarg>
#include <cstdio>

static const char* b(bool v) { return v ? "true" : "false"; }

namespace {

// Appends to a fixed buffer, and remembers when anything did not fit.
struct Writer {
    char*  buf;
    size_t len;
    size_t pos;
    bool   ok;

    void add(const char* fmt, ...) {
        if (!ok) return;
        va_list args;
        va_start(args, fmt);
        const int n = vsnprintf(buf + pos, len - pos, fmt, args);
        va_end(args);
        if (n < 0 || (size_t)n >= len - pos) {
            ok = false;
            return;
        }
        pos += (size_t)n;
    }
};

}  // namespace

size_t healthJson(const SensorHealth& h, char* buf, size_t len) {
    if (len == 0) return 0;
    Writer w = {buf, len, 0, true};
    w.add("{\"restarts\":%lu,\"checksum_failures\":{\"pmsa003i\":%lu,\"shtc3\":%lu,\"scd41\":%lu}",
          (unsigned long)h.restarts, (unsigned long)h.pmBadFrames,
          (unsigned long)h.shtc3CrcFailures, (unsigned long)h.scd41CrcFailures);
    if (h.bme688Seen) {
        w.add(",\"bme688\":{\"gas_valid\":%s,\"heat_stable\":%s,\"heater_c\":%u,\"heater_ms\":%u}",
              b(h.gasValid), b(h.heatStable), (unsigned)h.bme688HeaterC, (unsigned)h.bme688HeaterMs);
    }
    if (h.scd41Read) {
        // Hex, twelve digits: the serial is 48 bits, which a JSON number
        // holds, but it is a name, not a quantity.
        w.add(",\"scd41\":{\"serial\":\"%04x%04x%04x\"", (unsigned)(h.scd41Serial >> 32 & 0xFFFF),
              (unsigned)(h.scd41Serial >> 16 & 0xFFFF), (unsigned)(h.scd41Serial & 0xFFFF));
        if (h.ascKnown) w.add(",\"asc\":%s", b(h.asc));
        if (h.offsetKnown) w.add(",\"offset_c\":%.1f", (double)h.offsetC);
        if (h.pressureKnown) w.add(",\"pressure_hpa\":%lu", (unsigned long)((h.pressurePa + 50) / 100));
        w.add("}");
    }
    if (h.pmSeen) {
        w.add(",\"pmsa003i\":{\"version\":%u,\"error\":%u}", (unsigned)h.pmVersion, (unsigned)h.pmError);
    }
    if (h.shtc3IdKnown) {
        w.add(",\"shtc3\":{\"id\":\"%04x\",\"low_power\":%s}", (unsigned)h.shtc3Id, b(h.shtc3LowPower));
    }
    w.add("}");
    if (!w.ok) {
        buf[0] = '\0';
        return 0;
    }
    return w.pos;
}
