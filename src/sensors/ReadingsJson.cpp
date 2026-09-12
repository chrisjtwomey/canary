#include "sensors/Readings.h"
#include <cstdio>

// A hand-rolled encoder so the sensors layer has no library dependency and
// the host tests can pin the exact wire format.
size_t readingsToJson(const Readings& r, const char* device, char* buf, size_t len) {
    int n = snprintf(buf, len,
        "{\"ts\":%lu,\"device\":\"%s\"",
        (unsigned long)r.ts, device);
    if (n < 0 || (size_t)n >= len) { if (len) buf[0] = 0; return 0; }
    size_t pos = (size_t)n;

    // The gas plate must have reached temperature for its resistance, and
    // the IAQ derived from it, to mean anything. Pressure is unaffected.
    const bool gasTrusted = r.bme688Valid && r.bme688.gasValid && r.bme688.heatStable;

    auto add = [&](const char* fmt, double a, double b) {
        int k = snprintf(buf + pos, len - pos, fmt, a, b);
        if (k < 0 || (size_t)k >= len - pos) { pos = 0; return false; }
        pos += (size_t)k;
        return true;
    };
    auto addI = [&](const char* fmt, unsigned long a, unsigned long b) {
        int k = snprintf(buf + pos, len - pos, fmt, a, b);
        if (k < 0 || (size_t)k >= len - pos) { pos = 0; return false; }
        pos += (size_t)k;
        return true;
    };

    if (r.shtc3Valid && !add(",\"temp_c\":%.1f,\"rh_pct\":%.1f", r.shtc3.tempC, r.shtc3.rhPct)) goto fail;
    if (r.scd41Valid) {
        if (!addI(",\"co2_ppm\":%lu", r.scd41.co2Ppm, 0)) goto fail;
    }
    if (r.pmValid) {
        if (!addI(",\"pm1_0\":%lu,\"pm2_5\":%lu", r.pm.pm1_0, r.pm.pm2_5)) goto fail;
        if (!addI(",\"pm10\":%lu,\"pc_0_3\":%lu", r.pm.pm10, r.pm.pc0_3)) goto fail;
        if (!addI(",\"pc_0_5\":%lu,\"pc_1_0\":%lu", r.pm.pc0_5, r.pm.pc1_0)) goto fail;
        if (!addI(",\"pc_2_5\":%lu,\"pc_5_0\":%lu", r.pm.pc2_5, r.pm.pc5_0)) goto fail;
        if (!addI(",\"pc_10\":%lu", r.pm.pc10, 0)) goto fail;
    }
    if (gasTrusted && !add(",\"gas_ohm\":%.0f", r.bme688.gasOhm, 0.0)) goto fail;
    if (gasTrusted && r.bme688.hasIaq) {
        if (!add(",\"iaq\":%.0f,\"iaq_accuracy\":%.0f", r.bme688.iaq,
                 (double)r.bme688.iaqAccuracy)) goto fail;
    }
    if (r.bme688Valid && !add(",\"pressure_hpa\":%.1f", r.bme688.pressureHpa, 0.0)) goto fail;
    if (r.scd41Valid && !add(",\"scd41\":{\"temp_c\":%.1f,\"rh_pct\":%.1f}", r.scd41.tempC, r.scd41.rhPct)) goto fail;
    if (r.bme688Valid && !add(",\"bme688\":{\"temp_c\":%.1f,\"rh_pct\":%.1f}", r.bme688.tempC, r.bme688.rhPct)) goto fail;

    {
        int k = snprintf(buf + pos, len - pos,
            ",\"valid\":{\"temp_humidity\":%s,\"co2\":%s,\"particulates\":%s"
            ",\"pressure\":%s,\"gas\":%s}}",
            r.shtc3Valid ? "true" : "false", r.scd41Valid ? "true" : "false",
            r.pmValid ? "true" : "false", r.bme688Valid ? "true" : "false",
            gasTrusted ? "true" : "false");
        if (k < 0 || (size_t)k >= len - pos) goto fail;
        pos += (size_t)k;
    }
    return pos;

fail:
    if (len) buf[0] = 0;
    return 0;
}
