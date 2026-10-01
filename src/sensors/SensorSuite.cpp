#include "sensors/SensorSuite.h"

bool SensorSuite::begin() {
    started(shtc3State_, startShtc3());
    started(scd41State_, startScd41());
    started(pmState_, startPm());
    started(bmeState_, startBme688());
    return shtc3State_.running && scd41State_.running && pmState_.running && bmeState_.running;
}

// The ID is read again after begin() has checked it, because begin() leaves
// the part asleep and keeps the value to itself.
bool SensorSuite::startShtc3() {
    if (!shtc3_.begin(clock_.millis())) return false;
    if (shtc3_.wakeup(clock_.millis())) {
        shtc3Id_ = shtc3_.readId();
        shtc3_.sleep();
    }
    return true;
}

// The part takes its settings, and answers questions about them, only while
// idle, so both happen here, once a start, before it begins measuring.
bool SensorSuite::startScd41() {
    if (!scd41_.begin(clock_.millis())) return false;
    clock_.waitMs(kScd41WakeMs);
    scd41Read_ = scd41_.getSerialNumber(scd41Serial_);
    readScd41Settings();
    if (!scd41_.startPeriodicMeasurement(clock_.millis())) return false;
    scd41MeasuringSinceMs_ = clock_.millis();
    return true;
}

// Sets the options on the idle part, then reads back what it holds, for
// health().
void SensorSuite::readScd41Settings() {
    if (scd41OptionsSet_) {
        scd41_.setTemperatureOffset(scd41OffsetC_);
        scd41_.setAutomaticSelfCalibration(scd41Asc_);
    }
    ascKnown_ = scd41_.getAutomaticSelfCalibration(asc_);
    offsetKnown_ = scd41_.getTemperatureOffset(offsetC_);
}

bool SensorSuite::stopScd41() {
    if (!scd41_.stopPeriodicMeasurement(clock_.millis())) return false;
    clock_.waitMs(kScd41StopMs);
    return true;
}

// Measuring again after stopScd41(). A part that will not start is taken for
// stopped, so the next restartFailed() starts it from the beginning.
void SensorSuite::resumeScd41() {
    readScd41Settings();
    if (scd41_.startPeriodicMeasurement(clock_.millis())) {
        scd41MeasuringSinceMs_ = clock_.millis();
        return;
    }
    scd41State_.running = false;
    scd41State_.retryAtMs = clock_.millis();
    scd41State_.retryWaitMs = kRetryFirstMs;
}

void SensorSuite::setScd41Options(float offsetC, bool selfCalibration) {
    if (scd41OptionsSet_ && offsetC == scd41OffsetC_ && selfCalibration == scd41Asc_) return;
    scd41OptionsSet_ = true;
    scd41OffsetC_ = offsetC;
    scd41Asc_ = selfCalibration;
    if (!scd41State_.running) return;
    if (stopScd41()) resumeScd41();
}

SensorSuite::Recalibration SensorSuite::recalibrateScd41(uint16_t ppm, int16_t& correction) {
    if (!scd41State_.running || clock_.millis() - scd41MeasuringSinceMs_ < kFrcAfterMs) {
        return Recalibration::NotReady;
    }
    if (!stopScd41()) return Recalibration::Failed;
    const bool done = scd41_.performForcedRecalibration(clock_.millis(), ppm, correction);
    // The measurements so far are on the old calibration.
    if (done) scd41Sums_ = Scd41Sums();
    resumeScd41();
    return done ? Recalibration::Done : Recalibration::Failed;
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
        s.lastReadingMs = now;
        return;
    }
    if (!due || now - s.lastReadingMs < kStoppedAfterMs) return;
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
    newest_ = Readings();
    sampleShtc3(r);
    sampleBme688(r);
    sampleScd41(r);
    samplePm(r);
    // The SHTC3 and the PM module measure once a reading set, so their
    // newest sample is the reading's.
    newest_.ts = r.ts;
    newest_.shtc3 = r.shtc3;
    newest_.shtc3Valid = r.shtc3Valid;
    newest_.pm = r.pm;
    newest_.pmValid = r.pmValid;

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
    if (shtc3_.measure(clock_.millis(), shtc3LowPower_)) {
        clock_.waitMs(shtc3LowPower_ ? kShtc3LowPowerMs : kShtc3MeasureMs);
        r.shtc3Valid = shtc3_.read(clock_.millis(), r.shtc3);
    }
    shtc3_.sleep();
}

void SensorSuite::sampleBme688(Readings& r) {
    if (!bmeState_.running) return;
    if (!bme_.startForced(clock_.millis())) return;
    clock_.waitMs(bme_.measurementMs());
    Bme688Samples n = {};
    r.bme688Valid = bme_.fetchMean(clock_.millis(), r.bme688, newest_.bme688, n);
    newest_.bme688Valid = r.bme688Valid;
    r.bme688Samples = n.cycles;
    r.iaqSamples = n.iaq;
    r.staticIaqSamples = n.staticIaq;
    bmeSeen_ = r.bme688Valid;
    gasValid_ = r.bme688Valid && r.bme688.gasValid;
    heatStable_ = r.bme688Valid && r.bme688.heatStable;
}

