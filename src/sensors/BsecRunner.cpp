#include "sensors/BsecRunner.h"

namespace {

// BSEC's oversampling codes count the doublings; the driver takes the multiplier.
uint8_t multiplier(uint8_t code) { return code == 0 ? 0 : (uint8_t)(1u << (code - 1)); }

}  // namespace

int64_t BsecRunner::nowMs64() {
    const uint32_t ms = clock_.millis();
    if (ms < lastMs_) ++wraps_;
    lastMs_ = ms;
    return (int64_t)wraps_ << 32 | ms;
}

// Bosch's order: reset and configure, then any state, then the outputs. A
// state BSEC refuses, from another BSEC version say, means starting from
// nothing, and a copy of it from the server would fail the same way.
bool BsecRunner::startBsec(const BsecState* state) {
    bool fromState = state != nullptr && state->len > 0;
    started_ = false;
    {
        std::lock_guard<std::mutex> guard(lock_);
        status_.started = false;
    }
    if (bsec_.init() != IBsec::kOk) return false;
    if (fromState && bsec_.setState(state->blob, state->len) != IBsec::kOk) {
        fromState = false;
        if (bsec_.init() != IBsec::kOk) return false;
    }
    if (bsec_.subscribe() < IBsec::kOk) return false;
    started_ = true;
    nextCallNs_ = 0;
    std::lock_guard<std::mutex> guard(lock_);
    status_.started = true;
    status_.restored = fromState;
    status_.accuracy = fromState ? state->accuracy : 0;
    return true;
}

bool BsecRunner::begin(BsecState* stored) {
    BsecState loaded = {};
    const bool haveState = store_.load(loaded) && loaded.len > 0 && loaded.len <= IBsec::kMaxState;
    if (stored) *stored = haveState ? loaded : BsecState{};

    const bool sensor = bme_.begin(clock_.millis());
    missed_ = sensor ? 0 : kMissedLimit;
    settingsApplied_ = false;
    savedAtMs_ = clock_.millis();
    const bool bsec = startBsec(haveState ? &loaded : nullptr);

    std::lock_guard<std::mutex> guard(lock_);
    status_.running = sensor && bsec;
    return status_.running;
}

void BsecRunner::restartWith(const BsecState& state) {
    std::lock_guard<std::mutex> guard(lock_);
    pending_ = state;
    restartPending_ = true;
}

uint32_t BsecRunner::step() {
    BsecState pending;
    bool restart = false;
    {
        std::lock_guard<std::mutex> guard(lock_);
        if (restartPending_) {
            pending = pending_;
            restartPending_ = false;
            restart = true;
        }
    }
    if (restart || !started_) {
        if (!startBsec(restart ? &pending : nullptr)) return kRetryMs;
    }

    const int64_t nowNs = nowMs64() * 1000000;
    if (nowNs < nextCallNs_) return msUntilNextCall();

    BsecRequest request = {};
    const int status = bsec_.sensorControl(nowNs, request);
    if (status < IBsec::kOk) {
        nextCallNs_ = nowNs + (int64_t)kRetryMs * 1000000;
        return kRetryMs;
    }
    if (status == IBsec::kLateCall) {
        std::lock_guard<std::mutex> guard(lock_);
        ++status_.lateCalls;
    }
    if (request.measure) measure(request, nowNs);
    nextCallNs_ = request.nextCallNs;

    const uint32_t nowMs = clock_.millis();
    if (!haveCurrent_ || nowMs - copiedAtMs_ >= kCopyEveryMs) copyState(nowMs);
    saveIfDue(nowMs);
    return msUntilNextCall();
}

uint32_t BsecRunner::msUntilNextCall() {
    const int64_t nowNs = nowMs64() * 1000000;
    if (nextCallNs_ <= nowNs) return 0;
    const int64_t ms = (nextCallNs_ - nowNs + 999999) / 1000000;
    return ms > kRetryMs ? kRetryMs : (uint32_t)ms;
}

