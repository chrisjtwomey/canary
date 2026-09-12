#include "sensors/Pmsa003iDriver.h"

bool Pmsa003iDriver::begin(uint32_t nowMs) {
    // This also starts a module that has just had its power back, so the boot
    // and the warm-up count from here, whether or not the fan was meant to be
    // running already.
    if (setLine_) setLine_(true);
    enabled_ = true;
    enabledAtMs_ = nowMs;
    clock_.waitMs(kBootMs);

    uint8_t frame[32];
    PmData discarded;
    for (int attempt = 0; attempt < kBeginAttempts; ++attempt) {
        if (readFrame(clock_.millis(), frame) && parseFrame(frame, discarded)) return true;
        clock_.waitMs(kRetryMs);
    }
    return false;
}

void Pmsa003iDriver::setEnabled(bool on, uint32_t nowMs) {
    // Without the SET line the fan runs whenever the board has power, so
    // enabled_ stays true and says what the hardware is actually doing.
    if (!setLine_) return;
    if (on && !enabled_) enabledAtMs_ = nowMs;
    setLine_(on);
    enabled_ = on;
}

bool Pmsa003iDriver::readFrame(uint32_t nowMs, uint8_t out[32]) {
    if (!enabled_) return false;
    if (nowMs - enabledAtMs_ < kBootMs) return false;
    return bus_.read(addr_, out, 32);
}

bool Pmsa003iDriver::stable(uint32_t nowMs) const {
    return enabled_ && nowMs - enabledAtMs_ >= kWarmupMs;
}