void SensorSuite::poll() {
    if (scd41State_.running) pollScd41();
}

// None when it took a measurement.
SensorSuite::ReadFault SensorSuite::pollScd41() {
    // A failed transfer is a bad checksum when the driver counted one.
    const uint32_t crcBefore = scd41_.crcFailures();
    auto failed = [&] {
        return scd41_.crcFailures() != crcBefore ? ReadFault::BadChecksum : ReadFault::NoAnswer;
    };
    bool ready = false;
    if (!scd41_.getDataReadyStatus(clock_.millis(), ready)) return failed();
    if (!ready) return ReadFault::NoData;
    Scd41Data d = {};
    if (!scd41_.readMeasurement(clock_.millis(), d)) return failed();
    Scd41Sums& sums = scd41Sums_;
    sums.co2 += d.co2Ppm;
    ++sums.co2N;
    if (clock_.millis() - scd41MeasuringSinceMs_ >= scd41WarmupMs_) {
        sums.tempC += d.tempC;
        sums.rhPct += d.rhPct;
        ++sums.warmN;
    }
    sums.newest = d;
    return ReadFault::None;
}

// The reading set's SCD41 values are the mean of the measurements since the
// last one, the last of them taken here, so the part is never asked twice for
// the same measurement.
void SensorSuite::sampleScd41(Readings& r) {
    scd41Fault_ = ReadFault::None;
    if (!scd41State_.running) return;
    // NDIR absorption scales with gas density, so the SCD41 needs the real
    // ambient pressure to convert correctly. The BME688 has just measured it.
    if (r.bme688Valid) {
        const uint32_t pa = (uint32_t)(r.bme688.pressureHpa * 100.0f);
        if (scd41_.setAmbientPressure(pa)) {
            pressureKnown_ = true;
            pressurePa_ = pa;
        }
    }
    const ReadFault last = pollScd41();
    const Scd41Sums sums = scd41Sums_;
    scd41Sums_ = Scd41Sums();
    if (!sums.co2N) {
        scd41Fault_ = last;
        return;
    }
    r.scd41Valid = true;
    r.scd41Samples = sums.co2N;
    r.scd41.co2Ppm = (uint16_t)((sums.co2 + sums.co2N / 2) / sums.co2N);
    r.scd41WarmedUp = sums.warmN > 0;
    r.scd41.tempC = sums.warmN ? (float)(sums.tempC / sums.warmN) : sums.newest.tempC;
    r.scd41.rhPct = sums.warmN ? (float)(sums.rhPct / sums.warmN) : sums.newest.rhPct;
    newest_.scd41 = sums.newest;
    newest_.scd41Valid = true;
}

void SensorSuite::samplePm(Readings& r) {
    // Before the fan has run for 30 s the counts are still ramping up, so a
    // frame read now would be believable and wrong.
    pmReadCount_ = 0;
    if (!pmState_.running || !pm_.stable(clock_.millis())) return;
    for (int attempt = 0; attempt < kPmReadAttempts && !r.pmValid; ++attempt) {
        uint8_t* frame = pmFrames_[attempt];
        ReadFault fault = ReadFault::NoAnswer;
        if (pm_.readFrame(clock_.millis(), frame)) {
            switch (IPmsa003i::frameFault(frame)) {
                case IPmsa003i::FRAME_OK:     fault = ReadFault::None;        break;
                case IPmsa003i::BAD_START:    fault = ReadFault::BadStart;    break;
                case IPmsa003i::BAD_LENGTH:   fault = ReadFault::BadLength;   break;
                case IPmsa003i::BAD_CHECKSUM: fault = ReadFault::BadChecksum; break;
            }
            if (fault == ReadFault::None) {
                r.pmValid = IPmsa003i::parseFrame(frame, r.pm);
            } else {
                ++pmBadFrames_;
            }
        }
        pmReads_[pmReadCount_++] = fault;
    }
    if (r.pmValid) {
        pmSeen_ = true;
        pmVersion_ = r.pm.version;
        pmError_ = r.pm.error;
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
    h.pressureKnown = pressureKnown_;
    h.pressurePa = pressurePa_;
    h.bme688HeaterC = kBmeHeaterC;
    h.bme688HeaterMs = kBmeHeaterMs;
    h.pmSeen = pmSeen_;
    h.pmVersion = pmVersion_;
    h.pmError = pmError_;
    h.shtc3IdKnown = shtc3Id_ != 0;
    h.shtc3Id = shtc3Id_;
    h.shtc3LowPower = shtc3LowPower_;
    return h;
}

const char* SensorSuite::readFaultName(ReadFault fault) {
    switch (fault) {
        case ReadFault::None:        return "good";
        case ReadFault::NoAnswer:    return "no answer";
        case ReadFault::BadChecksum: return "bad checksum";
        case ReadFault::NoData:      return "no data ready";
        case ReadFault::BadStart:    return "bad start";
        case ReadFault::BadLength:   return "bad length";
    }
    return "?";
}
