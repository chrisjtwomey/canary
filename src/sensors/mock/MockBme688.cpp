#include "sensors/mock/MockBme688.h"
#include <cmath>

const float MockBme688::kSelfHeatingC = 1.5f;

bool MockBme688::begin(uint32_t nowMs) {
    running_ = false;
    cycles_ = 0;
    selfHeat_.primeAt(0.0f, nowMs);
    temp_.reset();
    rh_.reset();
    gas_.reset();
    return true;
}

void MockBme688::setOversampling(uint8_t osT, uint8_t osP, uint8_t osH) {
    osT_ = osT; osP_ = osP; osH_ = osH;
}

void MockBme688::setHeaterProfile(uint16_t degC, uint16_t ms) {
    heaterC_ = degC; heaterMs_ = ms;
}

uint32_t MockBme688::measurementMs() const {
    // Bosch's meas-duration formula, rounded: ~2 ms per oversample of each
    // channel plus a fixed 1 ms, then the heater.
    uint32_t tph = 1 + 2 * (osT_ + osP_ + osH_);
    return tph + heaterMs_;
}

bool MockBme688::startForced(uint32_t nowMs) {
    if (running_ && nowMs < doneAtMs_) return false;   // mode writes are ignored mid-cycle
    running_ = true;
    doneAtMs_ = nowMs + measurementMs();
    return true;
}

bool MockBme688::fetchData(uint32_t nowMs, Bme688Data& out) {
    if (!running_ || nowMs < doneAtMs_) return false;
    running_ = false;
    ++cycles_;

    out.tempC = temp_.update(room_.tempC(), nowMs)
                + selfHeat_.update(kSelfHeatingC, nowMs) + room_.noise(0.05f);
    out.pressureHpa = room_.pressureHpa() + room_.noise(0.02f);
    out.rhPct = rh_.update(EnvModel::rhFromAbs(room_.absHumidity(), out.tempC), nowMs)
                + room_.noise(0.2f);

    bool heaterOk = heaterMs_ >= kHeaterSettleMs && heaterC_ >= 200 && heaterC_ <= 400;
    out.heatStable = heaterOk && cycles_ > 1;
    out.gasValid = true;
    out.gasOhm = gas_.update(room_.gasOhm(), nowMs) * (1.0f + room_.noise(0.02f));
    if (!out.heatStable) out.gasOhm *= 1.6f;   // a cold plate reads high

    // What BSEC's IAQ looks like for this resistance: log-linear between
    // ~150 kOhm (excellent, 25) and ~15 kOhm (severe, 300).
    float lg = log10f(out.gasOhm < 1000.0f ? 1000.0f : out.gasOhm);
    float iaq = 25.0f + (5.176f - lg) * 275.0f;
    if (iaq < 0) iaq = 0;
    if (iaq > 500) iaq = 500;
    out.iaq = iaq;
    out.iaqAccuracy = cycles_ < 5 ? 0 : (cycles_ < 20 ? 1 : (cycles_ < 100 ? 2 : 3));
    out.hasIaq = true;
    return true;
}
