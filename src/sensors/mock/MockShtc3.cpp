#include "sensors/mock/MockShtc3.h"

bool MockShtc3::begin(uint32_t nowMs) {
    wakeup(nowMs);
    sleep();
    return true;
}

bool MockShtc3::wakeup(uint32_t nowMs) {
    asleep_ = false;
    measuring_ = false;
    wokeAtMs_ = nowMs;
    return true;
}

bool MockShtc3::sleep() {
    asleep_ = true;
    measuring_ = false;
    return true;
}

bool MockShtc3::measure(uint32_t nowMs, bool lowPower) {
    if (asleep_) return false;             // the part NACKs
    lowPower_ = lowPower;
    measuring_ = true;
    readyAtMs_ = nowMs + (lowPower ? kLowPowerMs : kNormalMs);
    return true;
}

bool MockShtc3::read(uint32_t nowMs, Shtc3Data& out) {
    if (asleep_ || !measuring_ || nowMs < readyAtMs_) return false;
    measuring_ = false;
    float sigmaT = lowPower_ ? 0.4f : 0.1f;
    float sigmaRh = lowPower_ ? 0.4f : 0.1f;
    out.tempC = temp_.update(room_.tempC(), nowMs) + room_.noise(sigmaT);
    out.rhPct = rh_.update(room_.rhPct(), nowMs) + room_.noise(sigmaRh);
    return true;
}
