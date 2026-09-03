#include "sensors/mock/MockPmsa003i.h"

bool MockPmsa003i::begin(uint32_t nowMs) {
    setEnabled(true, nowMs);
    return true;
}

void MockPmsa003i::setEnabled(bool on, uint32_t nowMs) {
    if (on && !enabled_) {
        enabledAtMs_ = nowMs;
        frameAtMs_ = 0;
        haveFrame_ = false;
    }
    enabled_ = on;
}

bool MockPmsa003i::stable(uint32_t nowMs) const {
    return enabled_ && nowMs - enabledAtMs_ >= kWarmupMs;
}

void MockPmsa003i::buildFrame(uint32_t nowMs) {
    // During warm-up the fan is still spinning up and the counts climb from
    // nothing toward the true value.
    float elapsed = (float)(nowMs - enabledAtMs_);
    float ramp = elapsed >= kWarmupMs ? 1.0f : elapsed / (float)kWarmupMs;
    ramp *= 1.0f + room_.noise(elapsed >= kWarmupMs ? 0.03f : 0.15f);
    if (ramp < 0) ramp = 0;

    float pm25 = room_.pm25() * ramp;
    float pm1 = room_.pm1() * ramp;
    float pm10 = room_.pm10() * ramp;

    // CF=1 ("standard particle") runs above the atmospheric value once the
    // air is dirty; they agree in clean air.
    auto cf1 = [](float env) { return env <= 30.0f ? env : 30.0f + (env - 30.0f) * 1.5f; };
    auto u16 = [](float v) { return (uint16_t)(v < 0 ? 0 : v + 0.5f); };

    uint8_t* f = frame_;
    f[0] = 0x42; f[1] = 0x4D;
    put16(f + 2, 28);
    put16(f + 4, u16(cf1(pm1)));  put16(f + 6, u16(cf1(pm25)));  put16(f + 8, u16(cf1(pm10)));
    put16(f + 10, u16(pm1));      put16(f + 12, u16(pm25));      put16(f + 14, u16(pm10));
    // Particle counts per 0.1 L, a rough size distribution around PM2.5.
    put16(f + 16, u16(pm25 * 150.0f));
    put16(f + 18, u16(pm25 * 45.0f));
    put16(f + 20, u16(pm25 * 8.0f));
    put16(f + 22, u16(pm25 * 0.6f));
    put16(f + 24, u16(pm25 * 0.15f));
    put16(f + 26, u16(pm25 * 0.05f));
    f[28] = 0x97;   // version, as seen on Adafruit's units
    f[29] = 0x00;
    uint16_t sum = 0;
    for (int i = 0; i < 30; ++i) sum += f[i];
    put16(f + 30, sum);
    haveFrame_ = true;
    frameAtMs_ = nowMs;
}

bool MockPmsa003i::readFrame(uint32_t nowMs, uint8_t out[32]) {
    if (!enabled_) return false;                            // asleep: no ACK
    if (nowMs - enabledAtMs_ < kBootMs) return false;       // still booting
    if (!haveFrame_ || nowMs - frameAtMs_ >= kFrameIntervalMs) buildFrame(nowMs);

    for (int i = 0; i < 32; ++i) out[i] = frame_[i];
    if (++reads_ % kChecksumFailEvery == 0) out[31] ^= 0x5A;   // a corrupt read
    return true;
}
