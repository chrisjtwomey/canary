#include "sensors/SensorSuite.h"

bool SensorSuite::begin() {
    started(shtc3State_, startShtc3());
    started(scd41State_, startScd41());
    started(pmState_, startPm());
    started(bmeState_, startBme688());
    return shtc3State_.running && scd41State_.running && pmState_.running && bmeState_.running;
}

bool SensorSuite::startShtc3() { return shtc3_.begin(clock_.millis()); }

// The part answers questions about its settings only while idle, so they
// are asked here, once a start, before it begins measuring.
bool SensorSuite::startScd41() {
    if (!scd41_.begin(clock_.millis())) return false;
    clock_.waitMs(kScd41WakeMs);
    scd41Read_ = scd41_.getSerialNumber(scd41Serial_);
    ascKnown_ = scd41_.getAutomaticSelfCalibration(asc_);
    offsetKnown_ = scd41_.getTemperatureOffset(offsetC_);
    return scd41_.startPeriodicMeasurement(clock_.millis());
}

bool SensorSuite::startPm() { return pm_.begin(clock_.millis()); }

bool SensorSuite::startBme688() {
    if (!bme_.begin(clock_.millis())) return false;
    bme_.setOversampling(kBmeOsT, kBmeOsP, kBmeOsH);
    bme_.setHeaterProfile(kBmeHeaterC, kBmeHeaterMs);
    return true;
}

void SensorSuite::started(SensorState& s, bool ok) {
    uint32_t now = clock_.millis();
    s.running = ok;
    s.missed = 0;
    s.lastReadingMs = now;
    if (ok) {
        s.retryWaitMs = kRetryFirstMs;
        return;
    }
    s.retryAtMs = now + s.retryWaitMs;
    s.retryWaitMs = s.retryWaitMs > kRetryMaxMs / 2 ? kRetryMaxMs : s.retryWaitMs * 2;
}

void SensorSuite::restartFailed() {
    retry(shtc3State_, &SensorSuite::startShtc3);
    retry(scd41State_, &SensorSuite::startScd41);
    retry(pmState_, &SensorSuite::startPm);
    retry(bmeState_, &SensorSuite::startBme688);
}

void SensorSuite::retry(SensorState& s, StartFn start) {
    if (s.running || (int32_t)(clock_.millis() - s.retryAtMs) < 0) return;
    ++restarts_;
    started(s, (this->*start)());
}

// `due` says a reading was expected this sample. A sensor that stops is
// started again straight away, so the first retry comes at the next
// restartFailed().
void SensorSuite::track(SensorState& s, bool due, bool valid) {
    if (!s.running) return;
    uint32_t now = clock_.millis();
    if (valid) {
        s.missed = 0;
        s.lastReadingMs = now;
        return;
    }
    if (!due) return;
    if (s.missed < kMissedLimit) ++s.missed;
    if (s.missed < kMissedLimit || now - s.lastReadingMs < kStoppedAfterMs) return;
    s.running = false;
    s.retryAtMs = now;
    s.retryWaitMs = kRetryFirstMs;
}

void SensorSuite::setFanEnabled(bool on) {
    if (pmState_.running) pm_.setEnabled(on, clock_.millis());
}

Readings SensorSuite::sample(uint32_t epoch) {
    Readings r = {};
    r.ts = epoch;
    sampleShtc3(r);
    sampleBme688(r);
    sampleScd41(r);
    samplePm(r);

    track(shtc3State_, true, r.shtc3Valid);
    track(bmeState_, true, r.bme688Valid);
    track(scd41State_, true, r.scd41Valid);
    // During the fan's warm-up no frame is read, so none is missed.
    track(pmState_, pm_.stable(clock_.millis()), r.pmValid);
    return r;
}

void SensorSuite::sampleShtc3(Readings& r) {
    if (!shtc3State_.running) return;
    if (!shtc3_.wakeup(clock_.millis())) return;
    if (shtc3_.measure(clock_.millis(), false)) {
        clock_.waitMs(kShtc3MeasureMs);
        r.shtc3Valid = shtc3_.read(clock_.millis(), r.shtc3);
    }
    shtc3_.sleep();
}

void SensorSuite::sampleBme688(Readings& r) {
    if (!bmeState_.running) return;
    if (!bme_.startForced(clock_.millis())) return;
    clock_.waitMs(bme_.measurementMs());
    r.bme688Valid = bme_.fetchData(clock_.millis(), r.bme688);
    bmeSeen_ = r.bme688Valid;
    gasValid_ = r.bme688Valid && r.bme688.gasValid;
    heatStable_ = r.bme688Valid && r.bme688.heatStable;
}

void SensorSuite::sampleScd41(Readings& r) {
    if (!scd41State_.running) return;
    // NDIR absorption scales with gas density, so the SCD41 needs the real
    // ambient pressure to convert correctly. The BME688 has just measured it.
    if (r.bme688Valid) {
        scd41_.setAmbientPressure((uint32_t)(r.bme688.pressureHpa * 100.0f));
    }
    bool ready = false;
    if (!scd41_.getDataReadyStatus(clock_.millis(), ready) || !ready) return;
    r.scd41Valid = scd41_.readMeasurement(clock_.millis(), r.scd41);
}

void SensorSuite::samplePm(Readings& r) {
    // Before the fan has run for 30 s the counts are still ramping up, so a
    // frame read now would be believable and wrong.
    if (!pmState_.running || !pm_.stable(clock_.millis())) return;
    uint8_t frame[32];
    for (int attempt = 0; attempt < kPmReadAttempts && !r.pmValid; ++attempt) {
        if (pm_.readFrame(clock_.millis(), frame)) {
            r.pmValid = IPmsa003i::parseFrame(frame, r.pm);
            if (!r.pmValid) ++pmBadFrames_;
        }
    }
}

SensorHealth SensorSuite::health() const {
    SensorHealth h = {};
    h.restarts = restarts_;
    h.pmBadFrames = pmBadFrames_;
    h.shtc3CrcFailures = shtc3_.crcFailures();
    h.scd41CrcFailures = scd41_.crcFailures();
    h.bme688Seen = bmeSeen_;
    h.gasValid = gasValid_;
    h.heatStable = heatStable_;
    h.scd41Read = scd41Read_;
    h.scd41Serial = scd41Serial_;
    h.ascKnown = ascKnown_;
    h.asc = asc_;
    h.offsetKnown = offsetKnown_;
    h.offsetC = offsetC_;
    return h;
}
