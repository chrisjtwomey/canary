#include "sensors/mock/MockScd41.h"

const float MockScd41::kSelfHeatingC = 4.0f;

bool MockScd41::begin(uint32_t nowMs) {
    mode_ = IDLE;
    ready_ = false;
    firstShotPending_ = true;
    busyUntilMs_ = nowMs + kWakeMs;
    return true;
}

bool MockScd41::startPeriodicMeasurement(uint32_t nowMs) {
    if (mode_ != IDLE || busy(nowMs)) return false;
    mode_ = PERIODIC;
    nextDataMs_ = nowMs + kPeriodicMs;
    ready_ = false;
    return true;
}

bool MockScd41::startLowPowerPeriodicMeasurement(uint32_t nowMs) {
    if (mode_ != IDLE || busy(nowMs)) return false;
    mode_ = LOW_POWER_PERIODIC;
    nextDataMs_ = nowMs + kLowPowerMs;
    ready_ = false;
    return true;
}

bool MockScd41::stopPeriodicMeasurement(uint32_t nowMs) {
    if (mode_ == POWERED_DOWN) return false;
    mode_ = IDLE;
    ready_ = false;
    busyUntilMs_ = nowMs + kStopBusyMs;
    return true;
}

bool MockScd41::measureSingleShot(uint32_t nowMs) {
    if (mode_ != IDLE || busy(nowMs)) return false;
    mode_ = SINGLE_SHOT;
    nextDataMs_ = nowMs + kSingleShotMs;
    ready_ = false;
    busyUntilMs_ = nextDataMs_;
    return true;
}

void MockScd41::refresh(uint32_t nowMs) {
    if (ready_) return;
    bool due = false;
    switch (mode_) {
        case PERIODIC:
        case LOW_POWER_PERIODIC:
            if (nowMs >= nextDataMs_) {
                due = true;
                nextDataMs_ += (mode_ == PERIODIC) ? kPeriodicMs : kLowPowerMs;
            }
            break;
        case SINGLE_SHOT:
            if (nowMs >= nextDataMs_) { due = true; mode_ = IDLE; }
            break;
        default:
            break;
    }
    if (!due) return;

    // NDIR absorption scales with gas density; the part converts using the
    // pressure it was told, so a wrong assumed pressure skews the result.
    float truePa = room_.pressureHpa() * 100.0f;
    float co2 = room_.co2Ppm() * (truePa / (float)assumedPa_) + room_.noise(10.0f);
    if (firstShotPending_) {
        co2 += 150.0f;   // the first shot after power-up is not to be trusted
        firstShotPending_ = false;
    }
    if (co2 < 0) co2 = 0;
    pending_.co2Ppm = (uint16_t)(co2 + 0.5f);
    pending_.tempC = room_.tempC() + kSelfHeatingC - offsetC_ + room_.noise(0.1f);
    pending_.rhPct = EnvModel::rhFromAbs(room_.absHumidity(), pending_.tempC) + room_.noise(0.4f);
    ready_ = true;
}

bool MockScd41::getDataReadyStatus(uint32_t nowMs, bool& ready) {
    if (mode_ == POWERED_DOWN) return false;
    refresh(nowMs);
    ready = ready_;
    return true;
}

bool MockScd41::readMeasurement(uint32_t nowMs, Scd41Data& out) {
    if (mode_ == POWERED_DOWN) return false;
    refresh(nowMs);
    if (!ready_) return false;             // NACK
    out = pending_;
    ready_ = false;
    return true;
}

bool MockScd41::setAmbientPressure(uint32_t pa) {
    if (mode_ == POWERED_DOWN) return false;
    if (pa < 70000 || pa > 120000) return false;
    assumedPa_ = pa;
    return true;
}

bool MockScd41::setTemperatureOffset(float degC) {
    if (mode_ != IDLE) return false;       // idle only
    offsetC_ = degC;
    return true;
}

bool MockScd41::powerDown() {
    if (mode_ != IDLE) return false;
    mode_ = POWERED_DOWN;
    ready_ = false;
    firstShotPending_ = true;
    return true;
}

bool MockScd41::wakeUp(uint32_t nowMs) {
    if (mode_ != POWERED_DOWN) return false;
    mode_ = IDLE;
    busyUntilMs_ = nowMs + kWakeMs;
    return true;
}

bool MockScd41::getSerialNumber(uint64_t& serial) {
    if (mode_ == POWERED_DOWN) return false;
    serial = 0x0000C0FFEE41ull;
    return true;
}