void BsecRunner::applySettings(const BsecRequest& r) {
    if (settingsApplied_ && r.osT == applied_.osT && r.osP == applied_.osP &&
        r.osH == applied_.osH && r.heaterC == applied_.heaterC &&
        r.heaterMs == applied_.heaterMs && r.runGas == applied_.runGas) {
        return;
    }
    bme_.setOversampling(multiplier(r.osT), multiplier(r.osP), multiplier(r.osH));
    bme_.setHeaterProfile(r.runGas ? r.heaterC : 0, r.runGas ? r.heaterMs : 0);
    applied_ = r;
    settingsApplied_ = true;
}

void BsecRunner::measure(const BsecRequest& request, int64_t nowNs) {
    applySettings(request);
    Bme688Data data = {};
    bool ok = bme_.startForced(clock_.millis());
    if (ok) {
        clock_.waitMs(bme_.measurementMs());
        ok = bme_.fetchData(clock_.millis(), data);
    }
    if (!ok) {
        if (missed_ < kMissedLimit) ++missed_;
        if (missed_ >= kMissedLimit && bme_.begin(clock_.millis())) {
            missed_ = 0;
            settingsApplied_ = false;
        }
        std::lock_guard<std::mutex> guard(lock_);
        status_.running = started_ && missed_ < kMissedLimit;
        return;
    }
    missed_ = 0;

    // Bosch's wrapper hands BSEC only a cycle with a real gas conversion.
    BsecResult result = {};
    if (data.gasValid && bsec_.doSteps(nowNs, data, result) >= IBsec::kOk && result.hasIaq) {
        data.hasIaq = true;
        data.iaq = result.iaq;
        data.iaqAccuracy = result.iaqAccuracy;
    }

    std::lock_guard<std::mutex> guard(lock_);
    latest_ = data;
    latestAtMs_ = clock_.millis();
    haveLatest_ = true;
    status_.running = true;
    if (data.hasIaq) status_.accuracy = data.iaqAccuracy;
}

void BsecRunner::copyState(uint32_t nowMs) {
    BsecState copy = {};
    uint32_t len = 0;
    if (bsec_.getState(copy.blob, sizeof(copy.blob), &len) != IBsec::kOk || len == 0 ||
        len > sizeof(copy.blob)) {
        return;
    }
    copy.len = len;
    copy.savedEpoch = epoch_ ? epoch_() : 0;
    std::lock_guard<std::mutex> guard(lock_);
    copy.accuracy = status_.accuracy;
    current_ = copy;
    haveCurrent_ = true;
    copiedAtMs_ = nowMs;
}

void BsecRunner::saveIfDue(uint32_t nowMs) {
    uint8_t accuracy;
    {
        std::lock_guard<std::mutex> guard(lock_);
        accuracy = status_.accuracy;
    }
    const bool reachedHigh = accuracy >= 3 && !savedAtHigh_;
    if (!reachedHigh && nowMs - savedAtMs_ < kSaveEveryMs) return;
    copyState(nowMs);
    BsecState copy;
    if (!current(copy) || !store_.save(copy)) return;
    savedAtMs_ = nowMs;
    if (copy.accuracy >= 3) savedAtHigh_ = true;
    std::lock_guard<std::mutex> guard(lock_);
    status_.savedEpoch = copy.savedEpoch;
}

bool BsecRunner::latest(Bme688Data& out, uint32_t& atMs) const {
    std::lock_guard<std::mutex> guard(lock_);
    if (!haveLatest_) return false;
    out = latest_;
    atMs = latestAtMs_;
    return true;
}

bool BsecRunner::current(BsecState& out) const {
    std::lock_guard<std::mutex> guard(lock_);
    if (!haveCurrent_) return false;
    out = current_;
    return true;
}

BsecRunner::Status BsecRunner::status() const {
    std::lock_guard<std::mutex> guard(lock_);
    return status_;
}
